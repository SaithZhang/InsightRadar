"""Canonical P0 contract for the InsightRadar decision workspace.

The after-close JSON remains the source of truth.  This module adds a stable,
typed view over that payload and owns the small local audit ledger used for
plan responses.  It deliberately does not implement intraday monitoring.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Literal, Mapping, TypedDict

from stock_assist.decision_evidence import (
    build_decision_evidence,
    link_evidence_to_plans,
)
from stock_assist.paths import DATA_DIR
from stock_assist.portfolio import Portfolio, portfolio_version
from stock_assist.signal_outcomes import price_basis_quarantine_reason


DataStatus = Literal["ready", "stale", "missing", "blocked", "pending", "failed"]
PlanStatus = Literal["unchanged", "revised", "voided", "new", "blocked"]
ResponseStatus = Literal[
    "pending",
    "accepted",
    "disputed",
    "rejected",
    "deferred",
    "blocked_acknowledged",
]
RunStage = Literal["after_close", "morning_recheck"]

DEFAULT_RESPONSE_LEDGER = DATA_DIR / "decision_workspace_responses.jsonl"
DEFAULT_PLAN_LEDGER = DATA_DIR / "decision_workspace_plans.jsonl"
DEFAULT_RUNTIME_STATE = DATA_DIR / "decision_workspace_runtime.json"
ALLOWED_RESPONSES = {
    "accepted",
    "disputed",
    "rejected",
    "deferred",
    "blocked_acknowledged",
}


def _requires_user_action(plan: Mapping[str, object]) -> bool:
    return (
        plan.get("status") in {"new", "revised", "voided", "blocked"}
        and plan.get("user_response_status") == "pending"
    )


def _requires_today_attention(plan: Mapping[str, object]) -> bool:
    if plan.get("status") == "blocked":
        return True
    return _requires_user_action(plan)


class DataHealthItem(TypedDict):
    id: str
    label: str
    status: DataStatus
    source_name: str
    source_time: str | None
    fetched_at: str
    freshness_rule: str
    is_simulated: bool
    error_code: str | None
    gap_reason: str | None
    evidence: str | None
    repair_action: str | None
    owner: str
    next_check: str


class DecisionPlan(TypedDict):
    plan_id: str
    symbol: str
    name: str
    plan_version: str
    previous_version: str | None
    status: PlanStatus
    current_branch: str
    current_action: str
    current_next_event: str
    if_condition: str
    then_action: str
    until_condition: str
    invalid_condition: str
    market_permission: str
    priority: str
    risk_constraints: list[str]
    blocking_reasons: list[str]
    authority_state: str
    next_event: str
    continue_waiting: str
    evidence_refs: list[str]
    branches: list[dict[str, object]]
    technical_snapshot: dict[str, object]
    cost_reference: dict[str, object]
    change_reasons: list[str]
    created_at: str
    effective_after_user_confirmation: bool
    user_response_status: ResponseStatus
    user_response_note: str
    user_response_at: str | None


def build_decision_workspace(
    payload: Mapping[str, object],
    portfolio: Portfolio,
    *,
    run_stage: RunStage = "after_close",
    generated_at: datetime | None = None,
    response_ledger: Path = DEFAULT_RESPONSE_LEDGER,
    plan_ledger: Path = DEFAULT_PLAN_LEDGER,
) -> dict[str, object]:
    """Build the additive V3 workspace without changing existing payload keys."""

    now = generated_at or _parse_datetime(payload.get("generated_at")) or datetime.now()
    decision = _mapping(payload.get("unified_decision"))
    reliability = _mapping(payload.get("reliability"))
    market_matrix = _mapping(payload.get("market_matrix"))
    responses = load_plan_responses(response_ledger)
    latest_by_plan = _latest_responses(responses)
    raw_plan_history = load_plan_versions(plan_ledger)
    previous_plans = _latest_plan_versions(raw_plan_history)
    plan_history = _annotate_plan_history(raw_plan_history, portfolio)
    plans = _plans(decision, reliability, now, latest_by_plan, previous_plans)
    gaps = _string_list(payload.get("data_gaps"))
    data_health = _data_health(decision, gaps, now)
    decision_evidence = build_decision_evidence(
        decision,
        data_health,
        plans,
    )
    link_evidence_to_plans(plans, decision_evidence)
    market_gate = _market_gate(decision, data_health)
    positions = _portfolio_positions(portfolio, plans)
    actionable = [plan for plan in plans if _requires_user_action(plan)]
    today_plans = [plan for plan in plans if _requires_today_attention(plan)]
    unresolved_blocked = [plan for plan in plans if plan["status"] == "blocked"]
    accepted = [
        plan
        for plan in plans
        if plan["user_response_status"] == "accepted"
        and plan["status"] not in {"voided", "blocked"}
    ]
    return {
        "schema_version": "decision-workspace/v1",
        "generated_at": now.isoformat(timespec="seconds"),
        "source_generated_at": str(
            payload.get("generated_at") or now.isoformat(timespec="seconds")
        ),
        "portfolio_version": portfolio_version(portfolio),
        "effective_market_date": str(decision.get("plan_date") or now.date().isoformat()),
        "run_stage": run_stage,
        "runtime_status": (
            "awaiting_confirmation"
            if actionable
            else "blocked_waiting"
            if unresolved_blocked
            else "reviewed"
        ),
        "stage_note": (
            "盘后生成：形成次日条件计划。"
            if run_stage == "after_close"
            else "晨间增量复核：仅重算现有来源时效；本阶段未接入实时行情刷新。"
        ),
        "data_health": data_health,
        "decision_evidence": decision_evidence,
        "market_gate": market_gate,
        "theme_observations": _theme_observations(market_matrix),
        "portfolio_summary": _portfolio_summary(portfolio, reliability),
        "portfolio_positions": positions,
        "plan_changes": actionable,
        "today_plans": today_plans,
        "attention_summary": {
            "pending_response_count": len(actionable),
            "unresolved_blocked_count": len(unresolved_blocked),
            "effective_plan_count": len(accepted),
        },
        "active_plans": plans,
        "plan_version_history": plan_history,
        "quarantined_plan_version_count": sum(
            item.get("evaluation_status") == "quarantined"
            for item in plan_history
        ),
        "research_tasks": _research_tasks(payload),
        "user_responses": responses,
        "monitor_handoffs": [
            {
                "status": "blocked",
                "reason": "P2 才接入真实 5 分钟盘中监控；未确认计划不会进入监控。",
                "eligible_plan_ids": [item["plan_id"] for item in accepted],
                "implemented": False,
            }
        ],
        "outcome_summary": _mapping(payload.get("signal_outcomes")),
        "provenance": {
            "rule_engine": [
                "unified_decision",
                "market_matrix",
                "core_reliability",
            ],
            "research_evidence": [
                str(item.get("source_name"))
                for item in data_health
                if item["status"] == "ready"
            ],
            "ai_summary": {
                "status": "not_used",
                "reason": "P0 的交易计划由规则生成；AI/NLP 留待后续非规则场景。",
            },
            "user_action": [item["response_id"] for item in responses],
        },
    }


def record_plan_versions(
    workspace: Mapping[str, object],
    path: Path = DEFAULT_PLAN_LEDGER,
) -> list[dict[str, object]]:
    """Persist only new plan versions; unchanged reruns do not add noise."""

    rows = load_plan_versions(path)
    latest = _latest_plan_versions(rows)
    plans = workspace.get("active_plans")
    for item in plans if isinstance(plans, list) else []:
        if not isinstance(item, Mapping):
            continue
        plan_id = str(item.get("plan_id") or "")
        version = str(item.get("plan_version") or "")
        if not plan_id or not version:
            continue
        previous = latest.get(plan_id)
        if previous and previous.get("plan_version") == version:
            continue
        record = {
            "plan_id": plan_id,
            "symbol": str(item.get("symbol") or ""),
            "plan_version": version,
            "previous_version": (
                str(previous.get("plan_version")) if previous else None
            ),
            "status": str(item.get("status") or "blocked"),
            "priority": str(item.get("priority") or "中"),
            "current_branch": str(item.get("current_branch") or ""),
            "current_action": str(item.get("current_action") or ""),
            "current_next_event": str(item.get("current_next_event") or ""),
            "if_condition": str(item.get("if_condition") or ""),
            "then_action": str(item.get("then_action") or ""),
            "until_condition": str(item.get("until_condition") or ""),
            "invalid_condition": str(item.get("invalid_condition") or ""),
            "blocking_reasons": _string_list(item.get("blocking_reasons")),
            "authority_state": str(item.get("authority_state") or "blocked"),
            "next_event": str(item.get("next_event") or ""),
            "change_reasons": _string_list(item.get("change_reasons")),
            "created_at": str(item.get("created_at") or datetime.now().isoformat(timespec="seconds")),
        }
        rows.append(record)
        latest[plan_id] = record
    _atomic_write_text(
        path,
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in rows),
    )
    workspace_history = workspace.get("plan_version_history")
    annotations = {
        (
            str(item.get("plan_id") or ""),
            str(item.get("plan_version") or ""),
        ): {
            "evaluation_status": item.get("evaluation_status"),
            "quarantine_reason": item.get("quarantine_reason"),
        }
        for item in (
            workspace_history if isinstance(workspace_history, list) else []
        )
        if isinstance(item, Mapping) and item.get("evaluation_status")
    }
    return [
        {
            **item,
            **annotations.get(
                (
                    str(item.get("plan_id") or ""),
                    str(item.get("plan_version") or ""),
                ),
                {
                    "evaluation_status": "eligible",
                    "quarantine_reason": None,
                },
            ),
        }
        for item in rows
    ]


def overlay_plan_responses(
    workspace: Mapping[str, object],
    *,
    response_ledger: Path = DEFAULT_RESPONSE_LEDGER,
) -> dict[str, object]:
    """Return a refreshed copy with the latest persisted user responses."""

    result = deepcopy(dict(workspace))
    responses = load_plan_responses(response_ledger)
    latest = _latest_responses(responses)
    for key in ("plan_changes", "today_plans", "active_plans"):
        rows = result.get(key)
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            response = latest.get(str(item.get("plan_id")))
            if response and response.get("plan_version") == item.get("plan_version"):
                item["user_response_status"] = response["response"]
                item["user_response_note"] = response.get("note", "")
                item["user_response_at"] = response.get("created_at")
    result["user_responses"] = responses
    active_plans = result.get("active_plans")
    if isinstance(active_plans, list):
        actionable = [
            item
            for item in active_plans
            if isinstance(item, dict) and _requires_user_action(item)
        ]
        today_plans = [
            item
            for item in active_plans
            if isinstance(item, dict) and _requires_today_attention(item)
        ]
        unresolved_blocked = [
            item
            for item in active_plans
            if isinstance(item, dict) and item.get("status") == "blocked"
        ]
        accepted = [
            item
            for item in active_plans
            if isinstance(item, dict)
            and item.get("user_response_status") == "accepted"
            and item.get("status") not in {"voided", "blocked"}
        ]
        result["plan_changes"] = actionable
        result["today_plans"] = today_plans
        result["attention_summary"] = {
            "pending_response_count": len(actionable),
            "unresolved_blocked_count": len(unresolved_blocked),
            "effective_plan_count": len(accepted),
        }
        result["runtime_status"] = (
            "awaiting_confirmation"
            if actionable
            else "blocked_waiting"
            if unresolved_blocked
            else "reviewed"
        )
    return result


def restage_workspace(
    workspace: Mapping[str, object],
    *,
    run_stage: RunStage,
    now: datetime | None = None,
) -> dict[str, object]:
    """Move the same evidence into a declared run stage without inventing data."""

    result = deepcopy(dict(workspace))
    current = now or datetime.now()
    result["generated_at"] = current.isoformat(timespec="seconds")
    result["run_stage"] = run_stage
    result["stage_note"] = (
        "盘后生成：形成次日条件计划。"
        if run_stage == "after_close"
        else "晨间增量复核：仅重算现有来源时效；本阶段未接入实时行情刷新。"
    )
    health = result.get("data_health")
    if isinstance(health, list):
        for item in health:
            if not isinstance(item, dict) or item.get("status") != "ready":
                continue
            source_date = _parse_date(item.get("source_time"))
            if source_date and (current.date() - source_date).days > 1:
                item["status"] = "stale"
                item["gap_reason"] = "晨间复核发现来源已超过 1 个自然日。"
    return result


def append_plan_response(
    *,
    plan_id: str,
    plan_version: str,
    response: str,
    note: str = "",
    plan_status: str | None = None,
    ledger_path: Path = DEFAULT_RESPONSE_LEDGER,
    created_at: datetime | None = None,
) -> dict[str, object]:
    """Atomically append a validated response to the local JSONL ledger."""

    clean_plan_id = plan_id.strip()
    clean_version = plan_version.strip()
    if not clean_plan_id or not clean_version:
        raise ValueError("plan_id 和 plan_version 不能为空")
    if response not in ALLOWED_RESPONSES:
        raise ValueError(f"不支持的计划回应：{response}")
    if plan_status == "blocked" and response == "accepted":
        raise ValueError("blocked 计划不能采纳；数据恢复并生成新计划版本后才能采纳")
    if response == "blocked_acknowledged" and plan_status != "blocked":
        raise ValueError("只有 blocked 计划可以确认已知悉阻断")
    now = created_at or datetime.now()
    record = {
        "response_id": hashlib.sha256(
            f"{clean_plan_id}|{clean_version}|{response}|{now.isoformat()}".encode("utf-8")
        ).hexdigest()[:20],
        "plan_id": clean_plan_id,
        "plan_version": clean_version,
        "response": response,
        "note": note.strip(),
        "created_at": now.isoformat(timespec="seconds"),
    }
    rows = load_plan_responses(ledger_path)
    rows.append(record)
    _atomic_write_text(
        ledger_path,
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in rows),
    )
    return record


def load_plan_responses(path: Path = DEFAULT_RESPONSE_LEDGER) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(item, dict)
            and item.get("plan_id")
            and item.get("plan_version")
            and item.get("response") in ALLOWED_RESPONSES
        ):
            rows.append(item)
    return rows


def load_plan_versions(path: Path = DEFAULT_PLAN_LEDGER) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("plan_id") and item.get("plan_version"):
            rows.append(item)
    return rows


def write_runtime_state(
    workspace: Mapping[str, object],
    path: Path = DEFAULT_RUNTIME_STATE,
) -> None:
    _atomic_write_text(
        path,
        json.dumps(dict(workspace), ensure_ascii=False, indent=2, default=str) + "\n",
    )


def load_runtime_state(path: Path = DEFAULT_RUNTIME_STATE) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _plans(
    decision: Mapping[str, object],
    reliability: Mapping[str, object],
    now: datetime,
    latest_responses: Mapping[str, Mapping[str, object]],
    previous_plans: Mapping[str, Mapping[str, object]],
) -> list[DecisionPlan]:
    raw = decision.get("holding_plans")
    rows = raw if isinstance(raw, list) else []
    market_permission = str(decision.get("stance") or "等待确认")
    global_constraints = _string_list(decision.get("blocked_actions"))
    plans: list[DecisionPlan] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("code") or "").strip()
        if not symbol:
            continue
        plan_id = f"holding:{symbol}"
        priority = str(item.get("priority") or "中")
        contract = _mapping(item.get("decision_contract"))
        contract_branches = _decision_branches(contract)
        repair = contract_branches.get("repair_observe", {})
        risk = contract_branches.get("risk_reduce_review", {})
        waiting = contract_branches.get("continue_waiting", {})
        if contract_branches:
            current_branch, current_action, current_next_event = _current_plan_state(
                contract,
                repair=repair,
                risk=risk,
                waiting=waiting,
            )
            content = {
                "symbol": symbol,
                "current_branch": current_branch,
                "current_action": current_action,
                "current_next_event": current_next_event,
                "if": _branch_condition(repair),
                "then": str(repair.get("action") or "修复成立后转为持有观察"),
                "until": _branch_condition(waiting),
                "invalid": _branch_condition(risk),
                "permission": market_permission,
            }
        else:
            current_action = str(
                item.get("position_action") or item.get("action") or "保持原计划"
            )
            content = {
                "symbol": symbol,
                "current_branch": "legacy_current",
                "current_action": current_action,
                "current_next_event": str(
                    item.get("upside_trigger")
                    or item.get("flat_trigger")
                    or "等待条件明确"
                ),
                "if": str(item.get("upside_trigger") or item.get("flat_trigger") or "等待条件明确"),
                "then": current_action,
                "until": str(item.get("flat_trigger") or "下一次有效复核"),
                "invalid": str(item.get("downside_trigger") or "风险线被触发"),
                "permission": market_permission,
            }
        version = "v-" + hashlib.sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:10]
        previous = previous_plans.get(plan_id)
        previous_version = str(previous.get("plan_version")) if previous else None
        blocking_reasons = _plan_blockers(
            symbol=symbol,
            action=content["current_action"],
            decision=decision,
            reliability=reliability,
        )
        if blocking_reasons:
            status: PlanStatus = "blocked"
        elif "退出" in content["then"] or "作废" in content["then"]:
            status = "voided"
        elif previous_version is None:
            status = "new"
        elif previous_version == version:
            status = "unchanged"
        else:
            status = "revised"
        response_status: ResponseStatus = "pending"
        response_note = ""
        response_at: str | None = None
        previous_response = latest_responses.get(plan_id)
        if previous_response and previous_response.get("plan_version") == version:
            response_status = str(previous_response.get("response"))  # type: ignore[assignment]
            response_note = str(previous_response.get("note") or "")
            response_at = str(previous_response.get("created_at") or "") or None
        if status != "blocked" and response_status == "blocked_acknowledged":
            response_status = "pending"
            response_note = "原回应仅确认知悉阻断；阻断解除后需重新确认当前计划。"
            response_at = None
        elif status == "blocked" and response_status == "accepted":
            response_status = "pending"
            response_note = "当前新增阻断已撤销旧执行授权；需先知悉阻断。"
            response_at = None
        plans.append(
            {
                "plan_id": plan_id,
                "symbol": symbol,
                "name": str(item.get("name") or symbol),
                "plan_version": version,
                "previous_version": previous_version,
                "status": status,
                "current_branch": content["current_branch"],
                "current_action": content["current_action"],
                "current_next_event": content["current_next_event"],
                "if_condition": content["if"],
                "then_action": content["then"],
                "until_condition": content["until"],
                "invalid_condition": content["invalid"],
                "market_permission": market_permission,
                "priority": priority,
                "risk_constraints": _dedupe_strings(
                    [*blocking_reasons, *global_constraints]
                ),
                "blocking_reasons": blocking_reasons,
                "authority_state": (
                    "blocked"
                    if status == "blocked"
                    else "effective"
                    if response_status == "accepted"
                    else "awaiting_confirmation"
                ),
                "next_event": content["current_next_event"],
                "continue_waiting": content["until"],
                "evidence_refs": ["unified_decision", f"holding:{symbol}"],
                "branches": list(contract_branches.values()),
                "technical_snapshot": _mapping(contract.get("technical")),
                "cost_reference": _mapping(contract.get("cost_reference")),
                "change_reasons": (
                    ["首次形成可审核计划"]
                    if status == "new"
                    else ["计划内容相对已回应版本发生变化"]
                    if status == "revised"
                    else blocking_reasons
                    if status == "blocked"
                    else ["计划内容未变化"]
                ),
                "created_at": now.isoformat(timespec="seconds"),
                "effective_after_user_confirmation": status != "blocked",
                "user_response_status": response_status,
                "user_response_note": response_note,
                "user_response_at": response_at,
            }
        )
    return sorted(
        plans,
        key=lambda plan: (
            {"高": 0, "中": 1, "低": 2}.get(plan["priority"], 3),
            0 if plan["status"] == "blocked" else 1,
            plan["symbol"],
        ),
    )


def _current_plan_state(
    contract: Mapping[str, object],
    *,
    repair: Mapping[str, object],
    risk: Mapping[str, object],
    waiting: Mapping[str, object],
) -> tuple[str, str, str]:
    technical = _mapping(contract.get("technical"))
    state = str(technical.get("state") or "unknown")
    risk_trigger = str(risk.get("trigger") or "")
    risk_active = state == "weak" and "已" in risk_trigger
    if risk_active:
        return (
            "risk_reduce_review",
            str(contract.get("action") or risk.get("action") or "降低仓位复核"),
            str(risk.get("persistence") or risk_trigger or "等待风险分支确认"),
        )
    return (
        "continue_waiting",
        str(contract.get("action") or waiting.get("action") or "继续等待"),
        (
            "下一有效收盘检查：修复="
            + str(repair.get("trigger") or "等待条件明确").rstrip("。； ")
            + "；风险="
            + str(risk.get("trigger") or "等待条件明确").rstrip("。； ")
        )
        or str(waiting.get("persistence") or "等待下一次有效收盘"),
    )


def _decision_branches(
    contract: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    raw = contract.get("branches")
    rows = raw if isinstance(raw, list) else []
    result: dict[str, dict[str, object]] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        branch_id = str(item.get("branch_id") or "")
        if branch_id:
            result[branch_id] = dict(item)
    required = {"repair_observe", "risk_reduce_review", "continue_waiting"}
    return result if required.issubset(result) else {}


def _branch_condition(branch: Mapping[str, object]) -> str:
    trigger = str(branch.get("trigger") or "等待条件明确")
    persistence = str(branch.get("persistence") or "")
    return f"{trigger} 持续条件：{persistence}" if persistence else trigger


def _plan_blockers(
    *,
    symbol: str,
    action: str,
    decision: Mapping[str, object],
    reliability: Mapping[str, object],
) -> list[str]:
    blockers: list[str] = []
    budget = _mapping(decision.get("risk_budget"))
    risk_level = str(budget.get("risk_level") or "unknown")
    if risk_level == "unknown":
        blockers.append("风险预算缺失，当前计划不能进入执行授权。")
    if _adds_exposure(action) and (
        risk_level in {"red", "orange"}
        or bool(budget.get("upgrade_blocked"))
        or not bool(budget.get("upgrade_eligible", True))
    ):
        blockers.append("当前风险预算禁止新增或提高风险仓位。")

    reconciliation = str(
        reliability.get("risk_reconciliation_status") or ""
    )
    if reconciliation == "blocked":
        blockers.append("组合风险预算对账未完成，计划只能保留为条件草案。")

    holding_rows = reliability.get("holdings")
    matching: Mapping[str, object] | None = None
    for item in holding_rows if isinstance(holding_rows, list) else []:
        if isinstance(item, Mapping) and str(item.get("code") or "") == symbol:
            matching = item
            break
    if matching is not None:
        missing_fields = _string_list(matching.get("missing_snapshot_fields"))
        if missing_fields:
            blockers.append(
                "持仓快照缺少字段：" + "、".join(missing_fields[:4]) + "。"
            )
        if matching.get("context_complete") is False:
            blockers.append("该持仓上下文未补全，需先恢复持仓级证据。")
        holding_reconciliation = str(
            matching.get("risk_reconciliation_status") or ""
        )
        if holding_reconciliation == "blocked" and reconciliation != "blocked":
            blockers.append("该持仓风险预算对账未完成。")
        if (
            matching.get("decision_ready") is False
            and not blockers
        ):
            blockers.append("该持仓尚未达到严格决策就绪门槛。")
    return _dedupe_strings(blockers)


def _adds_exposure(action: str) -> bool:
    clean = action.strip()
    if any(
        marker in clean
        for marker in ("不加仓", "不主动加仓", "不补仓", "不追涨", "不得加仓")
    ):
        return False
    return any(
        marker in clean
        for marker in ("加仓", "补仓", "新增仓位", "提高仓位", "追涨")
    )


def _data_health(
    decision: Mapping[str, object],
    gaps: list[str],
    now: datetime,
) -> list[DataHealthItem]:
    rows = decision.get("source_reports")
    sources = rows if isinstance(rows, list) else []
    labels = {
        "risk_watch": "市场风险",
        "market_pulse": "市场脉冲",
        "market_levels": "关键价位",
        "ai_capex_watch": "产业研究",
        "style_rotation": "风格轮动",
    }
    result: list[DataHealthItem] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        workflow = str(item.get("workflow") or "unknown")
        raw_status = str(item.get("status") or "missing")
        as_of = str(
            item.get("source_time")
            or item.get("as_of")
            or ""
        ) or None
        source_date = _parse_date(as_of)
        if raw_status == "current" and source_date:
            status: DataStatus = (
                "ready" if (now.date() - source_date).days <= 1 else "stale"
            )
        elif raw_status in {"blocked", "failed"}:
            status = raw_status  # type: ignore[assignment]
        else:
            status = "missing"
        if raw_status == "current" and source_date is None:
            gap_reason = "来源标记为 current，但缺少 source_time/as_of。"
        elif status == "stale":
            gap_reason = "来源超过新鲜度窗口。"
        elif status == "ready":
            gap_reason = None
        else:
            gap_reason = str(item.get("reason") or raw_status)
        result.append(
            {
                "id": workflow,
                "label": labels.get(workflow, workflow),
                "status": status,
                "source_name": workflow,
                "source_time": as_of,
                "fetched_at": now.isoformat(timespec="seconds"),
                "freshness_rule": "来源日期不晚于工作台生成日期 1 个自然日",
                "is_simulated": False,
                "error_code": None if status in {"ready", "stale"} else "SOURCE_UNAVAILABLE",
                "gap_reason": gap_reason,
                "evidence": str(item.get("path") or "") or None,
                "repair_action": (
                    None
                    if status == "ready"
                    else f"重新运行 {workflow} 并校验权威 source_time/as_of。"
                ),
                "owner": workflow,
                "next_check": (
                    "下一次 after-close 生成时"
                    if status != "ready"
                    else "晨间复核检查新鲜度"
                ),
            }
        )
    if gaps:
        result.append(
            {
                "id": "core_data_gaps",
                "label": "核心数据缺口",
                "status": "blocked",
                "source_name": "after-close",
                "source_time": now.date().isoformat(),
                "fetched_at": now.isoformat(timespec="seconds"),
                "freshness_rule": "核心决策字段不得缺失或以 0 推断",
                "is_simulated": False,
                "error_code": "CORE_DATA_GAP",
                "gap_reason": "；".join(gaps[:3]),
                "evidence": "after-close.data_gaps",
                "repair_action": "补齐命中的持仓上下文或账户字段后，重新生成 after-close。",
                "owner": "portfolio / after-close",
                "next_check": "字段补齐并重新生成计划版本后",
            }
        )
    return result


def _market_gate(
    decision: Mapping[str, object],
    health: list[DataHealthItem],
) -> dict[str, object]:
    budget = _mapping(decision.get("risk_budget"))
    blocked_count = sum(item["status"] in {"missing", "blocked", "failed"} for item in health)
    return {
        "permission": str(decision.get("stance") or "等待确认"),
        "risk_level": str(budget.get("risk_level") or "unknown"),
        "risk_score": budget.get("risk_score"),
        "first_action": str(decision.get("first_action") or "补齐数据前不新增仓位"),
        "status": "blocked" if blocked_count else "ready",
        "reason": (
            f"{blocked_count} 项核心来源不可用，计划只可审核、不可直接授权执行。"
            if blocked_count
            else "核心来源已就绪；仍需逐条确认计划。"
        ),
    }


def _portfolio_positions(
    portfolio: Portfolio,
    plans: list[DecisionPlan],
) -> list[dict[str, object]]:
    by_symbol = {item["symbol"]: item for item in plans}
    result: list[dict[str, object]] = []
    for holding in portfolio.holdings:
        plan = by_symbol.get(holding.code)
        result.append(
            {
                "symbol": holding.code,
                "name": holding.name or holding.code,
                "shares": holding.shares,
                "cost": holding.cost,
                "market_price": holding.market_price,
                "market_value": holding.market_value,
                "weight_pct": holding.weight_pct,
                "pnl_pct": holding.pnl_pct,
                "beta_classification": holding.beta_classification or "unknown",
                "review_status": holding.review_status or "unknown",
                "data_completeness": (
                    "ready"
                    if all(
                        value is not None
                        for value in (
                            holding.shares,
                            holding.cost,
                            holding.market_price,
                            holding.pnl_pct,
                        )
                    )
                    else "missing"
                ),
                "current_plan_id": plan["plan_id"] if plan else None,
                "current_plan_version": plan["plan_version"] if plan else None,
                "today_status": plan["status"] if plan else "blocked",
                "next_condition": plan["if_condition"] if plan else "等待形成规则计划",
            }
        )
    return result


def _portfolio_summary(
    portfolio: Portfolio,
    reliability: Mapping[str, object],
) -> dict[str, object]:
    weights = [item.weight_pct for item in portfolio.holdings if item.weight_pct is not None]
    return {
        "holding_count": len(portfolio.holdings),
        "cash": portfolio.cash,
        "snapshot_as_of": portfolio.as_of or None,
        "source_name": str(portfolio.source),
        "source_status": "missing" if portfolio.missing else "ready",
        "risk_reconciliation_status": portfolio.risk_reconciliation_status,
        "known_exposure_pct": sum(weights) if weights else None,
        "decision_ready_holdings": reliability.get("decision_ready_holdings", 0),
        "unknown_fields_remain_unknown": True,
    }


def _theme_observations(matrix: Mapping[str, object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    groups = matrix.get("groups")
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        for card in group.get("cards", []) if isinstance(group.get("cards"), list) else []:
            if not isinstance(card, dict):
                continue
            result.append(
                {
                    "id": card.get("id"),
                    "label": card.get("label"),
                    "status": card.get("freshness", "unavailable"),
                    "state": card.get("state"),
                    "day_change": card.get("day_change"),
                    "authority": "diagnostic_only",
                }
            )
    return result


def _research_tasks(payload: Mapping[str, object]) -> list[dict[str, object]]:
    sections = payload.get("sections")
    result: list[dict[str, object]] = []
    for item in sections if isinstance(sections, list) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        if any(marker in title for marker in ("研究", "公告", "同业", "业绩", "事件")):
            result.append(
                {
                    "task_id": hashlib.sha256(title.encode("utf-8")).hexdigest()[:12],
                    "title": title,
                    "status": "evidence_available",
                    "source": "after-close.sections",
                }
            )
    return result


def _latest_responses(
    rows: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    return {str(item["plan_id"]): item for item in rows}


def _latest_plan_versions(
    rows: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    return {str(item["plan_id"]): item for item in rows}


def _annotate_plan_history(
    rows: list[dict[str, object]],
    portfolio: Portfolio,
) -> list[dict[str, object]]:
    snapshot_date = _parse_date(portfolio.as_of)
    market_prices = {
        holding.code: holding.market_price
        for holding in portfolio.holdings
        if holding.market_price is not None and holding.market_price > 0
    }
    result = deepcopy(rows)
    for item in result:
        symbol = str(item.get("symbol") or "")
        market_price = market_prices.get(symbol)
        if market_price is None:
            continue
        created_date = _parse_date(item.get("created_at"))
        if (
            snapshot_date is None
            or created_date is None
            or abs((snapshot_date - created_date).days) > 10
        ):
            continue
        rule_text = " ".join(
            str(item.get(field) or "")
            for field in (
                "current_action",
                "current_next_event",
                "if_condition",
                "then_action",
                "until_condition",
                "invalid_condition",
            )
        )
        quarantine_reason = price_basis_quarantine_reason(
            rule_text,
            market_price,
        )
        if quarantine_reason:
            item["evaluation_status"] = "quarantined"
            item["quarantine_reason"] = quarantine_reason
        else:
            item["evaluation_status"] = "eligible"
            item["quarantine_reason"] = None
    return result


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))


def _parse_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()
