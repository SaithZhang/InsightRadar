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

from stock_assist.paths import DATA_DIR
from stock_assist.portfolio import Portfolio


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


class DecisionPlan(TypedDict):
    plan_id: str
    symbol: str
    name: str
    plan_version: str
    previous_version: str | None
    status: PlanStatus
    if_condition: str
    then_action: str
    until_condition: str
    invalid_condition: str
    market_permission: str
    risk_constraints: list[str]
    evidence_refs: list[str]
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
    plan_history = load_plan_versions(plan_ledger)
    previous_plans = _latest_plan_versions(plan_history)
    plans = _plans(decision, now, latest_by_plan, previous_plans)
    gaps = _string_list(payload.get("data_gaps"))
    data_health = _data_health(decision, gaps, now)
    market_gate = _market_gate(decision, data_health)
    positions = _portfolio_positions(portfolio, plans)
    actionable = [plan for plan in plans if _requires_user_action(plan)]
    accepted = [
        plan
        for plan in plans
        if plan["user_response_status"] == "accepted"
        and plan["status"] not in {"voided", "blocked"}
    ]
    return {
        "schema_version": "decision-workspace/v1",
        "generated_at": now.isoformat(timespec="seconds"),
        "source_generated_at": now.isoformat(timespec="seconds"),
        "effective_market_date": str(decision.get("plan_date") or now.date().isoformat()),
        "run_stage": run_stage,
        "runtime_status": (
            "awaiting_confirmation"
            if any(item["user_response_status"] == "pending" for item in actionable)
            else "reviewed"
        ),
        "stage_note": (
            "盘后生成：形成次日条件计划。"
            if run_stage == "after_close"
            else "晨间增量复核：仅重算现有来源时效；本阶段未接入实时行情刷新。"
        ),
        "data_health": data_health,
        "market_gate": market_gate,
        "theme_observations": _theme_observations(market_matrix),
        "portfolio_summary": _portfolio_summary(portfolio, reliability),
        "portfolio_positions": positions,
        "plan_changes": actionable,
        "active_plans": plans,
        "plan_version_history": plan_history,
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
            "if_condition": str(item.get("if_condition") or ""),
            "then_action": str(item.get("then_action") or ""),
            "until_condition": str(item.get("until_condition") or ""),
            "invalid_condition": str(item.get("invalid_condition") or ""),
            "change_reasons": _string_list(item.get("change_reasons")),
            "created_at": str(item.get("created_at") or datetime.now().isoformat(timespec="seconds")),
        }
        rows.append(record)
        latest[plan_id] = record
    _atomic_write_text(
        path,
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in rows),
    )
    return rows


def overlay_plan_responses(
    workspace: Mapping[str, object],
    *,
    response_ledger: Path = DEFAULT_RESPONSE_LEDGER,
) -> dict[str, object]:
    """Return a refreshed copy with the latest persisted user responses."""

    result = deepcopy(dict(workspace))
    responses = load_plan_responses(response_ledger)
    latest = _latest_responses(responses)
    for key in ("plan_changes", "active_plans"):
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
        result["plan_changes"] = actionable
        result["runtime_status"] = (
            "awaiting_confirmation" if actionable else "reviewed"
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
    now: datetime,
    latest_responses: Mapping[str, Mapping[str, object]],
    previous_plans: Mapping[str, Mapping[str, object]],
) -> list[DecisionPlan]:
    raw = decision.get("holding_plans")
    rows = raw if isinstance(raw, list) else []
    market_permission = str(decision.get("stance") or "等待确认")
    blocked = _string_list(decision.get("blocked_actions"))
    plans: list[DecisionPlan] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("code") or "").strip()
        if not symbol:
            continue
        plan_id = f"holding:{symbol}"
        content = {
            "symbol": symbol,
            "if": str(item.get("upside_trigger") or item.get("flat_trigger") or "等待条件明确"),
            "then": str(item.get("position_action") or item.get("action") or "保持原计划"),
            "until": str(item.get("flat_trigger") or "下一次有效复核"),
            "invalid": str(item.get("downside_trigger") or "风险线被触发"),
            "permission": market_permission,
        }
        version = "v-" + hashlib.sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:10]
        previous = previous_plans.get(plan_id)
        previous_version = str(previous.get("plan_version")) if previous else None
        if blocked:
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
        plans.append(
            {
                "plan_id": plan_id,
                "symbol": symbol,
                "name": str(item.get("name") or symbol),
                "plan_version": version,
                "previous_version": previous_version,
                "status": status,
                "if_condition": content["if"],
                "then_action": content["then"],
                "until_condition": content["until"],
                "invalid_condition": content["invalid"],
                "market_permission": market_permission,
                "risk_constraints": blocked,
                "evidence_refs": ["unified_decision", f"holding:{symbol}"],
                "change_reasons": (
                    ["首次形成可审核计划"]
                    if status == "new"
                    else ["计划内容相对已回应版本发生变化"]
                    if status == "revised"
                    else ["核心数据缺口阻断执行"]
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
    return plans


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
        as_of = str(item.get("as_of") or "") or None
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


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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
