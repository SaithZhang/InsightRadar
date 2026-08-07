"""Provider-neutral contracts for read-only intraday evidence.

Raw provider field names belong in provider adapters.  Every caller consumes
the typed objects in this module and receives explicit evidence status rather
than interpreting an empty collection as a zero observation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Generic, Literal, TypeAlias, TypeVar

EvidenceStatus = Literal["ok", "degraded", "stale", "blocked", "no_data"]
InstrumentKind = Literal["stock", "etf", "index", "unknown"]
TradeSide = Literal["buy", "sell"]
T = TypeVar("T")


@dataclass(frozen=True)
class InstrumentRef:
    """Canonical A-share/ETF/index identity used by all provider adapters."""

    code: str
    qualified_symbol: str
    market: Literal["SH", "SZ"]
    kind: InstrumentKind
    eastmoney_secid: str
    tencent_symbol: str
    display_name: str | None = None


@dataclass(frozen=True)
class TapeMinute:
    """One normalized minute observation.

    ``volume`` and ``amount`` are per-minute increments.  Cumulative fields are
    retained separately so callers never have to infer amount semantics.
    Missing provider fields stay ``None``.
    """

    timestamp: datetime
    price: float
    avg_price: float | None
    high: float | None
    low: float | None
    volume: float | None
    amount: float | None
    cumulative_volume: float | None = None
    cumulative_amount: float | None = None


@dataclass(frozen=True)
class IntradayTape:
    """One complete provider-owned series; tapes are never cross-source merged."""

    instrument: InstrumentRef
    name: str | None
    trade_date: date
    pre_close: float | None
    minutes: tuple[TapeMinute, ...]
    amount_kind: Literal["incremental", "incomplete"] = "incremental"
    amount_unit: Literal["CNY", "unknown"] = "CNY"
    volume_unit: Literal["share", "lot", "unknown"] = "unknown"


@dataclass(frozen=True)
class SourceStamp:
    provider: str
    source: str
    symbol: str | None
    provider_status: str
    source_time: datetime | None
    fetched_at: datetime
    trade_date: date | None
    gaps: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceConflict:
    primary_provider: str
    fallback_provider: str
    field: str
    primary_value: object
    fallback_value: object
    tolerance: float | None = None


@dataclass(frozen=True)
class EvidenceEnvelope(Generic[T]):
    schema_version: str
    status: EvidenceStatus
    reason: str | None
    source_time: datetime | None
    fetched_at: datetime
    stale_seconds: float | None
    data: T | None
    provenance: tuple[SourceStamp, ...]
    gaps: tuple[str, ...] = ()
    conflicts: tuple[SourceConflict, ...] = ()
    analysis_authority: str = "read_only_evidence"
    trade_authority: str = "none"


@dataclass(frozen=True)
class IntradayMinuteView:
    time: str
    price: float
    avg_price: float | None
    volume: float | None
    amount: float | None


@dataclass(frozen=True)
class IntradayView:
    symbol: str
    qualified_symbol: str
    name: str | None
    market: str
    trade_date: str
    source: str
    pre_close: float | None
    open: float | None
    last: float | None
    high: float | None
    low: float | None
    day_pct: float | None
    vwap: float | None
    return_5m: float | None
    return_15m: float | None
    return_30m: float | None
    distance_to_vwap_pct: float | None
    distance_to_high_pct: float | None
    volume_acceleration: float | None
    minutes: tuple[IntradayMinuteView, ...]
    amount_unit: Literal["CNY", "unknown"] = "CNY"
    volume_unit: Literal["share", "lot", "unknown"] = "unknown"


@dataclass(frozen=True)
class IntradayCompareRow:
    symbol: str
    qualified_symbol: str
    name: str | None
    time: str | None
    return_from_open: float | None
    return_5m: float | None
    return_15m: float | None
    distance_to_vwap_pct: float | None
    distance_to_high_pct: float | None
    volume_acceleration: float | None
    relative_strength_vs_benchmark: float | None
    rank: int | None
    status: EvidenceStatus
    reason: str | None


@dataclass(frozen=True)
class IntradayCompareView:
    trade_date: str
    requested_time: str | None
    benchmark: str
    rows: tuple[IntradayCompareRow, ...]


@dataclass(frozen=True)
class MarketAmountView:
    market: str
    trade_date: str
    previous_trade_date: str
    time: str
    today_amount: float
    previous_day_same_time_amount: float
    delta: float
    delta_pct: float | None


@dataclass(frozen=True)
class TradeInput:
    trade_date: date
    time: time
    symbol: str
    side: TradeSide
    quantity: float
    price: float


@dataclass(frozen=True)
class TradeDecisionContext:
    evidence_time: str | None
    trade_price: float
    vwap: float | None
    distance_to_vwap_pct: float | None
    day_high: float | None
    day_low: float | None
    distance_to_high_pct: float | None
    distance_to_low_pct: float | None
    range_position_pct: float | None
    return_before_5m: float | None
    return_before_15m: float | None
    relative_strength_vs_benchmark: float | None
    current_minute_volume: float | None
    average_volume_previous_5m: float | None
    volume_acceleration: float | None
    above_vwap: bool | None
    near_day_high: bool | None
    volume_confirmation: bool | None
    trend: Literal["strong", "weak", "mixed", "unknown"]


@dataclass(frozen=True)
class TradeOutcome:
    return_after_5m: float | None
    return_after_15m: float | None
    return_after_30m: float | None
    mae_5m: float | None
    mae_15m: float | None
    mae_30m: float | None
    mfe_5m: float | None
    mfe_15m: float | None
    mfe_30m: float | None
    max_continue_up_5m: float | None
    max_continue_up_15m: float | None
    max_continue_up_30m: float | None
    max_down_5m: float | None
    max_down_15m: float | None
    max_down_30m: float | None
    pending_horizons: tuple[int, ...] = ()


@dataclass(frozen=True)
class TradeReviewItem:
    trade: TradeInput
    benchmark: str
    status: EvidenceStatus
    reason: str | None
    decision_context: TradeDecisionContext | None
    outcome: TradeOutcome | None
    provenance: tuple[SourceStamp, ...] = ()
    gaps: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeReviewView:
    trades: tuple[TradeReviewItem, ...]
    summary: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GetIntradayQuery:
    symbol: str
    trade_date: date
    as_of: time | None = None


@dataclass(frozen=True)
class CompareIntradayQuery:
    symbols: tuple[str, ...]
    benchmark: str
    trade_date: date
    as_of: time | None = None


@dataclass(frozen=True)
class MarketAmountQuery:
    trade_date: date
    as_of: time | None = None


@dataclass(frozen=True)
class ReviewTradesQuery:
    trades: tuple[TradeInput, ...]
    benchmark: str
    horizons_minutes: tuple[int, ...] = (5, 15, 30)


EvidenceQuery: TypeAlias = (
    GetIntradayQuery | CompareIntradayQuery | MarketAmountQuery | ReviewTradesQuery
)
