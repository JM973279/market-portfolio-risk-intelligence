import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.portfolio.catalog import get_catalog
from src.portfolio.expansion import Receipt, validate_candidate, write_release, verify_release

RELEASE_META = {'snapshot_as_of':'2026-01-01', 'built_at':'2026-01-02T00:00:00Z', 'market':'US', 'base_currency':'USD', 'methodology_version':'test', 'revision_note':'synthetic initial receipt'}


def test_v1_entire_response_golden():
    golden = json.loads((Path(__file__).parent / 'fixtures/portfolio_v1_golden.json').read_text())
    from fastapi.testclient import TestClient
    from src.portfolio.server import app
    client = TestClient(app)
    for name, request in golden['requests'].items():
        response = client.post('/api/portfolio/analyze', json=request)
        assert response.status_code == 200
        assert response.json() == golden['responses'][name], name
    assert client.post('/api/portfolio/compare', json={'current':golden['requests']['before'], 'proposed':golden['requests']['after']}).json() == golden['comparison']


def test_catalog_does_not_grant_new_rights():
    catalog = get_catalog()
    assert len(catalog['assets']) == 28
    assert not catalog['new_public_support_enabled']
    assert all(a['support_scope'] == 'frozen_v1_only' and not a['source_license']['new_public_use_approved'] for a in catalog['assets'])
    assert next(a for a in catalog['assets'] if a['ticker'] == 'NVDA')['name_ko'] == '엔비디아'


@pytest.fixture
def candidate():
    dates = pd.bdate_range('2020-01-01', periods=757)
    prices = pd.Series(100*np.exp(np.arange(757)*.001), index=dates)
    factors = pd.DataFrame({n: np.sin(np.arange(756)/d) for n,d in [('market',3),('rate',7),('volatility',11)]}, index=dates[1:])
    receipt = Receipt(asset_id='TEST', market='US', currency='USD', source_id='synthetic', source_url='https://example.com', license_reference='test only', public_use_approved=True, retrieved_at='2026-01-01T00:00:00Z', published_at_missing_reason='not supplied', adjustment_method='synthetic', precision_policy='float64', code_version='test', dependency_version='test', corporate_actions_verified=True, trading_status_verified=True, identity_verified=True)
    return prices, dates, factors, receipt


def test_gate_full_partial_and_rights(candidate):
    prices, dates, factors, receipt = candidate
    assert validate_candidate(*candidate, factor_policy_verified=True, scenarios_verified=True)['support_status'] == 'full'
    assert validate_candidate(*candidate)['support_status'] == 'partial'
    receipt.public_use_approved = False
    result = validate_candidate(*candidate, factor_policy_verified=True, scenarios_verified=True)
    assert result['support_status'] == 'unsupported'
    assert not any(result['capabilities'].values())
    assert 'RIGHTS_UNCONFIRMED' in result['reason_codes']


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'reverse', 'zero', 'nan', 'jump', 'future', 'currency', 'kr'])
def test_gate_quarantines_bad_data(candidate, damage):
    prices, dates, factors, receipt = candidate
    if damage == 'missing': prices = prices.iloc[1:]
    if damage == 'duplicate': prices.index = pd.DatetimeIndex([dates[0], *dates[:-1]])
    if damage == 'reverse': prices = prices.iloc[::-1]
    if damage == 'zero': prices.iloc[10] = 0
    if damage == 'nan': prices.iloc[10] = np.nan
    if damage == 'jump': prices.iloc[10] *= 10
    if damage == 'future': receipt.retrieved_at = '2019-01-01T00:00:00Z'
    if damage == 'currency': receipt.currency = 'KRW'
    if damage == 'kr': receipt.market = 'KR'; receipt.currency = 'KRW'
    assert validate_candidate(prices, dates, factors, receipt)['support_status'] == 'unsupported'


def test_release_is_immutable_and_checks_hash(tmp_path):
    write_release(tmp_path, 's1', {'prices.csv': b'price\n100\n'}, RELEASE_META)
    assert verify_release(tmp_path/'s1')['snapshot_id'] == 's1'
    with pytest.raises(FileExistsError): write_release(tmp_path, 's1', {'prices.csv':b''}, RELEASE_META)
    with pytest.raises(ValueError): write_release(tmp_path, '../bad', {}, {})
    (tmp_path/'s1/prices.csv').write_bytes(b'corrupt')
    with pytest.raises(ValueError): verify_release(tmp_path/'s1')


def test_catalog_http_and_candidate_cannot_self_approve(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.portfolio.api import router
    from src.portfolio import catalog
    metadata = json.loads(catalog.CATALOG_PATH.read_text())
    metadata['candidates'] = [{'asset_id':'TEST:000001', 'ticker':'000001', 'name':'Synthetic only', 'market':'KR', 'currency':'KRW', 'support_status':'full', 'selectable':True}]
    path = tmp_path/'catalog.json'
    path.write_text(json.dumps(metadata))
    monkeypatch.setattr(catalog, 'CATALOG_PATH', path)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    candidate = client.get('/api/portfolio/v2/catalog').json()['assets'][-1]
    assert not candidate['selectable']
    assert candidate['support_status'] == 'unsupported'
    response = client.post('/api/portfolio/analyze', json={'holdings':[{'ticker':'000001','weight':100}], 'value_usd':100000})
    assert response.status_code == 422


def test_partial_never_claims_complete_comparison(candidate):
    prices, dates, factors, receipt = candidate
    factors.iloc[0,0] = np.inf
    result = validate_candidate(*candidate, factor_policy_verified=True, scenarios_verified=True)
    assert result['support_status'] == 'partial'
    assert result['capabilities'] == {'hidden_risk':True, 'factors':False, 'stress':False, 'what_if':False}
    assert not result['selectable']


def test_release_receipt_replay_and_isolation(tmp_path):
    payload = {'receipt.json':b'{"source":"synthetic"}'}
    one = write_release(tmp_path, 's1', payload, RELEASE_META)
    two = write_release(tmp_path, 's2', payload, RELEASE_META)
    assert one['sha256'] == two['sha256']
    (tmp_path/'s2/receipt.json').write_bytes(b'bad')
    assert verify_release(tmp_path/'s1') == one
    with pytest.raises(ValueError): verify_release(tmp_path/'s2')


def test_duplicate_factor_dates_are_quarantined(candidate):
    prices, dates, factors, receipt = candidate
    factors.index = pd.DatetimeIndex([dates[1], *dates[1:-1]])
    result = validate_candidate(*candidate, factor_policy_verified=True, scenarios_verified=True)
    assert result['support_status'] == 'partial'
    assert not result['capabilities']['factors']
