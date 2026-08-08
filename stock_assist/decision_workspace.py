"""Canonical P0 contract for the InsightRadar decision workspace.

The after-close JSON remains the source of truth.  This module adds a stable,
typed view over that payload and owns the small local audit ledger used for
plan responses.  It deliberately does not implement intraday monitoring.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Literal, TypedDict

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
    "disabled",
    "blocked_acknowledged",
]
RunStage = Literal["after_close", "morning_recheck"]

DEFAULT_RESPONSE_LEDGER = DATA_DIR / "decision_workspace_responses.jsonl"
DEFAULT_PLAN_LEDGER = DATA_DIR / "decision_workspace_plans.jsonl"
DEFAULT_RUNTIME_STATE = DATA_DIR / "decision_workspace_runtime.json"
DEFAULT_DAILY_KLINE_REPAIR_STATE = DATA_DIR / "daily_kline_repair_state.json"
DAILY_KLINE_REPAIR_REASON_CODES = {
    "PRICE_BASIS_QUARANTINED",
    "SECURITY_MAPPING_INVALID",
    "PROVIDER_FIELD_MAPPING_INVALID",
    "MARKET_SERIES_MISSING",
    "MARKET_SERIES_STALE",
}
ALLOWED_RESPONSES = {
    "accepted",
    "disputed",
    "rejected",
    "deferred",
    "disabled",
    "blocked_acknowledged",
}


def _requires_user_action(plan: Mapping[str, object]) -> bool:
    return (
        plan.get("status") in {"new", "revised", "unchanged", "voided", "blocked"}
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
    data_evidence: dict[str, object]
    cost_reference: dict[str, object]
    data_status: str
    repair_issue_ids: list[str]
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
    management_plans = _management_plans(
        portfolio,
        plans,
        reliability,
        decision,
        now,
        based_on_report=str(payload.get("generated_at") or now.isoformat(timespec="seconds")),
    )
    gaps = _string_list(payload.get("data_gaps"))
    data_health = _data_health(decision, gaps, now)
    repair_issues = _repair_issues(
        portfolio,
        plans,
        reliability,
        management_plans,
        data_health,
    )
    _link_repair_issues(plans, repair_issues)
    decision_evidence = build_decision_evidence(
        decision,
        data_health,
        plans,
    )
    link_evidence_to_plans(plans, decision_evidence)
    market_gate = _market_gate(decision, data_health)
    positions = _portfolio_positions(portfolio, plans, reliability, management_plans)
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
        "portfolio_management_plans": management_plans,
        "repair_issues": repair_issues,
        "repair_summary": {
            "blocked_count": len(repair_issues),
            "manual_count": sum(
                item.get("manual_repair_allowed") is True
                for item in repair_issues
            ),
            "automatic_retry_count": sum(
                item.get("repair_method")
                in {"retry_after_close", "refresh_sources"}
                for item in repair_issues
            ),
        },
        "management_attention_summary": {
            "pending_count": sum(
                item.get("context_status") in {"system_proposed", "stale"}
                for item in management_plans
            ),
            "data_blocked_count": sum(
                item.get("data_status") == "data_blocked"
                for item in management_plans
            ),
            "confirmation_blocks_base_analysis": False,
        },
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
                "reason": "P2 才接入真实 5 分钟盘中监控；方案确认只影响个性化跟踪，不影响规则级基础监控。",
                "eligible_plan_ids": [
                    item["plan_id"] for item in plans if item["status"] != "blocked"
                ],
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
    _refresh_plan_collections(result)
    return result


def _refresh_plan_collections(result: dict[str, object]) -> None:
    active_plans = result.get("active_plans")
    if isinstance(active_plans, list):
        for item in active_plans:
            if (
                isinstance(item, dict)
                and item.get("status") == "blocked"
                and item.get("user_response_status") == "accepted"
            ):
                item["user_response_status"] = "pending"
                item["user_response_note"] = (
                    "当前数据阻断已撤销旧 accepted 的执行授权；修复并生成新版本后需重新确认。"
                )
                item["user_response_at"] = None
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


def restage_workspace(
    workspace: Mapping[str, object],
    *,
    run_stage: RunStage,
    now: datetime | None = None,
    latest_completed_trade_date: date | None = None,
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
    if run_stage == "morning_recheck":
        expected_date = latest_completed_trade_date
        result["latest_completed_trade_date"] = (
            expected_date.isoformat() if expected_date else None
        )
    else:
        expected_date = latest_completed_trade_date or _parse_date(
            result.get("latest_completed_trade_date")
        )
    health = result.get("data_health")
    if run_stage == "morning_recheck" and isinstance(health, list):
        for item in health:
            if not isinstance(item, dict) or item.get("status") != "ready":
                continue
            source_date = _parse_date(item.get("source_time"))
            if expected_date is None:
                item["status"] = "blocked"
                item["error_code"] = "LATEST_COMPLETED_TRADE_DATE_UNAVAILABLE"
                item["gap_reason"] = (
                    "晨间复核无法确认最近已完成交易日；核心来源不能继续保持 ready。"
                )
            elif source_date is None:
                item["status"] = "blocked"
                item["error_code"] = "SOURCE_TIME_MISSING"
                item["gap_reason"] = (
                    "晨间复核无法解析来源交易日；核心来源不能继续保持 ready。"
                )
            elif source_date < expected_date:
                item["status"] = "stale"
                item["error_code"] = "SOURCE_STALE"
                item["gap_reason"] = (
                    f"晨间复核发现来源交易日 {source_date.isoformat()} 早于最近已完成交易日 "
                    f"{expected_date.isoformat()}。"
                )
            item["freshness_rule"] = "来源交易日不得早于当前时点的最近已完成交易日"
        _recompute_morning_derived_state(result, health)
    return result


def _recompute_morning_derived_state(
    result: dict[str, object],
    health: list[object],
) -> None:
    health_rows = [item for item in health if isinstance(item, dict)]
    previous_gate = _mapping(result.get("market_gate"))
    result["market_gate"] = _market_gate(
        {
            "stance": previous_gate.get("permission"),
            "risk_budget": {
                "risk_level": previous_gate.get("risk_level"),
                "risk_score": previous_gate.get("risk_score"),
            },
            "first_action": previous_gate.get("first_action"),
        },
        health_rows,  # type: ignore[arg-type]
    )
    market_blocked = _mapping(result.get("market_gate")).get("status") != "ready"
    active = result.get("active_plans")
    plans = (
        [item for item in active if isinstance(item, dict)]
        if isinstance(active, list)
        else []
    )
    if market_blocked:
        blocker = "晨间复核发现核心市场来源非 ready，计划执行授权已撤销。"
        for plan in plans:
            plan["status"] = "blocked"
            plan["authority_state"] = "blocked"
            plan["blocking_reasons"] = _dedupe_strings(
                [*_string_list(plan.get("blocking_reasons")), blocker]
            )
            plan["risk_constraints"] = _dedupe_strings(
                [*_string_list(plan.get("risk_constraints")), blocker]
            )
            plan["change_reasons"] = _dedupe_strings(
                [*_string_list(plan.get("change_reasons")), blocker]
            )
            plan["effective_after_user_confirmation"] = False
            if plan.get("user_response_status") == "accepted":
                plan["user_response_status"] = "pending"
                plan["user_response_note"] = (
                    "晨间来源 freshness 降级已撤销旧 accepted 的当前执行授权；"
                    "修复并生成新版本后需重新确认。"
                )
                plan["user_response_at"] = None

    existing = result.get("repair_issues")
    retained = (
        [
            item
            for item in existing
            if isinstance(item, dict)
            and str(_mapping(item.get("entity")).get("type") or "") != "source"
        ]
        if isinstance(existing, list)
        else []
    )
    source_issues = _restaged_source_repair_issues(health_rows, plans)
    unique = {
        str(item.get("issue_id") or ""): item
        for item in [*retained, *source_issues]
        if item.get("issue_id")
    }
    repair_issues = list(unique.values())
    result["repair_issues"] = repair_issues
    _link_repair_issues(plans, repair_issues)  # type: ignore[arg-type]
    result["repair_summary"] = {
        "blocked_count": len(repair_issues),
        "manual_count": sum(
            item.get("manual_repair_allowed") is True for item in repair_issues
        ),
        "automatic_retry_count": sum(
            item.get("repair_method") in {"retry_after_close", "refresh_sources"}
            for item in repair_issues
        ),
    }
    by_plan_id = {str(item.get("plan_id") or ""): item for item in plans}
    positions = result.get("portfolio_positions")
    if isinstance(positions, list):
        for position in positions:
            if not isinstance(position, dict):
                continue
            plan = by_plan_id.get(str(position.get("current_plan_id") or ""))
            if plan:
                position["today_status"] = plan.get("status")
    _refresh_plan_collections(result)


def _restaged_source_repair_issues(
    health: list[dict[str, object]],
    plans: list[dict[str, object]],
) -> list[dict[str, object]]:
    plan_ids = [str(item.get("plan_id") or "") for item in plans]
    issues: list[dict[str, object]] = []
    for item in health:
        status = str(item.get("status") or "missing")
        if status == "ready":
            continue
        is_core_gap = item.get("id") == "core_data_gaps"
        source_name = str(item.get("source_name") or "after-close")
        field = "after_close.core_inputs" if is_core_gap else f"source.{source_name}"
        field_label = (
            "核心决策输入"
            if is_core_gap
            else str(item.get("label") or source_name)
        )
        reason_code = str(
            item.get("error_code")
            or ("SOURCE_STALE" if status == "stale" else "SOURCE_NOT_READY")
        )
        issues.append(
            _new_repair_issue(
                entity={"type": "source", "symbol": "", "name": field_label},
                field=field,
                field_label=field_label,
                status=status,
                reason_code=reason_code,
                reason=str(item.get("gap_reason") or f"{field_label}尚未就绪。"),
                source=source_name,
                source_time=item.get("source_time"),
                fetched_at=str(item.get("fetched_at") or "") or None,
                price_basis=None,
                current_value=status,
                known_context={
                    "evidence": item.get("evidence"),
                    "owner": item.get("owner"),
                    "freshness_rule": item.get("freshness_rule"),
                    "next_check": item.get("next_check"),
                },
                criticality_reason=(
                    str(item.get("freshness_rule") or "来源必须通过时效校验。")
                    + "；该来源参与市场权限或组合风险判断，不能用 0、默认值或猜测替代。"
                ),
                repair_allowed=True,
                manual_repair_allowed=False,
                repair_method="refresh_sources",
                repair_label=f"重新运行 {source_name} 并校验时间",
                input_format=None,
                next_action=(
                    "刷新完成后重新生成 after-close；失败时保留 blocked 和最新失败原因。"
                ),
                affected_plan_ids=plan_ids,
            )
        )
    return issues


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


def record_daily_kline_repair(
    issue: Mapping[str, object],
    *,
    workspace_generated_at: str,
    path: Path = DEFAULT_DAILY_KLINE_REPAIR_STATE,
    now: datetime | None = None,
) -> dict[str, object]:
    """Persist one system-owned, provider-specific daily K-line repair route."""

    reason_code = str(issue.get("reason_code") or "")
    if reason_code not in DAILY_KLINE_REPAIR_REASON_CODES:
        raise ValueError("当前问题不支持日线口径自动修复")
    entity = _mapping(issue.get("entity"))
    symbol = str(entity.get("symbol") or "")
    if not symbol:
        raise ValueError("修复问题缺少证券代码")
    existing = load_daily_kline_repairs(path)
    requested_at = (now or datetime.now()).isoformat(timespec="seconds")
    existing[symbol] = {
        "strategy": "tencent_forward_adjusted_whole_series",
        "reason_code": reason_code,
        "issue_id": str(issue.get("issue_id") or ""),
        "workspace_generated_at": workspace_generated_at,
        "requested_at": requested_at,
    }
    payload = {
        "schema_version": "daily-kline-repair/v1",
        "updated_at": requested_at,
        "repairs": existing,
    }
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    return existing[symbol]


def load_daily_kline_repairs(
    path: Path = DEFAULT_DAILY_KLINE_REPAIR_STATE,
) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = payload.get("repairs") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {
        str(symbol): dict(value)
        for symbol, value in raw.items()
        if isinstance(value, dict)
        and value.get("strategy") == "tencent_forward_adjusted_whole_series"
    }


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
                "data_evidence": _mapping(contract.get("data_evidence")),
                "cost_reference": _mapping(contract.get("cost_reference")),
                "data_status": (
                    "data_blocked"
                    if str(_mapping(contract.get("technical")).get("state") or "")
                    in {"unknown", "quarantined"}
                    else "ready"
                ),
                "repair_issue_ids": [],
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


def _management_plans(
    portfolio: Portfolio,
    plans: list[DecisionPlan],
    reliability: Mapping[str, object],
    decision: Mapping[str, object],
    now: datetime,
    *,
    based_on_report: str,
) -> list[dict[str, object]]:
    """Build deterministic per-holding proposals without turning consent into data."""

    by_symbol = {item["symbol"]: item for item in plans}
    reliability_by_symbol = {
        str(item.get("code")): item
        for item in (
            reliability.get("holdings")
            if isinstance(reliability.get("holdings"), list)
            else []
        )
        if isinstance(item, Mapping) and item.get("code")
    }
    result: list[dict[str, object]] = []
    next_review = str(decision.get("plan_date") or "下一次 after-close")
    for holding in portfolio.holdings:
        plan = by_symbol.get(holding.code)
        reliability_row = reliability_by_symbol.get(holding.code, {})
        technical = _mapping(plan.get("technical_snapshot") if plan else None)
        technical_state = str(
            reliability_row.get("technical_state")
            or technical.get("state")
            or "not_evaluated"
        )
        data_status = str(
            reliability_row.get("data_status")
            or ("data_blocked" if technical_state in {"unknown", "quarantined"} else "ready")
        )
        stale = holding.review_status == "stale_context" or holding.context_status == "stale"
        if stale:
            context_status = "stale"
        elif holding.context_status in {"user_confirmed", "user_modified"}:
            context_status = holding.context_status
        elif holding.context_status == "system_proposed":
            context_status = "system_proposed"
        elif reliability_row.get("current_context_complete") is True:
            context_status = "user_confirmed"
        else:
            context_status = "system_proposed"

        proposal = _system_management_proposal(
            holding,
            plan,
            data_status=data_status,
            next_review=next_review,
        )
        use_saved = context_status in {"user_confirmed", "user_modified"}
        name = holding.management_name if use_saved and holding.management_name else proposal["name"]
        trigger = holding.management_trigger if use_saved and holding.management_trigger else proposal["trigger"]
        persistence = (
            holding.management_persistence
            if use_saved and holding.management_persistence
            else proposal["persistence"]
        )
        action = holding.management_action if use_saved and holding.management_action else proposal["action"]
        invalidation = (
            holding.management_invalidation
            if use_saved and holding.management_invalidation
            else proposal["invalidation"]
        )
        review_status = (
            holding.review_status
            if use_saved and holding.review_status in {"watch", "risk_review", "profit_protect"}
            else str(proposal["review_status"])
        )
        rule = (
            holding.risk_line
            if use_saved and holding.risk_line
            else _management_rule_text(trigger, persistence, action, invalidation)
        )
        version_content = {
            "symbol": holding.code,
            "review_status": review_status,
            "name": name,
            "trigger": trigger,
            "persistence": persistence,
            "action": action,
            "invalidation": invalidation,
            "next_review": holding.next_review_date if use_saved and holding.next_review_date else next_review,
            "data_status": data_status,
        }
        generated_version = "mp-" + hashlib.sha256(
            json.dumps(version_content, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        blocked_capabilities = _string_list(reliability_row.get("blocked_capabilities"))
        available_capabilities = _string_list(reliability_row.get("available_capabilities"))
        basis = _management_basis(holding, plan, data_status)
        source_time = (
            str(technical.get("as_of") or "")
            if data_status == "ready"
            else portfolio.as_of
        ) or portfolio.as_of or None
        result.append(
            {
                "symbol": holding.code,
                "name": holding.name or holding.code,
                "context_status": context_status,
                "context_source": holding.context_source or (
                    "deterministic_rule_v1" if not use_saved else "legacy_context"
                ),
                "review_status": review_status,
                "suggestion_name": name,
                "trigger_condition": trigger,
                "confirmation_window": persistence,
                "triggered_action": action,
                "invalidation_condition": invalidation,
                "next_review_time": (
                    holding.next_review_date
                    if use_saved and holding.next_review_date
                    else next_review
                ),
                "current_risk_line": rule,
                "management_plan_version": (
                    holding.management_plan_version
                    if use_saved and holding.management_plan_version
                    else generated_version
                ),
                "system_proposal_version": generated_version,
                "based_on_report": holding.based_on_report if use_saved and holding.based_on_report else based_on_report,
                "confirmed_at": holding.confirmed_at or None,
                "generated_source": "deterministic_rule_v1",
                "source_time": source_time,
                "generated_at": now.isoformat(timespec="seconds"),
                "decision_basis": basis,
                "data_status": data_status,
                "technical_state": technical_state,
                "data_confidence": "部分可用" if data_status == "data_blocked" else "可信",
                "data_issue_reason": (
                    "行情复权或标的映射口径未通过校验；系统不会使用该价格序列生成阈值。"
                    if data_status == "data_blocked"
                    else None
                ),
                "blocked_capabilities": blocked_capabilities,
                "available_capabilities": available_capabilities,
                "requires_confirmation": context_status in {"system_proposed", "stale"},
                "stale_reason": (
                    "原方案所依据的盈亏状态已与最新持仓快照冲突，已停用并生成替代建议。"
                    if stale
                    else None
                ),
                "profit_protect_applicable": bool(
                    holding.pnl_pct is not None and holding.pnl_pct > 0
                ),
                "user_note": holding.user_note,
                "user_disposition": holding.user_disposition,
                "base_analysis_available": bool(
                    reliability_row.get("base_analysis_ready", reliability_row.get("decision_ready"))
                ),
            }
        )
    return result


def _system_management_proposal(
    holding: object,
    plan: DecisionPlan | None,
    *,
    data_status: str,
    next_review: str,
) -> dict[str, str]:
    weight = getattr(holding, "weight_pct", None)
    pnl_pct = getattr(holding, "pnl_pct", None)
    if data_status == "data_blocked":
        review_status = "risk_review" if isinstance(weight, (int, float)) and weight >= 40 else "watch"
        return {
            "review_status": review_status,
            "name": "组合层保守观察" if review_status == "watch" else "组合集中度复核",
            "trigger": "组合仓位、风险预算或账户盈亏状态发生实质变化，或异常行情完成同口径修复。",
            "persistence": "行情异常持续期间，每次 after-close 仅复核可信的账户与组合字段。",
            "action": "维持组合层风险监控，不补仓；需要调整仓位时仍由用户确认。",
            "invalidation": "可靠行情恢复后，用同标的、同复权口径重新生成技术方案。",
            "next_review": next_review,
        }
    branch = str(plan.get("current_branch") or "") if plan else ""
    action_text = str(plan.get("current_action") or "") if plan else ""
    technical_state = str(
        _mapping(plan.get("technical_snapshot") if plan else None).get("state") or ""
    )
    if (
        branch == "risk_reduce_review"
        or technical_state == "weak"
        or (isinstance(weight, (int, float)) and weight >= 40)
    ):
        review_status = "risk_review"
        name = "风险复核"
    elif (
        isinstance(pnl_pct, (int, float))
        and pnl_pct > 0
        and "保护" in action_text
    ):
        review_status = "profit_protect"
        name = "利润保护"
    else:
        review_status = "watch"
        name = "继续观察"
    return {
        "review_status": review_status,
        "name": name,
        "trigger": str(plan.get("if_condition") or "下一次有效收盘重新评估结构") if plan else "下一次 after-close 重新评估",
        "persistence": str(plan.get("until_condition") or "持续到下一次有效复核") if plan else "持续到下一次有效复核",
        "action": str(plan.get("then_action") or plan.get("current_action") or "维持当前仓位并等待复核") if plan else "维持当前仓位并等待复核",
        "invalidation": str(plan.get("invalid_condition") or "持仓或组合风险预算发生实质变化") if plan else "持仓或组合风险预算发生实质变化",
        "next_review": next_review,
    }


def _management_rule_text(
    trigger: str,
    persistence: str,
    action: str,
    invalidation: str,
) -> str:
    return (
        f"触发：{trigger}；持续：{persistence}；"
        f"动作：{action}；失效：{invalidation}"
    )


def _management_basis(
    holding: object,
    plan: DecisionPlan | None,
    data_status: str,
) -> list[str]:
    result: list[str] = []
    for label, value, suffix in (
        ("持仓数量", getattr(holding, "shares", None), ""),
        ("成本", getattr(holding, "cost", None), ""),
        ("仓位占比", getattr(holding, "weight_pct", None), "%"),
        ("持仓盈亏", getattr(holding, "pnl_pct", None), "%"),
    ):
        if isinstance(value, (int, float)):
            result.append(f"{label} {value:.2f}{suffix}")
    if plan:
        result.append(f"组合规则：{plan.get('market_permission') or '等待确认'}")
    if data_status == "data_blocked":
        result.append("技术行情已隔离，未用于价格阈值")
    elif plan and plan.get("technical_snapshot"):
        result.append("技术行情已通过数据质量校验")
    return result


_SNAPSHOT_FIELD_CONTRACTS = {
    "股数": ("portfolio.shares", "持仓股数", "大于 0 的券商持仓股数"),
    "成本": ("portfolio.cost", "持仓成本", "大于 0 的券商成本价"),
    "券商市价": ("portfolio.market_price", "券商市价", "大于 0 的券商当前市价"),
    "单票盈亏": ("portfolio.pnl_pct", "单票盈亏", "券商盈亏比例，可为负数"),
    "市值/仓位": (
        "portfolio.market_value_or_weight",
        "市值或仓位",
        "大于 0 的券商市值或仓位占比",
    ),
}


def _repair_issues(
    portfolio: Portfolio,
    plans: list[DecisionPlan],
    reliability: Mapping[str, object],
    management_plans: list[dict[str, object]],
    data_health: list[DataHealthItem],
) -> list[dict[str, object]]:
    """Turn fail-closed states into an actionable, provider-aware UI contract."""

    by_symbol = {item["symbol"]: item for item in plans}
    holdings = {item.code: item for item in portfolio.holdings}
    issues: list[dict[str, object]] = []

    for management in management_plans:
        if management.get("data_status") != "data_blocked":
            continue
        symbol = str(management.get("symbol") or "")
        plan = by_symbol.get(symbol)
        evidence = _mapping(plan.get("data_evidence") if plan else None)
        technical = _mapping(plan.get("technical_snapshot") if plan else None)
        issue = _market_repair_issue(
            symbol=symbol,
            name=str(management.get("name") or symbol),
            reason=str(
                management.get("data_issue_reason")
                or "持仓行情未通过数据质量校验。"
            ),
            evidence=evidence,
            technical=technical,
            plan_id=str(plan.get("plan_id") or "") if plan else "",
        )
        issues.append(issue)

    holding_rows = reliability.get("holdings")
    for row in holding_rows if isinstance(holding_rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("code") or "")
        holding = holdings.get(symbol)
        plan = by_symbol.get(symbol)
        for missing_label in _string_list(row.get("missing_snapshot_fields")):
            contract = _SNAPSHOT_FIELD_CONTRACTS.get(missing_label)
            if contract is None:
                field, field_label, input_format = (
                    "portfolio.unknown_field",
                    missing_label,
                    "从券商持仓表重新提供该字段",
                )
            else:
                field, field_label, input_format = contract
            current_value = _holding_field_value(holding, field)
            issues.append(
                _new_repair_issue(
                    entity={
                        "type": "holding",
                        "symbol": symbol,
                        "name": str(row.get("name") or symbol),
                    },
                    field=field,
                    field_label=field_label,
                    status="missing",
                    reason_code="PORTFOLIO_FIELD_MISSING",
                    reason=f"当前持仓快照未提供{field_label}。",
                    source=str(portfolio.source),
                    source_time=portfolio.as_of or None,
                    fetched_at=None,
                    price_basis=None,
                    current_value=current_value,
                    known_context={
                        "portfolio_as_of": portfolio.as_of or None,
                        "missing_field": missing_label,
                    },
                    criticality_reason=(
                        "该字段参与持仓、风险预算或操作建议判断，"
                        "不能使用 0、默认值或猜测替代。"
                    ),
                    repair_allowed=True,
                    manual_repair_allowed=True,
                    repair_method="portfolio_import",
                    repair_label="打开持仓导入并重新提供",
                    input_format=f"券商持仓表中的{input_format}",
                    next_action="批准保存后系统会串行刷新并重新生成 after-close。",
                    affected_plan_ids=[str(plan.get("plan_id") or "")] if plan else [],
                )
            )

    if str(reliability.get("risk_reconciliation_status") or "") == "blocked":
        issues.append(
            _new_repair_issue(
                entity={"type": "portfolio", "symbol": "", "name": "组合风险预算"},
                field="portfolio.risk_reconciliation",
                field_label="组合风险对账",
                status="blocked",
                reason_code="RISK_RECONCILIATION_BLOCKED",
                reason="组合权重或 Beta 证据尚未完成可信对账。",
                source="portfolio-beta / risk-watch",
                source_time=portfolio.as_of or None,
                fetched_at=None,
                price_basis=None,
                current_value=None,
                known_context={
                    "reconciliation_status": reliability.get(
                        "risk_reconciliation_status"
                    )
                },
                criticality_reason=(
                    "组合风险预算会约束所有持仓动作，证据不完整时不能把 unknown 当作 0。"
                ),
                repair_allowed=True,
                manual_repair_allowed=False,
                repair_method="refresh_sources",
                repair_label="重新计算 Beta 与风险对账",
                input_format=None,
                next_action="刷新成功后重新生成 after-close 并复核各持仓计划。",
                affected_plan_ids=[str(item.get("plan_id") or "") for item in plans],
            )
        )

    for item in data_health:
        status = str(item.get("status") or "missing")
        if status == "ready":
            continue
        is_core_gap = item.get("id") == "core_data_gaps"
        source_name = str(item.get("source_name") or "after-close")
        field = (
            "after_close.core_inputs"
            if is_core_gap
            else f"source.{source_name}"
        )
        field_label = (
            "核心决策输入"
            if is_core_gap
            else str(item.get("label") or source_name)
        )
        reason_code = str(
            item.get("error_code")
            or ("SOURCE_STALE" if status == "stale" else "SOURCE_NOT_READY")
        )
        issues.append(
            _new_repair_issue(
                entity={"type": "source", "symbol": "", "name": field_label},
                field=field,
                field_label=field_label,
                status=status,
                reason_code=reason_code,
                reason=str(item.get("gap_reason") or f"{field_label}尚未就绪。"),
                source=source_name,
                source_time=item.get("source_time"),
                fetched_at=str(item.get("fetched_at") or "") or None,
                price_basis=None,
                current_value=status,
                known_context={
                    "evidence": item.get("evidence"),
                    "owner": item.get("owner"),
                    "freshness_rule": item.get("freshness_rule"),
                    "next_check": item.get("next_check"),
                },
                criticality_reason=(
                    str(item.get("freshness_rule") or "来源必须通过时效校验。")
                    + "；该来源参与市场权限或组合风险判断，不能用 0、默认值或猜测替代。"
                ),
                repair_allowed=True,
                manual_repair_allowed=False,
                repair_method="refresh_sources",
                repair_label=f"重新运行 {source_name} 并校验时间",
                input_format=None,
                next_action="刷新完成后重新生成 after-close；失败时保留 blocked 和最新失败原因。",
                affected_plan_ids=[str(item.get("plan_id") or "") for item in plans],
            )
        )

    unique: dict[str, dict[str, object]] = {}
    for issue in issues:
        unique[str(issue["issue_id"])] = issue
    return list(unique.values())


def _market_repair_issue(
    *,
    symbol: str,
    name: str,
    reason: str,
    evidence: Mapping[str, object],
    technical: Mapping[str, object],
    plan_id: str,
) -> dict[str, object]:
    markers = [
        *_string_list(evidence.get("gaps")),
        *_string_list(evidence.get("errors")),
    ]
    marker_text = " ".join(markers)
    if "code_mismatch" in marker_text:
        field = "security.mapping"
        field_label = "证券映射"
        reason_code = "SECURITY_MAPPING_INVALID"
    elif "missing_fields" in marker_text:
        field = "daily_kline.field_mapping"
        field_label = "行情字段映射"
        reason_code = "PROVIDER_FIELD_MAPPING_INVALID"
    elif "missing_series" in marker_text or evidence.get("status") == "empty":
        field = "daily_kline.series"
        field_label = "日线行情序列"
        reason_code = "MARKET_SERIES_MISSING"
    elif "stale_trade_date" in marker_text:
        field = "daily_kline.trade_date"
        field_label = "行情交易日"
        reason_code = "MARKET_SERIES_STALE"
    elif (
        "price_discontinuity" in marker_text
        or technical.get("state") == "quarantined"
    ):
        field = "daily_kline.price_basis"
        field_label = "行情复权口径"
        reason_code = "PRICE_BASIS_QUARANTINED"
    else:
        field = "daily_kline.provider_contract"
        field_label = "行情数据契约"
        reason_code = "PROVIDER_CONTRACT_INVALID"
    status = str(evidence.get("status") or technical.get("state") or "blocked")
    if technical.get("state") == "quarantined":
        status = "quarantined"
    repair_label = (
        "由系统改用腾讯前复权全序列重新抓取并校验"
        if reason_code in DAILY_KLINE_REPAIR_REASON_CODES
        else "由系统重新抓取并校验"
    )
    return _new_repair_issue(
        entity={"type": "holding", "symbol": symbol, "name": name},
        field=field,
        field_label=field_label,
        status=status,
        reason_code=reason_code,
        reason=reason,
        source=str(evidence.get("provider") or "after-close"),
        source_time=evidence.get("source_time"),
        fetched_at=str(evidence.get("fetched_at") or "") or None,
        price_basis=str(evidence.get("price_basis") or "unknown"),
        current_value=technical.get("close"),
        known_context={
            "provider_status": evidence.get("status") or "unknown",
            "trade_date": evidence.get("trade_date"),
            "price_basis": evidence.get("price_basis") or "unknown",
            "technical_state": technical.get("state") or "unknown",
            "gaps": _string_list(evidence.get("gaps")),
            "errors": _string_list(evidence.get("errors")),
        },
        criticality_reason=(
            "该字段参与均线、支撑/压力与价格阈值判断，"
            "不能使用 0、默认值或猜测替代。"
        ),
        repair_allowed=True,
        manual_repair_allowed=False,
        repair_method="retry_after_close",
        repair_label=repair_label,
        input_format=None,
        next_action=(
            "重新检查通过后保留 fallback 来源与原始 quarantine 证据，并重新生成新的 after-close 计划版本；"
            "仍异常则继续 blocked。"
        ),
        affected_plan_ids=[plan_id] if plan_id else [],
    )


def _new_repair_issue(
    *,
    entity: dict[str, str],
    field: str,
    field_label: str,
    status: str,
    reason_code: str,
    reason: str,
    source: str,
    source_time: object,
    fetched_at: str | None,
    price_basis: str | None,
    current_value: object,
    known_context: dict[str, object],
    criticality_reason: str,
    repair_allowed: bool,
    manual_repair_allowed: bool,
    repair_method: str,
    repair_label: str,
    input_format: str | None,
    next_action: str,
    affected_plan_ids: list[str],
) -> dict[str, object]:
    identity = "|".join(
        (
            str(entity.get("type") or "unknown"),
            str(entity.get("symbol") or entity.get("name") or "unknown"),
            field,
            field_label,
            reason_code,
            source,
        )
    )
    return {
        "issue_id": "repair-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12],
        "entity": entity,
        "field": field,
        "field_label": field_label,
        "status": status,
        "reason_code": reason_code,
        "reason": reason,
        "source": source,
        "source_time": source_time,
        "fetched_at": fetched_at,
        "price_basis": price_basis,
        "current_value": current_value,
        "known_context": known_context,
        "criticality_reason": criticality_reason,
        "repair_allowed": repair_allowed,
        "manual_repair_allowed": manual_repair_allowed,
        "repair_method": repair_method,
        "repair_label": repair_label,
        "input_format": input_format,
        "next_action": next_action,
        "affected_plan_ids": [item for item in affected_plan_ids if item],
    }


def _holding_field_value(holding: object, field: str) -> object:
    if holding is None:
        return None
    attribute = {
        "portfolio.shares": "shares",
        "portfolio.cost": "cost",
        "portfolio.market_price": "market_price",
        "portfolio.pnl_pct": "pnl_pct",
        "portfolio.market_value_or_weight": "market_value",
    }.get(field)
    return getattr(holding, attribute, None) if attribute else None


def _link_repair_issues(
    plans: list[DecisionPlan],
    issues: list[dict[str, object]],
) -> None:
    for plan in plans:
        plan_id = str(plan.get("plan_id") or "")
        symbol = str(plan.get("symbol") or "")
        plan["repair_issue_ids"] = [
            str(issue.get("issue_id") or "")
            for issue in issues
            if plan_id in _string_list(issue.get("affected_plan_ids"))
            or str(_mapping(issue.get("entity")).get("symbol") or "") == symbol
        ]


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
        if matching.get("data_status") == "data_blocked":
            blocked_capabilities = _string_list(matching.get("blocked_capabilities"))
            blockers.append(
                "该持仓行情数据异常，已暂停"
                + "、".join(blocked_capabilities or ["技术价格判断"])
                + "；用户确认不能解除该隔离。"
            )
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
        elif raw_status in {"stale", "missing", "blocked", "pending", "failed"}:
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
                "error_code": (
                    None
                    if status == "ready"
                    else "SOURCE_STALE"
                    if status == "stale"
                    else "SOURCE_UNAVAILABLE"
                ),
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
                "repair_action": "修复命中的账户字段或系统数据源后，重新生成 after-close；用户确认不能替代数据修复。",
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
    blocked_count = sum(item["status"] != "ready" for item in health)
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
    reliability: Mapping[str, object],
    management_plans: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_symbol = {item["symbol"]: item for item in plans}
    reliability_rows = reliability.get("holdings")
    context_by_symbol: dict[str, Mapping[str, object]] = {}
    management_by_symbol = {
        str(item.get("symbol")): item for item in management_plans
    }
    for item in reliability_rows if isinstance(reliability_rows, list) else []:
        if isinstance(item, Mapping) and item.get("code"):
            context_by_symbol[str(item.get("code"))] = item
    result: list[dict[str, object]] = []
    for holding in portfolio.holdings:
        plan = by_symbol.get(holding.code)
        context = context_by_symbol.get(holding.code, {})
        management = management_by_symbol.get(holding.code, {})
        current_context_complete = context.get("current_context_complete")
        if current_context_complete is None:
            current_context_complete = context.get("context_complete")
        historical_context_complete = context.get("historical_context_complete")
        missing_current_context_fields = _string_list(
            context.get("missing_current_context_fields")
        )
        missing_historical_context_fields = _string_list(
            context.get("missing_historical_context_fields")
        )
        result.append(
            {
                "symbol": holding.code,
                "name": holding.name or holding.code,
                "shares": holding.shares,
                "cost": holding.cost,
                "market_price": holding.market_price,
                "market_value": holding.market_value,
                "day_pnl": holding.day_pnl,
                "weight_pct": holding.weight_pct,
                "pnl_pct": holding.pnl_pct,
                "beta_classification": holding.beta_classification or "unknown",
                "beta_evidence": (
                    asdict(holding.beta_evidence)
                    if holding.beta_evidence is not None
                    else None
                ),
                "review_status": holding.review_status or "unknown",
                "current_context_status": (
                    "ready" if current_context_complete is True else "missing"
                ),
                "historical_context_status": (
                    "ready" if historical_context_complete is True else "unknown"
                ),
                "missing_current_context_fields": missing_current_context_fields,
                "missing_historical_context_fields": missing_historical_context_fields,
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
                "management_context_status": management.get("context_status", "system_proposed"),
                "management_data_status": management.get("data_status", "ready"),
                "management_plan": management,
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
        "current_context_ready_holdings": reliability.get(
            "current_context_ready_holdings", 0
        ),
        "historical_context_ready_holdings": reliability.get(
            "historical_context_ready_holdings", 0
        ),
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
