"""Synthesize Core monitor artifacts into one conditional next-session plan."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any

from stock_assist.paths import CONFIG_DIR, DATA_DIR, REPORT_DIR
from stock_assist.score_state import evaluate_score_state, load_score_state, save_score_state


MONITOR_PATTERNS = {
    "risk_watch": "*-risk-watch.json",
    "market_pulse": "*-market-pulse.json",
    "market_levels": "*-market-levels.json",
    "ai_capex_watch": "*-ai-capex-watch.json",
    "style_rotation": "*-style-rotation.json",
}
DEFAULT_DECISION_RULES_PATH = CONFIG_DIR / "decision_rules.json"
DEFAULT_SCORE_STATE_PATH = DATA_DIR / "bear_bull_score_state.json"


def build_unified_decision(
    actions: list[dict[str, object]],
    reliability: dict[str, object],
    *,
    report_dir: Path = REPORT_DIR,
    now: datetime | None = None,
    decision_rules_path: Path = DEFAULT_DECISION_RULES_PATH,
    score_state_path: Path | None = None,
    persist_score_state: bool = True,
) -> dict[str, object]:
    """Build a fail-closed, evidence-linked next-session decision surface."""

    current_time = now or datetime.now()
    sources, source_gaps = _load_monitor_sources(report_dir, current_time)
    risk = _risk_context(sources.get("risk_watch", {}).get("payload"))
    market = _market_context(sources.get("market_pulse", {}).get("payload"))
    levels_source = sources.get("market_levels", {})
    levels = _levels_context(levels_source.get("payload"), levels_source)
    industry = _industry_context(sources.get("ai_capex_watch", {}).get("payload"))
    style_rotation = _style_context(sources.get("style_rotation", {}).get("payload"))
    market_structure = _structure_context(risk.get("anchor_structure"))
    decision_rules = _load_decision_rules(decision_rules_path)
    market_level_state = _market_level_state(levels, risk, decision_rules)
    levels["market_level_state"] = market_level_state
    observation = _score_observation(risk, market, levels, sources, decision_rules)
    resolved_state_path = score_state_path or (
        DEFAULT_SCORE_STATE_PATH if report_dir.resolve() == REPORT_DIR.resolve() else report_dir / ".bear-bull-score-state.json"
    )
    score_contract, next_score_state = evaluate_score_state(
        observation,
        load_score_state(resolved_state_path),
        decision_rules,
        now=current_time,
    )
    if persist_score_state:
        save_score_state(resolved_state_path, next_score_state)
    market_regime = _market_regime(risk, levels, market_structure, score_contract)

    risk_level = str(risk.get("level") or "unknown")
    if risk_level == "red":
        stance = "防守观察"
    elif risk_level == "orange":
        stance = "收缩风险"
    elif risk_level == "yellow":
        stance = "谨慎持有"
    elif risk_level == "green" and market.get("direction") not in {None, "方向不清"}:
        stance = "条件进攻"
    else:
        stance = "等待确认"

    stance, market_level_impact = _apply_market_level_authority(stance, market_level_state, risk, score_contract)
    first_action = _first_action(actions, risk)
    if market_level_impact.get("first_action_override"):
        first_action = str(market_level_impact["first_action_override"])
    scenarios = _scenario_plan(actions, risk, industry)
    blocked_actions = _blocked_actions(risk, market, industry, market_structure, reliability)
    blocked_actions.extend(str(item) for item in market_level_impact.get("blocked_actions", []) if str(item))
    unlock_conditions = _unlock_conditions(actions, risk, industry, market_structure)
    evidence = _evidence_effects(risk, market, levels, industry, market_structure, style_rotation)
    decision_gaps = [*source_gaps]
    if market.get("direction") in {None, "方向不清"}:
        decision_gaps.append("盘中方向和股指期货基差尚未确认，开盘前不得把方向假设当成事实。")
    if float(reliability.get("decision_ready_coverage") or 0.0) < 1.0:
        decision_gaps.append("持仓成本、股数或盈亏等字段不完整，成本止盈与精确委托数量继续降级。")
    if market_structure.get("status") != "verified":
        decision_gaps.append("9·24锚点宽度未达到严格覆盖门槛，不得引用‘3900只’或等效点位作为确定事实。")
    if style_rotation.get("style_rotation_status") in {None, "数据不足"}:
        decision_gaps.append("风格矩阵数据不足，不能据此切换科技/金融/高股息或改变风险预算。")

    confidence = "中"
    if risk_level == "unknown" or not actions:
        confidence = "低"
    elif decision_gaps or industry.get("supplier_state") == "pending":
        confidence = "中低"

    plan_date = _next_weekday(current_time.date()).isoformat()
    budget = {
        "risk_level": risk_level,
        "risk_label": risk.get("label") or "待确认",
        "risk_score": risk.get("score"),
        "total_exposure_pct": risk.get("total_exposure_pct"),
        "total_exposure_cap_pct": risk.get("total_exposure_cap_pct"),
        "high_beta_exposure_pct": risk.get("high_beta_exposure_pct"),
        "high_beta_cap_pct": risk.get("high_beta_cap_pct"),
        "high_beta_over_cap_pct": risk.get("high_beta_over_cap_pct"),
        "market_level_review_state": market_level_impact.get("risk_budget_effect"),
        "upgrade_eligible": bool(market_level_impact.get("risk_budget_upgrade_eligible")),
        "upgrade_blocked": bool(score_contract.get("risk_budget_upgrade_blocked")),
        "upgrade_block_reason": market_level_impact.get("risk_budget_block_reason"),
    }
    return {
        "plan_date": plan_date,
        "stance": stance,
        "confidence": confidence,
        "headline": f"{plan_date}先执行条件计划：{first_action}",
        "first_action": first_action,
        "risk_budget": budget,
        "market_regime": market_regime,
        "market_structure": market_structure,
        "market_levels": levels,
        "market_level_impact": market_level_impact,
        "style_rotation": style_rotation,
        "tomorrow_watchlist": _tomorrow_watchlist(levels, market_structure, score_contract),
        "scenario_plan": scenarios,
        "holding_plans": actions,
        "blocked_actions": blocked_actions,
        "unlock_conditions": unlock_conditions,
        "evidence_effects": evidence,
        "source_reports": [_source_summary(key, sources.get(key)) for key in MONITOR_PATTERNS],
        "data_gaps": _dedupe(decision_gaps),
        "authority": "只提供条件化次日指引，不自动下单；等权等效点位不是官方指数，国家队ETF份额变化不能识别当前买卖方。",
    }


def render_unified_decision_markdown(decision: dict[str, object]) -> str:
    """Render the structured decision into a compact, first-screen section."""

    budget = decision.get("risk_budget") if isinstance(decision.get("risk_budget"), dict) else {}
    lines = [
        "## 明日统一指引",
        f"- 计划日期：{decision.get('plan_date') or '待确认'}",
        f"- 总体姿态：{decision.get('stance') or '等待确认'}（置信度：{decision.get('confidence') or '低'}）",
        f"- 第一动作：{decision.get('first_action') or '补齐数据前不新增仓位。'}",
    ]
    if budget:
        lines.append(
            "- 风险预算："
            f"{budget.get('risk_label') or '待确认'}；总仓位 {_pct_text(budget.get('total_exposure_pct'))} / "
            f"上限 {_pct_text(budget.get('total_exposure_cap_pct'))}；高β {_pct_text(budget.get('high_beta_exposure_pct'))} / "
            f"上限 {_pct_text(budget.get('high_beta_cap_pct'))}。"
        )
    regime = decision.get("market_regime") if isinstance(decision.get("market_regime"), dict) else {}
    if regime:
        lines.extend(
            [
                f"- 评分截至：{regime.get('score_as_of') or regime.get('as_of') or '待确认'}；口径：确定性状态机，{regime.get('calibration') or 'diagnostic_unbacktested'}。",
                f"- 熊牛评分：{regime.get('bear_bull_score', 'NA')}/10（正式分；{regime.get('regime_label') or '待确认'}）",
                f"- 评分变化：上一正式分 {regime.get('previous_score', 'NA')}；当前正式分 {regime.get('bear_bull_score', 'NA')}；盘中候选分 {regime.get('candidate_score', 'NA')}；正式变化 {_signed_score(regime.get('score_delta'))}；候选变化 {_signed_score(regime.get('candidate_delta'))}。",
                f"- 评分状态：{regime.get('finalization_status') or 'unavailable'}；正式确认 {regime.get('finalized_at') or '等待收盘'}；升级阻断 {str(bool(regime.get('upgrade_blocked'))).lower()}；风险预算阻断 {str(bool(regime.get('risk_budget_upgrade_blocked'))).lower()}。",
                f"- 恐慌贪婪：{regime.get('fear_greed_score', 'NA')}/100（{regime.get('fear_greed_label') or '待确认'}）",
                f"- 拥挤度：{regime.get('crowding_score', 'NA')}/100（{regime.get('crowding_label') or '待确认'}；{regime.get('crowding_status') or '待校准'}）",
            ]
        )
        lines.extend(["", "### 评分账单"])
        ledger = regime.get("score_ledger") if isinstance(regime.get("score_ledger"), list) else []
        if not ledger:
            lines.append("- 无新增计分规则；正式分维持不变。")
        for item in ledger:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('rule_id')}｜{item.get('direction')}｜{_signed_score(item.get('points'))}分｜"
                f"{item.get('status')}｜{item.get('explanation')}｜证据截至 {item.get('evidence_as_of') or '待确认'}"
            )
    structure = decision.get("market_structure") if isinstance(decision.get("market_structure"), dict) else {}
    if structure:
        lines.extend(
            [
                "",
                "### 市场宽度与指数失真",
                f"- 锚点累计宽度：{structure.get('health_score', 'NA')}/100（{structure.get('health_label') or '待确认'}；{structure.get('status') or 'unavailable'}；不代表当前短线趋势）。",
                f"- 低于锚点：{structure.get('below_anchor_count', 'NA')}/{structure.get('valid_count', 'NA')}（{_pct_ratio(structure.get('below_anchor_ratio'))}；覆盖率 {_pct_ratio(structure.get('coverage_ratio'))}）。",
                f"- 锚点股票池：返回 {structure.get('returned_unique_count', 'NA')}，锚点后上市剔除 {structure.get('post_anchor_listing_count', 'NA')}，上市日期缺失 {structure.get('missing_listing_date_count', 'NA')}。",
                f"- 等权等效上证：{_level_text(structure.get('equal_weight_equivalent_point'))}；中位数股票等效：{_level_text(structure.get('median_equivalent_point'))}；官方上证：{_level_text(structure.get('benchmark_current_close'))}。",
                f"- 指数偏离：官方区间 {_pct_ratio(structure.get('benchmark_return'))}，固定股票池等权 {_pct_ratio(structure.get('equal_weight_return'))}，差 {_pct_ratio(structure.get('benchmark_equal_weight_gap'))}。",
                f"- 3900只审计：{_claim_text(structure.get('claim_3900_status'))}；科技定义 {','.join(str(item) for item in structure.get('technology_definition', [])) or '待确认'}。",
            ]
        )
    style = decision.get("style_rotation") if isinstance(decision.get("style_rotation"), dict) else {}
    if style:
        questions = style.get("questions") if isinstance(style.get("questions"), dict) else {}
        lines.extend(
            [
                "",
                "### 科技—金融—高股息风格确认",
                f"- 风格状态：{style.get('style_rotation_status') or '数据不足'}；领先 {style.get('leader_style') or '待确认'}；走弱 {style.get('weakening_style') or '待确认'}；持续 {style.get('confirmation_days') or 0} 个交易日。",
                f"- 科技对比：{questions.get('technology_vs_financial_dividend') or '数据不足'}",
                f"- 单日还是轮动：{questions.get('single_day_or_rotation') or '数据不足'}",
                f"- 风险预算权限：{'只允许进入risk-watch复核' if questions.get('enough_to_change_risk_budget') else '证据不足，不改变风险预算'}；{style.get('calibration') or 'diagnostic_unbacktested'}。",
            ]
        )
    levels = decision.get("market_levels") if isinstance(decision.get("market_levels"), dict) else {}
    if levels:
        positions = levels.get("zone_positions") if isinstance(levels.get("zone_positions"), dict) else {}
        impact = decision.get("market_level_impact") if isinstance(decision.get("market_level_impact"), dict) else {}
        lines.extend(
            [
                "",
                "### 大盘点位与状态切换",
                f"- 当前点位：{_level_text(levels.get('latest'))}；market_level_state：{levels.get('market_level_state') or 'unavailable'}；结构：{levels.get('verdict') or '待确认'}。",
                f"- 生死支撑：{_zone_text(levels.get('support_zone'))}；{_zone_detail_text(positions.get('support'))}；动作：{levels.get('support_action') or '守住只按弱反弹处理。'}",
                f"- 第一确认：{_zone_text(levels.get('confirmation_zone'))}；{_zone_detail_text(positions.get('confirmation'))}；动作：站稳后只升级为有效反弹，不追涨。",
                f"- 较强压力：{_zone_text(levels.get('strong_resistance_zone'))}；{_zone_detail_text(positions.get('strong_resistance'))}；动作：收盘突破且宽度成交同步才候选+1。",
                f"- 日线修复：{_zone_text(levels.get('daily_repair_zone'))}；{_zone_detail_text(positions.get('daily_repair'))}；动作：配合宽度改善才允许趋势修复。",
                f"- 点位决策权：姿态 {impact.get('stance_before') or '待确认'} → {impact.get('stance_after') or '待确认'}；风险预算 {impact.get('risk_budget_effect') or '保持'}；{impact.get('stance_effect') or '维持'}。",
                f"- 失效预案：{impact.get('invalidation_plan') or levels.get('breakdown_action') or '15分钟跌破支撑后等待下一根确认，不用单根穿越判定失效。'}",
                f"- 点位算法：{levels.get('method_note') or '分型、均线、ATR、滚动高低点与波段回撤聚类；不是单一黄金分割。'}",
            ]
        )
    watchlist = decision.get("tomorrow_watchlist") if isinstance(decision.get("tomorrow_watchlist"), list) else []
    if watchlist:
        lines.extend(["", "### 四时点作战时间轴"])
        for item in watchlist:
            if isinstance(item, dict):
                lines.append(
                    f"- {item.get('time') or item.get('time_window') or '盘中'}｜观察：{item.get('observe') or '待确认'}｜"
                    f"当前：{item.get('current_status') or '等待观察'}｜动作：弱={item.get('action_if_bearish') or '保持'}；"
                    f"强={item.get('action_if_improved') or '保持'}；混合={item.get('action_if_mixed') or '保持'}｜"
                    f"候选影响：{item.get('candidate_score_effect') or '0'}｜正式确认：{'允许' if item.get('finalization_allowed') else '禁止'}"
                )
    execution_plans = decision.get("holding_execution_plans") if isinstance(decision.get("holding_execution_plans"), list) else []
    if execution_plans:
        lines.extend(["", "### 持仓整数手执行"])
        for item in execution_plans:
            if not isinstance(item, dict):
                continue
            ratio = _pct_ratio(item.get("target_trim_ratio"))
            raw = _level_text(item.get("raw_target_shares"))
            lot = item.get("executable_lot_shares")
            available = _level_text(item.get("available_shares"))
            lines.append(
                f"- {item.get('name') or item.get('code')}｜目标减仓 {ratio}｜原始 {raw} 股｜"
                f"可执行整数手 {lot if lot is not None else '未提供'} 股｜可卖 {available} 股｜"
                f"{item.get('execution_readiness') or 'unavailable'}｜{item.get('reason') or '待确认'}"
            )
    lines.extend(["", "### 明日四种情景"])
    scenarios = decision.get("scenario_plan") if isinstance(decision.get("scenario_plan"), list) else []
    for item in scenarios:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('scenario') or '情景'}｜触发：{item.get('trigger') or '待确认'}｜"
            f"动作：{item.get('action') or '保持不动'}"
        )
    lines.extend(["", "### 当前禁止动作"])
    for item in decision.get("blocked_actions", []) if isinstance(decision.get("blocked_actions"), list) else []:
        lines.append(f"- {item}")
    lines.extend(["", "### 允许提高风险前必须满足"])
    for item in decision.get("unlock_conditions", []) if isinstance(decision.get("unlock_conditions"), list) else []:
        lines.append(f"- {item}")
    lines.extend(["", "### 合并证据"])
    for item in decision.get("evidence_effects", []) if isinstance(decision.get("evidence_effects"), list) else []:
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('source') or '来源'}：{item.get('state') or '待确认'}；"
                f"对明日动作的影响：{item.get('effect') or '不改变动作'}"
            )
    gaps = decision.get("data_gaps") if isinstance(decision.get("data_gaps"), list) else []
    if gaps:
        lines.extend(["", "### 指引降级项"])
        lines.extend(f"- {item}" for item in gaps)
    return "\n".join(lines)


def inject_unified_decision(markdown: str, decision: dict[str, object]) -> str:
    section = render_unified_decision_markdown(decision)
    marker = "\n## 可选扩展缺口"
    if marker in markdown:
        return markdown.replace(marker, f"\n\n{section}{marker}", 1)
    lines = markdown.splitlines()
    if lines:
        return "\n".join([lines[0], "", section, *lines[1:]])
    return section


def _load_monitor_sources(
    report_dir: Path,
    current_time: datetime,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    sources: dict[str, dict[str, object]] = {}
    gaps: list[str] = []
    for key, pattern in MONITOR_PATTERNS.items():
        paths = sorted(report_dir.glob(pattern), reverse=True) if report_dir.exists() else []
        if not paths:
            gaps.append(f"未找到 {key} JSON，统一指引按缺失数据降级。")
            continue
        path = paths[0]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            gaps.append(f"{path.name} 无法读取：{exc}")
            continue
        generated_at = _parse_datetime(payload.get("generated_at"))
        age_days = (current_time - generated_at).total_seconds() / 86400 if generated_at else None
        stale = age_days is None or age_days > 4
        if stale:
            gaps.append(f"{path.name} 已超过4天或缺少生成时间，只能作为旧证据。")
        sources[key] = {
            "path": path,
            "payload": payload,
            "generated_at": payload.get("generated_at"),
            "as_of": payload.get("as_of"),
            "stale": stale,
        }
    return sources, gaps


def _risk_context(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else {}
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    budget = latest.get("risk_budget") if isinstance(latest.get("risk_budget"), dict) else {}
    metrics = latest.get("metrics") if isinstance(latest.get("metrics"), dict) else {}
    crowding = payload.get("crowding_snapshot") if isinstance(payload.get("crowding_snapshot"), dict) else {}
    manual_flags = profile.get("manual_flags") if isinstance(profile.get("manual_flags"), dict) else {}
    high_beta = _number(profile.get("high_beta_exposure_pct"))
    high_beta_cap = _number(budget.get("high_beta_cap_pct"))
    return {
        "as_of": payload.get("as_of") or latest.get("date"),
        "level": latest.get("level"),
        "label": latest.get("level_label"),
        "score": latest.get("score"),
        "total_exposure_pct": _number(profile.get("total_exposure_pct")),
        "total_exposure_cap_pct": _number(budget.get("total_exposure_cap_pct")),
        "high_beta_exposure_pct": high_beta,
        "high_beta_cap_pct": high_beta_cap,
        "high_beta_over_cap_pct": (
            round(high_beta - high_beta_cap, 2)
            if high_beta is not None and high_beta_cap is not None and high_beta > high_beta_cap
            else 0.0
        ),
        "actions": payload.get("actions") if isinstance(payload.get("actions"), list) else [],
        "signals": latest.get("signals") if isinstance(latest.get("signals"), list) else [],
        "metrics": metrics,
        "crowding_snapshot": crowding,
        "anchor_structure": payload.get("anchor_structure") if isinstance(payload.get("anchor_structure"), dict) else {},
        "manual_flags": manual_flags,
        "coverage_ratio": latest.get("coverage_ratio"),
        "active_families": latest.get("active_families"),
    }


def _market_context(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    state = payload.get("state_team_etf_proxy") if isinstance(payload.get("state_team_etf_proxy"), dict) else {}
    recent = state.get("recent_changes") if isinstance(state.get("recent_changes"), dict) else {}
    five = recent.get("five_observations") if isinstance(recent.get("five_observations"), dict) else {}
    twenty = recent.get("twenty_observations") if isinstance(recent.get("twenty_observations"), dict) else {}
    return {
        "as_of": payload.get("as_of"),
        "direction": analysis.get("verdict"),
        "action_bias": analysis.get("action_bias"),
        "state_team_signal": state.get("change_signal"),
        "state_team_as_of": state.get("as_of"),
        "state_team_five_pct": five.get("change_pct"),
        "state_team_twenty_pct": twenty.get("change_pct"),
        "minimum_exit_ratio": state.get("minimum_exit_ratio"),
    }


def _industry_context(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    supplier_state = None
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), list) else []
    for item in metrics:
        if isinstance(item, dict) and item.get("key") == "supplier_realization":
            supplier_state = item.get("state")
            break
    return {
        "as_of": payload.get("as_of"),
        "conclusion": payload.get("conclusion"),
        "supplier_state": supplier_state,
    }


def _style_context(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    keys = (
        "as_of",
        "style_rotation_status",
        "leader_style",
        "leader_style_key",
        "weakening_style",
        "confirmation_days",
        "relative_strength",
        "breadth_confirmation",
        "turnover_confirmation",
        "fund_proxy_confirmation",
        "earnings_confirmation",
        "positive_evidence",
        "negative_evidence",
        "blocked_conclusions",
        "source_coverage",
        "calibration",
        "questions",
        "authority",
    )
    return {key: payload.get(key) for key in keys}


def _levels_context(payload: object, source: object | None = None) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    timeframes = payload.get("timeframes") if isinstance(payload.get("timeframes"), list) else []
    day = next((item for item in timeframes if isinstance(item, dict) and item.get("timeframe") == "day"), {})
    week = next((item for item in timeframes if isinstance(item, dict) and item.get("timeframe") == "week"), {})
    fifteen = next((item for item in timeframes if isinstance(item, dict) and item.get("timeframe") == "15m"), {})
    support = analysis.get("confluence_zone") if isinstance(analysis.get("confluence_zone"), dict) else {}
    confirmation = analysis.get("confirmation_zone") if isinstance(analysis.get("confirmation_zone"), dict) else {}
    week_resistance = _first_zone(week.get("resistance_zones") if isinstance(week, dict) else None)
    day_resistance = _first_zone(day.get("resistance_zones") if isinstance(day, dict) else None)
    conditions = analysis.get("conditions") if isinstance(analysis.get("conditions"), list) else []
    latest = day.get("latest") if isinstance(day, dict) else None
    return {
        "as_of": day.get("as_of") if isinstance(day, dict) else None,
        "latest": latest,
        "latest_15m": fifteen.get("latest") if isinstance(fifteen, dict) else None,
        "as_of_15m": fifteen.get("as_of") if isinstance(fifteen, dict) else None,
        "completed_below_support_bars": payload.get("completed_below_support_bars"),
        "verdict": analysis.get("verdict"),
        "weak_timeframes": analysis.get("weak_timeframes"),
        "support_zone": _zone_payload(support),
        "confirmation_zone": _zone_payload(confirmation),
        "strong_resistance_zone": week_resistance,
        "daily_repair_zone": day_resistance,
        "zone_positions": {
            "support": _zone_position(latest, _zone_payload(support)),
            "confirmation": _zone_position(latest, _zone_payload(confirmation)),
            "strong_resistance": _zone_position(latest, week_resistance),
            "daily_repair": _zone_position(latest, day_resistance),
        },
        "support_action": conditions[0] if conditions else None,
        "breakdown_action": conditions[1] if len(conditions) > 1 else None,
        "confirmation_action": conditions[2] if len(conditions) > 2 else None,
        "method_note": "分型前低、均线、ATR、滚动高低点、布林轨道、中枢边界与0.382/0.5/0.618波段回撤共同聚类；少于两类证据不报重点区间。",
        "fibonacci_role": "辅助候选，不是唯一算法；当前3742-3770主要由分型/滚动低点/布林下轨/中枢与均线共振。",
        "source_status": (
            "stale"
            if isinstance(source, dict) and source.get("stale")
            else "current" if isinstance(source, dict) and source.get("payload") else "unavailable"
        ),
    }


def _structure_context(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    keys = (
        "as_of",
        "anchor_date",
        "status",
        "source",
        "returned_unique_count",
        "post_anchor_listing_count",
        "missing_listing_date_count",
        "eligible_count",
        "valid_count",
        "coverage_ratio",
        "below_anchor_count",
        "below_anchor_ratio",
        "claim_3900_status",
        "equal_weight_return",
        "median_return",
        "benchmark_return",
        "benchmark_current_close",
        "equal_weight_equivalent_point",
        "median_equivalent_point",
        "benchmark_equal_weight_gap",
        "technology_definition",
        "technology_current_free_float_share",
        "technology_equal_weight_return",
        "nontechnology_equal_weight_return",
        "health_score",
        "health_label",
        "breadth_label",
    )
    return {key: payload.get(key) for key in keys}


def _load_decision_rules(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _market_level_state(
    levels: dict[str, object],
    risk: dict[str, object],
    config: dict[str, object],
) -> str:
    if levels.get("source_status") == "stale":
        return "stale"
    latest = _number(levels.get("latest"))
    support = _zone_payload(levels.get("support_zone"))
    confirmation = _zone_payload(levels.get("confirmation_zone"))
    strong = _zone_payload(levels.get("strong_resistance_zone"))
    repair = _zone_payload(levels.get("daily_repair_zone"))
    if latest is None or not support or not confirmation or not strong:
        return "unavailable"
    score_config = config.get("score") if isinstance(config.get("score"), dict) else {}
    hysteresis = _number(score_config.get("zone_hysteresis_pct")) or 0.0
    lower_buffer = support["lower"] * hysteresis
    completed_below = int(_number(levels.get("completed_below_support_bars")) or 0)
    breadth = _breadth_state(risk, config)
    turnover = _turnover_state(risk, config)
    if latest < support["lower"] - lower_buffer:
        if completed_below >= int(_number(score_config.get("confirmation_persistence_bars")) or 2):
            return "support_failed"
        return "below_support"
    if support["lower"] - lower_buffer <= latest <= support["upper"]:
        return "support_testing"
    if latest < confirmation["lower"]:
        return "support_held"
    if latest <= confirmation["upper"]:
        return "confirmation_testing"
    if latest < strong["lower"]:
        return "rebound_confirmed"
    if latest <= strong["upper"]:
        return "strong_resistance_testing"
    if repair and latest >= repair["upper"] and breadth == "up" and turnover == "up":
        return "daily_repair_confirmed"
    if breadth == "up" and turnover == "up":
        return "strong_breakout_confirmed"
    return "strong_resistance_testing"


def _score_observation(
    risk: dict[str, object],
    market: dict[str, object],
    levels: dict[str, object],
    sources: dict[str, dict[str, object]],
    config: dict[str, object],
) -> dict[str, object]:
    market_date = str(risk.get("as_of") or levels.get("as_of") or "")[:10]
    required = ("risk_watch", "market_levels")
    gaps: list[str] = []
    for key in required:
        source = sources.get(key)
        if not isinstance(source, dict):
            gaps.append(f"{key} missing")
        elif source.get("stale"):
            gaps.append(f"{key} stale")
    if not levels.get("support_zone") or not levels.get("confirmation_zone") or not levels.get("strong_resistance_zone"):
        gaps.append("market-level zones incomplete")
    breadth = _breadth_state(risk, config)
    turnover = _turnover_state(risk, config)
    if breadth == "unavailable":
        gaps.append("short-cycle breadth unavailable; 9·24 anchor breadth is not a substitute")
    if turnover == "unavailable":
        gaps.append("turnover confirmation unavailable")
    level_date = str(levels.get("as_of") or "")[:10]
    if market_date and level_date and market_date != level_date:
        gaps.append(f"market date mismatch: risk {market_date}, levels {level_date}")
    metrics = risk.get("metrics") if isinstance(risk.get("metrics"), dict) else {}
    all_a = metrics.get("all_a") if isinstance(metrics.get("all_a"), dict) else {}
    level_state = str(levels.get("market_level_state") or "unavailable")
    if level_state in {"unavailable", "stale"}:
        gaps.append(f"market_level_state {level_state}")
    is_close = bool(market_date and level_date == market_date and str(levels.get("as_of_15m") or "").startswith(market_date))
    hard_risk = any(
        str(item.get("key") or "").endswith(("circuit_breaker", "second_circuit_breaker"))
        for item in risk.get("signals", [])
        if isinstance(item, dict)
    ) if isinstance(risk.get("signals"), list) else False
    return {
        "market_date": market_date,
        "market_level_state": level_state,
        "latest": levels.get("latest"),
        "breadth_state": breadth,
        "turnover_state": turnover,
        "is_close": is_close,
        "data_complete": not gaps,
        "data_gaps": gaps,
        "risk_level": risk.get("level"),
        "risk_veto": risk.get("level") in {"red", "orange"},
        "hard_risk_event": hard_risk,
        "evidence_source": {
            "market_levels": sources.get("market_levels", {}).get("path"),
            "breadth_turnover": sources.get("risk_watch", {}).get("path"),
        },
        "evidence_as_of": {
            "market_levels": levels.get("as_of_15m") or levels.get("as_of"),
            "breadth": all_a.get("as_of"),
            "turnover": all_a.get("as_of"),
            "market_pulse": market.get("as_of"),
        },
    }


def _breadth_state(risk: dict[str, object], config: dict[str, object]) -> str:
    metrics = risk.get("metrics") if isinstance(risk.get("metrics"), dict) else {}
    all_a = metrics.get("all_a") if isinstance(metrics.get("all_a"), dict) else {}
    day_return = _number(all_a.get("day_return"))
    ma20_gap = _number(all_a.get("ma20_gap"))
    if day_return is None or ma20_gap is None:
        return "unavailable"
    score_config = config.get("score") if isinstance(config.get("score"), dict) else {}
    up = _number(score_config.get("breadth_up_day_return")) or 0.005
    down = _number(score_config.get("breadth_down_day_return")) or -0.01
    if day_return >= up and ma20_gap >= -0.02:
        return "up"
    if day_return <= down and ma20_gap < 0:
        return "down"
    return "mixed"


def _turnover_state(risk: dict[str, object], config: dict[str, object]) -> str:
    metrics = risk.get("metrics") if isinstance(risk.get("metrics"), dict) else {}
    all_a = metrics.get("all_a") if isinstance(metrics.get("all_a"), dict) else {}
    percentile = _number(all_a.get("amount_percentile_60d"))
    if percentile is None:
        return "unavailable"
    score_config = config.get("score") if isinstance(config.get("score"), dict) else {}
    improved = _number(score_config.get("turnover_improved_percentile")) or 0.5
    not_weak = _number(score_config.get("turnover_not_weak_percentile")) or 0.2
    if percentile >= improved:
        return "up"
    if percentile >= not_weak:
        return "not_weak"
    return "weak"


def _apply_market_level_authority(
    stance: str,
    state: str,
    risk: dict[str, object],
    score: dict[str, object],
) -> tuple[str, dict[str, object]]:
    impact: dict[str, object] = {
        "market_level_state": state,
        "stance_before": stance,
        "stance_after": stance,
        "stance_effect": "维持原姿态",
        "risk_budget_effect": "保持",
        "risk_budget_upgrade_eligible": False,
        "risk_budget_block_reason": None,
        "blocked_actions": [],
        "invalidation_plan": None,
    }
    if state in {"unavailable", "stale"}:
        stance = "等待确认" if stance == "条件进攻" else stance
        impact.update(
            stance_after=stance,
            stance_effect="数据缺失或过期，禁止姿态升级",
            risk_budget_effect="禁止上调",
            risk_budget_block_reason="market-levels unavailable or stale",
            blocked_actions=["在market-levels缺失或过期时提高总仓位或高β预算。"],
        )
    elif state in {"below_support", "support_failed"}:
        stance = "防守观察" if state == "below_support" else "收缩风险"
        impact.update(
            stance_after=stance,
            stance_effect="生死支撑失效，强制取消进攻姿态",
            risk_budget_effect="保持或下调",
            risk_budget_block_reason="support failure",
            blocked_actions=["支撑失效后新增风险仓位、把反抽当反转或追涨高β。"],
            invalidation_plan="15分钟收在支撑下沿以下且下一根仍不能收回：保持或下调风险预算，按持仓风险线分批处理。",
            first_action_override="生死支撑失效且不能快速收回时不新增高β；按持仓风险线与可卖整数手执行减仓复核。",
        )
    elif state in {"support_testing", "support_held"}:
        impact.update(
            stance_effect="仅确认支撑有效或小周期止跌，不称反转",
            risk_budget_effect="保持",
            blocked_actions=["仅因支撑守住就追涨或提高高β预算。"],
        )
    elif state in {"confirmation_testing", "rebound_confirmed"}:
        impact.update(
            stance_effect="最多升级为有效反弹，不授权追涨",
            risk_budget_effect="保持，等待强压力突破与风险审核",
            blocked_actions=["只因站稳第一确认区就追涨或增加高β。"],
        )
    elif state in {"strong_breakout_confirmed", "daily_repair_confirmed"}:
        veto = bool(score.get("risk_budget_upgrade_blocked")) or risk.get("level") in {"red", "orange"}
        impact.update(
            stance_effect="强压力突破已取得价格、宽度和成交确认",
            risk_budget_effect="可上调一级，等待risk-watch审核" if not veto else "候选改善但被risk-watch veto阻断",
            risk_budget_upgrade_eligible=not veto,
            risk_budget_block_reason="risk-watch veto" if veto else None,
        )
    impact["stance_after"] = stance
    return stance, impact


def _market_regime(
    risk: dict[str, object],
    levels: dict[str, object],
    structure: dict[str, object],
    score_contract: dict[str, object],
) -> dict[str, object]:
    fear_greed = _fear_greed_score(risk)
    crowding = _crowding_score(risk)
    formal = _number(score_contract.get("bear_bull_score"))
    result = {
        "as_of": score_contract.get("score_as_of") or risk.get("as_of") or levels.get("as_of"),
        **score_contract,
        "regime_label": _bear_bull_label(formal),
        "fear_greed_score": fear_greed,
        "fear_greed_label": _fear_greed_label(fear_greed),
        "crowding_score": crowding,
        "crowding_label": _crowding_label(crowding),
        "crowding_status": "绝对阈值诊断，少于20个每日快照，尚非历史分位",
        "drivers": [str(item.get("explanation")) for item in score_contract.get("score_ledger", []) if isinstance(item, dict)],
    }
    return result


def _first_action(actions: list[dict[str, object]], risk: dict[str, object]) -> str:
    if not actions:
        return "补齐持仓动作与风险监控前不新增仓位。"
    item = actions[0]
    name = str(item.get("name") or item.get("code") or "持仓")
    flat = str(item.get("flat_trigger") or item.get("position_action") or item.get("action") or "保持仓位")
    downside = str(item.get("downside_trigger") or "触发原风险线后复核减仓")
    high_beta = _number(risk.get("high_beta_exposure_pct"))
    high_beta_cap = _number(risk.get("high_beta_cap_pct"))
    over_cap = _number(risk.get("high_beta_over_cap_pct"))
    if high_beta and high_beta_cap is not None and over_cap and over_cap > 0:
        trim_ratio = over_cap / high_beta
        return (
            f"不新增高β仓位；当前高β{high_beta:.1f}%高于{high_beta_cap:.1f}%上限，"
            f"优先利用反弹或正常流动性把{name}降低约{trim_ratio:.0%}，使高β向预算收敛；"
            f"若直接触发下行条件则执行：{downside}；其余时间不在开盘恐慌卖出（{flat}）"
        )
    if risk.get("level") in {"red", "orange"}:
        prefix = "不新增高β仓位；"
    elif not risk.get("level"):
        prefix = "风险预算未确认前不新增仓位；"
    else:
        prefix = ""
    return f"{prefix}{name}未触发下行条件时按震荡方案执行（{flat}）；触发时执行：{downside}"


def _scenario_plan(
    actions: list[dict[str, object]],
    risk: dict[str, object],
    industry: dict[str, object],
) -> list[dict[str, str]]:
    if not actions:
        return [
            {
                "scenario": "数据未补齐",
                "trigger": "没有可审计的持仓动作或风险预算",
                "action": "不新增仓位，先补齐数据并重跑产品。",
            }
        ]
    item = actions[0]
    name = str(item.get("name") or item.get("code") or "持仓")
    high_beta_locked = risk.get("level") in {"red", "orange"}
    supplier_pending = industry.get("supplier_state") == "pending"
    high_beta = _number(risk.get("high_beta_exposure_pct"))
    over_cap = _number(risk.get("high_beta_over_cap_pct"))
    high_beta_cap = _number(risk.get("high_beta_cap_pct"))
    trim_ratio = over_cap / high_beta if high_beta and over_cap and over_cap > 0 else None
    if trim_ratio is not None and high_beta_cap is not None:
        upside_action = (
            f"若反弹仍未完成趋势确认，优先降低约{trim_ratio:.0%}现有仓位，"
            f"使高β向{high_beta_cap:.1f}%上限收敛；若完成趋势确认则继续持有观察，仍不追涨。"
        )
    else:
        upside_action = "继续持有观察，不追涨。"
    if high_beta_locked or supplier_pending:
        upside_action += "风险预算或供应商业绩兑现未解锁前仍不加仓。"
    return [
        {
            "scenario": "开盘前",
            "trigger": "检查隔夜市场、临时公告和风险灯是否出现新变化",
            "action": "无新增反证就沿用本计划；有重大新信息先重跑产品，不凭旧报告下单。",
        },
        {
            "scenario": f"{name}高开或反弹",
            "trigger": f"出现高开/反弹；趋势确认线为：{item.get('upside_trigger') or '满足原上行确认条件'}",
            "action": upside_action,
        },
        {
            "scenario": f"{name}平开或震荡",
            "trigger": "上行和下行条件都未触发",
            "action": str(item.get("flat_trigger") or item.get("position_action") or "保持仓位，等待确认。"),
        },
        {
            "scenario": f"{name}低开或走弱",
            "trigger": str(item.get("downside_trigger") or "触发原风险线或出现明确反证"),
            "action": str(item.get("downside_trigger") or "按原风险线降低仓位并复核。"),
        },
    ]


def _blocked_actions(
    risk: dict[str, object],
    market: dict[str, object],
    industry: dict[str, object],
    structure: dict[str, object],
    reliability: dict[str, object],
) -> list[str]:
    blocked: list[str] = []
    if risk.get("level") in {"red", "orange"}:
        blocked.append("新增高β仓位、补跌中摊低成本或追逐单日反弹。")
    elif not risk.get("level"):
        blocked.append("风险预算缺失时新增仓位。")
    if market.get("direction") in {None, "方向不清"}:
        blocked.append("把未确认的盘中方向当作高开/低开预测。")
    if market.get("state_team_signal"):
        blocked.append("把国家队ETF短期回补直接解释为国家队重新全面入场，或据此自动切换高股息。")
    if industry.get("supplier_state") == "pending":
        blocked.append("仅凭云厂商CapEx叙事追涨CPO；供应商业绩兑现尚未闭环。")
    below_anchor = _number(structure.get("below_anchor_ratio"))
    if structure.get("status") == "verified" and below_anchor is not None and below_anchor >= 0.60:
        blocked.append("只因上证或少数科技权重反弹就判断全市场反转；多数股票仍低于9·24锚点。")
    if float(reliability.get("decision_ready_coverage") or 0.0) < 1.0:
        blocked.append("在缺少成本、股数或盈亏时生成精确卖出股数和成本止盈指令。")
    return _dedupe(blocked)


def _unlock_conditions(
    actions: list[dict[str, object]],
    risk: dict[str, object],
    industry: dict[str, object],
    structure: dict[str, object],
) -> list[str]:
    conditions: list[str] = []
    if actions:
        upside = actions[0].get("upside_trigger")
        if upside:
            conditions.append(f"个股趋势确认：{upside}")
    if risk.get("level") in {"red", "orange"}:
        conditions.append("风险预算解锁：重新站回MA20，且海外弱势市场少于2个，再逐级恢复高β预算。")
    elif not risk.get("level"):
        conditions.append("先生成最新risk-watch并确认总仓位与高β预算。")
    if industry.get("supplier_state") == "pending":
        conditions.append("产业兑现解锁：用官方财报或调研闭环毛利率、经营现金流、库存、应收和1.6T收入。")
    below_anchor = _number(structure.get("below_anchor_ratio"))
    if structure.get("status") == "verified" and below_anchor is not None and below_anchor >= 0.60:
        conditions.append("市场宽度解锁：低于9·24锚点比例连续改善，且等权收益同步强于市值加权反弹。")
    return _dedupe(conditions) or ["风险、趋势与基本面至少两类证据同时改善。"]


def _evidence_effects(
    risk: dict[str, object],
    market: dict[str, object],
    levels: dict[str, object],
    industry: dict[str, object],
    structure: dict[str, object],
    style_rotation: dict[str, object],
) -> list[dict[str, object]]:
    return [
        {
            "source": "risk-watch",
            "as_of": risk.get("as_of"),
            "state": f"{risk.get('label') or '待确认'} / {risk.get('score') if risk.get('score') is not None else 'NA'}",
            "effect": "限制新增高β；未触发个股风险线时不要求机械清仓。",
        },
        {
            "source": "market-pulse / 国家队ETF代理",
            "as_of": market.get("state_team_as_of"),
            "state": market.get("state_team_signal") or "待确认",
            "effect": "短期回补只能减轻单边撤出叙事，不能证明当前买方或解除中期收缩。",
        },
        {
            "source": "market-levels",
            "as_of": levels.get("as_of"),
            "state": (
                f"支撑 {_zone_text(levels.get('support_zone'))} / "
                f"第一确认 {_zone_text(levels.get('confirmation_zone'))}"
            ),
            "effect": "把指数状态切换变成可观察条件；跌破支撑且不能收回则继续防守，站稳确认区才上调反弹级别。",
        },
        {
            "source": "risk-watch / 9·24锚点宽度",
            "as_of": structure.get("as_of"),
            "state": (
                f"低于锚点 {_pct_ratio(structure.get('below_anchor_ratio'))} / "
                f"等权等效 {_level_text(structure.get('equal_weight_equivalent_point'))}"
            ),
            "effect": "用于识别指数失真和多数股票体感；覆盖未达标时不进入动作授权。",
        },
        {
            "source": "ai-capex-watch",
            "as_of": industry.get("as_of"),
            "state": industry.get("conclusion") or "待确认",
            "effect": "保留产业逻辑，但供应商兑现未闭环时不能授权追涨。",
        },
        {
            "source": "style-rotation",
            "as_of": style_rotation.get("as_of"),
            "state": (
                f"{style_rotation.get('style_rotation_status') or '数据不足'} / "
                f"领先 {style_rotation.get('leader_style') or '待确认'} / 持续 {style_rotation.get('confirmation_days') or 0}日"
            ),
            "effect": "只有持续确认才可进入风险预算复核；矩阵本身不授权买入或切换仓位。",
        },
    ]


def _source_summary(key: str, source: object) -> dict[str, object]:
    if not isinstance(source, dict):
        return {"workflow": key, "status": "missing"}
    path = source.get("path")
    return {
        "workflow": key,
        "status": "stale" if source.get("stale") else "current",
        "path": str(path) if isinstance(path, Path) else str(path or ""),
        "generated_at": source.get("generated_at"),
        "as_of": source.get("as_of"),
    }


def _next_weekday(value: date) -> date:
    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _scale(value: object, low: float, high: float) -> float:
    number = _number(value)
    if number is None or high <= low:
        return 50.0
    return max(0.0, min(100.0, (number - low) / (high - low) * 100.0))


def _fear_greed_score(risk: dict[str, object]) -> int | None:
    metrics = risk.get("metrics") if isinstance(risk.get("metrics"), dict) else {}
    all_a = metrics.get("all_a") if isinstance(metrics.get("all_a"), dict) else {}
    if not all_a:
        return None
    growth_rows = [
        metrics.get(key)
        for key in ("chinext", "star50", "csi1000")
        if isinstance(metrics.get(key), dict)
    ]
    breadth = (
        sum(_scale(row.get("ma20_gap"), -0.20, 0.10) for row in growth_rows) / len(growth_rows)
        if growth_rows
        else 50.0
    )
    components = [
        (0.25, _scale(all_a.get("return_20d"), -0.20, 0.20)),
        (0.20, _scale(all_a.get("ma20_gap"), -0.15, 0.15)),
        (0.15, _scale(all_a.get("drawdown_20d"), -0.25, 0.0)),
        (0.15, 100.0 - _scale(all_a.get("vol20_ratio"), 0.60, 1.80)),
        (0.15, breadth),
        (0.10, _scale(all_a.get("day_return"), -0.08, 0.04)),
    ]
    return int(round(sum(weight * score for weight, score in components)))


def _crowding_score(risk: dict[str, object]) -> int | None:
    snapshot = risk.get("crowding_snapshot") if isinstance(risk.get("crowding_snapshot"), dict) else {}
    if not snapshot:
        return None
    flags = risk.get("manual_flags") if isinstance(risk.get("manual_flags"), dict) else {}
    narrative_count = sum(bool(flags.get(key)) for key in ("long_horizon_pricing", "retail_euphoria"))
    narrative = 100.0 if narrative_count == 2 else 50.0 if narrative_count == 1 else 0.0
    components = [
        (0.35, _scale(snapshot.get("top20_amount_share"), 0.08, 0.25)),
        (0.35, _scale(snapshot.get("top1_turnover_free_float"), 0.02, 0.12)),
        (0.15, _scale(snapshot.get("top1_amount_share"), 0.005, 0.05)),
        (0.15, narrative),
    ]
    return int(round(sum(weight * score for weight, score in components)))


def _bear_bull_label(score: float | None) -> str:
    if score is None:
        return "待确认"
    if score <= 1.4:
        return "熊市加速 / 恐慌"
    if score <= 2.9:
        return "熊市风险开启"
    if score <= 4.4:
        return "弱势修复"
    if score <= 5.5:
        return "中性"
    if score <= 7.0:
        return "偏多"
    return "牛市结构"


def _fear_greed_label(score: int | None) -> str:
    if score is None:
        return "待确认"
    if score <= 20:
        return "极度恐慌"
    if score <= 40:
        return "恐慌"
    if score <= 60:
        return "中性"
    if score <= 80:
        return "贪婪"
    return "极度贪婪"


def _crowding_label(score: int | None) -> str:
    if score is None:
        return "待确认"
    if score <= 35:
        return "低拥挤"
    if score <= 55:
        return "中性"
    if score <= 75:
        return "偏拥挤"
    return "高度拥挤"


def _first_zone(value: object) -> dict[str, float] | None:
    if not isinstance(value, list):
        return None
    for item in value:
        zone = _zone_payload(item)
        if zone:
            return zone
    return None


def _zone_payload(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    lower = _number(value.get("lower"))
    upper = _number(value.get("upper"))
    if lower is None or upper is None:
        return None
    return {"lower": round(min(lower, upper), 2), "upper": round(max(lower, upper), 2)}


def _zone_position(latest_value: object, zone_value: object) -> dict[str, object] | None:
    latest = _number(latest_value)
    zone = _zone_payload(zone_value)
    if latest is None or not zone:
        return None
    lower = zone["lower"]
    upper = zone["upper"]
    if latest < lower:
        relation = "下方"
    elif latest > upper:
        relation = "上方"
    else:
        relation = "区间内"
    return {
        "current": round(latest, 2),
        "lower": lower,
        "upper": upper,
        "relation": relation,
        "distance_to_lower_pct": round((latest / lower - 1.0) * 100.0, 2) if relation != "区间内" else None,
        "distance_to_upper_pct": round((latest / upper - 1.0) * 100.0, 2) if relation != "区间内" else None,
    }


def _zone_detail_text(value: object) -> str:
    if not isinstance(value, dict):
        return "当前关系待确认"
    relation = str(value.get("relation") or "待确认")
    current = _level_text(value.get("current"))
    if relation == "区间内":
        return f"现价{current}，区间内"
    lower = _number(value.get("distance_to_lower_pct"))
    upper = _number(value.get("distance_to_upper_pct"))
    lower_text = f"{lower:+.2f}%" if lower is not None else "NA"
    upper_text = f"{upper:+.2f}%" if upper is not None else "NA"
    return f"现价{current}，位于区间{relation}，距下沿{lower_text}、上沿{upper_text}"


def _level_text(value: object) -> str:
    number = _number(value)
    if number is None:
        return "待确认"
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _zone_text(value: object) -> str:
    zone = _zone_payload(value)
    if not zone:
        return "待确认"
    return f"{_level_text(zone['lower'])}-{_level_text(zone['upper'])}"


def _tomorrow_watchlist(
    levels: dict[str, object],
    structure: dict[str, object],
    score: dict[str, object],
) -> list[dict[str, object]]:
    support = _zone_text(levels.get("support_zone"))
    confirmation = _zone_text(levels.get("confirmation_zone"))
    strong = _zone_text(levels.get("strong_resistance_zone"))
    breadth = _pct_ratio(structure.get("below_anchor_ratio"))
    equivalent = _level_text(structure.get("equal_weight_equivalent_point"))
    state = str(levels.get("market_level_state") or "unavailable")
    evidence_as_of = levels.get("as_of_15m") or levels.get("as_of")
    data_current = state not in {"unavailable", "stale"}
    return [
        {
            "time": "开盘前",
            "time_window": "开盘前",
            "observe": f"隔夜市场、临时公告、股指期货基差和风险灯是否出现新变化；前次锚点弱势占比{breadth}、等权等效上证{equivalent}",
            "current_status": "等待观察" if data_current else "数据缺失",
            "bearish_if": "海外科技继续急跌或基差明显走弱",
            "improve_if": "无新增冲击，且集合竞价未放大抛压",
            "action_if_bearish": "保持或下调风险预算，不新增高β。",
            "action_if_improved": "沿用正式分，不在开盘前升分。",
            "action_if_mixed": "保持原计划，等待9:30后的真实成交。",
            "evidence_as_of": evidence_as_of,
            "candidate_score_effect": "0；只更新风险观察",
            "finalization_allowed": False,
        },
        {
            "time": "9:30–10:00",
            "time_window": "9:30–10:00",
            "observe": f"上证能否守住{support}，以及跌破后15分钟内能否收回",
            "current_status": state if data_current else "数据缺失",
            "bearish_if": str(levels.get("breakdown_action") or f"有效跌破{support}且不能收回"),
            "improve_if": f"{support}承接有效，小周期止跌但仍不等于反转",
            "action_if_bearish": "标记below_support；下一根15分钟仍不收回则转support_failed并候选-1。",
            "action_if_improved": "只标记支撑有效，不追涨、不提高高β。",
            "action_if_mixed": "等待观察，不用盘后旧数据冒充实时确认。",
            "evidence_as_of": evidence_as_of,
            "candidate_score_effect": "支撑失败且宽度恶化时-1，否则0",
            "finalization_allowed": False,
        },
        {
            "time": "11:20–11:30 午间复核",
            "time_window": "11:20–11:30",
            "observe": f"反弹能否进入并站稳{confirmation}，上涨家数和成长板块是否同步",
            "current_status": state if data_current else "数据缺失",
            "bearish_if": "反弹不过第一确认区、宽度继续收缩",
            "improve_if": str(levels.get("confirmation_action") or f"站稳{confirmation}，且上涨家数/等权表现同步修复而非只拉权重"),
            "action_if_bearish": "维持原正式分和防守姿态。",
            "action_if_improved": "生成候选+1；不覆盖正式分，不授权追涨。",
            "action_if_mixed": "显示信号冲突，候选变化0。",
            "evidence_as_of": evidence_as_of,
            "candidate_score_effect": "+1候选或0冲突",
            "finalization_allowed": False,
        },
        {
            "time": "14:45–15:00 收盘确认",
            "time_window": "14:45–15:00",
            "observe": f"是否站稳第一确认区；{strong}是更强压力，不到该区不把弱反弹当反转",
            "current_status": str(score.get("finalization_status") or "等待收盘确认"),
            "bearish_if": "主要指数和成长板块继续同步新低",
            "improve_if": "站稳第一确认区且成交/宽度改善，次日才允许上调一级风险预算",
            "action_if_bearish": "完整收盘数据确认后正式降分最多1分，并保持/下调预算。",
            "action_if_improved": "只有收盘站上强压力且宽度、成交同步才正式+1；仍经过risk veto。",
            "action_if_mixed": "正式分维持，记录冲突账单。",
            "evidence_as_of": evidence_as_of,
            "candidate_score_effect": "唯一允许正式写入bear_bull_score的时点",
            "finalization_allowed": True,
        },
    ]


def _pct_text(value: object) -> str:
    number = _number(value)
    return f"{number:.1f}%" if number is not None else "待确认"


def _signed_score(value: object) -> str:
    number = _number(value)
    if number is None:
        return "NA"
    return f"{number:+.1f}".replace("+0.0", "0").replace("-0.0", "0")


def _pct_ratio(value: object) -> str:
    number = _number(value)
    return f"{number:.1%}" if number is not None else "待确认"


def _claim_text(value: object) -> str:
    return {
        "supported": "同口径支持至少3900只低于锚点",
        "not_supported": "同口径不支持3900只",
        "unverified": "覆盖不足，暂不验证",
    }.get(str(value), "暂不验证")


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item and item.strip()))
