"""Loopback-only diagnostic server. Never imported by the production app.

The V2 routes below replay existing V1 data for PRIVATE performance testing.
They do not use/modify the public approval registry or license any new asset.
"""
from contextlib import asynccontextmanager
from functools import lru_cache
import os
from pathlib import Path
import resource
import threading

ROOT = Path(__file__).resolve().parents[1]


def create_app():
    if os.environ.get('MPRI_PHASE3_LOCAL_PROBE') != '1':
        raise RuntimeError('This diagnostic app is only enabled by the local harness')
    cap = int(os.environ.get('MPRI_PHASE3_AS_MIB', '0'))
    if cap:
        resource.setrlimit(resource.RLIMIT_AS, (cap*1024**2, cap*1024**2))
    from src.portfolio.server import app
    from src.portfolio.v2 import V2Request, V2CompareRequest, load_research_bundle, analyze_bundle, compare_bundle
    import anyio.to_thread
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            tokens = int(os.environ.get('MPRI_PHASE3_THREAD_TOKENS', '0'))
            if tokens:
                anyio.to_thread.current_default_thread_limiter().total_tokens = tokens
            yield

    app.router.lifespan_context = lifespan

    @lru_cache(maxsize=1)
    def bundle():
        path = Path(os.environ['MPRI_PHASE3_RESEARCH_PATH']).resolve()
        allowed = (ROOT/'data/portfolio_expansion/research').resolve()
        if allowed not in path.parents:
            raise RuntimeError('Research path must stay in the ignored research tree')
        loaded = load_research_bundle(path)
        if loaded.provenance.get('scope') != 'research_only':
            raise RuntimeError('Probe expects the existing-data research replay only')
        return loaded

    @app.get('/_phase3/diagnostics')
    async def diagnostics():
        return {'as_limit_bytes':resource.getrlimit(resource.RLIMIT_AS)[0],
                'stack_limit_bytes':resource.getrlimit(resource.RLIMIT_STACK)[0],
                'nproc_limit':resource.getrlimit(resource.RLIMIT_NPROC)[0],
                'python_stack_size':threading.stack_size(),
                'anyio_thread_tokens':anyio.to_thread.current_default_thread_limiter().total_tokens,
                'allocator_arena_max':os.environ.get('MALLOC_ARENA_MAX'),
                'blas_threads':os.environ.get('OPENBLAS_NUM_THREADS')}

    @app.post('/_phase3/research/analyze')
    def research_analyze(request: V2Request):
        return analyze_bundle(bundle(), request)

    @app.post('/_phase3/research/compare')
    def research_compare(request: V2CompareRequest):
        return compare_bundle(bundle(), request)

    return app
