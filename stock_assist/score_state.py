"""Auditable bear-bull score state machine.

The state machine deliberately separates intraday candidates from the last
formally finalized close.  It is deterministic, configuration-driven, and
contains no trade-execution side effects.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any


RULE_IDS = (
    "ML_CONFIRM_BREADTH_UP",
    "ML_SUPPORT_FAIL_BREADTH_DOWN",
    "ML_STRONG_BREAKOUT_CONFIRMED",
    "SIGNAL_CONFLICT",
    "DATA_STALE_OR_MISSING",
    "RISK_VETO",
)


def load_score_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_score_state(path: Path, state: dict[str, object]) -> None:
    """Persist state atomically; score history is private runtime data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def evaluate_score_state(
    observation: dict[str, object],
    previous_state: dict[str, object] | None,
    config: dict[str, object],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Evaluate one market observation and return public contract plus state.

    ``observation`` is intentionally plain JSON data so tests and future
    intraday adapters can replay it without provider access.
    """

    current_time = now or datetime.now()
    prior = previous_state or {}
    score_config = config.get("score") if isinstance(config.get("score"), dict) else {}
    minimum = _number(score_config.get("minimum"), 0.0)
    maximum = _number(score_config.get("maximum"), 10.0)
    initial = _number(score_config.get("initial_formal_score"), 2.0)
    max_change = abs(_number(score_config.get("max_daily_change"), 1.0)) or 1.0
    formal = _number(prior.get("formal_score"), initial)
    prior_formal = _number(prior.get("previous_formal_score"), formal)
    market_date = str(observation.get("market_date") or "")
    already_finalized_date = str(prior.get("formal_market_date") or "")
    finalized_rules_by_date = prior.get("finalized_rule_ids_by_date")
    if not isinstance(finalized_rules_by_date, dict):
        finalized_rules_by_date = {}
    already_counted = {
        str(item)
        for item in finalized_rules_by_date.get(market_date, [])
        if isinstance(item, str)
    }

    rules = _rule_map(config)
    ledger: list[dict[str, object]] = []
    triggered: list[str] = []
    blocked: list[str] = []
    missing = [str(item) for item in observation.get("data_gaps", []) if str(item).strip()] if isinstance(observation.get("data_gaps"), list) else []
    data_complete = bool(observation.get("data_complete")) and not missing
    risk_veto = bool(observation.get("risk_veto")) or bool(observation.get("hard_risk_event"))
    level_state = str(observation.get("market_level_state") or "unavailable")
    breadth_state = str(observation.get("breadth_state") or "unavailable")
    turnover_state = str(observation.get("turnover_state") or "unavailable")
    is_close = bool(observation.get("is_close"))

    if not data_complete:
        ledger.append(
            _entry(
                rules,
                "DATA_STALE_OR_MISSING",
                status="blocked",
                observed_value={"gaps": missing or ["required confirmation input unavailable"]},
                threshold="market-levels, breadth and turnover must be current and complete",
                observation=observation,
                explanation="数据缺失或过期，禁止升分；缺失值没有被当作0或中性。",
                is_veto=True,
            )
        )
        blocked.append("DATA_STALE_OR_MISSING")

    candidate_rule: str | None = None
    raw_delta = 0.0
    if level_state == "support_failed" and breadth_state == "down":
        candidate_rule = "ML_SUPPORT_FAIL_BREADTH_DOWN"
        raw_delta = -1.0
    elif level_state == "strong_breakout_confirmed" and breadth_state == "up" and turnover_state == "up":
        candidate_rule = "ML_STRONG_BREAKOUT_CONFIRMED"
        raw_delta = 1.0
    elif level_state == "rebound_confirmed" and breadth_state == "up" and turnover_state in {"up", "not_weak"}:
        candidate_rule = "ML_CONFIRM_BREADTH_UP"
        raw_delta = 1.0
    elif _has_conflict(level_state, breadth_state, turnover_state):
        candidate_rule = "SIGNAL_CONFLICT"
        raw_delta = 0.0

    if candidate_rule:
        direction_blocked = raw_delta > 0 and not data_complete
        duplicate = candidate_rule in already_counted
        status = "blocked" if direction_blocked else "deduplicated" if duplicate else "triggered"
        ledger.append(
            _entry(
                rules,
                candidate_rule,
                status=status,
                observed_value={
                    "market_level_state": level_state,
                    "breadth_state": breadth_state,
                    "turnover_state": turnover_state,
                    "latest": observation.get("latest"),
                },
                threshold=_rule_threshold(candidate_rule),
                observation=observation,
                explanation=_rule_explanation(candidate_rule, direction_blocked, duplicate),
                is_veto=False,
            )
        )
        if direction_blocked or duplicate:
            blocked.append(candidate_rule)
            raw_delta = 0.0
        else:
            triggered.append(candidate_rule)

    if risk_veto:
        ledger.append(
            _entry(
                rules,
                "RISK_VETO",
                status="blocked",
                observed_value={
                    "risk_level": observation.get("risk_level"),
                    "hard_risk_event": bool(observation.get("hard_risk_event")),
                },
                threshold="risk-watch red or a hard risk event",
                observation=observation,
                explanation="候选评分可改善，但风险预算不得自动上调。",
                is_veto=True,
            )
        )
        blocked.append("RISK_VETO")

    candidate_delta = max(-max_change, min(max_change, raw_delta))
    candidate_score = _clamp(formal + candidate_delta, minimum, maximum)
    finalization_allowed = is_close and data_complete and bool(market_date)
    duplicate_close = already_finalized_date == market_date
    finalized_at: str | None = None
    score_delta = 0.0
    finalization_status = "candidate"
    new_formal = formal

    if finalization_allowed:
        finalization_status = "finalized"
        finalized_at = str(prior.get("finalized_at") or "") if duplicate_close else current_time.isoformat(timespec="seconds")
        if not duplicate_close:
            score_delta = candidate_delta
            new_formal = candidate_score
            prior_formal = formal
            if candidate_rule and candidate_rule != "SIGNAL_CONFLICT" and candidate_rule not in already_counted and not (candidate_delta > 0 and not data_complete):
                finalized_rules_by_date[market_date] = sorted(already_counted | {candidate_rule})
    elif not data_complete and not market_date:
        finalization_status = "unavailable"

    positive = [item for item in ledger if _number(item.get("points"), 0.0) > 0]
    negative = [item for item in ledger if _number(item.get("points"), 0.0) < 0 or item.get("direction") == "veto"]
    persistence_state = {
        "market_date": market_date or None,
        "last_market_level_state": prior.get("last_market_level_state"),
        "current_market_level_state": level_state,
        "same_state_as_previous": prior.get("last_market_level_state") == level_state,
        "daily_change_limit": max_change,
        "deduplicated_rule_ids": sorted(already_counted),
        "hysteresis": "zone_hysteresis_configured",
    }
    contract = {
        "previous_score": round(prior_formal, 1),
        "bear_bull_score": round(new_formal, 1),
        "candidate_score": round(candidate_score if not duplicate_close else new_formal, 1),
        "score_delta": round(score_delta, 1),
        "candidate_delta": round(0.0 if duplicate_close else candidate_delta, 1),
        "positive_points": positive,
        "negative_points": negative,
        "score_ledger": ledger,
        "triggered_rule_ids": list(dict.fromkeys(triggered)),
        "blocked_rule_ids": list(dict.fromkeys(blocked)),
        "finalization_status": finalization_status,
        "finalized_at": finalized_at or prior.get("finalized_at") if duplicate_close else finalized_at,
        "score_as_of": market_date or None,
        "calibration": "diagnostic_unbacktested",
        "persistence_state": persistence_state,
        "upgrade_blocked": not data_complete,
        "risk_budget_upgrade_blocked": risk_veto or not data_complete,
        "downgrade_forced": candidate_rule == "ML_SUPPORT_FAIL_BREADTH_DOWN" and candidate_delta < 0,
    }
    state = {
        "schema_version": "insightradar-bear-bull-state/v1",
        "formal_score": round(new_formal, 1),
        "previous_formal_score": round(prior_formal, 1),
        "formal_market_date": market_date if finalization_status == "finalized" else already_finalized_date or None,
        "finalized_at": contract.get("finalized_at"),
        "finalized_rule_ids_by_date": finalized_rules_by_date,
        "last_market_level_state": level_state,
        "updated_at": current_time.isoformat(timespec="seconds"),
    }
    return contract, state


def _rule_map(config: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = config.get("rules") if isinstance(config.get("rules"), list) else []
    mapped = {str(item.get("rule_id")): item for item in rows if isinstance(item, dict) and item.get("rule_id")}
    for rule_id in RULE_IDS:
        mapped.setdefault(rule_id, {"rule_id": rule_id, "direction": "neutral", "points": 0.0})
    return mapped


def _entry(
    rules: dict[str, dict[str, object]],
    rule_id: str,
    *,
    status: str,
    observed_value: object,
    threshold: object,
    observation: dict[str, object],
    explanation: str,
    is_veto: bool,
) -> dict[str, object]:
    rule = rules[rule_id]
    points = _number(rule.get("points"), 0.0)
    if status in {"blocked", "deduplicated"}:
        applied_points = 0.0
    else:
        applied_points = points
    return {
        "rule_id": rule_id,
        "direction": rule.get("direction") or "neutral",
        "points": applied_points,
        "configured_points": points,
        "status": status,
        "observed_value": observed_value,
        "threshold": threshold,
        "evidence_source": observation.get("evidence_source") or {},
        "evidence_as_of": observation.get("evidence_as_of") or observation.get("market_date"),
        "explanation": explanation,
        "is_veto": is_veto,
    }


def _has_conflict(level_state: str, breadth_state: str, turnover_state: str) -> bool:
    price_positive = level_state in {"confirmation_testing", "rebound_confirmed", "strong_resistance_testing", "strong_breakout_confirmed", "daily_repair_confirmed"}
    price_negative = level_state in {"below_support", "support_failed"}
    return (
        (price_positive and (breadth_state == "down" or turnover_state == "weak"))
        or (price_negative and breadth_state == "up")
        or breadth_state == "mixed"
        or turnover_state == "mixed"
    )


def _rule_threshold(rule_id: str) -> str:
    return {
        "ML_CONFIRM_BREADTH_UP": "price above confirmation upper; breadth up; turnover not weak",
        "ML_SUPPORT_FAIL_BREADTH_DOWN": "two completed 15m closes below support lower; breadth down",
        "ML_STRONG_BREAKOUT_CONFIRMED": "completed daily close above strong-resistance upper; breadth and turnover up",
        "SIGNAL_CONFLICT": "price, breadth and turnover do not agree",
    }.get(rule_id, "configured deterministic threshold")


def _rule_explanation(rule_id: str, blocked: bool, duplicate: bool) -> str:
    if blocked:
        return "价格条件出现，但确认数据缺失或过期，升分被阻断。"
    if duplicate:
        return "同一rule_id在同一市场日已经计入，重复信号不再次累计。"
    return {
        "ML_CONFIRM_BREADTH_UP": "第一确认区上沿站稳且宽度改善，形成候选+1；盘中不覆盖正式分。",
        "ML_SUPPORT_FAIL_BREADTH_DOWN": "支撑失效、下一根15分钟未收回且宽度恶化，候选-1。",
        "ML_STRONG_BREAKOUT_CONFIRMED": "强压力上沿收盘突破且宽度、成交同步，允许正式+1。",
        "SIGNAL_CONFLICT": "价格、宽度或成交相互矛盾，评分维持不变。",
    }.get(rule_id, "规则已评估。")


def _number(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
