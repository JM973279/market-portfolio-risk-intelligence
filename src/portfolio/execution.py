"""One bounded CPU executor for Portfolio HTTP work, independent of AnyIO's pool.

Timeout/cancellation never frees a running job's slot early or spawns a replacement
thread. Python cannot safely kill a running calculation; callers receive explicit
errors while capacity stays reserved until the actual calculation ends.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import wraps
import errno
import logging
import threading
import time

from fastapi import HTTPException

logger = logging.getLogger(__name__)
MAX_INFLIGHT = 4  # one running and at most three waiting
REQUEST_TIMEOUT_SECONDS = 25.0  # includes queue time; frontend deadline is 30s


def resource_failure(error):
    return (isinstance(error, MemoryError)
            or isinstance(error, OSError) and error.errno in {errno.ENOMEM, errno.EAGAIN}
            or isinstance(error, RuntimeError) and "can't start new thread" in str(error))


def unavailable(code):
    return HTTPException(status_code=503, detail={'code':code}, headers={'Retry-After':'1'})


class _ExpiredJob(Exception):
    pass


class PortfolioExecutor:
    def __init__(self, *, capacity=MAX_INFLIGHT, timeout=REQUEST_TIMEOUT_SECONDS):
        self.timeout = timeout
        self._slots = threading.BoundedSemaphore(capacity)
        self._lock = threading.Lock()
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='portfolio-cpu')
        # Force the sole thread to exist BEFORE submitting any user work. A failed
        # ThreadPoolExecutor.submit can otherwise leave that user job in its queue.
        try:
            self._executor.submit(lambda: None)
        except BaseException:
            self._executor.shutdown(wait=False, cancel_futures=True)
            raise

    async def run(self, function):
        if not self._slots.acquire(blocking=False):
            raise unavailable('portfolio_capacity_exhausted')
        deadline = time.monotonic() + self.timeout
        abandoned = threading.Event()

        def work():
            if abandoned.is_set() or time.monotonic() >= deadline:
                raise _ExpiredJob()
            return function()

        try:
            with self._lock:
                if self._closed:
                    raise unavailable('portfolio_executor_unavailable')
                future = self._executor.submit(work)
        except BaseException as error:
            self._slots.release()
            if resource_failure(error):
                logger.error('portfolio resource failure during submission', exc_info=True)
                raise unavailable('portfolio_resource_exhausted') from None
            raise
        future.add_done_callback(lambda _: self._slots.release())
        wrapped = asyncio.wrap_future(future)
        # Consume late exceptions after a timeout/client cancellation, without
        # cancelling the actual running job or losing its capacity accounting.
        wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped), timeout=self.timeout)
        except (TimeoutError, _ExpiredJob):
            # Keep even an abandoned queued item in the capacity accounting
            # until it is physically dequeued. Cancelling Future here would free
            # slots while stale WorkItems still grow an unbounded internal queue.
            abandoned.set()
            logger.warning('portfolio request deadline exceeded')
            raise HTTPException(status_code=504, detail={'code':'portfolio_deadline_exceeded'}) from None
        except asyncio.CancelledError:
            abandoned.set()
            raise
        except Exception as error:
            if resource_failure(error):
                logger.error('portfolio computation resource failure', exc_info=True)
                raise unavailable('portfolio_resource_exhausted') from None
            raise  # unknown defects remain genuine server errors

    def close(self):
        with self._lock:
            self._closed = True
            self._executor.shutdown(wait=False, cancel_futures=True)


_runtime = None
_runtime_lock = threading.Lock()


def get_executor():
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            try:
                _runtime = PortfolioExecutor()
            except Exception as error:
                if resource_failure(error):
                    logger.error('portfolio executor startup resource failure', exc_info=True)
                    raise unavailable('portfolio_executor_unavailable') from None
                raise
        return _runtime


def close_executor():
    global _runtime
    with _runtime_lock:
        if _runtime is not None:
            _runtime.close()
            _runtime = None


@asynccontextmanager
async def portfolio_lifespan(app):
    # Startup reserves just one thread. Failure leaves explicit 503 readiness,
    # rather than a false healthy status or a partially executed user request.
    try:
        get_executor()
    except HTTPException:
        pass
    try:
        yield
    finally:
        close_executor()


def bounded_endpoint(function=None, *, check=None):
    """Lift a sync core into an async HTTP endpoint with its signature preserved."""
    def decorate(core):
        @wraps(core)
        async def endpoint(*args, **kwargs):
            def transaction():
                if check is not None:
                    check()
                return core(*args, **kwargs)
            return await get_executor().run(transaction)
        return endpoint
    return decorate(function) if function is not None else decorate
