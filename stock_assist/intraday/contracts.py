"""Typed contracts for the point-in-time intraday radar.

The contracts deliberately accept ``None`` for unavailable account or market
fields.  Missing data is not zero, and every market observation carries both
the provider's source time and the local fetch time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
import math
from typing import Literal, Mapping


FreshnessState = Literal["fresh", "stale", "missing", "failed"]
OpportunityState = Literal["未出现", "观察", "正在形成", "确认", "过热", "失效"]
AlertSeverity = Literal["info", "yellow", "orange", "red"]


@dataclass(frozen=True)
class MinuteBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    source_time: datetime
    fetched_at: datetime
    source: str
    observation_id: str = ""
    trade_date: str = ""
    provider: str = ""

    @property
    def vwap(self) -> float | None:
        if self.volume <= 0:
            return None
        return self.amount / self.volume


@dataclass(frozen=True)
class PointQuote:
    symbol: str
    timestamp: datetime
    price: float
    pre_close: float | None
    open: float | None
    high: float | None
    low: float | None
    volume: float | None
    amount: float | None
    source_time: datetime
    fetched_at: datetime
    source: str
    phase: str = ""
    observation_id: str = ""
    trade_date: str = ""
    provider: str = ""


@dataclass(frozen=True)
class QuoteFreshness:
    symbol: str
    status: FreshnessState
    source_time: datetime | None
    fetched_at: datetime
    age_seconds: float | None
    max_age_seconds: int
    source: str
    gap_reason: str | None = None


@dataclass(frozen=True)
class HoldingSnapshot:
    symbol: str
    name: str
    shares: float | None
    available: float | None
    primary_theme_id: str
    price: float | None
    pre_close: float | None
    open: float | None
    market_value: float | None
    day_pnl: float | None
    return_pct: float | None
    return_from_open: float | None
    vwap_distance: float | None
    session_low: float | None
    no_new_low: bool | None
    higher_low: bool | None
    reclaimed_vwap: bool | None
    reclaimed_rebound_high: bool | None
    source_times: tuple[datetime, ...] = ()
    fetched_at: tuple[datetime, ...] = ()


@dataclass(frozen=True)
class ThemeSnapshot:
    theme_id: str
    representative_etf: str
    representative_symbols: tuple[str, ...]
    gap_pct: float | None
    return_pct: float | None
    return_from_open: float | None
    vwap_distance: float | None
    volume_ratio_same_time: float | None
    breadth_above_open: float | None
    breadth_above_vwap: float | None
    breadth_new_high: float | None
    leader_confirmation: bool | None
    external_mapping_return: float | None
    relative_strength: float | None
    state: str
    no_new_low: bool | None = None
    higher_low: bool | None = None
    reclaimed_vwap: bool | None = None
    reclaimed_rebound_high: bool | None = None
    source_times: tuple[datetime, ...] = ()
    fetched_at: tuple[datetime, ...] = ()
    price: float | None = None
    minutes_without_new_low: int | None = None
    component_source_times: Mapping[str, datetime | None] = field(default_factory=dict)
    component_freshness: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IntradaySnapshot:
    timestamp: datetime
    portfolio_value: float | None
    account_daily_pnl: float | None
    account_peak_daily_pnl: float | None
    pnl_giveback_ratio: float | None
    exposure_by_theme: Mapping[str, float | None]
    quote_freshness: tuple[QuoteFreshness, ...]
    theme_snapshots: tuple[ThemeSnapshot, ...]
    holding_snapshots: tuple[HoldingSnapshot, ...]
    source_times: tuple[datetime, ...]
    fetched_at: tuple[datetime, ...] = ()
    data_gaps: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntradayAlert:
    alert_id: str
    timestamp: datetime
    type: str
    severity: AlertSeverity
    target_type: str
    target_id: str
    title: str
    conclusion: str
    evidence: tuple[str, ...]
    action_state: str
    suggested_risk_change: Mapping[str, object]
    confirmation_conditions: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    reentry_conditions: tuple[str, ...]
    source_times: tuple[datetime, ...]
    rule_version: str
    fetched_at: tuple[datetime, ...] = ()
    event_state: str = "activated"


@dataclass(frozen=True)
class RuleEvaluation:
    alerts: tuple[IntradayAlert, ...] = ()
    opportunity_states: Mapping[str, OpportunityState] = field(default_factory=dict)
    state_updates: Mapping[str, object] = field(default_factory=dict)


def contract_dict(value: object) -> object:
    """Return a JSON-safe representation without converting unknown to zero."""

    if is_dataclass(value):
        return contract_dict(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): contract_dict(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [contract_dict(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
