"""Run as a script: python market_engine/operations/run.py [--collect].

Reuses hash-pinned original provider/calculation code in this isolated process.
Does not import the original API, refresh service, training or portfolio code.
"""
import argparse
import contextlib
import copy
import hashlib
import importlib.util
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    temporary.replace(path)


def public_summary(report):
    """Share derived signals and provenance without redistributing raw quotes/yields.

    Full provider observations remain in the ignored local run directory.
    """
    summary = copy.deepcopy(report)
    summary['sourceValuesIncluded'] = False
    for market in summary['markets'].values():
        for observation in market.get('availability', []):
            observation.pop('values', None)
        for point in [*market.get('history', []), market.get('current'), market.get('lastValid')]:
            if point is not None:
                point['price'] = None
    return summary


def assert_hash(path, expected):
    if digest(path) != expected:
        raise ValueError(f'Hash mismatch: {path.name}')


def verify_model(model, columns):
    import numpy as np
    if list(getattr(model, 'feature_names_in_', [])) != columns or model.n_features_in_ != 17:
        raise ValueError('Frozen model feature schema/order mismatch')
    if list(model.named_steps) != ['scaler', 'classifier']:
        raise ValueError('Frozen preprocessing Pipeline mismatch')
    scaler = model.named_steps['scaler']
    if not np.isfinite(scaler.mean_).all() or not np.isfinite(scaler.scale_).all() or (scaler.scale_ <= 0).any():
        raise ValueError('Invalid fitted scaler')


def compare(frame, reference, columns):
    """Every stored reference value must be reproducible, including date coverage."""
    import numpy as np
    if frame.index.duplicated().any() or reference.index.duplicated().any():
        raise ValueError('Duplicate comparison date')
    for column in columns:
        valid = reference[column].dropna()
        if valid.empty or not valid.index.isin(frame.index).all():
            raise ValueError(f'Reference dates unavailable: {column}')
        if not np.allclose(frame.loc[valid.index, column], valid, rtol=1e-9, atol=1e-9):
            raise ValueError(f'Historical reproduction mismatch: {column}')


US_CHANNELS = ['SPY', 'VIX', 'BAA_Treasury_Spread']
# Provider revisions of overlapping history that may be absorbed by anchoring.
# Observed 2026-11: Yahoo SPY adjusted closes differ by <= 0.00018 USD
# (2.4e-7 relative) between downloads; VIX and the credit spread are identical.
US_OVERLAP_RTOL = {'SPY': 1e-5, 'VIX': 1e-9, 'BAA_Treasury_Spread': 1e-9}
US_SCALE_LIMIT = 0.03  # a larger SPY basis change is not a dividend re-adjustment
US_OVERLAP_DAYS = 250


def anchor_us_history(cache, provider):
    """Keep the frozen US cache and append only provider observations after it.

    Re-downloading the full history makes the strict reference comparison fail
    on provider revisions (Yahoo re-adjusts SPY history; a credit value the
    research cleaner carried forward is later observed). Instead the cached
    rows stay exactly as they were, so historical features still reproduce the
    reference at 1e-9, and only post-cache dates come from the provider. SPY
    is rescaled to the cache's adjustment basis by the ratio on the last
    shared date, which leaves provider daily returns unchanged. Overlap
    differences beyond US_OVERLAP_RTOL still fail closed.
    """
    import numpy as np
    import pandas as pd
    end = cache.index.max()
    review = {'cacheEnd': end.strftime('%Y-%m-%d'), 'channels': {}}
    appended = {}
    for column in US_CHANNELS:
        old = cache[column].dropna()
        new = provider[column].dropna()
        shared = old.index.intersection(new.index)
        shared = shared[shared >= end - pd.Timedelta(days=int(US_OVERLAP_DAYS * 1.5))]
        if len(shared) < 20:
            raise ValueError(f'Provider overlap too short to verify revisions: {column}')
        scale = 1.0
        if column == 'SPY':
            last = shared.max()
            scale = float(old.loc[last] / new.loc[last])
            if not np.isfinite(scale) or abs(scale - 1) > US_SCALE_LIMIT:
                raise ValueError(f'Provider adjustment basis changed beyond limit: {column}')
        relative = ((new.loc[shared] * scale - old.loc[shared]).abs() / old.loc[shared].abs().clip(lower=1e-12)).max()
        review['channels'][column] = {'overlapDates': int(len(shared)), 'scale': scale,
                                      'maxRelativeDifference': float(relative)}
        if not relative <= US_OVERLAP_RTOL[column]:
            raise ValueError(f'Provider revision beyond anchoring tolerance: {column}')
        appended[column] = new.loc[new.index > end] * scale
    joined = pd.concat(appended, axis=1, sort=True).sort_index()
    joined = joined.loc[joined['SPY'].notna()]
    review['appendedDates'] = int(len(joined))
    raw = pd.concat([cache[US_CHANNELS], joined[US_CHANNELS]]).sort_index()
    if raw.index.duplicated().any():
        raise ValueError('Duplicate date after anchoring')
    return raw, review


def eligible_dates(features, raw, columns, cutoff):
    """Only post-training dates with exact-date real source observations qualify."""
    import numpy as np
    complete = raw.dropna(subset=columns).index
    dates = features.index.intersection(complete)
    dates = dates[dates > cutoff]
    return dates[np.isfinite(features.loc[dates].to_numpy(dtype=float)).all(axis=1)]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def calculate(market, stage, original, contract):
    import pandas as pd
    if market == 'us':
        from src.data import cleaner
        from src.features import engineering, stress_index, targets
        cleaner.DATA_RAW_DIR = cleaner.DATA_PROCESSED_DIR = stage
        engineering.DATA_PROCESSED_DIR = engineering.DATA_FEATURES_DIR = stage
        stress_index.DATA_PROCESSED_DIR = stress_index.DATA_FEATURES_DIR = stage
        targets.DATA_FEATURES_DIR = stage
        cleaner.MarketDataCleaner().clean()
        stress_index.StressIndexCalculator().calculate_msi()
        targets.TargetGenerator().generate_targets()
        engineering.FeatureEngineer().generate_features()
        features = pd.read_csv(stage/'latest_features.csv', index_col='Date', parse_dates=True)
        official = pd.read_csv(stage/'targets.csv', index_col='Date', parse_dates=True)
    else:
        features_module = load_module(ROOT/'market_engine/early_warning_v2/build_korea_features_v2.py', 'frozen_kr_features')
        msi = load_module(original/'src/korea/build_korea_stress_index.py', 'frozen_kr_msi')
        for module in [features_module, msi]:
            module.KRX_PATH = str(stage/'krx_indices.csv')
            module.VKOSPI_PATH = str(stage/'vkospi.csv')
            module.CREDIT_PATH = str(stage/'ecos_credit.csv')
        features_module.LATEST_OUTPUT_PATH = str(stage/'latest_features.csv')
        msi.OUTPUT_PATH = str(stage/'official_msi.csv')
        msi.main()
        features_module.main(inference_only=True)
        features = pd.read_csv(stage/'latest_features.csv', index_col='Date', parse_dates=True)
        official = pd.read_csv(stage/'official_msi.csv', index_col='Date', parse_dates=True)
    return features, official


def infer_history(market, stage, original, config, features, official, raw, channels, due, live=False, seed_end=None):
    import joblib
    import numpy as np
    import pandas as pd
    from src.operations.calendar import calendar
    model_path = (ROOT if market == 'korea' else original)/config['model']
    cols = config['features']
    # Cached reference run proves builder equivalence before new inference.
    # A provider's adjusted-history revisions are accepted only after a separate review;
    # no silent rebase of the frozen research history.
    reference_root = ROOT if market == 'korea' else original
    assert_hash(reference_root/config['reference'], config['reference_sha256'])
    reference = pd.read_csv(reference_root/config['reference'], index_col='Date', parse_dates=True)
    compare(features, reference, cols)
    msi_name = 'Korea_MSI' if market == 'korea' else 'MSI'
    compare(official, reference, [msi_name, 'Stress_Threshold'])
    history = []
    assert_hash(model_path, config['model_sha256'])
    model = joblib.load(model_path)
    verify_model(model, cols)
    eligible = eligible_dates(features[cols], raw, channels, pd.Timestamp(config['training_cutoff']))
    # No inference on holidays accidentally supplied by a provider.
    cal = calendar(market, pd.Timestamp(due).year)
    eligible = eligible.intersection(cal.sessions_in_range(eligible.min(), eligible.max())) if len(eligible) else eligible
    eligible = eligible.intersection(official.dropna(subset=[msi_name,'Stress_Threshold']).index)
    probabilities = model.predict_proba(features.loc[eligible, cols]) if len(eligible) else np.empty((0,2))
    if probabilities.shape != (len(eligible),2) or not np.isfinite(probabilities).all() or (probabilities<0).any() or (probabilities>1).any() or not np.allclose(probabilities.sum(axis=1),1):
        raise ValueError('Invalid prediction')
    equity_column = 'SPY' if market == 'us' else 'KOSPI200'
    for day, probability in zip(eligible, probabilities[:,1]):
        history.append({'date': day.strftime('%Y-%m-%d'), 'risk': float(probability),
            'msi': float(official.loc[day,msi_name]), 'threshold': float(official.loc[day,'Stress_Threshold']),
            'price': float(raw.loc[day,equity_column]), 'recordType': 'OPERATIONAL' if live and day > seed_end else 'RETROSPECTIVE_INFERENCE'})
    assert_hash(model_path, config['model_sha256'])
    return history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-v1-root', type=Path, default=ROOT.parent/'market-stress-early-warning')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--collect', action='store_true', help='Attempt independent provider refreshes (no scheduling).')
    mode.add_argument('--replay-run', type=Path, help='Replay retained source receipts without network.')
    args = parser.parse_args()
    original = args.original_v1_root.resolve()
    use_provider = bool(args.collect or args.replay_run)
    replay_report = None
    if args.replay_run:
        args.replay_run = args.replay_run.resolve()
        if not args.replay_run.is_relative_to(ROOT/'data/operations'):
            raise ValueError('Replay must use a retained operational run')
        replay_report = json.loads((args.replay_run/'report.json').read_text())
    contract = json.loads((ROOT/'market_engine/operations/contract.json').read_text())
    for relative, sha in contract['original_sources'].items():
        assert_hash(original/relative, sha)
    for relative, sha in contract['local_sources'].items():
        assert_hash(ROOT/relative, sha)
    # Original src imports stay inside this process, never inside Portfolio API.
    sys.path.insert(0, str(original))
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    from dotenv import load_dotenv
    # Existing credentials are used in memory only. Never exported in receipts.
    os.environ.pop('PYTHON_DOTENV_DISABLED', None)
    load_dotenv(original/'.env', override=False)
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    import pandas as pd
    from src.operations.providers import Providers, PROVIDERS
    from src.operations.calendar import expected, calendar
    from src.operations.validation import validate_series, TransientProviderError

    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    run = ROOT/'data/operations'/run_id
    run.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'runId': run_id, 'generatedAt': datetime.now(timezone.utc).isoformat(),
              'mode': 'receipt-replay' if args.replay_run else 'provider-refresh' if args.collect else 'cache-reproduction', 'markets': {}}

    class RecordedProviders(Providers):
        def call(self, series, fetch):
            for attempt in range(1, 4):
                receipt = {'series': series, 'provider': PROVIDERS[series], 'attempt': attempt,
                           'startedAt': datetime.now(timezone.utc).isoformat()}
                try:
                    result = fetch()
                    receipt.update(status='SUCCESS', retrievedAt=datetime.now(timezone.utc).isoformat())
                    receipts.append(receipt)
                    return result, receipt['retrievedAt']
                except Exception as error:
                    # Never persist str(error): provider exceptions can embed API keys.
                    receipt.update(status='ERROR', errorType=type(error).__name__,
                                   finishedAt=datetime.now(timezone.utc).isoformat())
                    receipts.append(receipt)
                    import requests
                    if not isinstance(error, (TransientProviderError, requests.RequestException)) or attempt == 3:
                        raise
                    time.sleep(attempt)

    for market in ['korea', 'us']:
        stage = run/market
        stage.mkdir()
        receipts = []
        config = contract['markets'][market]
        model_path = (ROOT if market == 'korea' else original)/config['model']
        result = {'status': 'UNAVAILABLE', 'expectedDate': None, 'series': [], 'history': [], 'current': None,
                  'lastValid': None, 'reason': None, 'modelSha256': config['model_sha256'],
                  'trainingCutoff': config['training_cutoff'], 'trainingEvidence': config['training_evidence'],
                  'featureOrder': config['features'], 'inferenceSucceeded': False}
        report['markets'][market] = result
        try:
            due, deadline = expected(market)
            result.update(expectedDate=due, publicationDeadline=deadline)
            if market == 'us':
                seed = pd.read_csv(original/'data/raw/raw_market_data.csv', index_col='Date', parse_dates=True)
                base = {c: seed[[c]] for c in ['SPY','VIX','BAA_Treasury_Spread']}
            else:
                indices = pd.read_csv(original/'data/raw/korea/krx_indices.csv', parse_dates=['Date'])
                equity = indices.loc[indices.Index == 'KOSPI200', ['Date','Close']].set_index('Date').rename(columns={'Close':'KOSPI200'})
                volatility = pd.read_csv(original/'data/raw/korea/vkospi.csv', index_col='Date', parse_dates=True)
                credit = pd.read_csv(original/'data/raw/korea/ecos_credit.csv', index_col='Date', parse_dates=True)
                base = {'KOSPI200': equity, 'VKOSPI': volatility[['Close']].rename(columns={'Close':'VKOSPI'}),
                        **{c: credit[[c]] for c in ['Korea_Treasury_3Y','Korea_Corporate_AAminus_3Y']}}
            frames = dict(base)
            failed = False
            providers = RecordedProviders(run_id)
            names = ['SPY','VIX','DBAA','DGS10'] if market == 'us' else ['KOSPI200','VKOSPI','Korea_Treasury_3Y','Korea_Corporate_AAminus_3Y']
            collected = {}
            for name in names:
                frame = base.get(name)
                info = {'name': name, 'provider': PROVIDERS[name], 'retrievedAt': None,
                        'observationDate': None, 'status': 'CACHE', 'reason': '기존 캐시: 수집 시각 미확인'}
                if args.collect:
                    try:
                        if market == 'us':
                            frame, retrieved = providers.yahoo(name, due) if name in ['SPY','VIX'] else providers.fred(name, due)
                        else:
                            frame, retrieved = providers.krx(name, due, base[name]) if name in ['KOSPI200','VKOSPI'] else providers.ecos(name, due)
                        info.update(retrievedAt=retrieved, status='OBSERVED', reason=None)
                        if market == 'korea' and name in ['KOSPI200','VKOSPI']:
                            frame = pd.concat([base[name], frame])
                            frame = frame[~frame.index.duplicated(keep='last')].sort_index()
                        collected[name] = frame
                    except Exception as error:
                        failed = True
                        reason = f'수집 실패 ({type(error).__name__}); 인증·네트워크·제공처 응답 확인 필요'
                        if name in ['KOSPI200','VKOSPI'] and not os.getenv('KRX_API_KEY'):
                            reason = 'KRX_API_KEY 미설정'
                        elif name.startswith('Korea_') and not os.getenv('ECOS_API_KEY'):
                            reason = 'ECOS_API_KEY 미설정'
                        elif str(error).startswith('Provider HTTP '):
                            reason = str(error).split(' (')[0]
                        info.update(status='ERROR', reason=reason)
                if args.replay_run:
                    saved = next(item for item in replay_report['markets'][market]['series'] if item['name'] == name)
                    if saved['status'] == 'OBSERVED':
                        source_path = args.replay_run/market/f'source_{name}.csv'
                        assert_hash(source_path, saved['sha256'])
                        frame = pd.read_csv(source_path, index_col=0, parse_dates=True)
                        info = dict(saved)
                        collected[name] = frame
                    else:
                        failed = True
                        info = dict(saved)
                if frame is not None:
                    latest = validate_series(frame, name, positive=name in ['SPY','VIX','KOSPI200','VKOSPI'], allow_missing=True, today=due)
                    info['observationDate'] = latest
                    frame.to_csv(stage/f'source_{name}.csv')
                    info['sha256'] = digest(stage/f'source_{name}.csv')
                result['series'].append(info)
            # Never mix a partial refresh with cache and label it a new current run.
            if use_provider and not failed:
                frames = collected
                if market == 'us':
                    joined = pd.concat(list(frames.values()), axis=1, sort=True).sort_index()
                    joined['BAA_Treasury_Spread'] = joined.DBAA - joined.DGS10
                    anchored, result['providerRevision'] = anchor_us_history(seed, joined)
                    frames = {c: anchored[[c]] for c in US_CHANNELS}
            raw = pd.concat(list(frames.values()), axis=1, sort=True).sort_index()
            equity_name = 'SPY' if market == 'us' else 'KOSPI200'
            if use_provider and not failed:
                start = base[equity_name].index.max() + pd.Timedelta(days=1)
                end = raw[equity_name].dropna().index.max()
                if start <= end:
                    required = calendar(market, pd.Timestamp(due).year).sessions_in_range(start, end)
                    if not required.isin(raw[equity_name].dropna().index).all():
                        raise ValueError('Missing equity session inside provider history; feature windows rejected')
            raw.index.name = 'Date'
            channels = ['SPY','VIX','BAA_Treasury_Spread'] if market == 'us' else names
            result['availability'] = [{'date': day.strftime('%Y-%m-%d'),
                'available': [c for c in channels if pd.notna(row[c])],
                'missing': [c for c in channels if pd.isna(row[c])],
                'values': {c: float(row[c]) if pd.notna(row[c]) else None for c in channels}} for day, row in raw.reindex(raw.index.union(pd.DatetimeIndex([pd.Timestamp(due)]))).tail(60).iterrows()]
            result['availabilityOrigin'] = 'provider-refresh' if use_provider and not failed else 'legacy-cache'
            # Keep the complete original history for original rolling/threshold semantics.
            if market == 'us':
                raw.to_csv(stage/'raw_market_data.csv')
            else:
                equity = raw.loc[raw.KOSPI200.notna()]
                if equity[channels].isna().any().any():
                    raise ValueError('Missing Korea equity-date channel; no imputation')
                raw = equity.copy()
                raw['Korea_Credit_Spread'] = raw.Korea_Corporate_AAminus_3Y - raw.Korea_Treasury_3Y
                raw['Korea_Credit_Spread_bp'] = raw.Korea_Credit_Spread * 100
                raw[['KOSPI200']].rename(columns={'KOSPI200':'Close'}).assign(Index='KOSPI200').to_csv(stage/'krx_indices.csv')
                raw[['VKOSPI']].rename(columns={'VKOSPI':'Close'}).to_csv(stage/'vkospi.csv')
                raw[['Korea_Treasury_3Y','Korea_Corporate_AAminus_3Y','Korea_Credit_Spread','Korea_Credit_Spread_bp']].to_csv(stage/'ecos_credit.csv')
            with (stage/'calculation.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                features, official = calculate(market, stage, original, contract)
            result['history'] = infer_history(market, stage, original, config, features, official, raw, channels, due,
                                               use_provider and not failed, base[channels[0]].index.max())
            result['historicalParity'] = True
            result['inferenceSucceeded'] = bool(result['history'])
            result['inferenceAt'] = datetime.now(timezone.utc).isoformat()
            result['lastValid'] = result['history'][-1] if result['history'] else None
            if use_provider and not failed and result['lastValid'] and result['lastValid']['date'] == due:
                result.update(status='CURRENT', current=result['lastValid'], reason=None)
            else:
                result.update(status='DELAYED' if result['lastValid'] else 'UNAVAILABLE', reason='최신 필수 원천 관측 미확인. 과거 재현 추론을 현재 점수로 이월하지 않습니다.' if not failed else '일부 원천 수집 실패. 과거 캐시 재현 결과만 별도 표시합니다.')
        except Exception as error:
            # Only controlled gate descriptions may enter the public export.
            reason = f'검증 또는 계산 실패 ({type(error).__name__})'
            if isinstance(error, ValueError) and str(error).startswith('Historical reproduction mismatch: '):
                reason = '재수집한 과거 자료가 기존 연구 feature와 불일치: ' + str(error).split(': ',1)[1] + '. 신규 점수 발행 보류.'
            result.update(status='BLOCKED', current=None, reason=reason, history=[], lastValid=None, inferenceSucceeded=False)
            (stage/'failure.txt').write_text(reason)
            if market == 'us':
                try:
                    fallback = stage/'cache-reproduction'
                    fallback.mkdir()
                    cached = pd.concat(list(base.values()), axis=1, sort=True).sort_index()
                    cached.index.name = 'Date'
                    cached.to_csv(fallback/'raw_market_data.csv')
                    with (fallback/'calculation.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                        f, o = calculate(market, fallback, original, contract)
                    result['history'] = infer_history(market, fallback, original, config, f, o, cached, channels, due)
                    result['lastValid'] = result['history'][-1] if result['history'] else None
                    result['inferenceSucceeded'] = bool(result['history'])
                    result['inferenceAt'] = datetime.now(timezone.utc).isoformat()
                    result['historicalParity'] = True
                except Exception as fallback_error:
                    (stage/'cache-failure.txt').write_text(type(fallback_error).__name__)

        finally:
            write_json(stage/'receipts.json', receipts)
            write_json(stage/'result.json', result)
    # Detect source mutation during the run before publishing the one atomic JSON.
    for relative, sha in contract['original_sources'].items():
        assert_hash(original/relative, sha)
    for relative, sha in contract['local_sources'].items():
        assert_hash(ROOT/relative, sha)
    write_json(run/'report.json', report)
    write_json(ROOT/'frontend/public/data/operational-markets.json', public_summary(report))
    print(json.dumps({'runId': run_id, 'markets': {k: {'status': v['status'], 'inferenceSucceeded': v['inferenceSucceeded'], 'lastValid': v['lastValid']['date'] if v['lastValid'] else None} for k,v in report['markets'].items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
