"""Concurrency/failure boundaries; real numerical results remain in golden tests."""
import asyncio
import errno
import json
from pathlib import Path
import threading
import time

import anyio.to_thread
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from src.portfolio import api, execution
from src.portfolio.execution import PortfolioExecutor, bounded_endpoint
from src.portfolio.server import app
from src.portfolio.schemas import CompareRequest


async def until(predicate):
    for _ in range(1000):
        if predicate():return
        await asyncio.sleep(.001)
    raise AssertionError('Worker state did not settle')


def test_single_worker_serializes_and_rejects_excess_without_blocking_loop():
    async def scenario():
        runner=PortfolioExecutor(capacity=4,timeout=2)
        release=threading.Event();started=threading.Event();identities=[]
        def work():
            identities.append(threading.get_ident());started.set();release.wait(2);return 7
        try:
            tasks=[asyncio.create_task(runner.run(work)) for _ in range(4)]
            await until(started.is_set)
            await asyncio.sleep(.005)
            with pytest.raises(HTTPException) as error:await runner.run(lambda:99)
            assert error.value.status_code==503
            assert error.value.detail['code']=='portfolio_capacity_exhausted'
            release.set()
            assert await asyncio.gather(*tasks)==[7]*4
            assert len(set(identities))==1
        finally:release.set();runner.close()
    asyncio.run(scenario())


def test_timeout_keeps_running_and_abandoned_queue_slots_until_dequeued():
    async def scenario():
        runner=PortfolioExecutor(capacity=2,timeout=.03)
        release=threading.Event();started=threading.Event();called=[]
        def blocking():started.set();release.wait(2);return 1
        try:
            first=asyncio.create_task(runner.run(blocking));await until(started.is_set)
            second=asyncio.create_task(runner.run(lambda:called.append('must not execute')))
            for task in (first,second):
                with pytest.raises(HTTPException) as error:await task
                assert error.value.status_code==504
            for _ in range(10):
                with pytest.raises(HTTPException) as error:await runner.run(lambda:None)
                assert error.value.status_code==503
            release.set()
            await until(lambda:runner._slots._value==2)
            assert called==[]
            assert await runner.run(lambda:8)==8
        finally:release.set();runner.close()
    asyncio.run(scenario())


def test_client_cancellation_never_starts_a_replacement_worker():
    async def scenario():
        runner=PortfolioExecutor(capacity=1,timeout=2)
        release=threading.Event();started=threading.Event();identities=[]
        def blocking():identities.append(threading.get_ident());started.set();release.wait(2)
        try:
            task=asyncio.create_task(runner.run(blocking));await until(started.is_set)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            with pytest.raises(HTTPException) as error:await runner.run(lambda:None)
            assert error.value.status_code==503
            release.set();await until(lambda:runner._slots._value==1)
            worker_id=await runner.run(threading.get_ident)
            assert identities==[worker_id]
        finally:release.set();runner.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('fault',[MemoryError(),OSError(errno.ENOMEM,'allocation failed'),RuntimeError("can't start new thread")])
def test_resource_failure_is_explicit_503_and_recovers(fault):
    async def scenario():
        runner=PortfolioExecutor()
        def fail():raise fault
        try:
            with pytest.raises(HTTPException) as error:await runner.run(fail)
            assert error.value.status_code==503
            assert error.value.detail['code']=='portfolio_resource_exhausted'
            assert await runner.run(lambda:42)==42
        finally:runner.close()
    asyncio.run(scenario())


def test_unexpected_defect_stays_a_server_error():
    async def scenario():
        runner=PortfolioExecutor()
        def bug():raise RuntimeError('real programming defect')
        try:
            with pytest.raises(RuntimeError,match='real programming defect'):await runner.run(bug)
        finally:runner.close()
    asyncio.run(scenario())


def test_http_routes_do_not_use_anyio_worker_pool(monkeypatch):
    async def forbidden(*args,**kwargs):raise AssertionError('Unexpected AnyIO threadpool dispatch')
    monkeypatch.setattr(anyio.to_thread,'run_sync',forbidden)
    before=json.loads(Path('examples/portfolio/before.json').read_text())
    with TestClient(app) as client:
        for path in ('/health','/api/portfolio/universe','/api/portfolio/scenarios','/api/portfolio/v2/catalog'):
            assert client.get(path).status_code==200
        assert client.post('/api/portfolio/analyze',json=before).status_code==200
        assert client.post('/api/portfolio/compare',json={'current':before,'proposed':before}).status_code==200
        v2={'snapshot_id':'no-approved-release','market':'US','base_currency':'USD','holdings':before['holdings'],'value_amount':before['value_usd']}
        assert client.post('/api/portfolio/v2/analyze',json=v2).status_code==409
        assert client.post('/api/portfolio/v2/compare',json={'current':v2,'proposed':v2}).status_code==409


def test_identical_compare_executes_one_analysis(monkeypatch):
    request=json.loads(Path('examples/portfolio/before.json').read_text())
    original=api.analyze;calls=[]
    def counted(body):calls.append(body);return original(body)
    monkeypatch.setattr(api,'analyze',counted)
    result=api.compare(CompareRequest(current=request,proposed=request))
    assert len(calls)==1
    assert result['current']==result['proposed']
    assert all(row['change']==0 for row in result['comparison'])


def test_failed_executor_start_has_no_user_side_effects(monkeypatch):
    execution.close_executor()
    def fail(*args,**kwargs):raise RuntimeError("can't start new thread")
    monkeypatch.setattr(threading.Thread,'start',fail)
    async def scenario():
        with pytest.raises(HTTPException) as error:execution.get_executor()
        assert error.value.status_code==503
        assert error.value.detail['code']=='portfolio_executor_unavailable'
    asyncio.run(scenario())


def test_http_error_statuses_are_not_rewritten(monkeypatch):
    runner=PortfolioExecutor(timeout=.015)
    monkeypatch.setattr(execution,'get_executor',lambda:runner)
    local=FastAPI()
    @local.get('/slow')
    @bounded_endpoint
    def slow():time.sleep(.05);return {'unexpected':'late success'}
    @local.get('/pressure')
    @bounded_endpoint
    def pressure():raise MemoryError()
    @local.get('/bug')
    @bounded_endpoint
    def bug():raise RuntimeError('unexpected defect')
    try:
        client=TestClient(local,raise_server_exceptions=False)
        timeout=client.get('/slow')
        assert timeout.status_code==504
        assert timeout.json()['detail']['code']=='portfolio_deadline_exceeded'
        time.sleep(.06)
        assert client.get('/pressure').status_code==503
        assert client.get('/bug').status_code==500
    finally:runner.close()


def test_http_startup_failure_is_unready_503_not_false_health(monkeypatch):
    execution.close_executor()
    def fail(*args,**kwargs):raise RuntimeError("can't start new thread")
    monkeypatch.setattr(execution,'ThreadPoolExecutor',fail)
    with TestClient(app) as client:
        health=client.get('/health')
        assert health.status_code==503
        assert health.json()['detail']['code']=='portfolio_executor_unavailable'
        invalid=client.post('/api/portfolio/analyze',json={})
        assert invalid.status_code==422
