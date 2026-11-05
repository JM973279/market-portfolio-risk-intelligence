"""Synthetic offline fixtures only; no real provider entitlement or prices implied."""
from datetime import date, datetime, timedelta
import json
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from src.portfolio.price_engine.adapters import (AlphaVantageArchiveAdapter, Capture,
    CsvArchiveAdapter, KrxArchiveAdapter, collect_archives)
from src.portfolio.price_engine.contracts import (Instrument, PipelineError,
    QualityPolicy, ResearchPermission, Session, SourceReceipt, SymbolMapping,
    TradingCalendar, Window)
from src.portfolio.price_engine.engine import analyze_research, validate_prices
from src.portfolio.price_engine import storage
from src.portfolio.risk_metrics import risk_metrics


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError('No external connections in price-engine tests')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


def fixture(market='US', kind='stock', source='local_csv', days=None):
    # Invented reviewed schedule, not a production exchange holiday calendar.
    days = days or ['2024-01-02','2024-01-03','2024-01-04','2024-01-05']
    timezone = 'America/New_York' if market == 'US' else 'Asia/Seoul'
    zone = ZoneInfo(timezone)
    mic, currency, symbol = ('XNAS','USD','TEST.A') if market == 'US' else ('XKRX','KRW','005930')
    instrument = Instrument(asset_id=f'{market}:{mic}:{symbol}:test', symbol=symbol,
        market=market, exchange_mic=mic, currency=currency, kind=kind,
        listed_on='2000-01-01', identity_reference='synthetic:test-identity')
    mapping = SymbolMapping(instrument=instrument, source_id=source, provider_symbol=symbol,
        valid_from='2000-01-01', evidence_reference='synthetic:test-mapping')
    sessions = []
    for day in days:
        close = datetime.combine(date.fromisoformat(day), datetime.min.time(), zone).replace(hour=16)
        sessions.append(Session(day=day, close_at=close, available_at=close+timedelta(hours=1)))
    calendar = TradingCalendar(calendar_id=f'test-{mic}', version='fixture-v1',
        market=market, exchange_mic=mic, timezone=timezone, coverage_start=days[0],
        coverage_end=days[-1], evidence_reference='synthetic:calendar', reviewed=True, sessions=tuple(sessions))
    retrieved = sessions[-1].available_at + timedelta(hours=1)
    window = Window(start=days[0], end=days[-1], as_of=retrieved)
    receipt = SourceReceipt(source_id=source, source_url='https://example.invalid/synthetic',
        retrieved_at=retrieved, publication_missing_reason='Synthetic fixture has no publisher',
        adjustment='total_return', adjustment_reference='synthetic:adjustment',
        corporate_actions_reference='synthetic:actions')
    permission = ResearchPermission(source_id=source, evidence_reference='synthetic:fixture-only',
                                    storage_allowed=True, processing_allowed=True)
    return mapping, calendar, window, receipt, permission


def csv_capture(mapping, receipt, days, values=None):
    values = values or [(100,100),(110,110),(88,88),(96.8,96.8)]
    content = 'date,symbol,currency,close,adjusted_close\n' + ''.join(
        f'{day},{mapping.provider_symbol},{mapping.instrument.currency},{raw},{adjusted}\n'
        for day, (raw, adjusted) in zip(days, values))
    return Capture(content.encode(), receipt)


def inputs(market='US', kind='stock', values=None, days=None):
    mapping, calendar, window, receipt, permission = fixture(market, kind, days=days)
    capture = csv_capture(mapping, receipt, [s.day.isoformat() for s in calendar.sessions], values)
    return collect_archives([(CsvArchiveAdapter(), mapping, capture)], [permission]), [calendar], window


def codes(validation):
    return {issue['code'] for issue in validation.report['issues']}


@pytest.mark.parametrize('market,kind', [('US','stock'),('US','etf'),('KR','stock'),('KR','etf')])
def test_price_to_risk_math_in_both_markets(market, kind):
    collection, calendars, window = inputs(market, kind)
    policy = QualityPolicy(min_prices=4)
    validation = validate_prices(collection, calendars, window, policy)
    assert validation.report['research_ready']
    assert not validation.report['public_analysis_allowed']
    assert not validation.report['selectable']
    asset = collection.mappings[0].instrument.asset_id
    result = analyze_research(collection, calendars, window, {asset:1}, policy=policy)
    np.testing.assert_allclose(validation.returns()[asset], [.1,-.2,.1])
    assert result['metrics']['volatility_annual'] == pytest.approx(np.std([.1,-.2,.1],ddof=1)*np.sqrt(252))
    assert result['metrics']['max_drawdown'] == pytest.approx(.2)
    assert result['metrics'] == risk_metrics(validation.returns(), {asset:1})
    comparison = analyze_research(collection, calendars, window, {asset:1}, proposed={asset:1}, policy=policy)
    assert all(v == 0 for v in comparison['metrics']['change'].values())
    json.dumps(result, allow_nan=False)
    assert collection.frame.provider_symbol.iloc[0] == ('005930' if market == 'KR' else 'TEST.A')


def test_default_minimum_757_and_full_window():
    collection, calendars, window = inputs()
    assert 'INSUFFICIENT_PRICES' in codes(validate_prices(collection, calendars, window))
    # Synthetic long schedule only: business-day sequence is NOT an exchange calendar.
    days = [d.date().isoformat() for d in pd.bdate_range('2020-01-01', periods=757)]
    values = [(100+i*.1,100+i*.1) for i in range(757)]
    collection, calendars, window = inputs(values=values, days=days)
    validation = validate_prices(collection, calendars, window)
    assert validation.report['research_ready'] and len(validation.returns()) == 756


@pytest.mark.parametrize('market,days', [
    ('US',['2024-07-03','2024-07-05','2024-07-08','2024-07-09']),
    ('KR',['2024-02-08','2024-02-13','2024-02-14','2024-02-15'])])
def test_explicit_holidays_and_weekends_are_not_filled(market,days):
    collection, calendars, window = inputs(market, days=days)
    result = validate_prices(collection,calendars,window,QualityPolicy(min_prices=4))
    assert result.report['research_ready']
    assert [d.date().isoformat() for d in result.prices.index] == days


@pytest.mark.parametrize('damage,expected', [
    ('missing','MISSING_SESSIONS'),('stale','STALE_PRICES'),('duplicate','DUPLICATE_OBSERVATION'),
    ('holiday','NON_SESSION_OR_UNAVAILABLE_OBSERVATION'),('zero','INVALID_PRICE'),
    ('nan','INVALID_PRICE'),('inf','INVALID_PRICE'),('jump','EXTREME_ADJUSTED_MOVE_REQUIRES_REVIEW'),
    ('raw','TOTAL_RETURN_ADJUSTMENT_UNVERIFIED'),('actions','CORPORATE_ACTIONS_UNVERIFIED'),
    ('identity','IDENTITY_UNVERIFIED'),('future','FUTURE_RETRIEVAL')])
def test_structured_quality_failures(damage,expected):
    mapping, calendar, window, receipt, permission = fixture()
    days = [s.day.isoformat() for s in calendar.sessions]
    values = [(100,100),(110,110),(88,88),(96.8,96.8)]
    if damage == 'missing': days.pop(1); values.pop(1)
    if damage == 'stale': days.pop(); values.pop()
    if damage == 'duplicate': days[1]=days[0]
    if damage == 'holiday': days[1]='2024-01-06'
    if damage in {'zero','nan','inf'}: values[1]=(100,{'zero':0,'nan':'N/A','inf':'inf'}[damage])
    if damage == 'jump': values[1]=(1000,1000)
    if damage == 'raw': receipt=receipt.model_copy(update={'adjustment':'raw'})
    if damage == 'actions': receipt=receipt.model_copy(update={'corporate_actions_reference':None})
    if damage == 'identity': mapping=mapping.model_copy(update={'evidence_reference':None})
    if damage == 'future': receipt=receipt.model_copy(update={'retrieved_at':window.as_of+timedelta(days=1)})
    capture=csv_capture(mapping,receipt,days,values)
    collection=collect_archives([(CsvArchiveAdapter(),mapping,capture)],[permission])
    validation=validate_prices(collection,[calendar],window,QualityPolicy(min_prices=3))
    assert expected in codes(validation)
    assert not validation.report['research_ready']
    with pytest.raises(PipelineError,match='QUALITY_GATE_FAILED'):
        analyze_research(collection,[calendar],window,{mapping.instrument.asset_id:1},policy=QualityPolicy(min_prices=3))


def test_adjusted_split_path_is_used_without_clipping():
    collection, calendars, window = inputs(values=[(200,100),(220,110),(110,110),(121,121)])
    result=validate_prices(collection,calendars,window,QualityPolicy(min_prices=4))
    assert result.report['research_ready']
    np.testing.assert_allclose(result.returns().iloc[:,0],[.1,0,.1])


def test_distinct_captures_with_identical_bytes_keep_retrieval_provenance():
    mapping,calendar,window,receipt,permission=fixture()
    one=csv_capture(mapping,receipt,['2024-01-02'],[(100,100)])
    two=Capture(one.content,receipt.model_copy(update={'retrieved_at':receipt.retrieved_at+timedelta(days=1)}))
    assert one.sha256==two.sha256 and one.capture_id!=two.capture_id
    collection=collect_archives([(CsvArchiveAdapter(),mapping,one),(CsvArchiveAdapter(),mapping,two)],[permission])
    report=validate_prices(collection,[calendar],window,QualityPolicy(min_prices=3))
    assert {'FUTURE_RETRIEVAL','DUPLICATE_OBSERVATION'} <= codes(report)


def test_calendar_close_cutoff_and_no_weekday_fallback():
    collection,calendars,window=inputs()
    calendar=calendars[0]
    before=window.model_copy(update={'as_of':calendar.sessions[-1].close_at})
    assert 'NON_SESSION_OR_UNAVAILABLE_OBSERVATION' in codes(validate_prices(collection,calendars,before,QualityPolicy(min_prices=3)))
    assert 'CALENDAR_MISSING' in codes(validate_prices(collection,[],window))
    unreviewed=calendar.model_copy(update={'reviewed':False})
    assert 'CALENDAR_UNREVIEWED' in codes(validate_prices(collection,[unreviewed],window))
    future_window=window.model_copy(update={'as_of':window.as_of+timedelta(days=4)})
    assert 'FRESHNESS_CALENDAR_COVERAGE_INCOMPLETE' in codes(validate_prices(collection,calendars,future_window))
    old=window.model_copy(update={'end':date(2024,1,4)})
    assert 'STALE_REQUEST_WINDOW' in codes(validate_prices(collection,calendars,old))


def test_dst_and_early_close_schedule_timestamps():
    _,calendar,_,_,_=fixture(days=['2024-03-08','2024-03-11','2024-03-12','2024-03-13'])
    assert calendar.sessions[0].close_at.utcoffset()!=calendar.sessions[1].close_at.utcoffset()
    payload=calendar.model_dump(mode='json')
    payload['sessions'][0]['close_at']='2024-03-08T13:00:00-05:00'
    assert TradingCalendar.model_validate(payload).sessions[0].close_at.hour==13


def test_conflicting_mapping_and_cross_exchange_ambiguity():
    mapping,calendar,window,receipt,permission=fixture()
    capture=csv_capture(mapping,receipt,[s.day.isoformat() for s in calendar.sessions])
    different=mapping.model_copy(update={'provider_symbol':'OTHER'})
    with pytest.raises(PipelineError,match='CONFLICTING_ASSET_MAPPING'):
        collect_archives([(CsvArchiveAdapter(),mapping,capture),(CsvArchiveAdapter(),different,capture)],[permission])
    other=mapping.model_copy(update={'instrument':mapping.instrument.model_copy(update={'asset_id':'US:XNYS:TEST.A:test','exchange_mic':'XNYS'})})
    with pytest.raises(PipelineError,match='AMBIGUOUS_PROVIDER_SYMBOL'):
        collect_archives([(CsvArchiveAdapter(),mapping,capture),(CsvArchiveAdapter(),other,capture)],[permission])


def test_mapping_expiration_and_delisting():
    mapping,calendar,window,receipt,permission=fixture()
    mapping=mapping.model_copy(update={'valid_to':date(2024,1,3)})
    capture=csv_capture(mapping,receipt,[s.day.isoformat() for s in calendar.sessions])
    collection=collect_archives([(CsvArchiveAdapter(),mapping,capture)],[permission])
    assert 'LISTING_OR_MAPPING_WINDOW_INVALID' in codes(validate_prices(collection,[calendar],window))


def test_unapproved_research_storage_fails_before_parsing():
    mapping,_,_,receipt,permission=fixture()
    with pytest.raises(PipelineError,match='RESEARCH_PERMISSION_REQUIRED'):
        collect_archives([(CsvArchiveAdapter(),mapping,Capture(b'not even csv',receipt))],[])
    with pytest.raises(PipelineError,match='RESEARCH_PERMISSION_REQUIRED'):
        collect_archives([(CsvArchiveAdapter(),mapping,Capture(b'',receipt))],
                         [permission.model_copy(update={'processing_allowed':False})])


def test_fx_path_remains_separate():
    us,_,_,receipt,permission=fixture()
    kr,_,_,kr_receipt,_=fixture('KR')
    jobs=[(CsvArchiveAdapter(),m,csv_capture(m,r,['2024-01-02'],[(100,100)]))
          for m,r in [(us,receipt),(kr,kr_receipt)]]
    collection=collect_archives(jobs,[permission])
    assert 'FX_POLICY_REQUIRED' in codes(validate_prices(collection,[],Window(start='2024-01-02',end='2024-01-02',as_of=receipt.retrieved_at)))


def test_alpha_json_archive_and_duplicate_json_error():
    mapping,calendar,window,receipt,permission=fixture(source='alpha_vantage')
    payload={'Meta Data':{'2. Symbol':mapping.provider_symbol},'Time Series (Daily)':{
        s.day.isoformat():{'4. close':str(100+i),'5. adjusted close':str(100+i)}
        for i,s in enumerate(calendar.sessions)}}
    collection=collect_archives([(AlphaVantageArchiveAdapter(),mapping,Capture(json.dumps(payload).encode(),receipt))],[permission])
    assert validate_prices(collection,[calendar],window,QualityPolicy(min_prices=4)).report['research_ready']
    for raw,code in [(b'{"Note":"rate limited"}','PROVIDER_ERROR_RESPONSE'),
                     (b'{"x":1,"x":2}','DUPLICATE_JSON_KEY'),(b'{}','PROVIDER_SCHEMA_MISMATCH')]:
        with pytest.raises(PipelineError,match=code):
            collect_archives([(AlphaVantageArchiveAdapter(),mapping,Capture(raw,receipt))],[permission])


@pytest.mark.parametrize('kind',['stock','etf'])
def test_krx_archive_preserves_raw_only_and_exact_identifier(kind):
    mapping,calendar,window,receipt,permission=fixture('KR',kind,source='krx_openapi')
    receipt=receipt.model_copy(update={'adjustment':'raw'})
    payload={'OutBlock_1':[{'BAS_DD':s.day.strftime('%Y%m%d'),'ISU_CD':mapping.provider_symbol,'TDD_CLSPRC':str(100+i)}
                           for i,s in enumerate(calendar.sessions)]}
    collection=collect_archives([(KrxArchiveAdapter(),mapping,Capture(json.dumps(payload).encode(),receipt))],[permission])
    assert collection.frame.adjusted_close.isna().all()
    assert 'TOTAL_RETURN_ADJUSTMENT_UNVERIFIED' in codes(validate_prices(collection,[calendar],window,QualityPolicy(min_prices=4)))
    with pytest.raises(PipelineError,match='ADAPTER_ADJUSTMENT_MISMATCH'):
        collect_archives([(KrxArchiveAdapter(),mapping,Capture(json.dumps(payload).encode(),receipt.model_copy(update={'adjustment':'total_return'})))],[permission])


def test_malformed_input_and_contracts_fail_closed():
    mapping,_,_,receipt,permission=fixture()
    for raw in [b'date,date\n1,2',b'date,symbol,currency,close,adjusted_close\nx,TEST.A,USD,1,1',
                b'date,symbol,currency,close,adjusted_close\n2024-01-02,TEST.A,KRW,1,1']:
        with pytest.raises(PipelineError): collect_archives([(CsvArchiveAdapter(),mapping,Capture(raw,receipt))],[permission])
    with pytest.raises(ValidationError):
        SourceReceipt.model_validate({**receipt.model_dump(),'retrieved_at':'2024-01-05T20:00:00'})
    with pytest.raises(ValidationError):
        SourceReceipt.model_validate({**receipt.model_dump(),'source_url':'https://example.invalid/?apikey=secret'})
    with pytest.raises(ValidationError):
        Instrument.model_validate({**mapping.instrument.model_dump(),'currency':'KRW'})


@pytest.mark.parametrize('market',['US','KR'])
def test_replay_hashes_immutability_and_private_destination(tmp_path,monkeypatch,market):
    monkeypatch.setattr(storage,'RESEARCH_ROOT',tmp_path/'private')
    collection,calendars,window=inputs(market)
    manifest=storage.save_research('test-v1',collection,calendars,window,policy=QualityPolicy(min_prices=4),
                                  code_version='synthetic-test-v1',revision_note='test only')
    assert manifest['metadata']['approval_status']=='quarantined'
    replayed,_,_,_,validation=storage.replay_research(tmp_path/'private/test-v1')
    pd.testing.assert_frame_equal(collection.frame,replayed.frame)
    assert validation.report['research_ready'] and not validation.report['public_analysis_allowed']
    with pytest.raises(FileExistsError):
        storage.save_research('test-v1',collection,calendars,window,policy=QualityPolicy(min_prices=4),code_version='test',revision_note='test')
    with pytest.raises(PipelineError,match='RESEARCH_DESTINATION_REQUIRED'):
        storage.replay_research(tmp_path/'public')
    (tmp_path/'private/test-v1/normalized.csv').write_text('tampered')
    with pytest.raises(ValueError,match='integrity'):
        storage.replay_research(tmp_path/'private/test-v1')


def test_modified_frame_is_not_trusted(tmp_path,monkeypatch):
    collection,calendars,window=inputs()
    collection.frame.loc[0,'adjusted_close']=100.1
    assert 'NORMALIZED_CONTENT_CHANGED' in codes(validate_prices(collection,calendars,window))
    monkeypatch.setattr(storage,'RESEARCH_ROOT',tmp_path/'private')
    with pytest.raises(PipelineError,match='RESEARCH_INPUT_NOT_AUTHORIZED_OR_IMMUTABLE'):
        storage.save_research('test',collection,calendars,window,code_version='test',revision_note='test')


def test_quarantined_failure_replay_and_symlink_rejection(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'RESEARCH_ROOT',tmp_path/'private')
    collection,calendars,window=inputs()
    storage.save_research('short',collection,calendars,window,code_version='test',revision_note='insufficient history')
    *_,validation=storage.replay_research(tmp_path/'private/short')
    assert 'INSUFFICIENT_PRICES' in codes(validation)
    (tmp_path/'alias').symlink_to(tmp_path/'private',target_is_directory=True)
    with pytest.raises(PipelineError,match='SYMLINK'):
        storage.replay_research(tmp_path/'alias/short')


def test_two_asset_covariance_and_whatif():
    mapping,calendar,window,receipt,permission=fixture('KR','etf')
    second=mapping.model_copy(update={
        'instrument':mapping.instrument.model_copy(update={'asset_id':'KR:XKRX:000001:test','symbol':'000001'}),
        'provider_symbol':'000001'})
    days=[s.day.isoformat() for s in calendar.sessions]
    one=csv_capture(mapping,receipt,days)
    two=csv_capture(second,receipt,days,[(100,100),(101,101),(102,102),(103,103)])
    collection=collect_archives([(CsvArchiveAdapter(),mapping,one),(CsvArchiveAdapter(),second,two)],[permission])
    a,b=mapping.instrument.asset_id,second.instrument.asset_id
    result=analyze_research(collection,[calendar],window,{a:.6,b:.4},proposed={a:.2,b:.8},policy=QualityPolicy(min_prices=4))
    prices=np.array([[100,100],[110,101],[88,102],[96.8,103]])
    returns=prices[1:]/prices[:-1]-1
    covariance=np.cov(returns,rowvar=False,ddof=1)
    assert result['metrics']['current']['volatility_annual']==pytest.approx(np.sqrt(np.array([.6,.4])@covariance@np.array([.6,.4])*252))
    assert result['metrics']['change']['volatility_annual'] < 0


def test_not_yet_available_session_is_not_a_missing_price():
    mapping,calendar,window,receipt,permission=fixture()
    as_of=calendar.sessions[-1].close_at
    receipt=receipt.model_copy(update={'retrieved_at':as_of})
    capture=csv_capture(mapping,receipt,[s.day.isoformat() for s in calendar.sessions[:-1]],[(100,100),(101,101),(102,102)])
    collection=collect_archives([(CsvArchiveAdapter(),mapping,capture)],[permission])
    validation=validate_prices(collection,[calendar],window.model_copy(update={'as_of':as_of}),QualityPolicy(min_prices=3))
    assert validation.report['research_ready']
    late=window.model_copy(update={'as_of':as_of+timedelta(hours=2)})
    assert 'STALE_PRICES' in codes(validate_prices(collection,[calendar],late,QualityPolicy(min_prices=3)))


def test_retrieval_preceding_availability_and_historical_freshness():
    mapping,calendar,window,receipt,permission=fixture()
    receipt=receipt.model_copy(update={'retrieved_at':calendar.sessions[0].available_at})
    capture=csv_capture(mapping,receipt,[s.day.isoformat() for s in calendar.sessions])
    collection=collect_archives([(CsvArchiveAdapter(),mapping,capture)],[permission])
    assert 'OBSERVATION_NOT_YET_AVAILABLE_AT_RETRIEVAL' in codes(validate_prices(collection,[calendar],window))
    collection,calendars,window=inputs()
    historical=window.model_copy(update={'mode':'historical','as_of':window.as_of+timedelta(days=10)})
    validation=validate_prices(collection,calendars,historical,QualityPolicy(min_prices=4))
    assert validation.report['research_ready'] and validation.report['freshness_scope']=='historical'


def test_cli_local_capture_and_replay(tmp_path,monkeypatch,capsys):
    from scripts.portfolio_price_engine import main
    monkeypatch.setattr(storage,'RESEARCH_ROOT',tmp_path/'private')
    mapping,calendar,window,receipt,permission=fixture('KR')
    raw=csv_capture(mapping,receipt,[s.day.isoformat() for s in calendar.sessions])
    (tmp_path/'archive.csv').write_bytes(raw.content)
    config={'mappings':[mapping.model_dump(mode='json')],
            'permissions':[permission.model_dump(mode='json')],
            'calendars':[calendar.model_dump(mode='json')],
            'window':window.model_dump(mode='json'),'policy':{'min_prices':4},
            'archives':[{'asset_id':mapping.instrument.asset_id,'adapter':'csv','path':'archive.csv',
                         'receipt':receipt.model_dump(mode='json')}]}
    path=tmp_path/'config.json'
    path.write_text(json.dumps(config))
    assert main(['ingest',str(path),'--run-id','cli-test','--code-version','synthetic','--revision-note','fixture'])==0
    assert json.loads(capsys.readouterr().out)['research_ready']
    assert main(['replay','cli-test'])==0
    assert not json.loads(capsys.readouterr().out)['public_analysis_allowed']
    assert main(['replay','../escape'])==2
    assert json.loads(capsys.readouterr().err)['code']=='RESEARCH_PATH_SYMLINK_OR_TRAVERSAL'


def test_revisions_are_separate_runs_and_environment_is_recorded(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'RESEARCH_ROOT',tmp_path/'private')
    one,calendars,window=inputs()
    two,_,_=inputs(values=[(100,100),(110,110),(88.1,88.1),(96.8,96.8)])
    kwargs=dict(policy=QualityPolicy(min_prices=4),code_version='synthetic',revision_note='test revision')
    first=storage.save_research('v1',one,calendars,window,**kwargs)
    second=storage.save_research('v2',two,calendars,window,previous_snapshot_id='v1',**kwargs)
    assert first['sha256']['normalized.csv']!=second['sha256']['normalized.csv']
    assert second['metadata']['previous_snapshot_id']=='v1'
    *_,before=storage.replay_research(tmp_path/'private/v1')
    *_,after=storage.replay_research(tmp_path/'private/v2')
    assert before.report['normalized_sha256']!=after.report['normalized_sha256']
    replay=json.loads((tmp_path/'private/v1/replay.json').read_text())
    assert {'python','pandas','numpy','pydantic'}==set(replay['dependencies'])
