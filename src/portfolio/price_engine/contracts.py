"""Explicit identities, reviewed calendars and provenance; no inferred permissions."""
from datetime import date
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class PipelineError(ValueError):
    def __init__(self, code, **details):
        self.code = code
        self.details = details
        super().__init__(code)

    def as_dict(self):
        return {'code': self.code, 'details': self.details}


class Instrument(Contract):
    asset_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1, strict=True)
    market: Literal['US', 'KR']
    exchange_mic: Literal['XNYS', 'XNAS', 'ARCX', 'XKRX', 'XKOS']
    currency: Literal['USD', 'KRW']
    kind: Literal['stock', 'etf']
    listed_on: date
    delisted_on: date | None = None
    identity_reference: str | None = None

    @model_validator(mode='after')
    def coherent(self):
        allowed = {'US': ('USD', {'XNYS', 'XNAS', 'ARCX'}), 'KR': ('KRW', {'XKRX', 'XKOS'})}
        currency, exchanges = allowed[self.market]
        if self.currency != currency or self.exchange_mic not in exchanges:
            raise ValueError('Market, exchange and currency must agree')
        if self.delisted_on and self.delisted_on < self.listed_on:
            raise ValueError('Invalid listing interval')
        return self


class SymbolMapping(Contract):
    instrument: Instrument
    source_id: str = Field(min_length=1)
    provider_symbol: str = Field(min_length=1, strict=True)
    valid_from: date
    valid_to: date | None = None
    evidence_reference: str | None = None

    @model_validator(mode='after')
    def coherent(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValueError('Invalid mapping interval')
        return self


class Session(Contract):
    day: date
    close_at: AwareDatetime
    available_at: AwareDatetime

    @model_validator(mode='after')
    def coherent(self):
        if self.available_at < self.close_at:
            raise ValueError('Availability cannot precede close')
        return self


class TradingCalendar(Contract):
    calendar_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    market: Literal['US', 'KR']
    exchange_mic: Literal['XNYS', 'XNAS', 'ARCX', 'XKRX', 'XKOS']
    timezone: Literal['America/New_York', 'Asia/Seoul']
    coverage_start: date
    coverage_end: date
    evidence_reference: str = Field(min_length=1)
    reviewed: bool = False
    sessions: tuple[Session, ...]

    @model_validator(mode='after')
    def coherent(self):
        zone = ZoneInfo(self.timezone)
        days = [s.day for s in self.sessions]
        if self.coverage_start > self.coverage_end or days != sorted(set(days)):
            raise ValueError('Invalid calendar interval or duplicate/unsorted sessions')
        if (self.market == 'US') != (self.timezone == 'America/New_York'):
            raise ValueError('Market timezone mismatch')
        if (self.market == 'US') != (self.exchange_mic in {'XNYS', 'XNAS', 'ARCX'}):
            raise ValueError('Market exchange mismatch')
        for session in self.sessions:
            if not self.coverage_start <= session.day <= self.coverage_end:
                raise ValueError('Session outside calendar coverage')
            if session.close_at.astimezone(zone).date() != session.day:
                raise ValueError('Close timestamp does not belong to local session date')
        return self


class ResearchPermission(Contract):
    """Evidence for local storage/processing, never a public-service approval."""
    source_id: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    storage_allowed: bool = False
    processing_allowed: bool = False


class SourceReceipt(Contract):
    source_id: str = Field(min_length=1)
    source_url: str
    retrieved_at: AwareDatetime
    published_at: AwareDatetime | None = None
    publication_missing_reason: str | None = None
    adjustment: Literal['total_return', 'split_only', 'raw', 'unknown'] = 'unknown'
    adjustment_reference: str | None = None
    corporate_actions_reference: str | None = None

    @model_validator(mode='after')
    def coherent(self):
        url = urlsplit(self.source_url)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Use a public HTTPS source reference without secrets/query strings')
        if self.published_at and self.published_at > self.retrieved_at:
            raise ValueError('Publication cannot follow retrieval')
        if not self.published_at and not self.publication_missing_reason:
            raise ValueError('Publication time or explicit missing reason required')
        return self


class Window(Contract):
    mode: Literal['latest', 'historical'] = 'latest'
    start: date
    end: date
    as_of: AwareDatetime

    @model_validator(mode='after')
    def coherent(self):
        if self.start > self.end:
            raise ValueError('Invalid requested interval')
        return self


class QualityPolicy(Contract):
    version: str = 'price-quality-v1'
    min_prices: int = Field(default=757, ge=3)
    max_abs_return: float = Field(default=.5, gt=0, allow_inf_nan=False)
