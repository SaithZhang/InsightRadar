"""Pure holding-level technical decision contract.

The module deliberately knows nothing about providers, report files, HTTP, or
user-response ledgers.  It turns one completed OHLCV frame plus the latest
broker holding snapshot into an auditable, human-confirmed decision plan.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil, log
from typing import Literal

import pandas as pd

from stock_assist.portfolio import Holding


TechnicalState = Literal[
    "unknown",
    "quarantined",
    "weak",
    "repairing",
    "neutral",
    "strong",
    "extended",
]


@dataclass(frozen=True)
class TechnicalSnapshot:
    state: TechnicalState
    as_of: str | None
    adjustment_basis: str
    close: float | None
    ma20: float | None
    ma60: float | None
    ma20_slope_5d: float | None
    support_20d: float | None
    resistance_20d: float | None
    atr14: float | None
    volume_ratio_20d: float | None
    change_5d: float | None
    evidence_families: tuple[str, ...]


@dataclass(frozen=True)
class DecisionBranch:
    branch_id: Literal["repair_observe", "risk_reduce_review", "continue_waiting"]
    label: str
    trigger: str
    persistence: str
    action: str
    invalidation: str
    review_time: str
    threshold: float | None
    reachability: str
    evidence_families: tuple[str, ...]


@dataclass(frozen=True)
class HoldingDecision:
    action: str
    reason: str
    data_gap: str
    position_action: str
    priority: str
    technical: TechnicalSnapshot
    cost_reference: dict[str, object]
    branches: tuple[DecisionBranch, DecisionBranch, DecisionBranch]

    def to_contract(self) -> dict[str, object]:
        return asdict(self)

    def branch(self, branch_id: str) -> DecisionBranch:
        for item in self.branches:
            if item.branch_id == branch_id:
                return item
        raise KeyError(branch_id)


def build_holding_decision(holding: Holding, frame: pd.DataFrame) -> HoldingDecision:
    """Build a holding plan without using cost to synthesize technical levels."""

    prepared = _prepare_frame(frame)
    if prepared.empty:
        return _unknown_decision(
            holding,
            "未取到该股票行情，无法判断趋势位置。",
            "补充至少20个已完成交易日的日线行情。",
        )

    close_col = _pick_column(prepared, ("close", "收盘价", "S_DQ_CLOSE"))
    if close_col is None:
        return _unknown_decision(
            holding,
            "行情缺少收盘价字段，不能计算技术结构。",
            "确认日线字段映射并重新刷新。",
        )

    closes = pd.to_numeric(prepared[close_col], errors="coerce")
    valid = closes.notna() & (closes > 0)
    prepared = prepared.loc[valid].copy()
    closes = closes.loc[valid].astype(float)
    if len(closes) < 20:
        return _unknown_decision(
            holding,
            "有效行情不足20个交易日，趋势参考不稳定。",
            "补齐更长历史行情。",
        )

    last = float(closes.iloc[-1])
    broker_price = holding.market_price
    if (
        broker_price is not None
        and broker_price > 0
        and abs(last / broker_price - 1.0) > 0.35
    ):
        technical = _technical_snapshot(
            prepared,
            closes,
            state="quarantined",
        )
        return _quarantined_decision(
            holding,
            technical,
            (
                f"日线收盘价 {last:.2f} 与券商快照 {broker_price:.2f} "
                "偏差超过35%，疑似复权或标的映射口径不一致。"
            ),
        )
    adjustment_basis = str(
        prepared.attrs.get("adjustment_basis")
        or prepared.attrs.get("adjust")
        or "provider_output_unspecified"
    )
    largest_gap = float(closes.pct_change().abs().dropna().max())
    if (
        largest_gap > 0.35
        and adjustment_basis == "provider_output_unspecified"
    ):
        technical = _technical_snapshot(
            prepared,
            closes,
            state="quarantined",
        )
        return _quarantined_decision(
            holding,
            technical,
            (
                f"日线序列存在 {largest_gap:.1%} 的单日价格断点，且数据源未声明"
                "复权口径；均线、支撑阻力与波动指标暂不进入决策。"
            ),
        )

    snapshot = _technical_snapshot(prepared, closes)
    assert snapshot.close is not None
    assert snapshot.ma20 is not None
    assert snapshot.ma60 is not None
    assert snapshot.support_20d is not None
    assert snapshot.resistance_20d is not None

    lost_structure = snapshot.close < snapshot.support_20d
    repair_level = (
        snapshot.support_20d
        if lost_structure
        else snapshot.ma20
        if snapshot.close < snapshot.ma20
        else snapshot.resistance_20d
    )
    risk_level = (
        snapshot.support_20d
        if snapshot.close < snapshot.ma20
        else snapshot.ma20
    )
    evidence_families = snapshot.evidence_families
    repair_reachability = _threshold_reachability(
        holding.code,
        snapshot.close,
        repair_level,
    )
    repair_horizon_note = (
        _reachability_note(repair_reachability)
    )

    if snapshot.state == "weak":
        action = "降低仓位复核"
        priority = "高"
        position_action = (
            "不加仓；风险分支持续成立时复核降低1/4至1/3仓位，"
            "任何仓位变化仍需用户确认。"
        )
    elif snapshot.state == "repairing":
        action = "持有但不加仓"
        priority = "中"
        position_action = "保持仓位，等待修复分支成立；不因单日反弹追买。"
    elif snapshot.state == "extended":
        action = "持有观察，不追高"
        priority = "中"
        position_action = "保留现有仓位，等待回踩确认；不追涨。"
    else:
        action = "持有观察"
        priority = "中" if snapshot.state in {"neutral", "strong"} else "低"
        position_action = "维持仓位，等待修复或风险分支给出持续确认。"

    if (holding.weight_pct or 0.0) >= 40:
        action = "降低集中度复核"
        priority = "高"
        position_action = (
            "不新增集中度；在技术风险分支成立或反弹量能不足时，"
            "复核降低1/4仓位，仍需用户确认。"
        )

    reason_parts = [
        (
            f"收盘 {snapshot.close:.2f}，20日线 {snapshot.ma20:.2f}，"
            f"中期均线 {snapshot.ma60:.2f}"
        ),
        (
            f"前20日支撑 {snapshot.support_20d:.2f}，"
            f"前20日阻力 {snapshot.resistance_20d:.2f}"
        ),
    ]
    if snapshot.atr14 is not None:
        reason_parts.append(f"ATR14 {snapshot.atr14:.2f}")
    if snapshot.volume_ratio_20d is not None:
        reason_parts.append(f"量比 {snapshot.volume_ratio_20d:.2f}")
    if (holding.weight_pct or 0.0) >= 40:
        reason_parts.append(f"仓位 {holding.weight_pct:.1f}% 存在集中度约束")

    repair = DecisionBranch(
        branch_id="repair_observe",
        label="修复后观察",
        trigger=(
            f"收盘站上 {repair_level:.2f}，且板块相对强弱不再恶化；"
            f"有成交量数据时量比不低于1.0。{repair_horizon_note}"
        ),
        persistence="连续2个交易日收盘不低于该技术位。",
        action="从降低仓位复核降为持有观察；不自动加仓。",
        invalidation=f"收盘重新跌回 {repair_level:.2f} 下方。",
        review_time="下一交易日收盘后；若标记为多交易日条件则按日滚动复核。",
        threshold=round(repair_level, 4),
        reachability=repair_reachability,
        evidence_families=evidence_families,
    )
    risk_already_triggered = snapshot.close < risk_level
    risk = DecisionBranch(
        branch_id="risk_reduce_review",
        label="风险降低复核",
        trigger=(
            (
                f"当前收盘 {snapshot.close:.2f} 已低于技术结构位 {risk_level:.2f}，"
                "风险分支已进入确认期。"
            )
            if risk_already_triggered
            else f"收盘跌破技术结构位 {risk_level:.2f}，且市场或板块风险没有改善。"
        ),
        persistence=(
            f"下一交易日收盘仍未收回 {risk_level:.2f}；"
            "若放量继续破位可当日进入人工复核。"
        ),
        action="复核降低1/4至1/3仓位；不自动执行。",
        invalidation=f"收盘重新站回 {risk_level:.2f} 且技术弱势不再扩大。",
        review_time="触发当日收盘后或下一交易日确认后。",
        threshold=round(risk_level, 4),
        reachability=_threshold_reachability(
            holding.code,
            snapshot.close,
            risk_level,
        ),
        evidence_families=evidence_families,
    )
    waiting = DecisionBranch(
        branch_id="continue_waiting",
        label="继续等待",
        trigger="修复分支与风险分支均未满足持续性条件。",
        persistence="保持到下一次有效收盘或新增基本面反证出现。",
        action="保持仓位，不补仓、不追涨，不因盘中噪声改计划。",
        invalidation="任一修复或风险分支完成持续性确认。",
        review_time="下一交易日收盘后。",
        threshold=None,
        reachability="not_applicable",
        evidence_families=evidence_families,
    )
    return HoldingDecision(
        action=action,
        reason="；".join(reason_parts) + "。",
        data_gap="",
        position_action=position_action,
        priority=priority,
        technical=snapshot,
        cost_reference=_cost_reference(holding),
        branches=(repair, risk, waiting),
    )


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    prepared = frame.copy()
    date_col = _pick_column(
        prepared,
        (
            "date",
            "trade_date",
            "kline_time",
            "trade_dt",
            "tradeDate",
            "交易日期",
            "TRADE_DT",
            "TRADE_DATE",
        ),
    )
    if date_col is not None:
        prepared = prepared.sort_values(date_col, kind="stable")
    return prepared


def _technical_snapshot(
    frame: pd.DataFrame,
    closes: pd.Series,
    *,
    state: TechnicalState | None = None,
) -> TechnicalSnapshot:
    last = float(closes.iloc[-1])
    ma20 = float(closes.tail(20).mean())
    ma60 = float(closes.tail(min(60, len(closes))).mean())
    prior_window = closes.iloc[-25:-5] if len(closes) >= 25 else pd.Series(dtype=float)
    prior_ma20 = float(prior_window.mean()) if len(prior_window) == 20 else None
    ma20_slope = (
        ma20 / prior_ma20 - 1.0
        if prior_ma20 is not None and prior_ma20 > 0
        else None
    )
    structure_window = closes.iloc[-21:-1] if len(closes) >= 21 else closes.tail(20)
    support = float(structure_window.min())
    resistance = float(structure_window.max())
    change_5 = (
        last / float(closes.iloc[-6]) - 1.0
        if len(closes) >= 6 and float(closes.iloc[-6]) > 0
        else None
    )
    atr14 = _atr14(frame, closes)
    volume_ratio = _volume_ratio_20d(frame)
    resolved_state = state or _technical_state(
        last=last,
        ma20=ma20,
        ma60=ma60,
        support=support,
        change_5=change_5,
    )
    evidence_families = ["moving_average", "price_structure"]
    if atr14 is not None:
        evidence_families.append("volatility")
    if volume_ratio is not None:
        evidence_families.append("volume")
    return TechnicalSnapshot(
        state=resolved_state,
        as_of=_as_of(frame),
        adjustment_basis=str(
            frame.attrs.get("adjustment_basis")
            or frame.attrs.get("adjust")
            or "provider_output_unspecified"
        ),
        close=round(last, 4),
        ma20=round(ma20, 4),
        ma60=round(ma60, 4),
        ma20_slope_5d=round(ma20_slope, 6) if ma20_slope is not None else None,
        support_20d=round(support, 4),
        resistance_20d=round(resistance, 4),
        atr14=round(atr14, 4) if atr14 is not None else None,
        volume_ratio_20d=round(volume_ratio, 4) if volume_ratio is not None else None,
        change_5d=round(change_5, 6) if change_5 is not None else None,
        evidence_families=tuple(evidence_families),
    )


def _technical_state(
    *,
    last: float,
    ma20: float,
    ma60: float,
    support: float,
    change_5: float | None,
) -> TechnicalState:
    if last < support or (last < ma20 and ma20 < ma60):
        return "weak"
    if last < ma20:
        return "repairing"
    if change_5 is not None and change_5 > 0.05:
        return "extended"
    if ma20 >= ma60:
        return "strong"
    return "neutral"


def _atr14(frame: pd.DataFrame, closes: pd.Series) -> float | None:
    high_col = _pick_column(frame, ("high", "最高价", "S_DQ_HIGH"))
    low_col = _pick_column(frame, ("low", "最低价", "S_DQ_LOW"))
    if high_col is None or low_col is None:
        return None
    highs = pd.to_numeric(frame.loc[closes.index, high_col], errors="coerce")
    lows = pd.to_numeric(frame.loc[closes.index, low_col], errors="coerce")
    previous_close = closes.shift(1)
    true_range = pd.concat(
        [
            highs - lows,
            (highs - previous_close).abs(),
            (lows - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    values = true_range.dropna().tail(14)
    return float(values.mean()) if len(values) >= 5 else None


def _volume_ratio_20d(frame: pd.DataFrame) -> float | None:
    volume_col = _pick_column(
        frame,
        ("volume", "vol", "成交量", "S_DQ_VOLUME"),
    )
    if volume_col is None:
        return None
    volumes = pd.to_numeric(frame[volume_col], errors="coerce").dropna()
    volumes = volumes[volumes >= 0]
    if len(volumes) < 21:
        return None
    baseline = float(volumes.iloc[-21:-1].mean())
    return float(volumes.iloc[-1]) / baseline if baseline > 0 else None


def _as_of(frame: pd.DataFrame) -> str | None:
    date_col = _pick_column(
        frame,
        (
            "date",
            "trade_date",
            "kline_time",
            "trade_dt",
            "tradeDate",
            "交易日期",
            "TRADE_DT",
            "TRADE_DATE",
        ),
    )
    if date_col is None or frame.empty:
        return None
    value = frame[date_col].iloc[-1]
    if pd.isna(value):
        return None
    if hasattr(value, "date"):
        try:
            return value.date().isoformat()
        except (AttributeError, ValueError):
            pass
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text or None


def _threshold_reachability(code: str, close: float, threshold: float) -> str:
    if close <= 0 or threshold <= 0:
        return "unknown"
    if threshold <= close:
        return "already_met_or_downside"
    reference_limit = 0.20 if code.startswith(("300", "301", "688")) else 0.10
    distance = threshold / close - 1.0
    if distance <= reference_limit + 1e-9:
        return "next_session_possible"
    sessions = max(2, ceil(log(threshold / close) / log(1.0 + reference_limit)))
    return f"multi_session_min_{sessions}_under_board_limit_reference"


def _reachability_note(reachability: str) -> str:
    if reachability.startswith("multi_session_min_"):
        sessions = reachability.removeprefix("multi_session_min_").split("_", 1)[0]
        return f"按板块涨跌幅参考估算至少需要{sessions}个交易日，这不是下一交易日条件。"
    if reachability == "next_session_possible":
        return "按板块涨跌幅参考，该技术位下一交易日理论可达。"
    return ""


def _unknown_decision(
    holding: Holding,
    reason: str,
    data_gap: str,
) -> HoldingDecision:
    technical = TechnicalSnapshot(
        state="unknown",
        as_of=None,
        adjustment_basis="unknown",
        close=None,
        ma20=None,
        ma60=None,
        ma20_slope_5d=None,
        support_20d=None,
        resistance_20d=None,
        atr14=None,
        volume_ratio_20d=None,
        change_5d=None,
        evidence_families=(),
    )
    branches = _blocked_branches("技术数据恢复并完成口径核对。")
    return HoldingDecision(
        action="等待数据，不做主动交易",
        reason=reason,
        data_gap=data_gap,
        position_action="不加仓；仅保留人工风险监控。",
        priority="高",
        technical=technical,
        cost_reference=_cost_reference(holding),
        branches=branches,
    )


def _quarantined_decision(
    holding: Holding,
    technical: TechnicalSnapshot,
    reason: str,
) -> HoldingDecision:
    return HoldingDecision(
        action="等待数据，不做主动交易",
        reason=reason,
        data_gap="行情复权或标的映射口径待核对。",
        position_action="不使用当前均线或价格阈值生成仓位动作。",
        priority="高",
        technical=technical,
        cost_reference=_cost_reference(holding),
        branches=_blocked_branches("同一标的、同一复权口径完成对账。"),
    )


def _blocked_branches(
    recovery_condition: str,
) -> tuple[DecisionBranch, DecisionBranch, DecisionBranch]:
    common = {
        "persistence": "数据恢复前不评估持续性。",
        "review_time": "数据恢复后。",
        "threshold": None,
        "reachability": "unknown",
        "evidence_families": (),
    }
    return (
        DecisionBranch(
            branch_id="repair_observe",
            label="修复后观察",
            trigger=recovery_condition,
            action="恢复技术判断后再形成计划；不自动加仓。",
            invalidation="数据再次缺失或口径仍不一致。",
            **common,
        ),
        DecisionBranch(
            branch_id="risk_reduce_review",
            label="风险降低复核",
            trigger="仅当用户已有人工风险线被触发。",
            action="按人工风险线复核；不采用模型阈值。",
            invalidation="人工风险线未触发。",
            **common,
        ),
        DecisionBranch(
            branch_id="continue_waiting",
            label="继续等待",
            trigger="技术数据仍缺失或口径未对齐。",
            action="保持仓位，不补仓、不追涨。",
            invalidation=recovery_condition,
            **common,
        ),
    )


def _cost_reference(holding: Holding) -> dict[str, object]:
    return {
        "authority": "reference_only",
        "cost": holding.cost,
        "pnl_pct": holding.pnl_pct,
        "note": "成本与账户盈亏只用于解释持仓体验，不生成技术触发点。",
    }


def _pick_column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lowered = {str(column).lower(): str(column) for column in frame.columns}
    for name in names:
        matched = lowered.get(name.lower())
        if matched is not None:
            return matched
    return None
