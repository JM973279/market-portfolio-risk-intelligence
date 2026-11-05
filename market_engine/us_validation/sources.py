"""HTTP bodies and normalizations are separately hashed. No credentials in receipts."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo
import json
import math
import re

import pandas as pd
import requests

from .store import EvidenceStore

SERIES = ('SPY', 'VIX', 'DBAA', 'DGS10')


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def date_string(value: str) -> str:
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError('ISO date required')
    return value


def encode_frame(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index_label='Date', float_format='%.17g').encode()


def read_frame(body: bytes) -> pd.DataFrame:
    return pd.read_csv(BytesIO(body), index_col='Date', parse_dates=True)


def normalize_yahoo(body: bytes, name: str) -> pd.DataFrame:
    payload = json.loads(body)
    results = payload.get('chart', {}).get('result')
    if payload.get('chart', {}).get('error') or not isinstance(results, list) or len(results) != 1:
        raise ValueError('YAHOO_RESULT_SCHEMA')
    result = results[0]
    symbol = 'SPY' if name == 'SPY' else '^VIX'
    if result['meta'].get('symbol') != symbol or result['meta'].get('exchangeTimezoneName') != 'America/New_York':
        raise ValueError('YAHOO_IDENTITY_TIMEZONE')
    stamps = result.get('timestamp', [])
    if not stamps or any(not isinstance(t, (int, float)) or not math.isfinite(t) for t in stamps):
        raise ValueError('YAHOO_TIMESTAMPS')
    dates = [datetime.fromtimestamp(t, timezone.utc).astimezone(ZoneInfo('America/New_York')).date() for t in stamps]
    quote = result['indicators']['quote'][0]
    adjusted = result['indicators'].get('adjclose', [{}])[0].get('adjclose')
    if name == 'SPY' and adjusted is None:
        raise ValueError('ADJUSTED_CLOSE_REQUIRED')
    columns = {'close': quote.get('close'), 'adj_close': adjusted or [None]*len(stamps),
               'open': quote.get('open'), 'high': quote.get('high'), 'low': quote.get('low'),
               'volume': quote.get('volume')}
    if any(not isinstance(values, list) or len(values) != len(stamps) for values in columns.values()):
        raise ValueError('YAHOO_ARRAY_LENGTH')
    frame = pd.DataFrame(columns, index=pd.DatetimeIndex(dates, name='Date'))
    for col in frame:
        frame[col] = pd.to_numeric(frame[col], errors='raise')
    frame['value'] = frame['adj_close'] if name == 'SPY' else frame['close']
    # Raw event payloads, including off-session events, remain in the HTTP body.
    for kind in ('dividends', 'splits'):
        events = result.get('events', {}).get(kind, {})
        if not isinstance(events, dict):
            raise ValueError('YAHOO_ACTION_SCHEMA')
        counts = {}
        for event in events.values():
            day = datetime.fromtimestamp(event['date'], timezone.utc).astimezone(ZoneInfo('America/New_York')).date()
            counts[day] = counts.get(day, 0) + 1
        frame[kind + '_count'] = [counts.get(day, 0) for day in dates]
    return frame


def normalize_fred(body: bytes, name: str, vintage: str | None = None) -> pd.DataFrame:
    if vintage:
        payload = json.loads(body)
        if payload.get('realtime_start') != vintage or payload.get('realtime_end') != vintage:
            raise ValueError('FRED_VINTAGE_MISMATCH')
        rows = payload.get('observations')
        if not isinstance(rows, list) or len(rows) != int(payload.get('count', -1)):
            raise ValueError('FRED_PAGINATION_OR_SCHEMA')
        frame = pd.DataFrame(rows)
        if frame.empty or not {'date', 'value', 'realtime_start', 'realtime_end'} <= set(frame):
            raise ValueError('FRED_OBSERVATION_SCHEMA')
        # These are response validity intervals, not first-publication timestamps.
        if not ((frame.realtime_start == vintage) & (frame.realtime_end == vintage)).all():
            raise ValueError('FRED_ROW_VINTAGE_MISMATCH')
        result = frame.set_index(pd.DatetimeIndex(pd.to_datetime(frame.date, errors='raise'), name='Date'))
        result['value'] = pd.to_numeric(result.value.replace('.', None), errors='raise')
        return result[['value', 'realtime_start', 'realtime_end']]
    frame = pd.read_csv(BytesIO(body), na_values='.')
    if list(frame.columns) != ['observation_date', name]:
        raise ValueError('FRED_CSV_SCHEMA')
    return pd.DataFrame({'value': pd.to_numeric(frame[name], errors='raise').to_numpy()},
                        index=pd.DatetimeIndex(pd.to_datetime(frame.observation_date, errors='raise'), name='Date'))


def collect(store: EvidenceStore, start: str, end: str, *, fred_vintage: str | None = None,
            fred_key: str | None = None, previous: str | None = None, get=None) -> str:
    """One bounded request per source; failed HTTP bodies are still retained.

    Explicit vintage requires a user-owned existing FRED key; it is never saved.
    No latest-known CSV is mislabelled as a historical vintage.
    """
    start, end = date_string(start), date_string(end)
    if start > end or end > datetime.now(timezone.utc).date().isoformat():
        raise ValueError('Invalid observation interval')
    if fred_vintage and (not fred_key or date_string(fred_vintage) > datetime.now(timezone.utc).date().isoformat()):
        raise ValueError('Explicit FRED vintage requires existing key and nonfuture date')
    if previous:
        verify_snapshot(store, previous)
    get = get or requests.get
    manifest = {'schema': 1, 'kind': 'PRIVATE_RESEARCH_SOURCE_SNAPSHOT', 'started_at': utcnow(),
                'interval': {'start': start, 'end': end}, 'previous': previous, 'sources': {},
                'public_approved': False}
    for name in SERIES:
        yahoo = name in ('SPY', 'VIX')
        if yahoo:
            symbol = 'SPY' if name == 'SPY' else '^VIX'
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
            params = {'period1': int(datetime.combine(date.fromisoformat(start), time(), timezone.utc).timestamp()),
                      'period2': int(datetime.combine(date.fromisoformat(end)+timedelta(days=1), time(), timezone.utc).timestamp()),
                      'interval': '1d', 'events': 'div,splits', 'includeAdjustedClose': 'true'}
        elif fred_vintage:
            url = 'https://api.stlouisfed.org/fred/series/observations'
            params = {'series_id': name, 'observation_start': start, 'observation_end': end,
                      'realtime_start': fred_vintage, 'realtime_end': fred_vintage,
                      'file_type': 'json', 'limit': 100000, 'api_key': fred_key}
        else:
            url = 'https://fred.stlouisfed.org/graph/fredgraph.csv'
            params = {'id': name, 'cosd': start, 'coed': end}
        record = {'normalization_version': 1, 'provider': 'Yahoo Finance' if yahoo else 'FRED', 'endpoint': url,
                  'request_options': {k:v for k,v in params.items() if k != 'api_key'},
                  'started_at': utcnow(), 'adjustment': 'PROVIDER_ADJ_CLOSE' if name == 'SPY' else 'UNADJUSTED_LEVEL',
                  'vintage': {'kind': 'EXPLICIT_AS_OF' if fred_vintage else 'LATEST_KNOWN_NOT_POINT_IN_TIME',
                              'as_of': fred_vintage} if not yahoo else {'kind': 'PROVIDER_RESPONSE_VERSION', 'as_of': None},
                  'status': 'FAILED'}
        try:
            response = get(url, params=params, timeout=(10, 30), headers={'User-Agent': 'MPRI-private-research/1.0'})
            record.update(http_status=response.status_code, retrieved_at=utcnow(),
                          raw_sha256=store.put(response.content),
                          response_headers={k:v for k,v in response.headers.items()
                                            if k.lower() in {'date', 'content-type', 'etag', 'last-modified'}})
            if response.status_code != 200:
                raise ValueError('PROVIDER_HTTP_STATUS')
            frame = normalize_yahoo(response.content, name) if yahoo else normalize_fred(response.content, name, fred_vintage)
            record.update(status='COLLECTED', normalized_sha256=store.put(encode_frame(frame)), rows=len(frame),
                          observation_dates=[day.strftime('%Y-%m-%d') for day in frame.index],
                          missing_values=int(frame.value.isna().sum()), duplicate_dates=int(frame.index.duplicated().sum()))
        except Exception as error:
            # Never persist requests' credential-bearing URL or exception text.
            record.update(error_type=type(error).__name__,
                          error_code=str(error) if re.fullmatch('[A-Z][A-Z0-9_]+',str(error)) else 'NORMALIZATION_OR_TRANSPORT_FAILURE')
        manifest['sources'][name] = record
    manifest['completed_at'] = utcnow()
    manifest['collection_complete'] = all(s['status'] == 'COLLECTED' for s in manifest['sources'].values())
    return store.document(manifest, 'snapshots')


def verify_snapshot(store: EvidenceStore, key: str) -> tuple[dict, dict[str, pd.DataFrame]]:
    manifest = store.load(key, 'snapshots')
    if manifest.get('schema') != 1 or set(manifest.get('sources', {})) != set(SERIES):
        raise ValueError('SNAPSHOT_SCHEMA')
    frames = {}
    for name, source in manifest['sources'].items():
        body = store.read(source['raw_sha256']) if source.get('raw_sha256') else None
        if source.get('normalization_version',1) != 1:
            raise ValueError('UNSUPPORTED_NORMALIZATION_VERSION')
        if source.get('status') == 'COLLECTED':
            if body is None:
                raise ValueError('RAW_RESPONSE_MISSING')
            reparsed = normalize_yahoo(body, name) if name in ('SPY','VIX') else normalize_fred(body, name, source['vintage']['as_of'])
            encoded = store.read(source['normalized_sha256'])
            if encode_frame(reparsed) != encoded:
                raise ValueError('NORMALIZATION_NOT_REPRODUCIBLE')
            frames[name] = reparsed
    return manifest, frames


def action_changes(old_body: bytes, new_body: bytes) -> dict:
    """Compare original action objects, including amounts/ratios, not only counts."""
    old = json.loads(old_body)['chart']['result'][0].get('events',{})
    new = json.loads(new_body)['chart']['result'][0].get('events',{})
    result = {}
    for kind in ('dividends','splits'):
        a,b = old.get(kind,{}),new.get(kind,{})
        result[kind] = {'added':[b[k] for k in sorted(b.keys()-a.keys())],
                        'removed':[a[k] for k in sorted(a.keys()-b.keys())],
                        'revised':[{'old':a[k],'new':b[k]} for k in sorted(a.keys()&b.keys()) if a[k]!=b[k]]}
    return result
