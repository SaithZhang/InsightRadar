"""Deterministic intraday risk, catalyst, opportunity, and re-entry rules."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable, Mapping

from stock_assist.intraday.contracts import (
    IntradayAlert,
    IntradaySnapshot,
    OpportunityState,
    RuleEvaluation,
    ThemeSnapshot,
)


RULE_VERSION = "intraday-rules/ir-001-v1"


@dataclass(frozen=True)
class ReentryPositionState:
    target_id: str
    sold_at: str
    sold_fraction: float
    sale_price: float
    reentry_count: int = 0
    first_reentry_price: float | None = None
    post_reentry_low_broken: bool = False
    account_profit_floor: float | None = None


class AccountRiskEngine:
    def __init__(self, technology_theme_ids: Iterable[str]) -> None:
        self.technology_theme_ids = tuple(technology_theme_ids)

    def evaluate(self, snapshot: IntradaySnapshot) -> RuleEvaluation:
        concentration = sum(
            float(snapshot.exposure_by_theme.get(item) or 0.0)
            for item in self.technology_theme_ids
        )
        technology = [
            item for item in snapshot.theme_snapshots if item.theme_id in self.technology_theme_ids
        ]
        extreme_gap = max(
            (item.gap_pct for item in technology if item.gap_pct is not None),
            default=None,
        )
        giveback = snapshot.pnl_giveback_ratio
        daily_pnl = snapshot.account_daily_pnl
        severity = None
        risk_range = (0, 0)
        if concentration >= 60 and (extreme_gap or 0) >= 8 and (daily_pnl or 0) >= 10000:
            severity = "red"
            risk_range = (40, 60)
        elif concentration >= 50 and ((extreme_gap or 0) >= 5 or (giveback or 0) >= 0.25):
            severity = "orange"
            risk_range = (20, 40)
        elif concentration >= 40:
            severity = "yellow"
            risk_range = (10, 25)
        if severity is None:
            return RuleEvaluation()
        evidence = [f"科技主题集中度 {concentration:.1f}%"]
        if extreme_gap is not None:
            evidence.append(f"相关主题最大高开 {extreme_gap:+.2f}%")
        if daily_pnl is not None:
            evidence.append(f"账户已知当日利润 {daily_pnl:,.0f} 元")
        if giveback is not None:
            evidence.append(f"从早盘利润峰值回吐 {giveback:.1%}")
        alert = _alert(
            snapshot=snapshot,
            alert_type="account_risk",
            severity=severity,
            target_type="account",
            target_id="portfolio",
            title="科技集中与极端高开触发账户利润保护",
            conclusion=(
                "禁止新增科技风险；当前利润与继续追高空间不对称，"
                f"建议由用户确认先兑现 {risk_range[0]}%—{risk_range[1]}% 的科技风险。"
            ),
            evidence=evidence,
            action_state="human_confirmation_required",
            suggested_risk_change={
                "target": "technology_cluster",
                "min_reduction_pct": risk_range[0],
                "max_reduction_pct": risk_range[1],
                "automatic_execution": False,
            },
            confirmation=(
                "核对可卖/冻结数量和既有委托后，由用户确认具体风险变化。",
                "集合竞价或分钟行情 source_time 处于新鲜度窗口内。",
            ),
            invalidation=(
                "最新券商快照推翻当前持仓数量或主题集中度。",
                "行情来源失败时只保留风险阻断，不计算可执行数量。",
            ),
            reentry=(
                "减仓后不得仅因价格下降接回。",
                "至少等待更高低点、收复VWAP/反弹高点和板块广度恢复。",
            ),
        )
        return RuleEvaluation(alerts=(alert,))


class CatalystFailureEngine:
    def __init__(self, theme_ids: Iterable[str]) -> None:
        self.theme_ids = tuple(theme_ids)

    def evaluate(
        self,
        snapshot: IntradaySnapshot,
        history: Iterable[IntradaySnapshot],
    ) -> RuleEvaluation:
        alerts: list[IntradayAlert] = []
        prior = list(history)
        for theme in snapshot.theme_snapshots:
            if theme.theme_id not in self.theme_ids:
                continue
            if (theme.external_mapping_return or 0) < 1.0 or (theme.gap_pct or 0) < 6.0:
                continue
            below_open = (theme.return_from_open or 0) <= -0.3
            below_vwap = (theme.vwap_distance or 0) <= -0.3
            if not (below_open or below_vwap):
                continue
            prior_themes = [
                item
                for snap in prior
                for item in snap.theme_snapshots
                if item.theme_id == theme.theme_id
            ]
            rebound_seen = any(
                (item.return_from_open or -999) >= 0.5
                and (item.vwap_distance or -999) >= 0.3
                for item in prior_themes
            )
            breadth_was_healthy = any(
                (item.breadth_above_vwap or 0) >= 0.75 for item in prior_themes
            )
            breadth_dropped = breadth_was_healthy and (theme.breadth_above_vwap or 0) <= 0.5
            first_rebound_failed = rebound_seen and below_open and below_vwap
            severity = "yellow"
            if first_rebound_failed and breadth_dropped:
                severity = "orange"
            if (
                first_rebound_failed
                and (theme.breadth_above_vwap or 0) <= 0.25
                and (theme.return_from_open or 0) <= -1.5
            ):
                severity = "red"
            evidence = [
                f"外部映射 {theme.external_mapping_return:+.2f}% 仍强",
                f"A股主题高开 {theme.gap_pct:+.2f}%",
                f"相对开盘 {theme.return_from_open:+.2f}% / VWAP {theme.vwap_distance:+.2f}%",
            ]
            if first_rebound_failed:
                evidence.append("首次反抽后再次跌破开盘价与VWAP")
            if breadth_dropped:
                evidence.append(f"代表股站上VWAP广度降至 {(theme.breadth_above_vwap or 0):.0%}")
            alerts.append(
                _alert(
                    snapshot=snapshot,
                    alert_type="catalyst_failure",
                    severity=severity,
                    target_type="theme",
                    target_id=theme.theme_id,
                    title=f"{theme.theme_id} 正向催化在A股内部失效",
                    conclusion="外部映射未转弱，但A股硬件出现内部兑现；已减仓部分不得无条件接回。",
                    evidence=evidence,
                    action_state="risk_reduction_review" if severity in {"orange", "red"} else "watch",
                    suggested_risk_change={
                        "target": theme.theme_id,
                        "min_reduction_pct": 10 if severity == "orange" else 20 if severity == "red" else 0,
                        "max_reduction_pct": 25 if severity == "orange" else 40 if severity == "red" else 0,
                        "automatic_execution": False,
                    },
                    confirmation=(
                        "开盘价/VWAP失守持续至少两个分钟观察。",
                        "板块广度同步下降，不以单只股票代替主题确认。",
                    ),
                    invalidation=(
                        "主题重新站上VWAP且广度恢复到60%以上。",
                        "龙头与跟随股同步收复首次反弹高点。",
                    ),
                    reentry=(
                        "不再创新低并形成更高低点。",
                        "收复VWAP或反弹高点，且板块广度恢复。",
                    ),
                )
            )
        return RuleEvaluation(alerts=tuple(alerts))


class OpportunityRadarEngine:
    def __init__(self, theme_ids: Iterable[str] | None = None) -> None:
        self.theme_ids = set(theme_ids or ())
        self._states: dict[str, OpportunityState] = {}

    def evaluate(
        self,
        snapshot: IntradaySnapshot,
        history: Iterable[IntradaySnapshot],
    ) -> RuleEvaluation:
        previous_states = dict(self._states)
        states: dict[str, OpportunityState] = {}
        alerts: list[IntradayAlert] = []
        for theme in snapshot.theme_snapshots:
            if self.theme_ids and theme.theme_id not in self.theme_ids:
                continue
            state = self._state(theme, previous_states.get(theme.theme_id))
            states[theme.theme_id] = state
            if state not in {"正在形成", "确认", "过热", "失效"}:
                continue
            alerts.append(
                _alert(
                    snapshot=snapshot,
                    alert_type="opportunity_radar",
                    severity="orange" if state in {"过热", "失效"} else "info",
                    target_type="theme",
                    target_id=theme.theme_id,
                    title=f"机会雷达：{theme.theme_id} {state}",
                    conclusion=(
                        "相对强势进入候选；该状态只表示结构确认，不强制推荐买入。"
                        if state in {"正在形成", "确认"}
                        else "当前结构不再适合追高或已失效。"
                    ),
                    evidence=(
                        f"相对强度 {theme.relative_strength if theme.relative_strength is not None else 'unknown'}",
                        f"VWAP距离 {theme.vwap_distance if theme.vwap_distance is not None else 'unknown'}",
                        f"同时间量比 {theme.volume_ratio_same_time if theme.volume_ratio_same_time is not None else 'unknown'}",
                        f"开盘/VWAP广度 {theme.breadth_above_open}/{theme.breadth_above_vwap}",
                    ),
                    action_state="observation_only",
                    suggested_risk_change={
                        "target": theme.theme_id,
                        "min_reduction_pct": 0,
                        "max_reduction_pct": 0,
                        "new_risk_authorized": False,
                    },
                    confirmation=(
                        "持续站上VWAP。",
                        "代表股开盘/VWAP广度均达到75%。",
                        "同时间成交量比达到1.3，龙头与跟随同步。",
                    ),
                    invalidation=(
                        "跌破VWAP且广度降到50%以下。",
                        "相对强度转负或龙头与跟随背离。",
                    ),
                    reentry=(),
                )
            )
        self._states = states
        return RuleEvaluation(alerts=tuple(alerts), opportunity_states=states)

    def _state(
        self,
        theme: ThemeSnapshot,
        previous: OpportunityState | None,
    ) -> OpportunityState:
        required = (
            theme.return_from_open,
            theme.vwap_distance,
            theme.volume_ratio_same_time,
            theme.breadth_above_open,
            theme.breadth_above_vwap,
            theme.relative_strength,
        )
        if any(value is None for value in required):
            return "观察" if theme.gap_pct is not None else "未出现"
        if previous == "确认" and (
            theme.vwap_distance < -0.3
            or theme.breadth_above_vwap < 0.5
            or theme.relative_strength < 0
        ):
            return "失效"
        if theme.return_pct is not None and theme.return_pct >= 9 and theme.return_from_open >= 4:
            return "过热"
        if (
            theme.return_from_open >= 1.5
            and theme.vwap_distance >= 0.5
            and theme.volume_ratio_same_time >= 1.3
            and theme.breadth_above_open >= 0.75
            and theme.breadth_above_vwap >= 0.75
            and theme.leader_confirmation is True
            and theme.relative_strength >= 1.0
        ):
            return "确认"
        if (
            theme.vwap_distance >= 0
            and theme.volume_ratio_same_time >= 1.0
            and theme.breadth_above_open >= 0.5
            and theme.breadth_above_vwap >= 0.5
            and theme.leader_confirmation is True
            and theme.relative_strength >= 0.3
        ):
            return "正在形成"
        if theme.relative_strength > 0 or theme.breadth_above_open >= 0.5:
            return "观察"
        return "未出现"


class ReentryGuardEngine:
    def evaluate(
        self,
        snapshot: IntradaySnapshot,
        states: Iterable[ReentryPositionState],
    ) -> RuleEvaluation:
        alerts: list[IntradayAlert] = []
        by_theme = {item.theme_id: item for item in snapshot.theme_snapshots}
        for state in states:
            theme = by_theme.get(state.target_id)
            if theme is None or theme.return_from_open is None:
                continue
            price_down_enough = theme.return_from_open <= -3.0
            if not price_down_enough and state.reentry_count == 0:
                continue
            profit_locked = (
                state.account_profit_floor is not None
                and snapshot.account_daily_pnl is not None
                and snapshot.account_daily_pnl < state.account_profit_floor
            )
            second_lock = state.reentry_count >= 1 and state.post_reentry_low_broken
            structure_ready = all(
                (
                    theme.no_new_low is True,
                    theme.higher_low is True,
                    bool(theme.reclaimed_vwap or theme.reclaimed_rebound_high),
                    (theme.breadth_above_vwap or 0) >= 0.6,
                )
            )
            eligible = structure_ready and not profit_locked and not second_lock
            evidence = [
                f"相对卖出/开盘后的主题变动 {theme.return_from_open:+.2f}%",
                f"不再创新低={theme.no_new_low} / 更高低点={theme.higher_low}",
                f"收复VWAP或反弹高点={bool(theme.reclaimed_vwap or theme.reclaimed_rebound_high)}",
                f"VWAP广度={(theme.breadth_above_vwap or 0):.0%}",
            ]
            if profit_locked:
                evidence.append("账户盈利已跌破保护线，禁止新增风险")
            if second_lock:
                evidence.append("第一次接回后再次破低，当天第二次接回锁死")
            alerts.append(
                _alert(
                    snapshot=snapshot,
                    alert_type="reentry_guard",
                    severity="info" if eligible else "red",
                    target_type="theme",
                    target_id=state.target_id,
                    title="结构修复后才允许人工复核接回" if eligible else "禁止仅因下跌无条件接回",
                    conclusion=(
                        "结构门槛已满足，但仍只允许人工复核，不自动接回。"
                        if eligible
                        else "价格下降不是接回理由；当前保持已降低风险状态。"
                    ),
                    evidence=evidence,
                    action_state="human_review_only" if eligible else "reentry_blocked",
                    suggested_risk_change={
                        "target": state.target_id,
                        "new_risk_authorized": False,
                        "automatic_execution": False,
                    },
                    confirmation=(
                        "不再创新低并形成更高低点。",
                        "收复VWAP或反弹高点。",
                        "代表股VWAP广度恢复到60%以上。",
                    ),
                    invalidation=(
                        "再次创新低。",
                        "账户盈利跌破保护线。",
                        "第一次接回后再次破低时，当天禁止第二次接回。",
                    ),
                    reentry=(
                        "全部结构条件满足后才进入人工复核。",
                    ),
                )
            )
        return RuleEvaluation(alerts=tuple(alerts))


class IntradayDecisionEngine:
    """One small interface over the four deterministic rule modules."""

    def __init__(
        self,
        *,
        technology_theme_ids: Iterable[str],
        catalyst_theme_ids: Iterable[str],
        opportunity_theme_ids: Iterable[str] | None = None,
    ) -> None:
        self.account_risk = AccountRiskEngine(technology_theme_ids)
        self.catalyst_failure = CatalystFailureEngine(catalyst_theme_ids)
        self.opportunity_radar = OpportunityRadarEngine(opportunity_theme_ids)
        self.reentry_guard = ReentryGuardEngine()

    def evaluate(
        self,
        snapshot: IntradaySnapshot,
        *,
        history: Iterable[IntradaySnapshot] = (),
        reentry_states: Iterable[ReentryPositionState] = (),
    ) -> RuleEvaluation:
        history_rows = list(history)
        account = self.account_risk.evaluate(snapshot)
        catalyst = self.catalyst_failure.evaluate(snapshot, history_rows)
        opportunity = self.opportunity_radar.evaluate(snapshot, history_rows)
        reentry = self.reentry_guard.evaluate(snapshot, reentry_states)
        return RuleEvaluation(
            alerts=tuple(
                [*account.alerts, *catalyst.alerts, *opportunity.alerts, *reentry.alerts]
            ),
            opportunity_states=opportunity.opportunity_states,
            state_updates={},
        )


def _alert(
    *,
    snapshot: IntradaySnapshot,
    alert_type: str,
    severity: str,
    target_type: str,
    target_id: str,
    title: str,
    conclusion: str,
    evidence: Iterable[str],
    action_state: str,
    suggested_risk_change: Mapping[str, object],
    confirmation: Iterable[str],
    invalidation: Iterable[str],
    reentry: Iterable[str],
) -> IntradayAlert:
    identity = f"{alert_type}|{target_id}|{snapshot.timestamp.isoformat()}|{severity}"
    alert_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return IntradayAlert(
        alert_id=alert_id,
        timestamp=snapshot.timestamp,
        type=alert_type,
        severity=severity,  # type: ignore[arg-type]
        target_type=target_type,
        target_id=target_id,
        title=title,
        conclusion=conclusion,
        evidence=tuple(evidence),
        action_state=action_state,
        suggested_risk_change=dict(suggested_risk_change),
        confirmation_conditions=tuple(confirmation),
        invalidation_conditions=tuple(invalidation),
        reentry_conditions=tuple(reentry),
        source_times=snapshot.source_times,
        rule_version=RULE_VERSION,
        fetched_at=snapshot.fetched_at,
    )
