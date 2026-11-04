"""Offline, fail-closed candidate validation and immutable release storage.

Never collects data, fills holidays, or promotes candidates into the runtime engine.
"""
from datetime import date
import hashlib
import json
import re
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

CAPABILITIES = ('hidden_risk', 'factors', 'stress', 'what_if')


class Receipt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    asset_id: str = Field(min_length=1)
    market: Literal['US', 'KR']
    currency: Literal['USD', 'KRW']
    source_id: str = Field(min_length=1)
    source_url: str = Field(pattern=r'^https://')
    license_reference: str = Field(min_length=1)
    public_use_approved: bool = False
    retrieved_at: AwareDatetime
    published_at: AwareDatetime | None = None
    published_at_missing_reason: str | None = None
    adjustment_method: str = Field(min_length=1)
    precision_policy: str = Field(min_length=1)
    code_version: str = Field(min_length=1)
    dependency_version: str = Field(min_length=1)
    corporate_actions_verified: bool = False
    trading_status_verified: bool = False
    identity_verified: bool = False


class ReleaseMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_as_of: date
    built_at: AwareDatetime
    market: Literal['US', 'KR']
    base_currency: Literal['USD', 'KRW']
    methodology_version: str = Field(min_length=1)
    previous_snapshot_id: str | None = None
    approval_status: Literal['quarantined', 'reviewed'] = 'quarantined'
    revision_note: str = Field(min_length=1)

    @model_validator(mode='after')
    def coherent(self):
        if self.snapshot_as_of > self.built_at.date():
            raise ValueError('Snapshot cannot contain future observations')
        if (self.market, self.base_currency) not in {('US', 'USD'), ('KR', 'KRW')}:
            raise ValueError('Mixed markets/currencies are not supported')
        return self


def validate_candidate(prices, expected_sessions, factors, receipt: Receipt, *,
                       factor_policy_verified=False, scenarios_verified=False):
    """Caller supplies an independently verified calendar and exactly 757 sessions.

    Factor dates must match the 756 returns; exceptions need a future explicit
    market policy adapter. Large moves are quarantined, never clipped.
    """
    reasons = []
    if not receipt.public_use_approved:
        reasons.append('RIGHTS_UNCONFIRMED')
    if (receipt.market, receipt.currency) not in {('US', 'USD'), ('KR', 'KRW')}:
        reasons.append('CURRENCY_MISMATCH')
    if receipt.market != 'US':
        reasons.append('MARKET_METHODOLOGY_UNAPPROVED')
    if not receipt.published_at and not receipt.published_at_missing_reason:
        reasons.append('PUBLICATION_PROVENANCE_MISSING')
    if receipt.published_at and receipt.published_at > pd.Timestamp(receipt.retrieved_at):
        reasons.append('FUTURE_PUBLICATION')
    for verified, code in [(receipt.identity_verified, 'IDENTITY_UNVERIFIED'),
                           (receipt.corporate_actions_verified, 'CORPORATE_ACTIONS_UNVERIFIED'),
                           (receipt.trading_status_verified, 'TRADING_STATUS_UNVERIFIED')]:
        if not verified:
            reasons.append(code)
    sessions = pd.DatetimeIndex(expected_sessions)
    valid_calendar = (len(sessions) == 757 and sessions.is_unique and sessions.is_monotonic_increasing)
    numeric_prices = pd.to_numeric(prices, errors='coerce')
    valid_prices = (valid_calendar and prices.index.equals(sessions)
                    and np.isfinite(numeric_prices.to_numpy(dtype=float)).all()
                    and (numeric_prices > 0).all())
    prices = numeric_prices
    if not valid_prices:
        reasons.append('INVALID_PRICE_WINDOW')
    elif (prices.pct_change(fill_method=None).dropna().abs() > .5).any():
        reasons.append('EXTREME_MOVE_REQUIRES_REVIEW')
    if valid_calendar:
        observed = sessions[-1]
        if pd.Timestamp(receipt.retrieved_at).date() < observed.date():
            reasons.append('FUTURE_OBSERVATION')
    price_ok = not reasons
    pair_counts = {}
    factor_ok = price_ok and factor_policy_verified
    valid_factor_dates = factors.index.is_unique and factors.index.is_monotonic_increasing
    factor_ok = factor_ok and valid_factor_dates
    for name in ('market', 'rate', 'volatility'):
        column = pd.to_numeric(factors[name], errors='coerce') if name in factors and valid_factor_dates else pd.Series(dtype=float)
        values = column.reindex(sessions[1:]).to_numpy(dtype=float)
        pair_counts[name] = int(np.isfinite(values).sum())
        factor_ok = factor_ok and len(values) == 756 and np.isfinite(values).all() and np.var(values) > 0
    if factor_ok:
        returns = prices.pct_change(fill_method=None).iloc[1:].to_numpy(dtype=float)
        for name in ('market', 'rate', 'volatility'):
            x = factors[name].reindex(sessions[1:]).to_numpy(dtype=float)
            with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
                beta = np.sum((x-x.mean())*(returns-returns.mean())) / np.sum((x-x.mean())**2)
                residuals = returns - (returns.mean() + beta*(x-x.mean()))
                factor_ok = factor_ok and bool(np.isfinite(beta) and np.isfinite(residuals).all())
    if not factor_ok:
        reasons.append('FACTOR_POLICY_OR_COVERAGE_UNVERIFIED')
    capabilities = {'hidden_risk': price_ok, 'factors': bool(factor_ok),
                    'stress': bool(factor_ok and scenarios_verified),
                    'what_if': bool(factor_ok and scenarios_verified)}
    if not scenarios_verified:
        reasons.append('SCENARIOS_UNVERIFIED')
    status = 'full' if all(capabilities.values()) else 'partial' if any(capabilities.values()) else 'unsupported'
    return {'support_status': status, 'capabilities': capabilities, 'reason_codes': reasons,
            'factor_pair_counts': pair_counts, 'required_count': 756,
            'selectable': False, 'note': 'Offline validation only; runtime approval is separate.'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_release(root, snapshot_id, artifacts, metadata):
    """Create a new directory only. Existing releases cannot be revised in place."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', snapshot_id):
        raise ValueError('Invalid snapshot_id')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+\.(json|csv|npy)', name) or name == 'manifest.json' for name in artifacts):
        raise ValueError('Invalid artifact name')
    metadata = ReleaseMetadata.model_validate(metadata).model_dump(mode='json')
    if not artifacts:
        raise ValueError('Release requires artifacts')
    release = Path(root) / snapshot_id
    release.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name, content in artifacts.items():
        target = release / name
        with target.open('xb') as stream:
            stream.write(content)
        hashes[name] = sha256(target)
    manifest = {'schema_version': 2, 'snapshot_id': snapshot_id, 'metadata': metadata, 'sha256': hashes}
    (release / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    return manifest


def verify_release(release):
    release = Path(release)
    if release.is_symlink() or (release / 'manifest.json').is_symlink():
        raise ValueError('Release cannot be a symlink')
    manifest = json.loads((release / 'manifest.json').read_text())
    ReleaseMetadata.model_validate(manifest['metadata'])
    if manifest.get('schema_version') != 2 or manifest['snapshot_id'] != release.name or not manifest['sha256']:
        raise ValueError('Invalid release manifest')
    for name, expected in manifest['sha256'].items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.(json|csv|npy)', name) or name == 'manifest.json':
            raise ValueError('Invalid artifact name')
        path = release / name
        if path.is_symlink() or sha256(path) != expected:
            raise ValueError(f'Artifact integrity failure: {name}')
    return manifest
