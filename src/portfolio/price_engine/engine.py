"""Deterministic research quality gate and connection to existing price risk math."""
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.portfolio.risk_metrics import compare_risk_metrics, risk_metrics
from .adapters import ADAPTER_VERSION, CollectedPrices, frame_sha256
from .contracts import PipelineError, QualityPolicy, TradingCalendar, Window

ENGINE_VERSION = 'research-price-engine-v1'


@dataclass
class Validation:
    report: dict
    prices: pd.DataFrame | None

    def returns(self):
        if self.prices is None or not self.report['research_ready']:
            raise PipelineError('QUALITY_GATE_FAILED', issues=self.report['issues'])
        return self.prices.pct_change(fill_method=None).iloc[1:]


def validate_prices(collection: CollectedPrices, calendars: list[TradingCalendar],
                    window: Window, policy: QualityPolicy | None = None):
    policy = policy or QualityPolicy()
    issues, columns, indexes, samples = [], {}, [], {}
    def issue(code, asset_id=None, **details):
        issues.append({'code': code, 'asset_id': asset_id, 'details': details})
    frame = collection.frame
    if frame_sha256(frame) != collection.normalized_sha256:
        issue('NORMALIZED_CONTENT_CHANGED')
    grants = {p.source_id: p for p in collection.permissions}
    for mapping in collection.mappings:
        grant = grants.get(mapping.source_id)
        if not grant or not grant.storage_allowed or not grant.processing_allowed:
            issue('RESEARCH_PERMISSION_REQUIRED', mapping.instrument.asset_id)
    calendar_map = {(c.market, c.exchange_mic): c for c in calendars}
    if len(calendar_map) != len(calendars):
        issue('DUPLICATE_CALENDAR')
    markets = {m.instrument.market for m in collection.mappings}
    currencies = {m.instrument.currency for m in collection.mappings}
    if len(markets) != 1 or len(currencies) != 1:
        issue('FX_POLICY_REQUIRED')
    if set(frame['asset_id']) - {m.instrument.asset_id for m in collection.mappings}:
        issue('UNMAPPED_ASSET')
    if frame.duplicated(['asset_id', 'date']).any():
        issue('DUPLICATE_OBSERVATION', count=int(frame.duplicated(['asset_id', 'date']).sum()))
    receipts = {c.capture_id: c.receipt for c in collection.captures}
    for mapping in collection.mappings:
        instrument = mapping.instrument
        asset_id = instrument.asset_id
        rows = frame.loc[frame['asset_id'] == asset_id].sort_values('date')
        if not instrument.identity_reference or not mapping.evidence_reference:
            issue('IDENTITY_UNVERIFIED', asset_id)
        if (window.start < max(mapping.valid_from, instrument.listed_on)
                or mapping.valid_to and window.end > mapping.valid_to
                or instrument.delisted_on and window.end >= instrument.delisted_on):
            issue('LISTING_OR_MAPPING_WINDOW_INVALID', asset_id)
        calendar = calendar_map.get((instrument.market, instrument.exchange_mic))
        if calendar is None:
            issue('CALENDAR_MISSING', asset_id)
            continue
        if not calendar.reviewed:
            issue('CALENDAR_UNREVIEWED', asset_id)
        if window.start < calendar.coverage_start or window.end > calendar.coverage_end:
            issue('CALENDAR_COVERAGE_INCOMPLETE', asset_id)
        if window.end > window.as_of.astimezone(ZoneInfo(calendar.timezone)).date():
            issue('FUTURE_WINDOW', asset_id)
        if window.mode == 'latest':
            local_day = window.as_of.astimezone(ZoneInfo(calendar.timezone)).date()
            if calendar.coverage_end < local_day:
                issue('FRESHNESS_CALENDAR_COVERAGE_INCOMPLETE', asset_id)
            current = [s.day for s in calendar.sessions if s.available_at <= window.as_of]
            if current and window.end < max(current):
                issue('STALE_REQUEST_WINDOW', asset_id, latest_available=str(max(current)))
        sessions = [s for s in calendar.sessions if window.start <= s.day <= window.end]
        available = [s for s in sessions if s.available_at <= window.as_of]
        expected = pd.DatetimeIndex([s.day for s in available])
        if len(expected) < policy.min_prices:
            issue('INSUFFICIENT_EXPECTED_SESSIONS', asset_id, count=len(expected), required=policy.min_prices)
        dates = pd.DatetimeIndex(rows['date'])
        samples[asset_id] = {
            'price_count': len(rows), 'expected_count': len(expected),
            'observed_start': str(dates.min().date()) if len(dates) else None,
            'observed_end': str(dates.max().date()) if len(dates) else None,
            'expected_start': str(expected[0].date()) if len(expected) else None,
            'expected_end': str(expected[-1].date()) if len(expected) else None,
        }
        availability = {pd.Timestamp(s.day): s.available_at for s in sessions}
        if dates.hasnans:
            issue('INVALID_OBSERVATION_DATE', asset_id)
        if len(rows) < policy.min_prices:
            issue('INSUFFICIENT_PRICES', asset_id, count=len(rows), required=policy.min_prices)
        missing = expected.difference(dates)
        unexpected = dates.difference(expected)
        if len(missing):
            issue('MISSING_SESSIONS', asset_id, dates=[str(d.date()) for d in missing])
        if len(unexpected):
            issue('NON_SESSION_OR_UNAVAILABLE_OBSERVATION', asset_id, dates=[str(d.date()) for d in unexpected])
        if len(expected) and (rows.empty or dates.max() < expected[-1]):
            issue('STALE_PRICES', asset_id, expected_last=str(expected[-1].date()))
        if not (rows['currency'] == instrument.currency).all():
            issue('CURRENCY_MISMATCH', asset_id)
        if not (rows['source_id'] == mapping.source_id).all() or not (rows['provider_symbol'] == mapping.provider_symbol).all():
            issue('SOURCE_MAPPING_MISMATCH', asset_id)
        for digest in rows['capture_id'].unique():
            receipt = receipts.get(digest)
            if receipt is None:
                issue('SOURCE_RECEIPT_MISSING', asset_id)
                continue
            if receipt.adjustment != 'total_return' or not receipt.adjustment_reference:
                issue('TOTAL_RETURN_ADJUSTMENT_UNVERIFIED', asset_id)
            if not receipt.corporate_actions_reference:
                issue('CORPORATE_ACTIONS_UNVERIFIED', asset_id)
            if receipt.retrieved_at > window.as_of:
                issue('FUTURE_RETRIEVAL', asset_id)
            observed = rows.loc[rows['capture_id'] == digest]
            # Publication timestamp describes this capture, not every historical bar.
            if not (observed['retrieved_at'] == pd.Timestamp(receipt.retrieved_at)).all():
                issue('RETRIEVAL_PROVENANCE_MISMATCH', asset_id)
            if any(receipt.retrieved_at < availability[day] for day in observed['date'] if day in availability):
                issue('OBSERVATION_NOT_YET_AVAILABLE_AT_RETRIEVAL', asset_id)
        for column in ('close', 'adjusted_close'):
            values = rows[column].to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values <= 0).any():
                issue('INVALID_PRICE', asset_id, column=column)
        adjusted = rows['adjusted_close'].to_numpy(dtype=float)
        if len(adjusted) > 1 and np.isfinite(adjusted).all() and (adjusted > 0).all():
            with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
                moves = adjusted[1:] / adjusted[:-1] - 1
            if not np.isfinite(moves).all() or (np.abs(moves) > policy.max_abs_return).any():
                issue('EXTREME_ADJUSTED_MOVE_REQUIRES_REVIEW', asset_id)
        if dates.is_unique:
            columns[asset_id] = pd.Series(adjusted, index=dates)
            indexes.append(expected)
    if indexes and any(not index.equals(indexes[0]) for index in indexes[1:]):
        issue('UNALIGNED_MARKET_SESSIONS')
    prices = pd.DataFrame(columns) if not issues and columns else None
    report = {
        'engine_version': ENGINE_VERSION, 'adapter_version': ADAPTER_VERSION,
        'scope': 'research_only', 'public_analysis_allowed': False, 'selectable': False,
        'public_blockers': ['NO_PUBLIC_RIGHTS_APPROVAL', 'NO_APPROVED_METHODOLOGY_RELEASE'],
        'research_ready': prices is not None, 'issues': issues,
        'window': window.model_dump(mode='json'), 'policy': policy.model_dump(mode='json'),
        'market': next(iter(markets)) if len(markets) == 1 else None,
        'currency': next(iter(currencies)) if len(currencies) == 1 else None,
        'asset_ids': sorted(m.instrument.asset_id for m in collection.mappings),
        'observations': len(prices) if prices is not None else 0, 'samples': samples,
        'normalized_sha256': collection.normalized_sha256,
        'payload_sha256': sorted({c.sha256 for c in collection.captures}),
        'calendar_versions': {c.calendar_id: c.version for c in calendars},
        'freshness_scope': window.mode,
        'imputation': 'none', 'price_basis': 'reviewed_total_return_adjusted_close',
    }
    return Validation(report, prices)


def analyze_research(collection, calendars, window, weights, *, proposed=None, policy=None, confidence=.95):
    """Weights use stable asset IDs. Each call reruns validation; no cached approval."""
    validation = validate_prices(collection, calendars, window, policy)
    returns = validation.returns()
    result = (risk_metrics(returns, weights, confidence=confidence) if proposed is None else
              compare_risk_metrics(returns, weights, proposed, confidence=confidence))
    return {'scope': 'research_only', 'public_analysis_allowed': False,
            'validation': validation.report, 'metrics': result}
