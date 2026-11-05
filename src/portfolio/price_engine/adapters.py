"""Archive adapters only: no HTTP client, API key, subscription or retry loop.

Provider parsers accept bytes from a caller-authorized local capture. The generic
CSV adapter is the integration point for a future separately reviewed collector.
"""
import csv
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from .contracts import PipelineError, ResearchPermission, SourceReceipt, SymbolMapping

ADAPTER_VERSION = 'archive-adapters-v1'


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PipelineError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


@dataclass(frozen=True)
class Capture:
    content: bytes
    receipt: SourceReceipt

    @property
    def sha256(self):
        return hashlib.sha256(self.content).hexdigest()

    @property
    def capture_id(self):
        provenance = self.receipt.model_dump_json()
        return hashlib.sha256((self.sha256 + provenance).encode()).hexdigest()


class PriceAdapter(Protocol):
    source_id: str

    def normalize(self, capture: Capture, mapping: SymbolMapping) -> list[dict]: ...


class CsvArchiveAdapter:
    """Canonical daily CSV: date,symbol,currency,close,adjusted_close.

    Symbol/currency are strings. Missing numeric values remain NaN for the gate.
    Rows must represent the mapped listing, not a cross-exchange ticker search.
    """
    def __init__(self, source_id='local_csv'):
        self.source_id = source_id

    def normalize(self, capture, mapping):
        reader = csv.DictReader(io.StringIO(capture.content.decode('utf-8-sig')))
        required = {'date', 'symbol', 'currency', 'close', 'adjusted_close'}
        if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
                or set(reader.fieldnames) != required):
            raise PipelineError('CSV_SCHEMA_MISMATCH')
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise PipelineError('CSV_SCHEMA_MISMATCH')
            if row['symbol'] != mapping.provider_symbol:
                raise PipelineError('PROVIDER_SYMBOL_MISMATCH')
            if row['currency'] != mapping.instrument.currency:
                raise PipelineError('SOURCE_CURRENCY_MISMATCH')
            rows.append({'date': row['date'], 'close': row['close'], 'adjusted_close': row['adjusted_close']})
        return rows


class AlphaVantageArchiveAdapter:
    """TIME_SERIES_DAILY_ADJUSTED JSON capture; live premium endpoint disabled."""
    source_id = 'alpha_vantage'

    def normalize(self, capture, mapping):
        if mapping.instrument.market != 'US':
            raise PipelineError('ADAPTER_MARKET_UNSUPPORTED')
        body = strict_json(capture.content)
        if not isinstance(body, dict) or any(key in body for key in ('Note', 'Information', 'Error Message')):
            raise PipelineError('PROVIDER_ERROR_RESPONSE')
        if body['Meta Data']['2. Symbol'] != mapping.provider_symbol:
            raise PipelineError('PROVIDER_SYMBOL_MISMATCH')
        if capture.receipt.adjustment != 'total_return':
            raise PipelineError('ADAPTER_ADJUSTMENT_MISMATCH')
        return [{'date': day, 'close': row['4. close'], 'adjusted_close': row['5. adjusted close']}
                for day, row in body['Time Series (Daily)'].items()]


class KrxArchiveAdapter:
    """KRX daily stock/ETF archive. Raw close is never relabeled adjusted.

    ISU_CD can be ISIN; provider_symbol must explicitly map that exact field.
    No inference from a six-digit ticker to ISIN is performed.
    """
    source_id = 'krx_openapi'

    def normalize(self, capture, mapping):
        if mapping.instrument.market != 'KR':
            raise PipelineError('ADAPTER_MARKET_UNSUPPORTED')
        if capture.receipt.adjustment != 'raw':
            raise PipelineError('ADAPTER_ADJUSTMENT_MISMATCH')
        body = strict_json(capture.content)
        rows = body['OutBlock_1']
        if not isinstance(rows, list):
            raise PipelineError('PROVIDER_SCHEMA_MISMATCH')
        selected = []
        for row in rows:
            if row['ISU_CD'] == mapping.provider_symbol:
                day = pd.to_datetime(row['BAS_DD'], format='%Y%m%d', errors='raise').date().isoformat()
                selected.append({'date': day, 'close': row['TDD_CLSPRC'], 'adjusted_close': None})
        return selected


@dataclass(frozen=True)
class CollectedPrices:
    frame: pd.DataFrame
    captures: tuple[Capture, ...]
    mappings: tuple[SymbolMapping, ...]
    permissions: tuple[ResearchPermission, ...]
    jobs: tuple[dict, ...]
    normalized_sha256: str


def frame_sha256(frame):
    return hashlib.sha256(frame.to_csv(index=False, float_format="%.17g").encode()).hexdigest()


def collect_archives(jobs, permissions):
    """jobs: (adapter, mapping, capture) tuples. Retain duplicates for validation.

    Returns in-memory research data; no destination, registry or public route.
    """
    grants = {p.source_id: p for p in permissions}
    if len(grants) != len(permissions):
        raise PipelineError('DUPLICATE_PERMISSION')
    frames, captures, mappings, job_records = [], [], {}, []
    provider_keys = {}
    for adapter, mapping, capture in jobs:
        source = adapter.source_id
        grant = grants.get(source)
        if not grant or not grant.storage_allowed or not grant.processing_allowed:
            raise PipelineError('RESEARCH_PERMISSION_REQUIRED', source_id=source)
        if source != mapping.source_id or source != capture.receipt.source_id:
            raise PipelineError('SOURCE_ID_MISMATCH')
        asset_id = mapping.instrument.asset_id
        previous = mappings.get(asset_id)
        if previous and previous != mapping:
            raise PipelineError('CONFLICTING_ASSET_MAPPING', asset_id=asset_id)
        # A parser must be able to disambiguate its symbol without guessing a MIC.
        key = (source, mapping.provider_symbol)
        if key in provider_keys and provider_keys[key] != asset_id:
            raise PipelineError('AMBIGUOUS_PROVIDER_SYMBOL')
        provider_keys[key] = asset_id
        mappings[asset_id] = mapping
        try:
            rows = adapter.normalize(capture, mapping)
            frame = pd.DataFrame(rows, columns=['date', 'close', 'adjusted_close'])
            # Do not guess numeric dates (e.g. nanoseconds) or localize intraday data.
            if not all(isinstance(v, str) and len(v) == 10 for v in frame['date']):
                raise PipelineError('INVALID_OBSERVATION_DATE')
            frame['date'] = pd.to_datetime(frame['date'], format='%Y-%m-%d', errors='raise')
            for column in ('close', 'adjusted_close'):
                frame[column] = pd.to_numeric(frame[column], errors='coerce')
            frame['asset_id'] = asset_id
            frame['currency'] = mapping.instrument.currency
            frame['source_id'] = source
            frame['provider_symbol'] = mapping.provider_symbol
            frame['payload_sha256'] = capture.sha256
            frame['capture_id'] = capture.capture_id
            frame['retrieved_at'] = pd.Timestamp(capture.receipt.retrieved_at).tz_convert('UTC')
            frames.append(frame)
        except PipelineError:
            raise
        except (ValueError, KeyError, TypeError, UnicodeError, AttributeError) as error:
            raise PipelineError('PROVIDER_SCHEMA_MISMATCH', source_id=source) from error
        job_records.append({'adapter': type(adapter).__name__, 'source_id': source,
                            'asset_id': asset_id, 'capture_index': len(captures)})
        captures.append(capture)
    if not frames:
        raise PipelineError('EMPTY_COLLECTION')
    frame = pd.concat(frames, ignore_index=True)
    return CollectedPrices(frame, tuple(captures), tuple(mappings.values()),
                           tuple(permissions), tuple(job_records), frame_sha256(frame))


def read_capture(path, receipt):
    """Read local bytes only. Rights must be supplied before collect_archives."""
    return Capture(Path(path).read_bytes(), receipt)
