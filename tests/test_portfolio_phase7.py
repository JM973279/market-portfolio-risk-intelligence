"""Discovery is never an approval; risk diagnostics use independently known paths."""
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.portfolio.catalog import discovery_catalog
from src.portfolio.risk_metrics import compare_risk_metrics, risk_metrics
from src.portfolio.server import app

client = TestClient(app)


def test_legacy_contract_and_discovery_paging():
    assert len(client.get('/api/portfolio/v2/catalog').json()['assets']) == 80
    seen = []
    offset = 0
    while True:
        response = client.get('/api/portfolio/v2/discovery', params={'offset': offset, 'limit': 7})
        assert response.status_code == 200
        body = response.json()
        seen.extend(a['asset_id'] for a in body['assets'])
        if body['next_offset'] is None:
            break
        offset = body['next_offset']
    assert len(seen) == len(set(seen)) == body['total'] == 96
    assert len([a for a in discovery_catalog()['assets'] if a['selectable']]) == 28


def test_korean_identity_filters_and_analysis_block():
    body = client.get('/api/portfolio/v2/discovery', params={'q': '００５９３０', 'market': 'KR', 'kind': 'stock'}).json()
    assert body['total'] == 1
    asset = body['assets'][0]
    assert asset['ticker'] == '005930' and asset['currency'] == 'KRW'
    assert not asset['selectable'] and not any(asset['capabilities'].values())
    assert asset['snapshot_as_of'] is None
    assert 'NO_APPROVED_RELEASE' in asset['reason_codes']
    assert client.get('/api/portfolio/v2/discovery', params={'q': '삼성전자'}).json()['total'] == 1
    assert client.get('/api/portfolio/v2/discovery', params={'market': 'KR', 'kind': 'etf'}).json()['total'] == 6
    assert client.post('/api/portfolio/analyze', json={'holdings': [{'ticker': '005930', 'weight': 100}], 'value_usd': 1000}).status_code == 422


@pytest.mark.parametrize('params', [{'limit':0}, {'limit':101}, {'offset':-1}, {'market':'JP'}, {'kind':'bond'}, {'status':'approved'}, {'q':'x'*101}])
def test_search_rejects_invalid_queries(params):
    assert client.get('/api/portfolio/v2/discovery', params=params).status_code == 422


def sample():
    return pd.DataFrame({'A':[.1,-.2,.1,-.1], 'B':[.02,.01,-.01,.03]}, index=pd.date_range('2024-01-01', periods=4))


def test_known_risk_path_and_covariance():
    frame = sample()
    result = risk_metrics(frame, {'A':1}, confidence=.75)
    assert result['var_daily'] == pytest.approx(.125)
    assert result['expected_shortfall_daily'] == pytest.approx(.2)
    assert result['max_drawdown'] == pytest.approx(.208)
    assert result['cumulative_return'] == pytest.approx(-.1288)
    assert result['volatility_annual'] == pytest.approx(np.std(frame.A, ddof=1)*np.sqrt(252))
    assert result['covariance_daily'][0][0] == pytest.approx(np.var(frame.A, ddof=1))
    json.dumps(result, allow_nan=False)
    comparison = compare_risk_metrics(frame, {'A':1}, {'B':1})
    assert comparison['change']['max_drawdown'] < 0
    assert compare_risk_metrics(frame, {'A':1}, {'A':1})['change'] == dict.fromkeys(comparison['change'], 0)


@pytest.mark.parametrize('damage', ['nan','inf','duplicate','reversed','loss','weights'])
def test_risk_rejects_unusable_data(damage):
    frame = sample()
    weights = {'A':1}
    if damage == 'nan': frame.iloc[0,0] = np.nan
    if damage == 'inf': frame.iloc[0,0] = np.inf
    if damage == 'duplicate': frame.index = pd.DatetimeIndex([frame.index[0]]*4)
    if damage == 'reversed': frame = frame.iloc[::-1]
    if damage == 'loss': frame.iloc[0,0] = -1
    if damage == 'weights': weights = {'A':.5}
    with pytest.raises(ValueError): risk_metrics(frame, weights)


def test_initial_nav_and_zero_variance():
    frame = pd.DataFrame({'A':[-.1,-.1]}, index=pd.date_range('2024-01-01', periods=2))
    result = risk_metrics(frame, {'A':1})
    assert result['max_drawdown'] == pytest.approx(.19)
    assert result['correlation'] == [[None]]
    assert result['volatility_annual'] == 0
    json.dumps(result, allow_nan=False)
