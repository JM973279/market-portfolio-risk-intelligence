"""Isolated V2 discovery contract. No new asset is granted V1 engine access."""
import json
from pathlib import Path

from src.portfolio.analytics import load_snapshot_meta
from src.portfolio.universe import load_universe

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / 'data/portfolio_v2/catalog.json'
CAPABILITIES = ('hidden_risk', 'factors', 'stress', 'what_if')


def get_catalog():
    metadata = json.loads(CATALOG_PATH.read_text())
    meta = load_snapshot_meta()
    assets = []
    for ticker, row in load_universe().iterrows():
        assets.append({
            **row.to_dict(), 'ticker': ticker, 'asset_id': f'US:V1:{ticker}',
            'display_symbol': ticker, 'name_en': row['name'],
            'name_ko': metadata['names_ko'][ticker], 'aliases': [],
            'market': 'US', 'currency': 'USD', 'exchange_mic': None,
            'support_status': 'full', 'selectable': True,
            'capabilities': dict.fromkeys(CAPABILITIES, True), 'reason_codes': [],
            'support_scope': 'frozen_v1_only',
            'snapshot_id': metadata['snapshot_id'], 'snapshot_as_of': meta['as_of'],
            'first_valid_observed_at': meta['start'], 'last_valid_observed_at': meta['as_of'],
            'retrieved_at': None, 'published_at': None, 'approved_at': None,
            'source_references': [meta['price_source'], meta['rate_source'], meta['vol_source']],
            'source_license': {'status': 'legacy_unverified', 'new_public_use_approved': False},
        })
    # Candidates are discovery only. Approval cannot be inferred from catalog metadata.
    for candidate in metadata['candidates']:
        assets.append({**candidate, 'support_status': 'unsupported', 'selectable': False,
                       'capabilities': dict.fromkeys(CAPABILITIES, False),
                       'snapshot_id': None, 'support_scope': 'discovery_only',
                       'source_license': {'status':'unconfirmed_public_use', 'new_public_use_approved':False},
                       'reason_codes': list(dict.fromkeys([*candidate.get('reason_codes', []), 'NO_APPROVED_RELEASE']))})
    return {'schema_version': 2, 'snapshot_id': metadata['snapshot_id'],
            'as_of': meta['as_of'], 'market': 'US', 'base_currency': 'USD',
            'methodology_version': 'portfolio-v1-frozen', 'assets': assets,
            'new_public_support_enabled': False,
            'notice': {'ko': '기존 28개 고정 V1 지원입니다. 신규 공개 사용 권리 승인을 뜻하지 않습니다.',
                       'en': 'Existing 28 assets use Frozen V1. This does not approve new public data use.'}}


def discovery_catalog():
    """Separate discovery universe; metadata can never grant analysis access."""
    result = get_catalog()
    seed = json.loads((CATALOG_PATH.parent / 'kr_candidates.json').read_text())
    assets = list(result['assets'])
    for candidate in seed['candidates']:
        assets.append({**candidate, 'support_status': 'unsupported', 'selectable': False,
                       'capabilities': dict.fromkeys(CAPABILITIES, False),
                       'support_scope': 'discovery_only', 'snapshot_id': None,
                       'snapshot_as_of': None,
                       'source_license': {'status': 'unconfirmed_public_use', 'new_public_use_approved': False},
                       'reason_codes': list(dict.fromkeys([*candidate['reason_codes'], 'NO_APPROVED_RELEASE']))})
    ids = [a['asset_id'] for a in assets]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate discovery asset_id')
    return {**result, 'market': 'MULTI', 'assets': assets,
            'universe_scope': 'curated_research_seed_not_complete_exchange_master'}


def search_discovery(q='', market=None, kind=None, status=None, offset=0, limit=30):
    import unicodedata
    normalize = lambda value: unicodedata.normalize('NFKC', value).strip().casefold()
    query = normalize(q)
    catalog = discovery_catalog()
    rows = [a for a in catalog['assets']
            if (market is None or a['market'] == market)
            and (kind is None or a['type'] == kind)
            and (status is None or a['support_status'] == status)
            and any(query in normalize(s) for s in
                    [a['ticker'], a['name'], a.get('name_ko', ''), *a.get('aliases', [])])]
    rows.sort(key=lambda a: (0 if normalize(a['ticker']) == query else
                            1 if normalize(a['ticker']).startswith(query) else 2,
                            a['asset_id']))
    return {**catalog, 'assets': rows[offset:offset+limit], 'total': len(rows),
            'universe_total': len(catalog['assets']), 'offset': offset, 'limit': limit,
            'next_offset': offset+limit if offset+limit < len(rows) else None}
