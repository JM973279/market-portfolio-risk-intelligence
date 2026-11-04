"""Real V1 replay verifies the new adapter, never pretends to approve new prices."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.portfolio import v2
from scripts.portfolio_phase2_replay import real_replay_inputs
from src.portfolio.server import app

ROOT = Path(__file__).resolve().parents[1]




@pytest.fixture
def replay(tmp_path):
    v2.build_bundle(tmp_path, 'real-v1-replay', *real_replay_inputs())
    return v2.load_research_bundle(tmp_path/'real-v1-replay')


def request(holdings=None, **patch):
    return v2.V2Request(**{'snapshot_id':'real-v1-replay','market':'US','base_currency':'USD',
                         'holdings':holdings or [{'ticker':'AAPL','weight':30},{'ticker':'MSFT','weight':30}, {'ticker':'NVDA','weight':20},{'ticker':'AMZN','weight':20}],
                         'value_amount':100000,**patch})


def test_real_hidden_risk_factors_stress_and_whatif(replay):
    before = request()
    proposed = request(json.loads((ROOT/'examples/portfolio/after.json').read_text())['holdings'])
    result = v2.analyze_bundle(replay, before)
    actual = result['analysis']
    golden = json.loads((ROOT/'tests/fixtures/portfolio_v1_golden.json').read_text())
    expected = golden['responses']['before']
    for key in actual:
        assert actual[key] == expected[key], key
    comparison = v2.compare_bundle(replay,v2.V2CompareRequest(current=before,proposed=proposed))
    assert comparison['comparison'] == golden['comparison']['comparison']
    assert comparison['current'] == v2.analyze_bundle(replay,before)
    assert comparison['proposed'] == v2.analyze_bundle(replay,proposed)
    assert result['scope'] == 'research_only'


def test_real_formulas_independent(replay):
    body = v2.analyze_bundle(replay,request())['analysis']
    tickers = [h.ticker for h in request().holdings]
    w = np.array([h.weight/100 for h in request().holdings])
    cov = np.cov(replay.returns[tickers].to_numpy(),rowvar=False,ddof=1)
    variance = w @ cov @ w
    assert body['volatility'] == round(float(np.sqrt(252*variance))*100,2)
    shares = w*(cov@w)/variance*100
    for ticker,share in zip(tickers,shares):
        assert next(r['share'] for r in body['risk_contribution'] if r['ticker']==ticker) == round(float(share),2)
    y = replay.returns['AAPL']
    for factor in v2.FACTORS:
        pair = pd.concat([y,replay.factors[factor]],axis=1).dropna().to_numpy()
        beta = np.linalg.lstsq(np.column_stack([np.ones(len(pair)),pair[:,1]]),pair[:,0],rcond=None)[0][1]
        assert replay.betas.at['AAPL',factor] == pytest.approx(beta,rel=1e-9,abs=1e-12)


def test_public_build_requires_all_dependency_rights(tmp_path):
    with pytest.raises(v2.V2Unavailable,match='SOURCE_RIGHTS_INCOMPLETE'):
        v2.build_bundle(tmp_path,'never-public',*real_replay_inputs(),scope='public_approved')
    assert not (tmp_path/'never-public').exists()


def test_research_cannot_be_loaded_as_public(replay,tmp_path):
    path = ROOT/'data/portfolio_v2/registry.json'
    assert json.loads(path.read_text())['releases'] == {}
    with pytest.raises(v2.V2Unavailable,match='RESEARCH_ONLY_BUNDLE'):
        v2.Bundle(tmp_path/'real-v1-replay', replay.manifest, public=True)


def test_corruption_is_quarantined_and_v1_still_works(replay,tmp_path):
    (tmp_path/'real-v1-replay/returns.npy').write_text('corrupt')
    with pytest.raises(ValueError): v2.load_research_bundle(tmp_path/'real-v1-replay')
    client = TestClient(app)
    assert client.get('/health').status_code == 200
    assert client.post('/api/portfolio/analyze',json={'holdings':[{'ticker':'SPY','weight':100}],'value_usd':100000}).status_code == 200


def test_no_public_release_and_us_only():
    client = TestClient(app)
    body = request().model_dump()
    response = client.post('/api/portfolio/v2/analyze',json=body)
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'NO_APPROVED_RELEASE'
    assert client.post('/api/portfolio/v2/analyze',json={**body,'market':'KR','base_currency':'KRW'}).status_code == 422
    assert client.post('/api/portfolio/v2/analyze',json={**body,'snapshot_id':'../escape'}).status_code == 422
    assert client.post('/api/portfolio/v2/compare',json={'current':body,'proposed':{**body,'snapshot_id':'another'}}).status_code == 422


@pytest.mark.parametrize('damage', ['zero','missing','duplicate','reversed','jump','factor_nan','factor_inf','exclusion_reference'])
def test_data_gates(tmp_path,damage):
    prices,sessions,moves,universe,scenarios,provenance,exclusions,metadata = real_replay_inputs()
    prices=prices.copy();moves=moves.copy()
    if damage=='zero':prices.iloc[2,0]=0
    if damage=='missing':prices=prices.iloc[1:]
    if damage=='duplicate':prices.index=pd.DatetimeIndex([sessions[0],*sessions[:-1]])
    if damage=='reversed':prices=prices.iloc[::-1]
    if damage=='jump':prices.iloc[2,0]*=10
    if damage=='factor_nan':moves.iloc[0,0]=np.nan
    if damage=='factor_inf':moves.iloc[0,0]=np.inf
    if damage=='exclusion_reference':exclusions['rate'][0]['reference']=''
    with pytest.raises(v2.V2Unavailable):
        v2.build_bundle(tmp_path,'bad',prices,sessions,moves,universe,scenarios,provenance,exclusions,metadata)
    assert not (tmp_path/'bad').exists()


def test_candidate_catalog_and_v1_rejection():
    client = TestClient(app)
    assets = client.get('/api/portfolio/v2/catalog').json()['assets']
    assert len(assets)==80
    candidates = [a for a in assets if a['support_scope']=='discovery_only']
    assert len(candidates)==52
    assert all(not a['selectable'] and a['support_status']=='unsupported' and 'RIGHTS_UNCONFIRMED' in a['reason_codes'] for a in candidates)
    assert client.post('/api/portfolio/analyze',json={'holdings':[{'ticker':'AVGO','weight':100}],'value_usd':100000}).status_code==422


def test_rights_cannot_be_inferred_from_price_access_or_partial_license():
    dependencies={category:['unit-test-license'] for category in v2.REQUIRED_RIGHTS}
    provenance={'dependencies':dependencies}
    with pytest.raises(v2.V2Unavailable,match='RIGHTS_UNCONFIRMED'):
        v2.require_rights(provenance,{},['AVGO'])
    # Artificial permission record tests scope matching; not a real source entitlement.
    ledger={'unit-test-license':{'status':'approved','source_id':'unit-test-only','categories':list(v2.REQUIRED_RIGHTS),
                                'evidence_reference':'unit-test-only','reviewed_at':'2026-11-04',
                                'storage_allowed':True,'public_derived_allowed':True,'artifact_distribution_allowed':True,
                                'subjects':['AAPL','SPY','DGS10','VIX','equity_selloff','rate_shock','volatility_shock']}}
    with pytest.raises(v2.V2Unavailable,match='LICENSE_SUBJECTS_INCOMPLETE'):
        v2.require_rights(provenance,ledger,['AVGO'])
    ledger['unit-test-license']['public_derived_allowed']=False
    with pytest.raises(v2.V2Unavailable,match='RIGHTS_UNCONFIRMED'):
        v2.require_rights(provenance,ledger,['AAPL'])


def test_missing_v2_registry_does_not_disable_v1(tmp_path,monkeypatch):
    monkeypatch.setattr(v2,'REGISTRY_PATH',tmp_path/'missing.json')
    client=TestClient(app)
    assert client.post('/api/portfolio/v2/analyze',json=request().model_dump()).status_code==503
    assert client.get('/api/portfolio/universe').status_code==200
    assert client.get('/health').status_code==200


def test_unknown_asset_is_not_silently_dropped(replay):
    with pytest.raises(v2.V2Unavailable,match='ASSET_NOT_IN_APPROVED_SNAPSHOT'):
        v2.analyze_bundle(replay,request([{'ticker':'AVGO','weight':100}]))


def test_snapshot_metadata_rejects_future_and_currency(tmp_path):
    args=list(real_replay_inputs())
    args[-1]={**args[-1], 'snapshot_as_of':'2099-01-01'}
    with pytest.raises(v2.V2Unavailable,match='SNAPSHOT_DATE_MISMATCH'):
        v2.build_bundle(tmp_path,'bad-date',*args)
    args[-1]={**args[-1], 'base_currency':'KRW'}
    with pytest.raises(v2.V2Unavailable,match='UNSUPPORTED_MARKET_OR_CURRENCY'):
        v2.build_bundle(tmp_path,'bad-currency',*args)


def test_revisions_are_reported_without_mutating_original():
    prices,*_ = real_replay_inputs()
    original = prices.copy()
    revised = prices.copy()
    revised.iloc[5,0] += .01  # Unit-test defect, never a replacement market observation.
    result = v2.revision_diff(prices,revised)
    assert result['changed_observations']==1
    assert result['changes']==[{'ticker':prices.columns[0],'date':str(prices.index[5].date())}]
    pd.testing.assert_frame_equal(prices,original)
    assert v2.revision_diff(prices,prices)['changed_observations']==0
