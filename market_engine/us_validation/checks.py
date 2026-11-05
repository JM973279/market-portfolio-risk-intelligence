"""Explicit unchanged tolerances; no interpolation, automatic approval or scoring."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

ATOL = RTOL = 1e-9


def comparisons(new: pd.DataFrame, old: pd.DataFrame, columns: list[str]) -> dict:
    if new.index.has_duplicates or old.index.has_duplicates:
        raise ValueError('DUPLICATE_COMPARISON_DATE')
    result = {}
    for column in columns:
        reference = old[column].dropna()
        aligned = new[column].reindex(reference.index)
        finite = np.isfinite(aligned.to_numpy(dtype=float))
        close = np.isclose(aligned, reference, rtol=RTOL, atol=ATOL)
        bad = reference.index[~close]
        delta = (aligned-reference).abs()
        valid_delta = delta[np.isfinite(delta)]
        result[column] = {'reference_rows': len(reference), 'missing_or_nonfinite': int((~finite).sum()),
                          'mismatches': int((~close).sum()),
                          'max_abs_delta': float(valid_delta.max()) if len(valid_delta) else None,
                          'first_changed': str(bad.min().date()) if len(bad) else None,
                          'last_changed': str(bad.max().date()) if len(bad) else None,
                          'passed': bool(len(reference) and close.all())}
    return result


def source_changes(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    """Distinguish absent dates, late arrivals, removed/missing data and revisions."""
    if old.index.has_duplicates or new.index.has_duplicates:
        return {'comparable': False, 'reason': 'DUPLICATE_DATES'}
    changes = []
    for day in old.index.union(new.index).sort_values():
        a = old.loc[day, 'value'] if day in old.index else None
        b = new.loc[day, 'value'] if day in new.index else None
        av, bv = pd.notna(a), pd.notna(b)
        if day not in old.index:
            kind = 'NEW_OBSERVATION' if bv else 'NEW_MISSING_ROW'
        elif day not in new.index:
            kind = 'REMOVED_OBSERVATION' if av else 'REMOVED_MISSING_ROW'
        elif not av and bv:
            kind = 'FILLED_MISSING_OBSERVATION'
        elif av and not bv:
            kind = 'BECAME_MISSING'
        elif av and bv and a != b:
            kind = 'REVISED_OBSERVATION'
        else:
            continue
        changes.append({'date': day.strftime('%Y-%m-%d'), 'kind': kind,
                        'old': float(a) if av else None, 'new': float(b) if bv else None,
                        'exceeds_frozen_tolerance': bool(av and bv and not np.isclose(a,b,rtol=RTOL,atol=ATOL))})
    counts = {kind: sum(c['kind'] == kind for c in changes) for kind in sorted({c['kind'] for c in changes})}
    return {'comparable': True, 'counts': counts, 'changes': changes}


def due_session(as_of: str) -> tuple[str, str]:
    import exchange_calendars as xcals
    now = datetime.fromisoformat(as_of)
    if now.tzinfo is None:
        raise ValueError('Timezone-aware collection time required')
    now = now.astimezone(timezone.utc)
    cal = xcals.get_calendar('XNYS', start=f'{now.year-2}-01-01', end=f'{now.year+1}-12-31')
    ready = cal.schedule[cal.schedule.close + timedelta(hours=12) <= pd.Timestamp(now)]
    if ready.empty:
        raise ValueError('No due session')
    return ready.index[-1].strftime('%Y-%m-%d'), (ready.close.iloc[-1]+timedelta(hours=12)).isoformat()


def validate_sources(manifest: dict, frames: dict, baseline_end: str) -> dict:
    import exchange_calendars as xcals
    from pandas.tseries.holiday import USFederalHolidayCalendar
    due, deadline = due_session(manifest['completed_at'])
    issues, warnings = [], []
    start, end = manifest['interval']['start'], manifest['interval']['end']
    if set(frames) != {'SPY','VIX','DBAA','DGS10'}:
        return {'passed': False, 'structural_passed': False, 'issues': [{'code': 'COLLECTION_INCOMPLETE'}], 'due_date': due, 'deadline': deadline}
    cal = xcals.get_calendar('XNYS', start=f'{pd.Timestamp(start).year-1}-01-01',
                             end=f'{max(pd.Timestamp(end).year,pd.Timestamp(due).year)+1}-12-31')
    sessions = cal.sessions_in_range(start, min(end, due))
    closed = cal.schedule[cal.schedule.close <= pd.Timestamp(manifest['completed_at'])].index[-1]
    federal = USFederalHolidayCalendar().holidays(start=start, end=max(end, due))
    sources = {}
    for name, frame in frames.items():
        values = frame.value.to_numpy(dtype=float)
        dates = frame.index
        if dates.has_duplicates: issues.append({'code': 'DUPLICATE_DATES', 'source': name})
        if not dates.is_monotonic_increasing: issues.append({'code': 'UNSORTED_DATES', 'source': name})
        if dates.tz is not None: issues.append({'code': 'NON_SESSION_DATE_INDEX', 'source': name})
        if (dates < pd.Timestamp(start)).any() or (dates > pd.Timestamp(end)).any():
            issues.append({'code': 'OUTSIDE_REQUEST_INTERVAL', 'source': name})
        if (dates[frame.value.notna()] > closed).any():
            issues.append({'code':'UNCOMPLETED_SESSION','source':name})
        if np.isinf(values).any(): issues.append({'code': 'NONFINITE_VALUE', 'source': name})
        if name in ('SPY','VIX') and (values[np.isfinite(values)] <= 0).any():
            issues.append({'code': 'NONPOSITIVE_MARKET_LEVEL', 'source': name})
        if name in ('SPY','VIX'):
            off = dates[~dates.isin(cal.sessions_in_range(start, end))]
            if len(off):
                (issues if name == 'SPY' else warnings).append({'code': 'NON_XNYS_OBSERVATION', 'source': name,
                                                            'dates': [str(d.date()) for d in off]})
        present = dates[frame.value.notna()]
        required = sessions if name == 'SPY' else sessions[sessions > pd.Timestamp(baseline_end)]
        if name in ('DBAA','DGS10'):
            required = required[~required.isin(federal)]
        gaps = required[~required.isin(present)]
        if len(gaps): issues.append({'code': 'REQUIRED_SESSION_GAPS', 'source': name, 'dates': [str(d.date()) for d in gaps]})
        if pd.Timestamp(due) not in present:
            issues.append({'code': 'DUE_DATE_REAL_VALUE_MISSING', 'source': name, 'date': due})
        missing = dates[frame.value.isna()]
        sources[name] = {'rows': len(frame), 'latest': str(present.max().date()) if len(present) else None,
                         'missing_dates': [str(d.date()) for d in missing], 'duplicate_count': int(dates.duplicated().sum()),
                         'adjustment': manifest['sources'][name]['adjustment'],
                         'vintage': manifest['sources'][name]['vintage']}
    if manifest['sources']['SPY']['adjustment'] != 'PROVIDER_ADJ_CLOSE':
        issues.append({'code': 'ADJUSTED_PRICE_REQUIRED', 'source': 'SPY'})
    if end < due: issues.append({'code': 'REQUEST_END_BEFORE_DUE_SESSION'})
    fatal = {'DUPLICATE_DATES','UNSORTED_DATES','NON_SESSION_DATE_INDEX','OUTSIDE_REQUEST_INTERVAL',
             'NONFINITE_VALUE','UNCOMPLETED_SESSION','NONPOSITIVE_MARKET_LEVEL','ADJUSTED_PRICE_REQUIRED','NON_XNYS_OBSERVATION'}
    return {'passed': not issues, 'structural_passed': not any(i['code'] in fatal for i in issues),
            'issues': issues, 'warnings': warnings,
            'due_date': due, 'deadline': deadline, 'sources': sources,
            'note': '12h is a project policy, not a guarantee of FRED publication.'}


def independent_msi(cleaned: pd.DataFrame, quantile: float) -> pd.DataFrame:
    """Independent check of pinned official past-only distribution, not a new model."""
    stress = pd.DataFrame({'equity': -cleaned.SPY.pct_change(21), 'volatility': cleaned.VIX,
                           'credit': cleaned.BAA_Treasury_Spread}, index=cleaned.index)
    history = stress.shift(1)
    z = (stress-history.rolling(252,min_periods=126).mean()) / (history.rolling(252,min_periods=126).std(ddof=1)+1e-8)
    msi = z.mean(axis=1, skipna=False).dropna()
    # The expanding distribution begins with the original MSI's full valid history.
    threshold = msi.shift(1).expanding(min_periods=252).quantile(quantile)
    return pd.DataFrame({'MSI': msi, 'Stress_Threshold': threshold}).dropna()


def stages(collection: bool, sources: bool, inputs: bool, msi: bool, inference: bool = False) -> dict:
    return {'collection': 'PASSED' if collection else 'FAILED',
            'source_validation': 'PASSED' if sources else 'FAILED',
            'input_change_validation': 'PASSED' if inputs else ('BLOCKED' if sources else 'NOT_RUN'),
            'msi_validation': 'PASSED' if msi else ('BLOCKED' if sources else 'NOT_RUN'),
            'model_inference_validation': 'PASSED' if inference else ('READY' if inputs and msi and sources else 'BLOCKED'),
            'public_approval': 'PENDING' if inference else 'NOT_ELIGIBLE'}


def candidate_eligible(report: dict) -> bool:
    s = report['stages']
    return (all(s.get(k) == 'PASSED' for k in ('collection','source_validation','input_change_validation','msi_validation'))
            and report.get('baseline_reproduction_passed') is True
            and report.get('model_contract', {}).get('passed') is True
            and report.get('public_approved') is False)
