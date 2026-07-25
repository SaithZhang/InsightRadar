"""Diagnostic-only energy-to-technology macro transmission states."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
import math
import statistics
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from stock_assist.risk_watch import DailySeries


StateValue = Literal["unavailable", "observe", "confirmed", "invalidated"]
SUPPLY_EVENT_TYPES = {"supply_disruption", "sanction", "producer_policy"}
NORMALIZATION_EVENT_TYPES = {"ceasefire", "supply_normalization"}
DEFAULT_MARKET_LAGS = {
    "brent": 1,
    "wti": 1,
    "us10y": 1,
    "sp500": 1,
    "qqq": 1,
    "sox": 1,
    "kospi": 0,
}


@dataclass(frozen=True)
class SourceRef:
    key: str
    url: str
    as_of: str
    fetched_at: str | None = None
    timezone: str = "UTC"


@dataclass(frozen=True)
class VerifiedMacroEvent:
    event_id: str
    event_type: str
    published_at: str
    confirmed_at: str
    active_from: date
    active_until: date | None
    verification_status: str
    source_url: str


@dataclass(frozen=True)
class ShadowState:
    status: StateValue
    triggered_rule_ids: tuple[str, ...]
    blocked_rule_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    gaps: tuple[str, ...]
    next_review_condition: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "triggered_rule_ids": list(self.triggered_rule_ids),
            "blocked_rule_ids": list(self.blocked_rule_ids),
            "evidence": list(self.evidence),
            "counter_evidence": list(self.counter_evidence),
            "gaps": list(self.gaps),
            "next_review_condition": self.next_review_condition,
        }


@dataclass(frozen=True)
class MacroTransmissionObservation:
    as_of: date
    energy_supply_shock: ShadowState
    duration_pressure: ShadowState
    korea_import_stress: ShadowState
    metrics: dict[str, float | None]
    sources: tuple[SourceRef, ...]
    calibration_status: str
    independent_event_count: int
    authority: str = "diagnostic_only"

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of.isoformat(),
            "energy_supply_shock": self.energy_supply_shock.to_dict(),
            "duration_pressure": self.duration_pressure.to_dict(),
            "korea_import_stress": self.korea_import_stress.to_dict(),
            "metrics": self.metrics,
            "sources": [
                {
                    "key": source.key,
                    "url": source.url,
                    "as_of": source.as_of,
                    "fetched_at": source.fetched_at,
                    "timezone": source.timezone,
                }
                for source in self.sources
            ],
            "calibration_status": self.calibration_status,
            "independent_event_count": self.independent_event_count,
            "authority": self.authority,
        }


@dataclass(frozen=True)
class MacroCalibrationResult:
    calibration_status: str
    independent_event_count: int
    in_sample_event_count: int
    out_of_sample_event_count: int
    outcomes: tuple[dict[str, object], ...]
    threshold_sensitivity: tuple[dict[str, object], ...]
    authority: str = "diagnostic_only"

    def to_dict(self) -> dict[str, object]:
        return {
            "calibration_status": self.calibration_status,
            "independent_event_count": self.independent_event_count,
            "in_sample_event_count": self.in_sample_event_count,
            "out_of_sample_event_count": self.out_of_sample_event_count,
            "outcomes": list(self.outcomes),
            "threshold_sensitivity": list(self.threshold_sensitivity),
            "authority": self.authority,
        }


def evaluate_macro_transmission(
    series: dict[str, DailySeries],
    as_of: date,
    config: dict[str, object],
    events: tuple[VerifiedMacroEvent, ...] = (),
    previous: MacroTransmissionObservation | None = None,
) -> MacroTransmissionObservation:
    """Evaluate independent macro shadow states without changing risk authority."""

    thresholds = config.get("thresholds")
    if not isinstance(thresholds, dict):
        thresholds = {}
    lags = _market_lags(config.get("market_calendar_lag_days"))
    oil_threshold = _number(thresholds.get("oil_5d_return"), 0.08)
    yield_threshold = _number(
        thresholds.get("yield_5d_change_pct_points"), 0.15
    )
    qqq_threshold = _number(
        thresholds.get("qqq_sp500_5d_relative"), -0.03
    )
    sox_threshold = _number(
        thresholds.get("sox_sp500_5d_relative"), -0.04
    )
    kospi_threshold = _number(
        thresholds.get("kospi_sp500_5d_relative"), -0.04
    )
    unwind_threshold = _number(
        thresholds.get("oil_unwind_5d_return"), -0.05
    )
    yield_divisor = _number(config.get("yield_divisor"), 10.0)

    metrics: dict[str, float | None] = {
        "brent_5d_return": _return(
            series.get("brent"),
            as_of,
            5,
            calendar_lag_days=lags["brent"],
        ),
        "wti_5d_return": _return(
            series.get("wti"),
            as_of,
            5,
            calendar_lag_days=lags["wti"],
        ),
        "us10y_5d_change_pct_points": _yield_change(
            series.get("us10y"),
            as_of,
            5,
            divisor=yield_divisor,
            calendar_lag_days=lags["us10y"],
        ),
        "qqq_sp500_5d_relative": _relative_return(
            series.get("qqq"),
            series.get("sp500"),
            as_of,
            5,
            left_lag_days=lags["qqq"],
            right_lag_days=lags["sp500"],
        ),
        "sox_sp500_5d_relative": _relative_return(
            series.get("sox"),
            series.get("sp500"),
            as_of,
            5,
            left_lag_days=lags["sox"],
            right_lag_days=lags["sp500"],
        ),
        "kospi_sp500_5d_relative": _relative_return(
            series.get("kospi"),
            series.get("sp500"),
            as_of,
            5,
            left_lag_days=lags["kospi"],
            right_lag_days=lags["sp500"],
        ),
    }

    cutoff = _evaluation_cutoff(as_of, config)
    max_age_days = _positive_int(config.get("event_max_age_days"), 20)
    eligible_events = _eligible_events(events, as_of, cutoff, max_age_days)
    official_supply = tuple(
        event
        for event in eligible_events
        if event.verification_status == "official"
        and event.event_type in SUPPLY_EVENT_TYPES
    )
    official_normalization = tuple(
        event
        for event in eligible_events
        if event.verification_status == "official"
        and event.event_type in NORMALIZATION_EVENT_TYPES
    )
    conflicting = tuple(
        event
        for event in eligible_events
        if event.verification_status == "conflicting"
    )

    energy = _energy_state(
        metrics,
        oil_threshold=oil_threshold,
        unwind_threshold=unwind_threshold,
        official_supply=official_supply,
        official_normalization=official_normalization,
        conflicting=conflicting,
        previous=previous,
    )
    duration = _duration_state(
        metrics,
        energy,
        series,
        yield_threshold=yield_threshold,
        qqq_threshold=qqq_threshold,
        sox_threshold=sox_threshold,
    )
    korea = _korea_state(
        metrics,
        energy,
        series,
        kospi_threshold=kospi_threshold,
    )
    sources = _source_refs(series, as_of, lags, config)
    return MacroTransmissionObservation(
        as_of=as_of,
        energy_supply_shock=energy,
        duration_pressure=duration,
        korea_import_stress=korea,
        metrics=metrics,
        sources=sources,
        calibration_status="not_replayed",
        independent_event_count=0,
    )


def replay_macro_transmission(
    series: dict[str, DailySeries],
    start: date,
    end: date,
    config: dict[str, object],
    events: tuple[VerifiedMacroEvent, ...],
) -> tuple[MacroTransmissionObservation, ...]:
    """Replay the shadow on completed source dates without forward inputs."""

    days = sorted(
        {
            point.day
            for item in series.values()
            for point in item.points
            if start <= point.day <= end
        }
    )
    observations: list[MacroTransmissionObservation] = []
    independent_count = 0
    prior_confirmed = False
    previous: MacroTransmissionObservation | None = None
    for day in days:
        current = evaluate_macro_transmission(
            series,
            day,
            config,
            events,
            previous=previous,
        )
        current_confirmed = current.duration_pressure.status == "confirmed"
        if current_confirmed and not prior_confirmed:
            independent_count += 1
        current = replace(
            current,
            independent_event_count=independent_count,
        )
        observations.append(current)
        previous = current
        prior_confirmed = current_confirmed
    return tuple(observations)


def calibrate_macro_transmission(
    observations: tuple[MacroTransmissionObservation, ...],
    series: dict[str, DailySeries],
    config: dict[str, object],
) -> MacroCalibrationResult:
    """Compare price-rule episodes; never promote or grant decision authority."""

    ordered = tuple(sorted(observations, key=lambda item: item.as_of))
    thresholds = config.get("thresholds")
    if not isinstance(thresholds, dict):
        thresholds = {}
    gap_sessions = _positive_int(config.get("episode_gap_sessions"), 20)
    minimum_events = _positive_int(
        config.get("minimum_promotion_events"),
        60,
    )
    horizons = _positive_int_list(config.get("forward_horizons"), (5, 20))
    anchor_days = _anchor_days(series, ordered)
    rule_events = {
        rule_set: _cluster_rule_events(
            ordered,
            rule_set,
            thresholds,
            anchor_days,
            gap_sessions,
            multiplier=1.0,
        )
        for rule_set in (
            "oil_only",
            "oil_plus_rates",
            "triple_confirmation",
        )
    }
    outcomes = _calibration_outcomes(
        rule_events,
        series,
        horizons,
        config,
    )
    multipliers = _positive_float_list(
        config.get("threshold_sensitivity_multipliers"),
        (0.8, 1.0, 1.2),
    )
    sensitivity = tuple(
        {
            "multiplier": multiplier,
            "independent_event_count": len(
                _cluster_rule_events(
                    ordered,
                    "triple_confirmation",
                    thresholds,
                    anchor_days,
                    gap_sessions,
                    multiplier=multiplier,
                )
            ),
        }
        for multiplier in multipliers
    )
    triple_events = rule_events["triple_confirmation"]
    out_of_sample_start = _optional_date(config.get("out_of_sample_start"))
    if out_of_sample_start is None:
        in_sample_count = len(triple_events)
        out_of_sample_count = 0
    else:
        in_sample_count = sum(
            event.as_of < out_of_sample_start for event in triple_events
        )
        out_of_sample_count = sum(
            event.as_of >= out_of_sample_start for event in triple_events
        )
    if len(triple_events) < minimum_events:
        status = "insufficient_events"
    elif out_of_sample_count == 0:
        status = "missing_out_of_sample_events"
    else:
        status = "shadow_calibrated_not_promoted"
    return MacroCalibrationResult(
        calibration_status=status,
        independent_event_count=len(triple_events),
        in_sample_event_count=in_sample_count,
        out_of_sample_event_count=out_of_sample_count,
        outcomes=outcomes,
        threshold_sensitivity=sensitivity,
    )


def _cluster_rule_events(
    observations: tuple[MacroTransmissionObservation, ...],
    rule_set: str,
    thresholds: dict[str, object],
    anchor_days: tuple[date, ...],
    gap_sessions: int,
    *,
    multiplier: float,
) -> tuple[MacroTransmissionObservation, ...]:
    positions = {day: index for index, day in enumerate(anchor_days)}
    selected: list[MacroTransmissionObservation] = []
    last_position: int | None = None
    for observation in observations:
        if not _matches_rule(
            observation.metrics,
            rule_set,
            thresholds,
            multiplier=multiplier,
        ):
            continue
        position = _position_on_or_before(anchor_days, positions, observation.as_of)
        if position is None:
            continue
        if last_position is None or position - last_position >= gap_sessions:
            selected.append(observation)
            last_position = position
    return tuple(selected)


def _matches_rule(
    metrics: dict[str, float | None],
    rule_set: str,
    thresholds: dict[str, object],
    *,
    multiplier: float,
) -> bool:
    oil_values = [
        value
        for value in (
            metrics.get("brent_5d_return"),
            metrics.get("wti_5d_return"),
        )
        if value is not None
    ]
    oil_threshold = _number(thresholds.get("oil_5d_return"), 0.08) * multiplier
    oil_match = bool(oil_values) and max(oil_values) >= oil_threshold
    if rule_set == "oil_only":
        return oil_match
    yield_change = metrics.get("us10y_5d_change_pct_points")
    yield_threshold = (
        _number(thresholds.get("yield_5d_change_pct_points"), 0.15)
        * multiplier
    )
    rates_match = (
        yield_change is not None and yield_change >= yield_threshold
    )
    if rule_set == "oil_plus_rates":
        return oil_match and rates_match
    qqq_relative = metrics.get("qqq_sp500_5d_relative")
    sox_relative = metrics.get("sox_sp500_5d_relative")
    qqq_threshold = (
        _number(thresholds.get("qqq_sp500_5d_relative"), -0.03)
        * multiplier
    )
    sox_threshold = (
        _number(thresholds.get("sox_sp500_5d_relative"), -0.04)
        * multiplier
    )
    return (
        rule_set == "triple_confirmation"
        and oil_match
        and rates_match
        and qqq_relative is not None
        and qqq_relative <= qqq_threshold
        and sox_relative is not None
        and sox_relative <= sox_threshold
    )


def _calibration_outcomes(
    rule_events: dict[str, tuple[MacroTransmissionObservation, ...]],
    series: dict[str, DailySeries],
    horizons: tuple[int, ...],
    config: dict[str, object],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    lags = _market_lags(config.get("market_calendar_lag_days"))
    for rule_set, events in rule_events.items():
        for asset in ("qqq", "sox", "kospi"):
            for horizon in horizons:
                absolute_values: list[float] = []
                relative_values: list[float] = []
                absolute_unavailable = 0
                relative_unavailable = 0
                for event in events:
                    absolute = _forward_return(
                        series.get(asset),
                        event.as_of,
                        horizon,
                        calendar_lag_days=lags.get(asset, 0),
                    )
                    benchmark = _forward_return(
                        series.get("sp500"),
                        event.as_of,
                        horizon,
                        calendar_lag_days=lags.get("sp500", 0),
                    )
                    if absolute is None:
                        absolute_unavailable += 1
                    else:
                        absolute_values.append(absolute)
                    if absolute is None or benchmark is None:
                        relative_unavailable += 1
                    else:
                        relative_values.append(absolute - benchmark)
                rows.append(
                    _outcome_row(
                        rule_set,
                        asset,
                        horizon,
                        "absolute",
                        absolute_values,
                        absolute_unavailable,
                        len(events),
                    )
                )
                rows.append(
                    _outcome_row(
                        rule_set,
                        asset,
                        horizon,
                        "relative_sp500",
                        relative_values,
                        relative_unavailable,
                        len(events),
                    )
                )
    return tuple(rows)


def _outcome_row(
    rule_set: str,
    asset: str,
    horizon: int,
    basis: str,
    values: list[float],
    unavailable: int,
    event_count: int,
) -> dict[str, object]:
    mean = statistics.fmean(values) if values else None
    median = statistics.median(values) if values else None
    hit_rate = (
        sum(value < 0 for value in values) / len(values)
        if values
        else None
    )
    interval: list[float] | None = None
    if len(values) >= 30 and mean is not None:
        standard_error = statistics.stdev(values) / math.sqrt(len(values))
        interval = [mean - 1.96 * standard_error, mean + 1.96 * standard_error]
    return {
        "rule_set": rule_set,
        "asset": asset,
        "horizon_sessions": horizon,
        "basis": basis,
        "event_count": event_count,
        "sample_size": len(values),
        "unavailable_outcomes": unavailable,
        "mean": mean,
        "median": median,
        "hit_rate_below_zero": hit_rate,
        "max_drawdown": min(values) if values else None,
        "confidence_interval_95": interval,
    }


def _forward_return(
    series: DailySeries | None,
    as_of: date,
    horizon: int,
    *,
    calendar_lag_days: int,
) -> float | None:
    if series is None:
        return None
    cutoff = as_of - timedelta(days=calendar_lag_days)
    points = sorted(
        (
            point
            for point in series.points
            if point.close > 0
        ),
        key=lambda point: point.day,
    )
    baseline = [point for point in points if point.day <= cutoff]
    if not baseline:
        return None
    baseline_point = baseline[-1]
    future = [point for point in points if point.day > baseline_point.day]
    if len(future) < horizon:
        return None
    return future[horizon - 1].close / baseline_point.close - 1


def _anchor_days(
    series: dict[str, DailySeries],
    observations: tuple[MacroTransmissionObservation, ...],
) -> tuple[date, ...]:
    anchor = series.get("sp500")
    if anchor is not None:
        days = sorted({point.day for point in anchor.points})
    else:
        days = sorted(
            {
                point.day
                for item in series.values()
                for point in item.points
            }
        )
    if days:
        return tuple(days)
    return tuple(item.as_of for item in observations)


def _position_on_or_before(
    anchor_days: tuple[date, ...],
    positions: dict[date, int],
    target: date,
) -> int | None:
    if target in positions:
        return positions[target]
    prior = [day for day in anchor_days if day <= target]
    return positions[prior[-1]] if prior else None


def _energy_state(
    metrics: dict[str, float | None],
    *,
    oil_threshold: float,
    unwind_threshold: float,
    official_supply: tuple[VerifiedMacroEvent, ...],
    official_normalization: tuple[VerifiedMacroEvent, ...],
    conflicting: tuple[VerifiedMacroEvent, ...],
    previous: MacroTransmissionObservation | None,
) -> ShadowState:
    oil_values = [
        value
        for value in (
            metrics.get("brent_5d_return"),
            metrics.get("wti_5d_return"),
        )
        if value is not None
    ]
    if not oil_values:
        return _unavailable(
            ("missing_series:brent_or_wti",),
            "补齐至少一条已完成收盘的原油序列。",
        )
    oil_shock = max(oil_values) >= oil_threshold
    broad_unwind = max(oil_values) <= unwind_threshold
    prior_confirmed = (
        previous is not None
        and previous.energy_supply_shock.status == "confirmed"
    )
    if (
        prior_confirmed
        and official_normalization
        and broad_unwind
        and not conflicting
    ):
        return ShadowState(
            status="invalidated",
            triggered_rule_ids=("official_normalization_and_oil_unwind",),
            blocked_rule_ids=(),
            evidence=tuple(
                [f"oil_5d_max={max(oil_values):.4f}"]
                + [event.source_url for event in official_normalization]
            ),
            counter_evidence=(),
            gaps=(),
            next_review_condition="继续观察科技与韩国相对价格是否独立修复。",
        )
    if not oil_shock:
        return ShadowState(
            status="observe",
            triggered_rule_ids=(),
            blocked_rule_ids=("oil_shock_threshold_not_met",),
            evidence=(f"oil_5d_max={max(oil_values):.4f}",),
            counter_evidence=("油价尚未达到供给冲击观察阈值。",),
            gaps=(),
            next_review_condition="等待油价阈值或新增一手供给证据。",
        )
    if conflicting:
        return ShadowState(
            status="observe",
            triggered_rule_ids=("oil_shock_observed",),
            blocked_rule_ids=("conflicting_primary_evidence",),
            evidence=(f"oil_5d_max={max(oil_values):.4f}",),
            counter_evidence=tuple(event.source_url for event in conflicting),
            gaps=(),
            next_review_condition="等待冲突的一手来源得到解决。",
        )
    if official_supply:
        return ShadowState(
            status="confirmed",
            triggered_rule_ids=("verified_supply_and_oil_shock",),
            blocked_rule_ids=(),
            evidence=tuple(
                [f"oil_5d_max={max(oil_values):.4f}"]
                + [event.source_url for event in official_supply]
            ),
            counter_evidence=(),
            gaps=(),
            next_review_condition="观察供给事件期限、停火或油价回落。",
        )
    return ShadowState(
        status="observe",
        triggered_rule_ids=("oil_shock_observed",),
        blocked_rule_ids=("missing_verified_supply_event",),
        evidence=(f"oil_5d_max={max(oil_values):.4f}",),
        counter_evidence=("需求推动或原因未知仍是替代解释。",),
        gaps=("missing_verified_supply_event",),
        next_review_condition="需要一手供给事件确认，不能仅凭油价升级。",
    )


def _duration_state(
    metrics: dict[str, float | None],
    energy: ShadowState,
    series: dict[str, DailySeries],
    *,
    yield_threshold: float,
    qqq_threshold: float,
    sox_threshold: float,
) -> ShadowState:
    required = {
        "us10y": metrics.get("us10y_5d_change_pct_points"),
        "sp500_or_qqq": metrics.get("qqq_sp500_5d_relative"),
        "sp500_or_sox": metrics.get("sox_sp500_5d_relative"),
    }
    gaps = tuple(
        dict.fromkeys(
            [
                gap
                for metric_key, required_keys in (
                    ("us10y", ("us10y",)),
                    ("sp500_or_qqq", ("qqq", "sp500")),
                    ("sp500_or_sox", ("sox", "sp500")),
                )
                for gap in _metric_gaps(
                    required[metric_key],
                    required_keys,
                    series,
                )
            ]
        )
    )
    if gaps:
        return _unavailable(
            tuple(dict.fromkeys(gaps)),
            "补齐利率、标普、QQQ 与 SOX 的已完成收盘。",
        )
    if energy.status == "invalidated":
        return ShadowState(
            status="observe",
            triggered_rule_ids=(),
            blocked_rule_ids=(
                "technology_repair_requires_relative_price_confirmation",
            ),
            evidence=(),
            counter_evidence=("能源冲击失效不等于科技自动修复。",),
            gaps=(),
            next_review_condition="等待 QQQ 与 SOX 相对标普价格修复。",
        )
    yield_change = required["us10y"]
    qqq_relative = required["sp500_or_qqq"]
    sox_relative = required["sp500_or_sox"]
    confirmed = (
        energy.status == "confirmed"
        and yield_change is not None
        and yield_change >= yield_threshold
        and qqq_relative is not None
        and qqq_relative <= qqq_threshold
        and sox_relative is not None
        and sox_relative <= sox_threshold
    )
    if confirmed:
        return ShadowState(
            status="confirmed",
            triggered_rule_ids=("oil_rates_tech_triple_confirmation",),
            blocked_rule_ids=(),
            evidence=(
                f"us10y_5d_change={yield_change:.4f}",
                f"qqq_sp500_5d_relative={qqq_relative:.4f}",
                f"sox_sp500_5d_relative={sox_relative:.4f}",
            ),
            counter_evidence=(),
            gaps=(),
            next_review_condition="观察利率回落和科技相对价格修复。",
        )
    blocked: list[str] = []
    if energy.status != "confirmed":
        blocked.append("energy_supply_shock_not_confirmed")
    if yield_change is not None and yield_change < yield_threshold:
        blocked.append("yield_pressure_not_confirmed")
    if qqq_relative is not None and qqq_relative > qqq_threshold:
        blocked.append("qqq_relative_weakness_not_confirmed")
    if sox_relative is not None and sox_relative > sox_threshold:
        blocked.append("sox_relative_weakness_not_confirmed")
    return ShadowState(
        status="observe",
        triggered_rule_ids=(),
        blocked_rule_ids=tuple(blocked),
        evidence=(),
        counter_evidence=tuple(blocked),
        gaps=(),
        next_review_condition="等待能源、利率和两条科技相对价格共同确认。",
    )


def _korea_state(
    metrics: dict[str, float | None],
    energy: ShadowState,
    series: dict[str, DailySeries],
    *,
    kospi_threshold: float,
) -> ShadowState:
    relative = metrics.get("kospi_sp500_5d_relative")
    if relative is None:
        return _unavailable(
            _metric_gaps(relative, ("kospi", "sp500"), series),
            "补齐 KOSPI 与标普已完成收盘。",
        )
    if energy.status == "confirmed" and relative <= kospi_threshold:
        return ShadowState(
            status="confirmed",
            triggered_rule_ids=("verified_energy_and_korea_relative_weakness",),
            blocked_rule_ids=(),
            evidence=(f"kospi_sp500_5d_relative={relative:.4f}",),
            counter_evidence=(),
            gaps=(),
            next_review_condition="观察能源进口成本与 KOSPI 相对价格修复。",
        )
    blocked = []
    if energy.status != "confirmed":
        blocked.append("verified_energy_or_import_evidence_missing")
    if relative > kospi_threshold:
        blocked.append("korea_relative_weakness_not_confirmed")
    return ShadowState(
        status="observe",
        triggered_rule_ids=(),
        blocked_rule_ids=tuple(blocked),
        evidence=(f"kospi_sp500_5d_relative={relative:.4f}",),
        counter_evidence=tuple(blocked),
        gaps=(),
        next_review_condition="等待能源证据与韩国相对弱势同时成立。",
    )


def _unavailable(gaps: tuple[str, ...], next_review: str) -> ShadowState:
    return ShadowState(
        status="unavailable",
        triggered_rule_ids=(),
        blocked_rule_ids=("required_data_unavailable",),
        evidence=(),
        counter_evidence=(),
        gaps=gaps,
        next_review_condition=next_review,
    )


def _metric_gaps(
    metric: float | None,
    required_keys: tuple[str, ...],
    series: dict[str, DailySeries],
) -> tuple[str, ...]:
    if metric is not None:
        return ()
    missing = tuple(
        f"missing_series:{key}"
        for key in required_keys
        if key not in series
    )
    if missing:
        return missing
    return (f"insufficient_history:{'_or_'.join(required_keys)}",)


def _eligible_events(
    events: tuple[VerifiedMacroEvent, ...],
    as_of: date,
    cutoff: datetime,
    max_age_days: int,
) -> tuple[VerifiedMacroEvent, ...]:
    eligible: list[VerifiedMacroEvent] = []
    for event in events:
        if event.verification_status not in {"official", "conflicting"}:
            continue
        try:
            confirmed_at = _aware_datetime(event.confirmed_at)
        except ValueError:
            continue
        if confirmed_at > cutoff.astimezone(confirmed_at.tzinfo):
            continue
        if event.active_from > as_of:
            continue
        if event.active_until is not None and event.active_until < as_of:
            continue
        if (as_of - event.active_from).days > max_age_days:
            continue
        eligible.append(event)
    return tuple(eligible)


def _evaluation_cutoff(as_of: date, config: dict[str, object]) -> datetime:
    timezone_name = str(config.get("evaluation_timezone") or "Asia/Shanghai")
    try:
        evaluation_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        evaluation_timezone = ZoneInfo("UTC")
    time_text = str(config.get("evaluation_time") or "15:30:00")
    try:
        clock = time.fromisoformat(time_text)
    except ValueError:
        clock = time(15, 30)
    return datetime.combine(as_of, clock, tzinfo=evaluation_timezone)


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("event timestamp must include timezone")
    return parsed


def _market_lags(value: object) -> dict[str, int]:
    configured = value if isinstance(value, dict) else {}
    return {
        key: max(0, _int_value(configured.get(key), default))
        for key, default in DEFAULT_MARKET_LAGS.items()
    }


def _source_refs(
    series: dict[str, DailySeries],
    as_of: date,
    lags: dict[str, int],
    config: dict[str, object],
) -> tuple[SourceRef, ...]:
    timezone_name = str(config.get("evaluation_timezone") or "Asia/Shanghai")
    refs: list[SourceRef] = []
    for key in sorted(series):
        item = series[key]
        cutoff = as_of - timedelta(days=lags.get(key, 0))
        known = [point.day for point in item.points if point.day <= cutoff]
        refs.append(
            SourceRef(
                key=key,
                url=item.source,
                as_of=max(known).isoformat() if known else "",
                timezone=timezone_name,
            )
        )
    return tuple(refs)


def _close_on_or_before(
    series: DailySeries,
    as_of: date,
    *,
    calendar_lag_days: int,
) -> list[float]:
    cutoff = as_of - timedelta(days=calendar_lag_days)
    return [
        point.close
        for point in series.points
        if point.day <= cutoff and point.close > 0
    ]


def _return(
    series: DailySeries | None,
    as_of: date,
    sessions: int,
    *,
    calendar_lag_days: int,
) -> float | None:
    if series is None:
        return None
    closes = _close_on_or_before(
        series,
        as_of,
        calendar_lag_days=calendar_lag_days,
    )
    if len(closes) <= sessions or closes[-sessions - 1] <= 0:
        return None
    return closes[-1] / closes[-sessions - 1] - 1


def _yield_change(
    series: DailySeries | None,
    as_of: date,
    sessions: int,
    *,
    divisor: float,
    calendar_lag_days: int,
) -> float | None:
    if series is None or divisor <= 0:
        return None
    closes = _close_on_or_before(
        series,
        as_of,
        calendar_lag_days=calendar_lag_days,
    )
    if len(closes) <= sessions:
        return None
    return closes[-1] / divisor - closes[-sessions - 1] / divisor


def _relative_return(
    left: DailySeries | None,
    right: DailySeries | None,
    as_of: date,
    sessions: int,
    *,
    left_lag_days: int,
    right_lag_days: int,
) -> float | None:
    left_return = _return(
        left,
        as_of,
        sessions,
        calendar_lag_days=left_lag_days,
    )
    right_return = _return(
        right,
        as_of,
        sessions,
        calendar_lag_days=right_lag_days,
    )
    if left_return is None or right_return is None:
        return None
    return left_return - right_return


def _number(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_value(value: object, default: int) -> int:
    if type(value) is int:
        return value
    return default


def _positive_int(value: object, default: int) -> int:
    parsed = _int_value(value, default)
    return parsed if parsed > 0 else default


def _positive_int_list(
    value: object,
    default: tuple[int, ...],
) -> tuple[int, ...]:
    if not isinstance(value, list):
        return default
    parsed = tuple(
        item
        for item in value
        if type(item) is int and item > 0
    )
    return parsed or default


def _positive_float_list(
    value: object,
    default: tuple[float, ...],
) -> tuple[float, ...]:
    if not isinstance(value, list):
        return default
    parsed: list[float] = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if number > 0:
            parsed.append(number)
    return tuple(parsed) or default


def _optional_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
