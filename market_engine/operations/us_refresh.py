"""Refresh US observations and frozen-model inference with an explicit source vintage.

Frozen-cache reproduction remains an exact gate. Provider revisions are recorded
as a separate operational vintage; they never replace research inputs or OOS.
"""
import argparse
import contextlib
import copy
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from market_engine.operations.run import (
    ROOT, assert_hash, calculate, digest, eligible_dates, infer_history,
    public_summary, verify_model, write_json,
)

POLICY = 'us-full-source-vintage-v1'
CHANNELS = ['SPY', 'VIX', 'BAA_Treasury_Spread']
SOURCES = ['SPY', 'VIX', 'DBAA', 'DGS10']


def verify_contract(original, contract):
    for relative, expected in contract['original_sources'].items():
        assert_hash(original / relative, expected)
    for relative, expected in contract['local_sources'].items():
        assert_hash(ROOT / relative, expected)
    config = contract['markets']['us']
    for name in ['reference', 'model']:
        assert_hash(original / config[name], config[name + '_sha256'])


def revision_audit(features, official, reference, columns):
    """Describe revisions without silently changing an equality tolerance."""
    audit = {}
    for frame, names in [(features, columns), (official, ['MSI', 'Stress_Threshold'])]:
        if frame.index.duplicated().any() or reference.index.duplicated().any():
            raise ValueError('Duplicate revision-audit date')
        for name in names:
            old = reference[name].dropna()
            if old.empty or not old.index.isin(frame.index).all():
                raise ValueError('Reference coverage missing from provider vintage')
            new = frame.loc[old.index, name].to_numpy(dtype=float)
            if not np.isfinite(new).all():
                raise ValueError('Nonfinite revision-audit value')
            delta = np.abs(new - old.to_numpy(dtype=float))
            audit[name] = {'compared': len(old), 'changed': int((delta > 1e-9).sum()),
                           'maxAbsoluteChange': float(delta.max())}
    return audit


def operational_history(original, config, features, official, raw, due, seed_end):
    """Use exact-date source observations, fixed preprocessing and fixed model."""
    import joblib
    from src.operations.calendar import calendar

    model_path = original / config['model']
    assert_hash(model_path, config['model_sha256'])
    model = joblib.load(model_path)
    columns = config['features']
    verify_model(model, columns)
    cutoff = max(pd.Timestamp(config['training_cutoff']), pd.Timestamp(seed_end))
    dates = eligible_dates(features[columns], raw, CHANNELS, cutoff)
    dates = dates[dates <= pd.Timestamp(due)]
    dates = dates.intersection(official.dropna(subset=['MSI', 'Stress_Threshold']).index)
    if len(dates):
        dates = dates.intersection(calendar('us', pd.Timestamp(due).year).sessions_in_range(dates.min(), dates.max()))
    predictions = model.predict_proba(features.loc[dates, columns]) if len(dates) else np.empty((0, 2))
    if (predictions.shape != (len(dates), 2) or not np.isfinite(predictions).all()
            or (predictions < 0).any() or (predictions > 1).any()
            or not np.allclose(predictions.sum(axis=1), 1)):
        raise ValueError('Invalid frozen-model output')
    history = [
        {'date': day.strftime('%Y-%m-%d'), 'price': float(raw.loc[day, 'SPY']),
         'risk': float(probability), 'msi': float(official.loc[day, 'MSI']),
         'threshold': float(official.loc[day, 'Stress_Threshold']), 'recordType': 'OPERATIONAL'}
        for day, probability in zip(dates, predictions[:, 1])
    ]
    assert_hash(model_path, config['model_sha256'])
    return history


def merge_export(previous, market, generated_at, publish_prices=False):
    """Replace US atomically while retaining Korea's original collection timestamp."""
    result = copy.deepcopy(previous)
    previous_time = result.get('generatedAt')
    for name, existing in result['markets'].items():
        if name != 'us':
            existing.setdefault('generatedAt', previous_time)
    result['generatedAt'] = generated_at
    result['markets']['us'] = market
    result = public_summary(result)
    result['sourceValuesIncluded'] = publish_prices
    if publish_prices:
        # Only the explicitly requested SPY price chart is public, never FRED yields.
        result['markets']['us']['priceHistory'] = market['priceHistory']
        for point in result['markets']['us']['history']:
            point['price'] = next((p['price'] for p in market['history'] if p['date'] == point['date']), None)
        for name in ['current', 'lastValid']:
            if result['markets']['us'].get(name):
                result['markets']['us'][name]['price'] = market[name]['price']
    else:
        result['markets']['us'].pop('priceHistory', None)
    return result


def refresh(original, output, publish_prices=False, replay=None):
    contract = json.loads((ROOT / 'market_engine/operations/contract.json').read_text())
    original = original.resolve()
    verify_contract(original, contract)
    sys.path.insert(0, str(original))
    from src.operations.calendar import expected, latest_closed, calendar
    from src.operations.providers import Providers, PROVIDERS
    from src.operations.validation import validate_series

    config = contract['markets']['us']
    generated_at = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    run = ROOT / 'data/operations' / run_id
    run.mkdir(parents=True)
    due, deadline = expected('us')
    through = max(due, latest_closed('us'))
    replay_meta = None
    if replay:
        replay = replay.resolve()
        if not replay.is_relative_to(ROOT / 'data/operations'):
            raise ValueError('Replay requires a retained local run')
        replay_meta = json.loads((replay / 'us-refresh.json').read_text())
        if replay_meta['policy'] != POLICY:
            raise ValueError('Replay policy mismatch')
        for name in ['model', 'reference']:
            if replay_meta[name + 'Sha256'] != config[name + '_sha256']:
                raise ValueError('Replay artifact mismatch')
        due, deadline = replay_meta['due'], replay_meta['deadline']
        through = replay_meta.get('observedThrough', due)

    seed = pd.read_csv(original / 'data/raw/raw_market_data.csv', index_col='Date', parse_dates=True)
    baseline = run / 'baseline'
    baseline.mkdir()
    seed.to_csv(baseline / 'raw_market_data.csv')
    # This is the unchanged strict reference gate, on its own frozen input.
    with (baseline / 'calculation.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        baseline_features, baseline_official = calculate('us', baseline, original, contract)
        baseline_history = infer_history('us', baseline, original, config, baseline_features,
                                         baseline_official, seed, CHANNELS, due)

    receipts = []

    class RecordedProviders(Providers):
        def call(self, series, fetch):
            for attempt in range(1, 4):
                receipt = {'series': series, 'attempt': attempt, 'startedAt': datetime.now(timezone.utc).isoformat()}
                try:
                    value = fetch()
                    receipt.update(status='SUCCESS', retrievedAt=datetime.now(timezone.utc).isoformat())
                    receipts.append(receipt)
                    return value, receipt['retrievedAt']
                except Exception as error:
                    receipt.update(status='ERROR', errorType=type(error).__name__)
                    receipts.append(receipt)
                    if attempt == 3:
                        raise
                    time.sleep(attempt)

    providers = RecordedProviders(run_id)
    import yfinance as yf
    yf.set_tz_cache_location(str(run / 'yahoo-cache'))
    frames, series, failures = {}, [], []
    for name in SOURCES:
        info = {'name': name, 'provider': PROVIDERS[name], 'status': 'ERROR',
                'observationDate': None, 'retrievedAt': None, 'reason': None}
        try:
            if replay:
                info = copy.deepcopy(next(s for s in replay_meta['series'] if s['name'] == name))
                path = replay / ('source_' + name + '.csv')
                assert_hash(path, info['sha256'])
                frame = pd.read_csv(path, index_col=0, parse_dates=True, float_precision='round_trip')
                retrieved = info['retrievedAt']
            else:
                frame, retrieved = providers.yahoo(name, through) if name in ['SPY', 'VIX'] else providers.fred(name, through)
            latest = validate_series(frame, name, positive=name in ['SPY', 'VIX'], allow_missing=True, today=through)
            path = run / ('source_' + name + '.csv')
            frame.to_csv(path)
            frames[name] = frame
            info.update(status='OBSERVED', retrievedAt=retrieved, observationDate=latest,
                        sha256=digest(path), reason=None)
        except Exception as error:
            failures.append(name)
            info['reason'] = '수집 또는 원천 검증 실패 (' + type(error).__name__ + ')'
        series.append(info)

    market = {'status': 'BLOCKED', 'expectedDate': due, 'publicationDeadline': deadline,
              'generatedAt': generated_at, 'inferenceAt': None, 'current': None,
              'history': baseline_history, 'lastValid': baseline_history[-1] if baseline_history else None,
              'reason': None, 'series': series, 'availabilityOrigin': 'provider-refresh',
              'availability': [], 'inferenceSucceeded': False, 'baselineParity': True,
              'modelSha256': config['model_sha256'], 'trainingCutoff': config['training_cutoff'],
              'trainingEvidence': config['training_evidence'], 'featureOrder': config['features'],
              'priceBasis': 'SPY dividend/split-adjusted close (USD)',
              'priceHistory': [], 'dataPolicy': POLICY,
              'policyNote': '동결 캐시 재현 검증과 별도로 전체 제공처 수정본을 계산한 운영 추론입니다. 과거 OOS 성능을 재검증한 결과가 아닙니다.'}
    if 'SPY' in frames:
        price = frames['SPY']['SPY'].dropna().tail(504)
        market['priceHistory'] = [{'date': day.strftime('%Y-%m-%d'), 'price': float(value)} for day, value in price.items()]
    try:
        if failures:
            raise ValueError('Required provider source unavailable')
        raw = pd.concat(list(frames.values()), axis=1, sort=True).sort_index()
        raw['BAA_Treasury_Spread'] = raw.DBAA - raw.DGS10
        raw.index.name = 'Date'
        seed_end = seed.SPY.dropna().index.max()
        latest_price = raw.SPY.dropna().index.max()
        if latest_price > seed_end:
            required = calendar('us', pd.Timestamp(due).year).sessions_in_range(seed_end + pd.Timedelta(days=1), latest_price)
            if not required.isin(raw.SPY.dropna().index).all():
                raise ValueError('Missing SPY trading session; rolling windows rejected')
        raw[CHANNELS].to_csv(run / 'raw_market_data.csv')
        with (run / 'calculation.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            features, official = calculate('us', run, original, contract)
            reference = pd.read_csv(original / config['reference'], index_col='Date', parse_dates=True)
            market['revisionAudit'] = revision_audit(features, official, reference, config['features'])
            history = operational_history(original, config, features, official, raw, due, seed_end)
        market['history'] = history
        market['lastValid'] = history[-1] if history else None
        market['inferenceSucceeded'] = bool(history)
        market['inferenceAt'] = generated_at
        market['historicalParity'] = not any(row['changed'] for row in market['revisionAudit'].values())
        if history and history[-1]['date'] == due:
            market.update(status='CURRENT', current=history[-1])
        else:
            market.update(status='DELAYED', reason='필수 원천이 모두 관측된 날짜까지만 추론했습니다. 최신 검증 관측일과 수집 기준일을 구분합니다.')
        market['availability'] = [{'date': day.strftime('%Y-%m-%d'),
                                  'available': [c for c in CHANNELS if pd.notna(row[c])],
                                  'missing': [c for c in CHANNELS if pd.isna(row[c])]} for day, row in raw[CHANNELS].tail(60).iterrows()]
    except Exception as error:
        market['reason'] = '미국 운영 추론 검증 실패 (' + type(error).__name__ + '). 원천 가격과 추론 상태를 구분합니다.'
        write_json(run / 'failure.json', {'errorType': type(error).__name__, 'failedSources': failures})

    verify_contract(original, contract)
    metadata = {'policy': POLICY, 'runId': run_id, 'due': due, 'deadline': deadline, 'observedThrough': through,
                'series': series, 'receipts': receipts, 'modelSha256': config['model_sha256'],
                'referenceSha256': config['reference_sha256']}
    write_json(run / 'us-refresh.json', metadata)
    write_json(run / 'result.json', market)
    previous = json.loads(output.read_text())
    shared = merge_export(previous, market, generated_at, publish_prices)
    shared['runId'] = run_id
    write_json(output, shared)
    return run, market


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-v1-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'frontend/public/data/operational-markets.json')
    parser.add_argument('--publish-prices', action='store_true', help='Include the requested SPY chart; yields remain private.')
    parser.add_argument('--replay-run', type=Path)
    args = parser.parse_args()
    run, market = refresh(args.original_v1_root, args.output, args.publish_prices, args.replay_run)
    print(json.dumps({'run': str(run), 'status': market['status'], 'expectedDate': market['expectedDate'],
                      'lastValid': (market['lastValid'] or {}).get('date'),
                      'priceDate': market['priceHistory'][-1]['date'] if market['priceHistory'] else None}, ensure_ascii=False))
    if market['status'] == 'BLOCKED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
