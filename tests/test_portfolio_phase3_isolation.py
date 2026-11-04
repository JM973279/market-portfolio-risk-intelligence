"""Diagnostic research routes must never become production API routes."""
import pytest
from fastapi.testclient import TestClient
from src.portfolio.server import app
from scripts.portfolio_phase3_probe import create_app


def test_research_probe_requires_explicit_local_context(monkeypatch):
    monkeypatch.delenv('MPRI_PHASE3_LOCAL_PROBE', raising=False)
    with pytest.raises(RuntimeError, match='local harness'):
        create_app()


def test_production_server_never_exposes_diagnostic_or_private_replay_routes():
    client = TestClient(app)
    assert client.get('/_phase3/diagnostics').status_code == 404
    assert client.post('/_phase3/research/analyze', json={}).status_code == 404
    assert client.post('/_phase3/research/compare', json={}).status_code == 404
    assert client.get('/health').status_code == 200
