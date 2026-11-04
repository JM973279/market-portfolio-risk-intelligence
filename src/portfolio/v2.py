"""Isolated US V2 bundle preparation and analysis; no collector or V1 mutations.

Research bundles can be analyzed offline, but are never served by the public API.
Public activation requires a separately reviewed manifest hash and source rights ledger.
"""
from functools import lru_cache
import json
import io
from pathlib import Path
import re

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

from src.portfolio.analytics import analyze_portfolio
from src.portfolio.expansion import sha256, verify_release, write_release
from src.portfolio.factors import FACTORS, estimate_betas, portfolio_exposure
from src.portfolio.stress import compute_stress
from src.portfolio.whatif import compare_analyses

ROOT = Path(__file__).resolve().parents[2] / 'data/portfolio_v2'
REGISTRY_PATH = ROOT / 'registry.json'
RELEASES_PATH = ROOT / 'releases'
REQUIRED_RIGHTS = {'prices', 'corporate_actions', 'market_factor', 'rate_factor', 'volatility_factor', 'scenarios'}
REQUIRED_FILES = {'returns.npy', 'factor_moves.npy', 'universe.json', 'betas.npy', 'layout.json', 'scenarios.json', 'validation.json', 'provenance.json'}
SNAPSHOT_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$'


class V2Holding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ticker: str = Field(min_length=1)
    weight: float = Field(gt=0, le=100, allow_inf_nan=False)


class V2Request(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: str = Field(pattern=SNAPSHOT_PATTERN)
    market: Literal['US']
    base_currency: Literal['USD']
    holdings: list[V2Holding] = Field(min_length=1, max_length=10)
    value_amount: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def coherent(self):
        tickers = [h.ticker for h in self.holdings]
        if len(set(tickers)) != len(tickers):
            raise ValueError('Duplicate holding')
        if abs(sum(h.weight for h in self.holdings) - 100) > .01:
            raise ValueError('Weights must sum to 100 percent')
        return self


class V2CompareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current: V2Request
    proposed: V2Request

    @model_validator(mode='after')
    def same_context(self):
        for field in ('snapshot_id', 'market', 'base_currency', 'value_amount'):
            if getattr(self.current, field) != getattr(self.proposed, field):
                raise ValueError(f'Comparison requires identical {field}')
        return self


class V2Unavailable(ValueError):
    pass


def require_rights(provenance, ledger, tickers):
    """Each dependency needs evidence covering storage, derived output and artifacts.

    This function checks reviewed records, not the legal sufficiency of a provider's
    license. Empty or unreviewed ledgers never confer rights.
    """
    dependencies = provenance.get('dependencies', {})
    if set(dependencies) != REQUIRED_RIGHTS:
        raise V2Unavailable('SOURCE_RIGHTS_INCOMPLETE')
    required = {'prices':set(tickers), 'corporate_actions':set(tickers),
                'market_factor':{'SPY'}, 'rate_factor':{'DGS10'}, 'volatility_factor':{'VIX'},
                'scenarios':{'equity_selloff', 'rate_shock', 'volatility_shock'}}
    for category, approval_ids in dependencies.items():
        covered = set()
        if not isinstance(approval_ids, list) or not approval_ids:
            raise V2Unavailable('SOURCE_RIGHTS_INCOMPLETE')
        for approval_id in approval_ids:
            approval = ledger.get(approval_id, {})
            if (approval.get('status') != 'approved'
                    or category not in approval.get('categories', [])
                    or not approval.get('evidence_reference')
                    or not approval.get('reviewed_at')
                    or not approval.get('source_id')
                    or not all(approval.get(field) is True for field in
                               ('storage_allowed', 'public_derived_allowed', 'artifact_distribution_allowed'))):
                raise V2Unavailable('RIGHTS_UNCONFIRMED')
            covered.update(approval.get('subjects', []))
        if not required[category] <= covered:
            raise V2Unavailable('LICENSE_SUBJECTS_INCOMPLETE')


def validate_inputs(prices, sessions, factor_moves, universe, exclusions):
    """Exact 757 sessions and explicit factor exclusion evidence, never ffill.

    Calendar/identity/actions must be independently reviewed; this numerical gate
    does not turn a business-day calendar or a receipt flag into such evidence.
    """
    sessions = pd.DatetimeIndex(sessions)
    if (len(sessions) != 757 or sessions.hasnans or not sessions.is_unique
            or not sessions.is_monotonic_increasing or not prices.index.equals(sessions)):
        raise V2Unavailable('INVALID_PRICE_CALENDAR')
    if (not prices.columns.is_unique or prices.empty or not np.isfinite(prices.to_numpy(dtype=float)).all()
            or not (prices > 0).all().all()):
        raise V2Unavailable('INVALID_PRICES')
    if (not universe.index.is_unique or set(universe.index) != set(prices.columns)
            or not {'name', 'sector', 'type', 'asset_class'} <= set(universe.columns)
            or universe.isna().any().any()):
        raise V2Unavailable('INVALID_ASSET_IDENTITY')
    returns = prices.pct_change(fill_method=None).iloc[1:]
    if not np.isfinite(returns.to_numpy()).all() or (returns.abs() > .5).any().any():
        raise V2Unavailable('PRICE_MOVE_REQUIRES_REVIEW')
    if any(float(returns[t].var()) <= 0 for t in returns):
        raise V2Unavailable('ZERO_ASSET_VARIANCE')
    if (not factor_moves.index.equals(sessions[1:]) or not factor_moves.columns.is_unique
            or set(factor_moves.columns) != set(FACTORS) or set(exclusions) - set(FACTORS)):
        raise V2Unavailable('INVALID_FACTOR_CALENDAR')
    counts = {}
    for factor in FACTORS:
        column = factor_moves[factor]
        evidence = exclusions.get(factor, [])
        allowed = set()
        for record in evidence:
            if not record.get('reason') or not str(record.get('reference', '')).startswith('https://'):
                raise V2Unavailable('EXCLUSION_EVIDENCE_MISSING')
            day = pd.Timestamp(record['date'])
            if day in allowed or day not in sessions[1:]:
                raise V2Unavailable('INVALID_EXCLUSION_DATE')
            allowed.add(day)
        missing = set(column.index[column.isna()])
        if missing != allowed:
            raise V2Unavailable('UNEXPLAINED_FACTOR_MISSINGNESS')
        values = column.dropna().to_numpy(dtype=float)
        if len(values) <= 2 or not np.isfinite(values).all() or not np.isfinite(np.var(values)) or np.var(values) <= 0:
            raise V2Unavailable('INVALID_FACTOR_SAMPLE')
        counts[factor] = len(values)
    return returns, {'support_status':'full', 'required_returns':756, 'factor_pair_counts':counts,
                     'window_start':str(sessions[1].date()), 'window_end':str(sessions[-1].date()),
                     'exclusions':exclusions}


def build_bundle(root, snapshot_id, prices, sessions, factor_moves, universe, scenarios,
                 provenance, exclusions, metadata, *, scope='research_only', ledger=None):
    """Offline export only. Unapproved material stays in gitignored research roots."""
    if scope not in {'research_only', 'public_approved'}:
        raise V2Unavailable('INVALID_SCOPE')
    if scope == 'public_approved':
        require_rights(provenance, ledger or {}, prices.columns)
        required_reviews = ('calendar', 'identity', 'corporate_actions', 'precision', 'revisions', 'factor_policy', 'scenarios')
        reviews = provenance.get('reviews', {})
        if any(reviews.get(key, {}).get('approved') is not True or not reviews[key].get('reference') for key in required_reviews):
            raise V2Unavailable('DATA_REVIEW_INCOMPLETE')
    elif Path(root).resolve() == RELEASES_PATH.resolve() or RELEASES_PATH.resolve() in Path(root).resolve().parents:
        raise V2Unavailable('RESEARCH_CANNOT_ENTER_PUBLIC_RELEASES')
    if metadata['market'] != 'US' or metadata['base_currency'] != 'USD':
        raise V2Unavailable('UNSUPPORTED_MARKET_OR_CURRENCY')
    returns, validation = validate_inputs(prices, sessions, factor_moves, universe, exclusions)
    if metadata['snapshot_as_of'] != validation['window_end']:
        raise V2Unavailable('SNAPSHOT_DATE_MISMATCH')
    if set(scenarios) != {'equity_selloff', 'rate_shock', 'volatility_shock'}:
        raise V2Unavailable('SCENARIOS_INCOMPLETE')
    expected = {'equity_selloff':('market', 'return'), 'rate_shock':('rate','bp'), 'volatility_shock':('volatility','pt')}
    for key, scenario in scenarios.items():
        if scenario.get('id') != key or (scenario.get('factor'),scenario.get('unit')) != expected[key] or not np.isfinite(scenario['shock']):
            raise V2Unavailable('INVALID_SCENARIO')
        if pd.Timestamp(scenario['reference']['end']) > pd.Timestamp(metadata['snapshot_as_of']):
            raise V2Unavailable('FUTURE_SCENARIO_REFERENCE')
    betas = estimate_betas(returns, factor_moves)
    numerical = [f'{factor}{suffix}' for factor in FACTORS for suffix in ('', '_r2', '_n')]
    if not np.isfinite(betas[numerical].to_numpy()).all():
        raise V2Unavailable('NONFINITE_REGRESSION')
    provenance = {**provenance, 'scope':scope}
    metadata = {**metadata, 'approval_status':'reviewed' if scope == 'public_approved' else 'quarantined'}
    validation['scope'] = scope
    encode = lambda value: (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n').encode()
    def array_bytes(frame):
        buffer = io.BytesIO()
        np.save(buffer, frame.to_numpy(dtype=float), allow_pickle=False)
        return buffer.getvalue()
    layout = {'dates':[str(day.date()) for day in returns.index],
              'tickers':list(returns.columns), 'factors':list(factor_moves.columns),
              'beta_tickers':list(betas.index), 'beta_columns':list(betas.columns)}
    artifacts = {'returns.npy':array_bytes(returns),
                 'factor_moves.npy':array_bytes(factor_moves),
                 'betas.npy':array_bytes(betas), 'layout.json':encode(layout),
                 'universe.json':encode(universe.reset_index(names='ticker').to_dict(orient='records')),
                 'scenarios.json':encode([scenarios[key] for key in expected]),
                 'provenance.json':encode(provenance), 'validation.json':encode(validation)}
    return write_release(root, snapshot_id, artifacts, metadata)


class Bundle:
    def __init__(self, path, manifest, *, public=False):
        self.manifest = manifest
        self.metadata = manifest['metadata']
        if set(manifest['sha256']) != REQUIRED_FILES:
            raise V2Unavailable('BUNDLE_FILES_INCOMPLETE')
        self.provenance = json.loads((path/'provenance.json').read_text())
        self.validation = json.loads((path/'validation.json').read_text())
        if public and (self.provenance.get('scope') != 'public_approved' or self.metadata['approval_status'] != 'reviewed'):
            raise V2Unavailable('RESEARCH_ONLY_BUNDLE')
        if self.metadata['market'] != 'US' or self.metadata['base_currency'] != 'USD':
            raise V2Unavailable('UNSUPPORTED_MARKET_OR_CURRENCY')
        layout = json.loads((path/'layout.json').read_text())
        dates = pd.DatetimeIndex(layout['dates'])
        self.returns = pd.DataFrame(np.load(path/'returns.npy', mmap_mode='r', allow_pickle=False), index=dates, columns=layout['tickers'], copy=False)
        self.factors = pd.DataFrame(np.load(path/'factor_moves.npy', mmap_mode='r', allow_pickle=False), index=dates, columns=layout['factors'], copy=False)
        self.universe = pd.DataFrame(json.loads((path/'universe.json').read_text())).set_index('ticker')
        self.betas = pd.DataFrame(np.load(path/'betas.npy', mmap_mode='r', allow_pickle=False), index=layout['beta_tickers'], columns=layout['beta_columns'], copy=False)
        self.scenarios = json.loads((path/'scenarios.json').read_text())
        if (len(self.returns) != 756 or not self.returns.index.equals(self.factors.index)
                or not self.returns.index.is_unique or not self.returns.index.is_monotonic_increasing
                or not np.isfinite(self.returns.to_numpy()).all()
                or set(self.returns.columns) != set(self.universe.index)
                or set(self.betas.index) != set(self.universe.index)):
            raise V2Unavailable('INVALID_BUNDLE_SHAPE')
        if str(self.returns.index[-1].date()) != self.metadata['snapshot_as_of']:
            raise V2Unavailable('SNAPSHOT_DATE_MISMATCH')


def load_research_bundle(path):
    path = Path(path)
    return Bundle(path, verify_release(path))


@lru_cache(maxsize=1)
def _load_public(snapshot_id, manifest_hash, registry_hash):
    # Hashes bind the one-entry cache to a reviewed immutable release and ledger.
    path = RELEASES_PATH / snapshot_id
    if sha256(path/'manifest.json') != manifest_hash:
        raise V2Unavailable('MANIFEST_NOT_APPROVED')
    bundle = Bundle(path, verify_release(path), public=True)
    ledger = json.loads(REGISTRY_PATH.read_text())['license_approvals']
    require_rights(bundle.provenance, ledger, bundle.universe.index)
    return bundle


def load_public_bundle(snapshot_id):
    if not re.fullmatch(SNAPSHOT_PATTERN, snapshot_id):
        raise V2Unavailable('INVALID_SNAPSHOT_ID')
    registry = json.loads(REGISTRY_PATH.read_text())
    if registry.get('schema_version') != 2:
        raise V2Unavailable('INVALID_REGISTRY')
    entry = registry.get('releases', {}).get(snapshot_id)
    if not entry or entry.get('status') != 'approved' or not entry.get('manifest_sha256'):
        raise V2Unavailable('NO_APPROVED_RELEASE')
    return _load_public(snapshot_id, entry['manifest_sha256'], sha256(REGISTRY_PATH))


def analyze_bundle(bundle, request):
    if request.snapshot_id != bundle.manifest['snapshot_id']:
        raise V2Unavailable('SNAPSHOT_MISMATCH')
    weights = {h.ticker:h.weight/100 for h in request.holdings}
    if not set(weights) <= set(bundle.universe.index):
        raise V2Unavailable('ASSET_NOT_IN_APPROVED_SNAPSHOT')
    selected = bundle.returns[list(weights)]
    variance = float(np.array(list(weights.values())) @ selected.cov().to_numpy() @ np.array(list(weights.values())))
    if not np.isfinite(variance) or variance <= 0:
        raise V2Unavailable('DEGENERATE_PORTFOLIO')
    analysis = analyze_portfolio(weights, bundle.returns, bundle.universe)
    exposure = portfolio_exposure(weights, bundle.betas, (bundle.returns, bundle.factors))
    stress = compute_stress(weights, request.value_amount, exposure['by_asset'], bundle.scenarios)
    for row in stress:
        row['significant'] = exposure['significant'][row['factor']]
    analysis.update({'as_of':bundle.metadata['snapshot_as_of'], 'value_usd':request.value_amount,
                     'window':{'start':bundle.validation['window_start'], 'end':bundle.validation['window_end'], 'days':756},
                     'factor_exposure':exposure, 'stress':stress})
    # Fail closed before JSON serialization rather than returning NaN or partial finances.
    json.dumps(analysis, allow_nan=False)
    return {'snapshot_id':request.snapshot_id, 'market':'US', 'base_currency':'USD',
            'methodology_version':bundle.metadata['methodology_version'],
            'scope':bundle.provenance['scope'], 'support_status':'full', 'analysis':analysis}


def compare_bundle(bundle, request):
    current = analyze_bundle(bundle, request.current)
    proposed = analyze_bundle(bundle, request.proposed)
    return {'snapshot_id':request.current.snapshot_id, 'market':'US', 'base_currency':'USD',
            'scope':bundle.provenance['scope'], 'current':current, 'proposed':proposed,
            'comparison':compare_analyses(current['analysis'], proposed['analysis'])}


def revision_diff(previous, current):
    """Report exact overlapping vintage changes, never overwrite or smooth them."""
    for frame in (previous, current):
        if not frame.index.is_unique or not frame.columns.is_unique or not frame.index.is_monotonic_increasing:
            raise V2Unavailable('INVALID_REVISION_INDEX')
    dates = previous.index.intersection(current.index)
    tickers = previous.columns.intersection(current.columns)
    changes = []
    for ticker in sorted(tickers):
        before, after = previous.loc[dates,ticker], current.loc[dates,ticker]
        different = ~(before.eq(after) | (before.isna() & after.isna()))
        for day in dates[different]:
            changes.append({'ticker':ticker, 'date':str(day.date())})
    return {'overlap_observations':len(dates)*len(tickers), 'changed_observations':len(changes),
            'changes':changes, 'added_tickers':sorted(set(current)-set(previous)),
            'removed_tickers':sorted(set(previous)-set(current)),
            'added_dates':[str(day.date()) for day in current.index.difference(previous.index)],
            'removed_dates':[str(day.date()) for day in previous.index.difference(current.index)]}
