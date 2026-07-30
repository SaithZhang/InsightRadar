"""Normalize decision evidence into an auditable, plan-linked contract."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping


def build_decision_evidence(
    decision: Mapping[str, object],
    data_health: list[Mapping[str, object]],
    plans: list[Mapping[str, object]],
) -> dict[str, object]:
    """Return the conclusion and evidence used by the workbench.

    Source-health metadata is joined by source id, never by list position.
    """

    health_by_source = {
        _source_key(str(item.get("source_name") or item.get("id") or "")): item
        for item in data_health
    }
    plan_ids = [str(item.get("plan_id") or "") for item in plans if item.get("plan_id")]
    items: list[dict[str, object]] = []

    raw_effects = decision.get("evidence_effects")
    effects = raw_effects if isinstance(raw_effects, list) else []
    for raw in effects:
        if not isinstance(raw, Mapping):
            continue
        source = str(raw.get("source") or "unknown")
        source_key = _source_key(source.split("/")[0].strip())
        health = health_by_source.get(source_key, {})
        claim = str(raw.get("state") or "来源未提供具体状态")
        impact = str(raw.get("effect") or "未声明对计划的影响")
        scope = _scope(source_key)
        evidence_id = _evidence_id(scope, source_key, claim)
        supports, opposes = _conclusion_links(impact)
        status = str(health.get("status") or "unknown")
        gap = str(health.get("gap_reason") or "").strip()
        linked_plan_ids = (
            _explicit_plan_links(raw, plans)
            if source_key == "ai_capex_watch"
            else plan_ids
        )
        gaps = [gap] if gap else []
        if source_key == "ai_capex_watch" and not linked_plan_ids:
            gaps.append("产业证据尚未提供到具体持仓的官方映射。")
        items.append(
            {
                "evidence_id": evidence_id,
                "scope": scope,
                "fact_class": "fact_with_rule_inference",
                "claim": claim,
                "change": _change_summary(raw, decision),
                "source_ref": source,
                "source_time": (
                    str(raw.get("as_of") or health.get("source_time") or "") or None
                ),
                "freshness": status,
                "supports": supports,
                "opposes": opposes,
                "plan_impact": impact,
                "counter_evidence": _counter_evidence(source_key, decision),
                "gaps": gaps,
                "authority": (
                    "diagnostic_only"
                    if source_key
                    in {"style_rotation", "market_pulse", "ai_capex_watch"}
                    else "rule_input"
                ),
                "linked_plan_ids": linked_plan_ids,
            }
        )

    for plan in plans:
        plan_id = str(plan.get("plan_id") or "")
        symbol = str(plan.get("symbol") or "")
        technical = _mapping(plan.get("technical_snapshot"))
        if not plan_id or not technical:
            continue
        claim = _technical_claim(technical)
        items.append(
            {
                "evidence_id": f"holding:{symbol}:technical",
                "scope": "holding",
                "fact_class": "fact_with_rule_inference",
                "claim": claim,
                "change": _technical_change(technical),
                "source_ref": f"holding:{symbol}:completed_daily_bars",
                "source_time": technical.get("as_of"),
                "freshness": (
                    "ready"
                    if technical.get("state") not in {"unknown", "quarantined"}
                    else "blocked"
                ),
                "supports": [f"plan:{plan_id}"],
                "opposes": [],
                "plan_impact": str(
                    plan.get("current_action")
                    or plan.get("then_action")
                    or "等待计划条件"
                ),
                "counter_evidence": _technical_counter_evidence(technical),
                "gaps": (
                    []
                    if technical.get("state") not in {"unknown", "quarantined"}
                    else ["技术行情缺失或复权口径未对齐"]
                ),
                "authority": "rule_input",
                "linked_plan_ids": [plan_id],
            }
        )

    if not items:
        items.append(
            {
                "evidence_id": "system:no-decision-evidence",
                "scope": "market",
                "fact_class": "unknown",
                "claim": "当前报告没有形成可归因的决策证据。",
                "change": "unknown",
                "source_ref": "unified_decision",
                "source_time": None,
                "freshness": "blocked",
                "supports": [],
                "opposes": [],
                "plan_impact": "保持等待，不新增风险。",
                "counter_evidence": [],
                "gaps": ["evidence_effects 与持仓技术契约均为空"],
                "authority": "blocked",
                "linked_plan_ids": plan_ids,
            }
        )

    conclusion = _conclusion(decision, items)
    return {
        "schema_version": "decision-evidence/v1",
        "conclusion": conclusion,
        "items": items,
        "evidence_count": len(items),
        "blocked_count": sum(
            item.get("freshness") in {"stale", "missing", "blocked", "failed", "unknown"}
            for item in items
        ),
    }


def link_evidence_to_plans(
    plans: list[dict[str, object]],
    evidence: Mapping[str, object],
) -> None:
    rows = evidence.get("items")
    items = rows if isinstance(rows, list) else []
    by_plan: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        evidence_id = str(item.get("evidence_id") or "")
        linked = item.get("linked_plan_ids")
        for plan_id in linked if isinstance(linked, list) else []:
            if evidence_id:
                by_plan.setdefault(str(plan_id), []).append(evidence_id)
    for plan in plans:
        plan_id = str(plan.get("plan_id") or "")
        plan["evidence_refs"] = list(dict.fromkeys(by_plan.get(plan_id, [])))


def _conclusion(
    decision: Mapping[str, object],
    items: list[dict[str, object]],
) -> dict[str, object]:
    style = _mapping(decision.get("style_rotation"))
    relative_strength = _mapping(style.get("relative_strength"))
    technology = _mapping(relative_strength.get("technology_growth"))
    dividend = _mapping(relative_strength.get("high_dividend"))
    tech_5d = _number(technology.get("5d"))
    tech_20d = _number(technology.get("20d"))
    dividend_5d = _number(dividend.get("5d"))
    dividend_20d = _number(dividend.get("20d"))
    technology_stance = _style_stance(
        "科技",
        tech_5d,
        tech_20d,
    )
    dividend_stance = _style_stance(
        "红利",
        dividend_5d,
        dividend_20d,
    )
    eligible_reasons = [
        {
            "evidence_id": str(item.get("evidence_id") or ""),
            "claim": str(item.get("claim") or ""),
            "plan_impact": str(item.get("plan_impact") or ""),
            "source_ref": str(item.get("source_ref") or ""),
        }
        for item in items
        if item.get("freshness") not in {"missing", "failed", "blocked"}
    ]
    preferred_sources = (
        "risk-watch",
        "market-levels",
        "ai-capex-watch",
        "style-rotation",
    )
    top_reasons: list[dict[str, str]] = []
    for source in preferred_sources:
        match = next(
            (
                reason
                for reason in eligible_reasons
                if source in reason["source_ref"]
                and reason["evidence_id"]
                not in {row["evidence_id"] for row in top_reasons}
            ),
            None,
        )
        if match is not None:
            top_reasons.append(match)
    for reason in eligible_reasons:
        if len(top_reasons) >= 4:
            break
        if reason["evidence_id"] not in {row["evidence_id"] for row in top_reasons}:
            top_reasons.append(reason)
    market_levels = _mapping(decision.get("market_levels"))
    invalidation: list[str] = []
    breakdown = str(market_levels.get("breakdown_action") or "").strip()
    confirmation = str(market_levels.get("confirmation_action") or "").strip()
    if breakdown:
        invalidation.append(breakdown)
    if confirmation:
        invalidation.append(confirmation)
    invalidation.extend(_string_list(decision.get("unlock_conditions"))[:2])
    overall_stance = str(decision.get("stance") or "等待确认")
    risk_budget = _mapping(decision.get("risk_budget"))
    risk_score = _number(risk_budget.get("risk_score"))
    risk_level = str(risk_budget.get("risk_level") or "").lower()
    risk_label = {
        "red": "红灯",
        "yellow": "黄灯",
        "green": "绿灯",
    }.get(risk_level, "风险状态待确认")
    risk_clause = (
        f"市场风险 {risk_score:.0f}/100（{risk_label}）"
        if risk_score is not None
        else risk_label
    )
    headline = (
        f"{overall_stance}；{technology_stance}，{dividend_stance}。"
        f"{risk_clause}；组合不新增高β，个股只按已完成日线的"
        "修复、风险与继续等待分支复核。"
    )
    return {
        "overall_stance": overall_stance,
        "headline": headline,
        "confidence": str(decision.get("confidence") or "unknown"),
        "technology_stance": technology_stance,
        "dividend_stance": dividend_stance,
        "top_reasons": top_reasons,
        "counter_evidence": _top_counter_evidence(items),
        "invalidation": list(dict.fromkeys(invalidation)),
        "authority": str(decision.get("authority") or "conditional_only"),
    }


def _scope(source_key: str) -> str:
    if source_key == "style_rotation":
        return "style"
    if source_key == "ai_capex_watch":
        return "industry"
    return "market"


def _explicit_plan_links(
    evidence: Mapping[str, object],
    plans: list[Mapping[str, object]],
) -> list[str]:
    raw_symbols = (
        evidence.get("linked_symbols")
        or evidence.get("symbols")
        or evidence.get("holding_codes")
    )
    symbols = {
        str(value).strip()
        for value in raw_symbols
        if str(value).strip()
    } if isinstance(raw_symbols, list) else set()
    if not symbols:
        return []
    return [
        str(plan.get("plan_id"))
        for plan in plans
        if str(plan.get("symbol") or "") in symbols and plan.get("plan_id")
    ]


def _source_key(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _evidence_id(scope: str, source: str, claim: str) -> str:
    digest = sha256(claim.encode("utf-8")).hexdigest()[:8]
    return f"{scope}:{source}:{digest}"


def _conclusion_links(impact: str) -> tuple[list[str], list[str]]:
    defensive = any(
        marker in impact
        for marker in ("限制新增", "不能授权", "不授权", "继续防守", "保持")
    )
    repair = any(
        marker in impact
        for marker in ("减轻", "上调", "修复", "支持")
    )
    supports: list[str] = []
    opposes: list[str] = []
    if defensive:
        supports.append("overall:defensive")
        opposes.append("overall:increase_risk")
    if repair:
        supports.append("overall:conditional_repair")
    return supports, opposes


def _change_summary(
    effect: Mapping[str, object],
    decision: Mapping[str, object],
) -> str:
    source = _source_key(str(effect.get("source") or "").split("/")[0].strip())
    if source == "style_rotation":
        style = _mapping(decision.get("style_rotation"))
        days = style.get("confirmation_days")
        leader = str(style.get("leader_style") or style.get("leader_style_key") or "unknown")
        return f"领先风格 {leader}，已确认 {days} 日" if days is not None else f"领先风格 {leader}"
    if source == "market_levels":
        levels = _mapping(decision.get("market_levels"))
        return str(levels.get("verdict") or levels.get("market_level_state") or "unknown")
    return "与上一版的结构化变化未单独提供"


def _counter_evidence(
    source_key: str,
    decision: Mapping[str, object],
) -> list[str]:
    if source_key == "risk_watch":
        return _string_list(decision.get("unlock_conditions"))[:1]
    if source_key == "market_pulse":
        return ["ETF代理改善不等于真实增量资金或中期趋势反转。"]
    if source_key == "ai_capex_watch":
        return ["产业资本开支增长不等于持仓公司订单、利润率和现金流已经兑现。"]
    if source_key == "style_rotation":
        return ["风格矩阵只提供相对强弱，不直接授权切换持仓。"]
    return []


def _technical_claim(technical: Mapping[str, object]) -> str:
    state = str(technical.get("state") or "unknown")
    close = _format_number(technical.get("close"))
    ma20 = _format_number(technical.get("ma20"))
    support = _format_number(technical.get("support_20d"))
    resistance = _format_number(technical.get("resistance_20d"))
    return (
        f"技术状态 {state}；收盘 {close}，MA20 {ma20}，"
        f"20日支撑 {support}，20日阻力 {resistance}。"
    )


def _technical_change(technical: Mapping[str, object]) -> str:
    slope = _number(technical.get("ma20_slope_5d"))
    change_5d = _number(technical.get("change_5d"))
    parts: list[str] = []
    if slope is not None:
        parts.append(f"MA20五日斜率 {slope:.2%}")
    if change_5d is not None:
        parts.append(f"五日涨跌 {change_5d:.2%}")
    return "；".join(parts) or "变化数据不足"


def _technical_counter_evidence(
    technical: Mapping[str, object],
) -> list[str]:
    state = str(technical.get("state") or "")
    if state in {"weak", "repairing"}:
        return ["站回MA20并获得价格结构与量能持续确认，可否定当前弱势判断。"]
    if state in {"strong", "extended"}:
        return ["跌回MA20或跌破近期支撑，可否定当前强势/延伸判断。"]
    return []


def _style_stance(
    label: str,
    value_5d: float | None,
    value_20d: float | None,
) -> str:
    if value_5d is None or value_20d is None:
        return f"{label}证据不足"
    if value_5d < 0 and value_20d < 0:
        return f"{label}偏弱，等待修复"
    if value_5d >= 0 > value_20d:
        return f"{label}短线修复，中期未确认"
    if value_5d >= 0 and value_20d >= 0:
        return f"{label}相对占优"
    return f"{label}短线转弱"


def _top_counter_evidence(items: list[dict[str, object]]) -> list[str]:
    rows: list[str] = []
    for item in items:
        rows.extend(_string_list(item.get("counter_evidence")))
    return list(dict.fromkeys(rows))[:4]


def _format_number(value: object) -> str:
    parsed = _number(value)
    return f"{parsed:.2f}" if parsed is not None else "unknown"


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def evidence_json(evidence: Mapping[str, object]) -> str:
    """Stable serialization used by the SQLite mirror."""

    return json.dumps(dict(evidence), ensure_ascii=False, sort_keys=True)
