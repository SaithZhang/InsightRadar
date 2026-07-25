"""Leakage-aware daily market and portfolio risk temperature engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import math
import statistics
from typing import Iterable


LEVEL_ORDER = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
LEVEL_LABELS = {"green": "绿灯", "yellow": "黄灯", "orange": "橙灯", "red": "红灯"}
RISK_BUDGETS = {
    "green": {"total_exposure_cap_pct": 90, "high_beta_cap_pct": 50},
    "yellow": {"total_exposure_cap_pct": 75, "high_beta_cap_pct": 35},
    "orange": {"total_exposure_cap_pct": 50, "high_beta_cap_pct": 25},
    "red": {"total_exposure_cap_pct": 30, "high_beta_cap_pct": 15},
}


@dataclass(frozen=True)
class DailyPoint:
    day: date
    close: float
    amount: float | None = None


@dataclass(frozen=True)
class DailySeries:
    key: str
    name: str
    source: str
    points: tuple[DailyPoint, ...]


@dataclass(frozen=True)
class PortfolioRiskProfile:
    total_exposure_pct: float | None = None
    holding_weights_pct: tuple[float, ...] = ()
    high_beta_exposure_pct: float | None = None
    fomo_flag: bool = False
    long_horizon_pricing_flag: bool = False
    retail_euphoria_flag: bool = False
    portfolio_effective_from: date | None = None
    behavior_effective_from: date | None = None
    source: str = "未提供"


@dataclass(frozen=True)
class Signal:
    family: str
    key: str
    points: int
    detail: str


@dataclass
class RiskSnapshot:
    day: date
    score: int
    raw_level: str
    level: str
    budget_level: str
    coverage_ratio: float
    active_families: int
    signals: list[Signal] = field(default_factory=list)
    metrics: dict[str, dict[str, float | str | None]] = field(default_factory=dict)
    data_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        budget = RISK_BUDGETS[self.budget_level]
        return {
            "date": self.day.isoformat(),
            "score": self.score,
            "raw_level": self.raw_level,
            "level": self.level,
            "level_label": LEVEL_LABELS[self.level],
            "budget_level": self.budget_level,
            "budget_level_label": LEVEL_LABELS[self.budget_level],
            "coverage_ratio": round(self.coverage_ratio, 3),
            "active_families": self.active_families,
            "risk_budget": budget,
            "signals": [signal.__dict__ for signal in self.signals],
            "metrics": self.metrics,
            "data_gaps": self.data_gaps,
        }


def replay_risk(
    series: dict[str, DailySeries],
    profile: PortfolioRiskProfile,
    *,
    start: date,
    end: date,
) -> list[RiskSnapshot]:
    """Replay daily signals using only observations available on each date."""

    anchor = series.get("all_a") or series.get("csi1000") or series.get("shanghai")
    if anchor is None:
        raise ValueError("risk replay requires all_a, csi1000, or shanghai series")
    days = [point.day for point in anchor.points if start <= point.day <= end]
    snapshots: list[RiskSnapshot] = []
    for day in days:
        snapshot = score_risk(series, profile, day)
        snapshot.level = _confirm_level(snapshot, snapshots)
        snapshot.budget_level = _budget_level(snapshot, snapshots)
        snapshots.append(snapshot)
    return snapshots


def score_risk(
    series: dict[str, DailySeries],
    profile: PortfolioRiskProfile,
    as_of: date,
) -> RiskSnapshot:
    metrics: dict[str, dict[str, float | str | None]] = {}
    gaps: list[str] = []
    for key, item in series.items():
        metric = _metric_as_of(item, as_of)
        if metric is None:
            gaps.append(f"{item.name}截至{as_of.isoformat()}少于25根有效日线")
        else:
            metrics[key] = metric

    portfolio_active = profile.portfolio_effective_from is None or as_of >= profile.portfolio_effective_from
    behavior_active = profile.behavior_effective_from is None or as_of >= profile.behavior_effective_from
    active_profile = PortfolioRiskProfile(
        total_exposure_pct=profile.total_exposure_pct if portfolio_active else None,
        holding_weights_pct=profile.holding_weights_pct if portfolio_active else (),
        high_beta_exposure_pct=profile.high_beta_exposure_pct if portfolio_active else None,
        fomo_flag=profile.fomo_flag if behavior_active else False,
        long_horizon_pricing_flag=profile.long_horizon_pricing_flag if behavior_active else False,
        retail_euphoria_flag=profile.retail_euphoria_flag if behavior_active else False,
        portfolio_effective_from=profile.portfolio_effective_from,
        behavior_effective_from=profile.behavior_effective_from,
        source=profile.source,
    )
    signals: list[Signal] = []
    signals.extend(_breadth_signals(metrics))
    signals.extend(_a_share_structure_signals(metrics))
    signals.extend(_global_signals(metrics))
    signals.extend(_crowding_signals(metrics, active_profile))
    signals.extend(_portfolio_signals(active_profile))
    score = sum(signal.points for signal in signals)
    expected = {"all_a", "shanghai", "chinext", "star50", "csi1000", "sp500", "qqq", "sox", "kospi", "kosdaq", "nikkei"}
    coverage_ratio = len(expected.intersection(metrics)) / len(expected)
    active_families = len({signal.family for signal in signals if signal.points > 0})
    raw_level = _raw_level(score)
    if coverage_ratio < 0.6 and LEVEL_ORDER[raw_level] > LEVEL_ORDER["yellow"]:
        gaps.append("有效行情覆盖低于60%，风险等级上限收缩为黄灯")
        raw_level = "yellow"
    if active_families < 2 and LEVEL_ORDER[raw_level] > LEVEL_ORDER["yellow"]:
        gaps.append("少于两个独立信号家族，不能确认橙灯或红灯")
        raw_level = "yellow"
    if active_families < 3 and raw_level == "red":
        gaps.append("少于三个独立信号家族，红灯降为橙灯")
        raw_level = "orange"
    if "all_a" not in metrics:
        gaps.append("同花顺全A缺失；等权广度信号未参与计分，数据来自同花顺问财时会明确标注")
    if active_profile.total_exposure_pct is None:
        gaps.append("组合总仓位未知；仅计算市场风险，不推断账户风险")
    return RiskSnapshot(
        day=as_of,
        score=score,
        raw_level=raw_level,
        level=raw_level,
        budget_level=raw_level,
        coverage_ratio=coverage_ratio,
        active_families=active_families,
        signals=signals,
        metrics=metrics,
        data_gaps=gaps,
    )


def _metric_as_of(series: DailySeries, as_of: date) -> dict[str, float | str | None] | None:
    points = [point for point in series.points if point.day <= as_of and point.close > 0]
    if len(points) < 25:
        return None
    closes = [point.close for point in points]
    returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))]
    ma20 = statistics.fmean(closes[-20:])
    ma20_prior = statistics.fmean(closes[-25:-5])
    ma60 = statistics.fmean(closes[-60:]) if len(closes) >= 60 else None
    amount_values = [point.amount for point in points[-60:] if point.amount is not None and point.amount > 0]
    amount_percentile = None
    if len(amount_values) >= 20 and points[-1].amount is not None:
        amount_percentile = sum(value <= points[-1].amount for value in amount_values) / len(amount_values)
    vol20 = statistics.pstdev(returns[-20:]) * math.sqrt(252) if len(returns) >= 20 else None
    prior_vol20 = statistics.pstdev(returns[-40:-20]) * math.sqrt(252) if len(returns) >= 40 else None
    recent_returns = returns[-10:]
    recent_returns_20 = returns[-20:]
    prior_shock_returns = returns[-30:-10] if len(returns) >= 30 else returns[:-10]
    prior_daily_vol = (
        statistics.pstdev(prior_shock_returns)
        if len(prior_shock_returns) >= 10
        else None
    )
    shock_z_10d = (
        min(recent_returns) / prior_daily_vol
        if recent_returns and prior_daily_vol and prior_daily_vol > 0
        else None
    )
    sigma_down_days_10d = (
        float(sum(value <= -2.5 * prior_daily_vol for value in recent_returns))
        if recent_returns and prior_daily_vol and prior_daily_vol > 0
        else None
    )
    return {
        "name": series.name,
        "source": series.source,
        "as_of": points[-1].day.isoformat(),
        "close": round(closes[-1], 4),
        "day_return": closes[-1] / closes[-2] - 1,
        "return_5d": closes[-1] / closes[-6] - 1 if len(closes) >= 6 else None,
        "return_20d": closes[-1] / closes[-21] - 1 if len(closes) >= 21 else None,
        "drawdown_20d": closes[-1] / max(closes[-20:]) - 1,
        "ma20_gap": closes[-1] / ma20 - 1,
        "ma20_slope_5d": ma20 / ma20_prior - 1,
        "ma60_gap": closes[-1] / ma60 - 1 if ma60 else None,
        "vol20": vol20,
        "vol20_ratio": vol20 / prior_vol20 if vol20 and prior_vol20 and prior_vol20 > 0 else None,
        "min_day_return_10d": min(recent_returns) if recent_returns else None,
        "large_down_days_10d": float(sum(value <= -0.04 for value in recent_returns)),
        "circuit_down_days_20d": float(sum(value <= -0.08 for value in recent_returns_20)),
        "shock_z_10d": shock_z_10d,
        "sigma_down_days_10d": sigma_down_days_10d,
        "amount_percentile_60d": amount_percentile,
    }


def _breadth_signals(metrics: dict[str, dict[str, float | str | None]]) -> list[Signal]:
    item = metrics.get("all_a")
    if not item:
        return []
    signals: list[Signal] = []
    if _number(item, "ma20_gap") < 0:
        signals.append(Signal("breadth", "all_a_below_ma20", 5, "同花顺全A跌破MA20"))
    slope = _number(item, "ma20_slope_5d")
    if slope <= -0.015:
        signals.append(Signal("breadth", "all_a_ma20_falling", 6, f"全A MA20五日斜率{slope:.1%}"))
    drawdown = _number(item, "drawdown_20d")
    if drawdown <= -0.08:
        signals.append(Signal("breadth", "all_a_drawdown", 10, f"全A距20日高点{drawdown:.1%}"))
    elif drawdown <= -0.05:
        signals.append(Signal("breadth", "all_a_drawdown", 6, f"全A距20日高点{drawdown:.1%}"))
    return20 = _number(item, "return_20d")
    if return20 <= -0.10:
        signals.append(Signal("breadth", "all_a_return_20d", 9, f"全A 20日收益{return20:.1%}"))
    elif return20 <= -0.06:
        signals.append(Signal("breadth", "all_a_return_20d", 6, f"全A 20日收益{return20:.1%}"))
    day_return = _number(item, "day_return")
    if day_return <= -0.025:
        signals.append(Signal("breadth", "all_a_heavy_down_day", 4, f"全A单日{day_return:.1%}"))
    return _cap_family(signals, 30)


def _a_share_structure_signals(metrics: dict[str, dict[str, float | str | None]]) -> list[Signal]:
    growth = [metrics[key] for key in ("chinext", "star50", "csi1000") if key in metrics]
    if not growth:
        return []
    signals: list[Signal] = []
    below20 = sum(_number(item, "ma20_gap") < 0 for item in growth)
    below60 = sum(item.get("ma60_gap") is not None and _number(item, "ma60_gap") < 0 for item in growth)
    if below20 >= 2:
        signals.append(Signal("a_share_structure", "growth_below_ma20", 3 * below20, f"{below20}/3个成长/小盘指数低于MA20"))
    if below60 >= 2:
        signals.append(Signal("a_share_structure", "growth_below_ma60", 2 * below60, f"{below60}/3个成长/小盘指数低于MA60"))
    all_a = metrics.get("all_a")
    shanghai = metrics.get("shanghai")
    if all_a and shanghai:
        lag = _number(all_a, "return_20d") - _number(shanghai, "return_20d")
        if lag <= -0.06:
            signals.append(Signal("a_share_structure", "equal_weight_lag", 6, f"全A 20日落后上证{lag:.1%}"))
        elif lag <= -0.03:
            signals.append(Signal("a_share_structure", "equal_weight_lag", 4, f"全A 20日落后上证{lag:.1%}"))
    growth_return5 = statistics.median(_number(item, "return_5d") for item in growth)
    if growth_return5 <= -0.04:
        signals.append(Signal("a_share_structure", "growth_short_term_drop", 4, f"成长指数5日收益中位数{growth_return5:.1%}"))
    return _cap_family(signals, 20)


def _global_signals(metrics: dict[str, dict[str, float | str | None]]) -> list[Signal]:
    signals: list[Signal] = []
    shock_regions: set[str] = set()
    shock_specs = {
        "sp500": ("美国", -0.035),
        "qqq": ("美国", -0.045),
        "sox": ("美国", -0.060),
        "nikkei": ("日本", -0.050),
    }
    for key, (region, absolute_floor) in shock_specs.items():
        item = metrics.get(key)
        if not item:
            continue
        minimum = _number(item, "min_day_return_10d")
        shock_z = _number(item, "shock_z_10d", default=0)
        sigma_days = _number(item, "sigma_down_days_10d", default=0)
        is_shock = minimum <= absolute_floor or (shock_z <= -3.5 and minimum <= absolute_floor * 0.6)
        if is_shock:
            shock_regions.add(region)
            signals.append(
                Signal(
                    "global",
                    f"{key}_shock_window",
                    5,
                    f"{item.get('name')}过去10个交易日出现{minimum:.1%}冲击（波动标准分{shock_z:.1f}）",
                )
            )
        if sigma_days >= 2 and minimum <= absolute_floor * 0.6:
            shock_regions.add(region)
            signals.append(
                Signal(
                    "global",
                    f"{key}_repeat_shock",
                    3,
                    f"{item.get('name')}10个交易日内至少{sigma_days:.0f}次超过2.5倍常态波动的下跌",
                )
            )
    kospi = metrics.get("kospi")
    kosdaq = metrics.get("kosdaq")
    if kospi and _number(kospi, "min_day_return_10d") <= -0.08:
        signals.append(
            Signal(
                "global",
                "korea_circuit_breaker_window",
                8,
                f"韩国KOSPI过去10个交易日出现{_number(kospi, 'min_day_return_10d'):.1%}冲击，进入熔断事件观察窗",
            )
        )
    if kospi and _number(kospi, "circuit_down_days_20d", default=0) >= 2:
        signals.append(
            Signal(
                "global",
                "korea_second_circuit_breaker",
                5,
                "韩国KOSPI在20个交易日内第二次出现超过8%的单日冲击",
            )
        )
    korea_large_down_days = max(
        _number(kospi or {}, "large_down_days_10d", default=0),
        _number(kosdaq or {}, "large_down_days_10d", default=0),
    )
    if korea_large_down_days >= 2:
        signals.append(
            Signal(
                "global",
                "korea_repeat_shock",
                4,
                f"韩国主要指数10个交易日内至少{korea_large_down_days:.0f}次单日下跌超过4%",
            )
        )
    if kosdaq and _number(kosdaq, "min_day_return_10d") <= -0.065:
        signals.append(
            Signal(
                "global",
                "kosdaq_liquidity_shock",
                3,
                f"韩国KOSDAQ过去10个交易日最大单日跌幅{_number(kosdaq, 'min_day_return_10d'):.1%}",
            )
        )
    if any(signal.key.startswith("korea_") or signal.key == "kosdaq_liquidity_shock" for signal in signals):
        shock_regions.add("韩国")
    if "美国" in shock_regions and ({"日本", "韩国"} & shock_regions):
        signals.append(
            Signal(
                "global",
                "cross_region_shock",
                4,
                "美国与亚洲市场冲击窗口同时生效，跨市场风险共振",
            )
        )
    candidates: list[tuple[str, dict[str, float | str | None]]] = [
        (key, metrics[key]) for key in ("sp500", "qqq", "sox", "kospi", "kosdaq", "nikkei") if key in metrics
    ]
    weak: list[tuple[str, dict[str, float | str | None]]] = []
    for key, item in candidates:
        if (
            _number(item, "ma20_gap") < 0
            or _number(item, "drawdown_20d") <= -0.05
            or _number(item, "vol20_ratio", default=0) >= 1.4
        ):
            weak.append((key, item))
    signals.extend(
        Signal(
            "global",
            f"{key}_risk",
            3,
            f"{item.get('name')}低于MA20/回撤或波动率扩张",
        )
        for key, item in weak
    )
    strong = [
        (key, item)
        for key, item in weak
        if item.get("ma60_gap") is not None
        and _number(item, "ma60_gap") < 0
        and _number(item, "drawdown_20d") <= -0.08
    ]
    signals.extend(
        Signal("global", f"{key}_strong_risk", 2, f"{item.get('name')}同时跌破MA60且20日回撤超过8%")
        for key, item in strong
    )
    if len(weak) < 2 and not any(signal.key.startswith("korea_") for signal in signals):
        return _cap_family(signals, 3)
    return _cap_family(signals, 20)


def _crowding_signals(
    metrics: dict[str, dict[str, float | str | None]], profile: PortfolioRiskProfile
) -> list[Signal]:
    signals: list[Signal] = []
    item = metrics.get("all_a")
    if item:
        percentile = item.get("amount_percentile_60d")
        if isinstance(percentile, (int, float)) and percentile >= 0.9 and _number(item, "drawdown_20d") >= -0.05:
            signals.append(Signal("crowding", "turnover_euphoria", 6, f"全A成交额处于60日{percentile:.0%}分位且仍靠近高位"))
        elif isinstance(percentile, (int, float)) and percentile >= 0.8 and _number(item, "drawdown_20d") >= -0.05:
            signals.append(Signal("crowding", "turnover_euphoria", 4, f"全A成交额处于60日{percentile:.0%}分位且仍靠近高位"))
    manual_flags = [
        (profile.fomo_flag, "self_fomo", "本人出现FOMO或追涨冲动"),
        (profile.long_horizon_pricing_flag, "long_horizon_pricing", "市场集中交易远期叙事/2030业绩"),
        (profile.retail_euphoria_flag, "retail_euphoria", "新手普遍盈利和平台亢奋特征"),
    ]
    signals.extend(Signal("crowding", key, 2, detail) for active, key, detail in manual_flags if active)
    return _cap_family(signals, 15)


def _portfolio_signals(profile: PortfolioRiskProfile) -> list[Signal]:
    signals: list[Signal] = []
    exposure = profile.total_exposure_pct
    if exposure is not None:
        if exposure >= 80:
            signals.append(Signal("portfolio", "high_total_exposure", 6, f"总仓位{exposure:.1f}%"))
        elif exposure >= 65:
            signals.append(Signal("portfolio", "high_total_exposure", 4, f"总仓位{exposure:.1f}%"))
        elif exposure >= 50:
            signals.append(Signal("portfolio", "high_total_exposure", 2, f"总仓位{exposure:.1f}%"))
    weights = sorted((weight for weight in profile.holding_weights_pct if weight > 0), reverse=True)
    if weights:
        if weights[0] >= 25:
            signals.append(Signal("portfolio", "top1_concentration", 4, f"第一大持仓{weights[0]:.1f}%"))
        elif weights[0] >= 18:
            signals.append(Signal("portfolio", "top1_concentration", 2, f"第一大持仓{weights[0]:.1f}%"))
        top3 = sum(weights[:3])
        if top3 >= 60:
            signals.append(Signal("portfolio", "top3_concentration", 4, f"前三大持仓{top3:.1f}%"))
        elif top3 >= 45:
            signals.append(Signal("portfolio", "top3_concentration", 2, f"前三大持仓{top3:.1f}%"))
    high_beta = profile.high_beta_exposure_pct
    if high_beta is not None:
        if high_beta >= 60:
            signals.append(Signal("portfolio", "high_beta_exposure", 4, f"高β仓位{high_beta:.1f}%"))
        elif high_beta >= 40:
            signals.append(Signal("portfolio", "high_beta_exposure", 2, f"高β仓位{high_beta:.1f}%"))
        elif high_beta >= 25:
            signals.append(Signal("portfolio", "high_beta_exposure", 1, f"高β仓位{high_beta:.1f}%"))
    return _cap_family(signals, 15)


def _confirm_level(snapshot: RiskSnapshot, history: list[RiskSnapshot]) -> str:
    raw = snapshot.raw_level
    if not history:
        return raw
    previous_level = history[-1].level
    if LEVEL_ORDER[raw] < LEVEL_ORDER[previous_level]:
        recent_raw = [item.raw_level for item in history[-2:]] + [raw]
        if len(recent_raw) >= 3 and all(LEVEL_ORDER[level] < LEVEL_ORDER[previous_level] for level in recent_raw):
            return _step_down(previous_level)
        return previous_level
    if LEVEL_ORDER[raw] <= LEVEL_ORDER[previous_level]:
        return previous_level
    if raw == "yellow":
        return raw
    recent = [item.raw_level for item in history[-2:]] + [raw]
    threshold = "red" if raw == "red" else "orange"
    confirmations = sum(LEVEL_ORDER[level] >= LEVEL_ORDER[threshold] for level in recent)
    all_a = snapshot.metrics.get("all_a", {})
    crash_day = _number(all_a, "day_return", default=0) <= -0.035
    if confirmations >= 2:
        return raw
    if crash_day and LEVEL_ORDER[previous_level] >= LEVEL_ORDER["orange"]:
        return raw
    return "yellow" if raw == "orange" else "orange"


def _step_down(level: str) -> str:
    return {"red": "orange", "orange": "yellow", "yellow": "green", "green": "green"}[level]


def _budget_level(snapshot: RiskSnapshot, history: list[RiskSnapshot]) -> str:
    """Keep a red risk budget locked until three confirmed green sessions."""

    if not history:
        return snapshot.level
    previous = history[-1].budget_level
    if previous == "red":
        recent_levels = [item.level for item in history[-2:]] + [snapshot.level]
        return "green" if len(recent_levels) >= 3 and all(level == "green" for level in recent_levels) else "red"
    if LEVEL_ORDER[snapshot.level] > LEVEL_ORDER[previous]:
        return snapshot.level
    return snapshot.level


def _raw_level(score: int) -> str:
    if score >= 53:
        return "red"
    if score >= 36:
        return "orange"
    if score >= 21:
        return "yellow"
    return "green"


def _cap_family(signals: Iterable[Signal], cap: int) -> list[Signal]:
    result: list[Signal] = []
    remaining = cap
    for signal in signals:
        if remaining <= 0:
            break
        points = min(signal.points, remaining)
        result.append(Signal(signal.family, signal.key, points, signal.detail))
        remaining -= points
    return result


def _number(item: dict[str, float | str | None], key: str, *, default: float = math.inf) -> float:
    value = item.get(key)
    return float(value) if isinstance(value, (int, float)) else default
