"""Deterministic contract for the Today Workbench conclusion layer.

The module deliberately keeps facts, rule state, and display templates apart.
It consumes only structured workspace/runtime fields and never calls a model.
Unknown inputs remain ``None`` and blocked rules never become monitor eligible.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal, TypedDict
from zoneinfo import ZoneInfo

MarketPhase = Literal["pre_market", "intraday", "after_close", "weekend"]
DataQualityStatus = Literal["ready", "partial", "stale", "blocked", "unknown"]
AttentionType = Literal["position", "opportunity"]
RuleStatus = Literal[
    "blocked",
    "pending_confirmation",
    "confirmed",
    "modification_requested",
    "observation_only",
    "disabled",
]
DecisionRequirementStatus = Literal[
    "blocked",
    "pending_confirmation",
    "confirmed",
    "observation_only",
    "disabled",
]


class Evidence(TypedDict):
    evidence_id: str
    claim: str
    source_ref: str
    source_time: str | None
    freshness: DataQualityStatus
    authority: str
    gaps: list[str]
    counter_evidence: list[str]


class AccountSnapshot(TypedDict):
    as_of: str | None
    daily_pnl: float | None
    peak_daily_pnl: float | None
    giveback_amount: float | None
    giveback_ratio: float | None
    data_quality: DataQualityStatus
    pnl_source: str
    attribution: list[dict[str, object]]
    gaps: list[str]


class AttentionItem(TypedDict):
    attention_id: str
    type: AttentionType
    title: str
    symbol: str | None
    importance_score: int
    what_happened: str
    why_it_matters: str
    plan_status: RuleStatus
    data_quality: DataQualityStatus
    evidence: list[Evidence]
    counter_evidence: list[str]
    detail_route: str
    detail_query: dict[str, str]


class Rule(TypedDict):
    rule_id: str
    rule_version: str
    title: str
    summary: str
    status: RuleStatus
    data_quality: DataQualityStatus
    blocking_reasons: list[str]
    monitor_eligible: bool
    response: str


class DecisionRequirement(TypedDict):
    requirement_id: str
    title: str
    prompt: str
    status: DecisionRequirementStatus
    rule_id: str | None
    rule_version: str | None
    data_quality: DataQualityStatus
    blocking_reasons: list[str]
    allowed_responses: list[str]
    detail_route: str


class TodayWorkbench(TypedDict):
    schema_version: str
    generated_at: str
    phase: MarketPhase
    phase_label: str
    phase_message: str
    review_trade_date: str
    account_snapshot: AccountSnapshot
    attention_items: list[AttentionItem]
    rules: list[Rule]
    decision_requirements: list[DecisionRequirement]
    data_quality: DataQualityStatus
    data_gaps: list[str]
    ai_status: Literal["not_used"]
    trade_authority: Literal["none"]


def build_today_workbench(
    workspace: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> TodayWorkbench:
    """Build the after-close/weekend Today contract from structured data."""

    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    session = _selected_session(workspace)
    phase = _market_phase(workspace, session)
    review_trade_date = str(
        session.get("runtime_trade_date")
        or session.get("trade_date")
        or workspace.get("effective_market_date")
        or "unknown"
    )
    evidence = _evidence_items(workspace)
    account = _account_snapshot(workspace, session)
    plans = _dict_rows(workspace.get("active_plans"))
    attention = _attention_items(plans, evidence)
    rules = [
        _rule(
            item,
            [
                evidence[ref]
                for ref in _strings(item.get("evidence_refs"))
                if ref in evidence
            ],
        )
        for item in plans
    ]
    requirements = [
        _decision_requirement(plan, rule)
        for plan, rule in zip(plans, rules, strict=False)
    ]
    gaps = _dedupe(
        [
            *account["gaps"],
            *_strings(workspace.get("data_gaps")),
            *_strings(session.get("data_gaps")),
        ]
    )
    quality = _combined_quality(
        [
            account["data_quality"],
            *(item["data_quality"] for item in attention),
            *(item["data_quality"] for item in requirements),
        ]
    )
    phase_label, phase_message = _phase_copy(phase, review_trade_date)
    return {
        "schema_version": "today-workbench/v1",
        "generated_at": current.isoformat(timespec="seconds"),
        "phase": phase,
        "phase_label": phase_label,
        "phase_message": phase_message,
        "review_trade_date": review_trade_date,
        "account_snapshot": account,
        "attention_items": attention,
        "rules": rules,
        "decision_requirements": requirements,
        "data_quality": quality,
        "data_gaps": gaps,
        "ai_status": "not_used",
        "trade_authority": "none",
    }


def _selected_session(workspace: Mapping[str, object]) -> dict[str, object]:
    for key in ("selected_session", "latest_completed_session", "intraday_radar"):
        value = workspace.get(key)
        if isinstance(value, Mapping) and value:
            return dict(value)
    return {}


def _market_phase(
    workspace: Mapping[str, object],
    session: Mapping[str, object],
) -> MarketPhase:
    if (
        session.get("session_mode") == "non_trading_day"
        or session.get("view_mode") == "historical_review"
    ):
        return "weekend"
    # V1 renders only the implemented after-close/weekend states.  The literal
    # contract reserves pre_market and intraday for later runtime admission.
    return "after_close"


def _phase_copy(phase: MarketPhase, trade_date: str) -> tuple[str, str]:
    if phase == "weekend":
        return (
            "周末复盘",
            f"今天休市，正在回看 {trade_date} 最近交易日；仅用于复盘，不产生实时交易动作。",
        )
    return (
        "盘后复盘",
        f"正在复核 {trade_date} 收盘后的账户、证据与规则；所有仓位动作仍需人工确认。",
    )


def _account_snapshot(
    workspace: Mapping[str, object],
    session: Mapping[str, object],
) -> AccountSnapshot:
    latest = _mapping(session.get("latest_snapshot"))
    if latest:
        holdings = _dict_rows(latest.get("holding_snapshots"))
        daily = _number(latest.get("account_daily_pnl"))
        peak = _number(latest.get("account_peak_daily_pnl"))
        giveback_ratio = _ratio(latest.get("pnl_giveback_ratio"))
        source = "intraday-runtime.latest_snapshot"
        as_of = str(latest.get("timestamp") or session.get("source_time") or "") or None
        gaps = _strings(latest.get("data_gaps"))
    else:
        holdings = _dict_rows(workspace.get("portfolio_positions"))
        values = [_number(item.get("day_pnl")) for item in holdings]
        daily = (
            sum(value for value in values if value is not None)
            if holdings and all(value is not None for value in values)
            else None
        )
        peak = None
        giveback_ratio = None
        source = "portfolio_positions.day_pnl"
        as_of = (
            str(
                _mapping(workspace.get("portfolio_summary")).get("snapshot_as_of")
                or workspace.get("effective_market_date")
                or ""
            )
            or None
        )
        gaps = []
        if daily is None:
            gaps.append("持仓日盈亏不完整，账户当日盈亏保持 unknown。")
        gaps.append("未找到交易日内账户峰值快照，峰值与回吐保持 unknown。")
    giveback_amount = (
        max(0.0, peak - daily) if peak is not None and daily is not None else None
    )
    if (
        giveback_ratio is None
        and peak is not None
        and peak > 0
        and daily is not None
        and giveback_amount is not None
    ):
        giveback_ratio = max(0.0, min(1.0, giveback_amount / peak))
    attribution = _pnl_attribution(holdings)
    if giveback_amount not in (None, 0) and not all(
        item.get("peak_day_pnl") is not None for item in holdings
    ):
        gaps.append("缺少持仓级利润峰值序列，不能确定性归因峰值回吐来源。")
    quality: DataQualityStatus
    if daily is None:
        quality = "blocked"
    elif peak is None or giveback_ratio is None:
        quality = "partial"
    else:
        quality = "ready"
    return {
        "as_of": as_of,
        "daily_pnl": daily,
        "peak_daily_pnl": peak,
        "giveback_amount": giveback_amount,
        "giveback_ratio": giveback_ratio,
        "data_quality": quality,
        "pnl_source": source,
        "attribution": attribution,
        "gaps": _dedupe(gaps),
    }


def _pnl_attribution(holdings: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "symbol": str(item.get("symbol") or item.get("code") or ""),
            "name": str(item.get("name") or item.get("symbol") or "未命名持仓"),
            "day_pnl": _number(item.get("day_pnl")),
        }
        for item in holdings
        if _number(item.get("day_pnl")) is not None
    ]
    rows.sort(key=lambda item: abs(_number(item["day_pnl"]) or 0), reverse=True)
    return rows[:4]


def _evidence_items(workspace: Mapping[str, object]) -> dict[str, Evidence]:
    contract = _mapping(workspace.get("decision_evidence"))
    result: dict[str, Evidence] = {}
    for item in _dict_rows(contract.get("items")):
        evidence_id = str(item.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        result[evidence_id] = {
            "evidence_id": evidence_id,
            "claim": str(item.get("claim") or "当前证据没有提供可复核结论。"),
            "source_ref": str(item.get("source_ref") or "unknown"),
            "source_time": str(item.get("source_time") or "") or None,
            "freshness": _quality(item.get("freshness")),
            "authority": str(item.get("authority") or "diagnostic_only"),
            "gaps": _strings(item.get("gaps")),
            "counter_evidence": _strings(item.get("counter_evidence")),
        }
    return result


def _attention_items(
    plans: list[dict[str, object]],
    evidence_by_id: Mapping[str, Evidence],
) -> list[AttentionItem]:
    positions: list[AttentionItem] = []
    for plan in plans:
        refs = _strings(plan.get("evidence_refs"))
        evidence = [evidence_by_id[item] for item in refs if item in evidence_by_id]
        counters = _dedupe(
            [
                *(value for item in evidence for value in item["counter_evidence"]),
                str(plan.get("invalid_condition") or ""),
            ]
        )
        blocking = _strings(plan.get("blocking_reasons"))
        state = _rule_status(plan)
        quality = _plan_quality(plan, evidence)
        what_happened = (
            evidence[0]["claim"]
            if evidence
            else "；".join(_strings(plan.get("change_reasons")))
            or "当前版本没有形成新的可归因证据。"
        )
        why = str(
            plan.get("current_next_event")
            or plan.get("next_event")
            or plan.get("if_condition")
            or "等待下一项已完成数据"
        )
        positions.append(
            {
                "attention_id": str(plan.get("plan_id") or "position:unknown"),
                "type": "position",
                "title": str(plan.get("name") or plan.get("symbol") or "未命名持仓"),
                "symbol": str(plan.get("symbol") or "") or None,
                "importance_score": _importance(plan, state, blocking),
                "what_happened": what_happened,
                "why_it_matters": why,
                "plan_status": state,
                "data_quality": quality,
                "evidence": evidence,
                "counter_evidence": [item for item in counters if item],
                "detail_route": "portfolio",
                "detail_query": {
                    "symbol": str(plan.get("symbol") or ""),
                    "plan_id": str(plan.get("plan_id") or ""),
                },
            }
        )
    positions.sort(key=lambda item: (-item["importance_score"], item["title"]))
    # The opportunity slot is explicit and honest until a verified, target-bound
    # opportunity contract is introduced.  A research-section title alone is
    # insufficient evidence for naming a stock.
    opportunity: AttentionItem = {
        "attention_id": "opportunity:none-verified",
        "type": "opportunity",
        "title": "暂无经证据验证的机会",
        "symbol": None,
        "importance_score": 0,
        "what_happened": "当前结构化数据没有形成标的绑定、来源可追溯且通过规则校验的持仓外机会。",
        "why_it_matters": "缺少证据时保持空位，避免把研究线索包装成可行动机会。",
        "plan_status": "observation_only",
        "data_quality": "unknown",
        "evidence": [],
        "counter_evidence": [
            "出现带标的、来源时间和反证条件的结构化机会后，本项才可被替换。"
        ],
        "detail_route": "lookup",
        "detail_query": {"intent": "opportunity"},
    }
    return [*positions, opportunity]


def _rule(plan: Mapping[str, object], evidence: list[Evidence]) -> Rule:
    status = _rule_status(plan)
    blocking = _strings(plan.get("blocking_reasons"))
    quality = _plan_quality(plan, evidence)
    return {
        "rule_id": str(plan.get("plan_id") or "rule:unknown"),
        "rule_version": str(plan.get("plan_version") or "unknown"),
        "title": str(plan.get("name") or plan.get("symbol") or "未命名规则"),
        "summary": str(
            plan.get("current_action")
            or plan.get("then_action")
            or "继续观察，不生成操作提醒"
        ),
        "status": status,
        "data_quality": quality,
        "blocking_reasons": blocking,
        "monitor_eligible": (
            status == "confirmed"
            and not blocking
            and plan.get("status") != "blocked"
            and quality == "ready"
        ),
        "response": str(plan.get("user_response_status") or "pending"),
    }


def _decision_requirement(
    plan: Mapping[str, object],
    rule: Rule,
) -> DecisionRequirement:
    state: DecisionRequirementStatus = (
        "blocked"
        if rule["status"] == "blocked"
        else "confirmed"
        if rule["status"] == "confirmed"
        else "disabled"
        if rule["status"] == "disabled"
        else "observation_only"
        if rule["status"] == "observation_only"
        else "pending_confirmation"
    )
    if state == "blocked":
        prompt = "数据阻断尚未解除；只能确认已知悉、请求修改或暂不启用，不能绕过阻断。"
        allowed = ["blocked_acknowledged", "disputed", "disabled"]
    elif state == "confirmed":
        prompt = (
            "规则已确认；可请求修改或暂不启用。只有确认且未阻断的规则可进入提醒候选。"
        )
        allowed = ["disputed", "disabled"]
    elif state == "disabled":
        prompt = "规则已暂不启用，不会生成操作提醒；后续需由新版本重新进入确认。"
        allowed = ["disputed"]
    elif state == "observation_only":
        prompt = "当前仅观察，不生成操作提醒。"
        allowed = ["disputed", "disabled"]
    elif rule["status"] == "modification_requested":
        prompt = "修改请求已记录；等待新规则版本，当前版本不会生成操作提醒。"
        allowed = ["disabled"]
    else:
        prompt = "请确认当前条件规则；未确认前不会生成操作提醒。"
        allowed = ["accepted", "disputed", "disabled"]
    return {
        "requirement_id": f"decision:{rule['rule_id']}",
        "title": f"{rule['title']}｜{rule['summary']}",
        "prompt": prompt,
        "status": state,
        "rule_id": rule["rule_id"],
        "rule_version": rule["rule_version"],
        "data_quality": rule["data_quality"],
        "blocking_reasons": rule["blocking_reasons"],
        "allowed_responses": allowed,
        "detail_route": "portfolio",
    }


def _rule_status(plan: Mapping[str, object]) -> RuleStatus:
    response = str(plan.get("user_response_status") or "pending")
    if response in {"disabled", "rejected"}:
        return "disabled"
    if plan.get("status") == "blocked":
        return "blocked"
    if response == "accepted":
        return "confirmed"
    if response == "disputed":
        return "modification_requested"
    if response == "deferred":
        return "observation_only"
    return "pending_confirmation"


def _importance(
    plan: Mapping[str, object],
    state: RuleStatus,
    blocking: list[str],
) -> int:
    score = {
        "blocked": 100,
        "pending_confirmation": 80,
        "modification_requested": 75,
        "confirmed": 60,
        "observation_only": 35,
        "disabled": 10,
    }[state]
    priority = str(plan.get("priority") or "").lower()
    if priority in {"高", "high", "p0"}:
        score += 10
    elif priority in {"中", "medium", "p1"}:
        score += 5
    if blocking:
        score += min(10, len(blocking) * 2)
    return score


def _plan_quality(
    plan: Mapping[str, object],
    evidence: list[Evidence],
) -> DataQualityStatus:
    if plan.get("status") == "blocked" or _strings(plan.get("blocking_reasons")):
        return "blocked"
    qualities = [item["freshness"] for item in evidence]
    return _combined_quality(qualities) if qualities else "unknown"


def _combined_quality(values: list[DataQualityStatus]) -> DataQualityStatus:
    if not values:
        return "unknown"
    if "blocked" in values:
        return "blocked"
    if "stale" in values:
        return "stale"
    if "partial" in values or "unknown" in values:
        return "partial"
    return "ready"


def _quality(value: object) -> DataQualityStatus:
    state = str(value or "unknown").lower()
    if state in {"ready", "fresh", "current", "available"}:
        return "ready"
    if state in {"stale", "expired", "historical"}:
        return "stale"
    if state in {"blocked", "missing", "failed", "unavailable"}:
        return "blocked"
    if state in {"partial", "pending"}:
        return "partial"
    return "unknown"


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _dict_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(value: object) -> float | None:
    parsed = _number(value)
    if parsed is None:
        return None
    return max(0.0, min(1.0, parsed))
