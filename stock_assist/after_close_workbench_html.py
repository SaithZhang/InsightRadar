"""Self-contained V3 HTML renderer for the after-close decision workspace."""

from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape

from stock_assist.branding import PRODUCT_NAME
from stock_assist.decision_workspace import overlay_plan_responses
from stock_assist.today_workbench import build_today_workbench


def render_after_close_workbench(
    payload: Mapping[str, object],
    markdown: str,
) -> str:
    """Render a file-safe report; local write actions activate via loopback."""

    raw_workspace = payload.get("decision_workspace")
    workspace = (
        overlay_plan_responses(raw_workspace)
        if isinstance(raw_workspace, Mapping)
        else _legacy_workspace(payload)
    )
    return _document(workspace)


def _document(workspace: Mapping[str, object]) -> str:
    workspace = dict(workspace)
    workspace["today_workbench"] = build_today_workbench(workspace)
    safe_json = _browser_workspace_json(workspace)
    positions = _dict_rows(workspace.get("portfolio_positions"))
    plans = _today_plans(workspace)
    source_time = _latest_source_time(workspace)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta name="insightradar-session-token" content="__LOCAL_SESSION_TOKEN__">
  <title>{escape(PRODUCT_NAME)} V3 — A股决策情报闭环</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark">IR</span><div>{escape(PRODUCT_NAME)}<small>Rule-first decision intelligence</small></div></div>
      <nav class="nav" aria-label="主要任务">
        {_nav("today", "今日工作台", str(len(plans)), True)}
        {_nav("portfolio", "组合风险", f"{len(positions)} 持仓")}
        {_nav("lookup", "标的研究", "证据优先")}
        {_nav("review", "复盘账本", "历史验证")}
      </nav>
      <div class="sidebar-card"><strong>本地单用户工作台</strong>真实本地数据 · 无交易权<br>规则决定状态，AI只做解释。</div>
    </aside>
    <main class="content">
      <header class="topbar">
        <div><div id="pageEyebrow" class="eyebrow">After close · Weekend ready</div><h1 id="pageTitle">今日工作台</h1></div>
        <div class="top-actions">
          <span class="chip">数据截至 {escape(source_time)}</span>
          <span class="chip" id="stage-label">{escape(_stage_label(workspace))}</span>
          <button class="btn small" id="morning-recheck" type="button">晨间增量复核</button>
          <button class="btn small" id="refresh-data" type="button">刷新异常数据</button>
          <button class="btn small ghost" id="refresh-all-data" type="button">全量刷新</button>
          <button class="btn small" id="data-status-open" type="button" aria-haspopup="dialog">数据状态</button>
        </div>
      </header>
      <div class="stage">
        {_today(workspace)}
        {_portfolio(workspace)}
        {_research(workspace)}
        {_review(workspace)}
      </div>
    </main>
  </div>
  <nav class="mobile-nav" aria-label="移动端主要任务">
    {_nav("today", "今日", "", True)}
    {_nav("portfolio", "组合")}
    {_nav("lookup", "研究")}
    {_nav("review", "复盘")}
  </nav>
  {_evidence_drawer(workspace)}
  {_data_drawer(workspace)}
  {_repair_drawer(workspace)}
  {_management_drawer(workspace)}
  <div class="toast" id="toast" role="status" aria-live="polite"></div>
  <script type="application/json" id="workspace-data">{safe_json}</script>
  <script>{_script()}</script>
</body>
</html>"""


def _browser_workspace_json(workspace: Mapping[str, object]) -> str:
    """Embed useful read-only evidence without exposing legacy field names."""

    hidden_keys = {"current_risk_line", "review_status"}

    def sanitize(value: object) -> object:
        if isinstance(value, Mapping):
            return {
                str(key): sanitize(item)
                for key, item in value.items()
                if str(key) not in hidden_keys
            }
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if isinstance(value, tuple):
            return [sanitize(item) for item in value]
        if value == "stale_context":
            return "needs_review"
        return value

    return json.dumps(sanitize(workspace), ensure_ascii=False, default=str).replace(
        "</", "<\\/"
    )


def _nav(
    route: str,
    label: str,
    meta: str = "",
    active: bool = False,
) -> str:
    class_name = ' class="active"' if active else ""
    trailing = (
        f'<span class="count">{escape(meta)}</span>'
        if route == "today" and meta
        else f"<small>{escape(meta)}</small>"
        if meta
        else ""
    )
    return (
        f'<button type="button"{class_name} data-view="{route}" data-route="{route}">'
        f"<span>{escape(label)}</span>{trailing}</button>"
    )


def _today(workspace: Mapping[str, object]) -> str:
    today = _mapping(workspace.get("today_workbench"))
    phase = str(today.get("phase") or "after_close")
    quality = str(today.get("data_quality") or "unknown")
    return f"""
<section class="view active" id="route-today" data-route-panel="today">
  <section class="today-phase-banner {escape(phase)}" aria-label="当前市场阶段">
    <span class="phase-dot" aria-hidden="true"></span>
    <strong>{escape(str(today.get('phase_label') or '盘后复盘'))}</strong>
    <span>{escape(str(today.get('phase_message') or '仅用于复盘，不产生实时交易动作。'))}</span>
    <em class="source {_status_class(quality)}">数据质量 {escape(quality)}</em>
  </section>
  <div class="today-workbench-grid">
    {_today_account_column(today)}
    {_today_attention_column(today)}
    {_today_decision_column(today)}
  </div>
  {_today_data_details(today)}
  <footer class="authority-disclaimer">
    事实与数字由结构化数据和确定性代码计算；规则状态由本地状态机管理；AI 未使用；交易权限始终为 none。
  </footer>
</section>"""


def _today_account_column(today: Mapping[str, object]) -> str:
    account = _mapping(today.get("account_snapshot"))
    daily = account.get("daily_pnl")
    peak = account.get("peak_daily_pnl")
    giveback = account.get("giveback_amount")
    ratio = account.get("giveback_ratio")
    if isinstance(daily, (int, float)) and isinstance(ratio, (int, float)):
        headline = (
            "账户仍赚钱，但利润回吐过半。"
            if daily > 0 and ratio >= 0.5
            else "账户收红，回吐仍在一半以内。"
            if daily > 0
            else "账户收亏，先核对亏损来源与数据质量。"
        )
    else:
        headline = "账户关键数字不完整，先看已确认事实。"
    attribution = _dict_rows(account.get("attribution"))
    attribution_html = "".join(
        f'<li><span>{escape(str(item.get("name") or item.get("symbol") or "未命名持仓"))}</span>'
        f'<strong class="pnl {"up" if isinstance(item.get("day_pnl"), (int, float)) and float(item["day_pnl"]) >= 0 else "down"}">{_money(item.get("day_pnl"))}</strong></li>'
        for item in attribution
    ) or '<li><span>盈亏来源</span><strong class="unknown-text">unknown</strong></li>'
    gaps = _string_rows(account.get("gaps"))
    gaps_html = "".join(f"<li>{escape(item)}</li>" for item in gaps) or "<li>当前未记录额外数据缺口。</li>"
    return f"""<article class="today-column what-column">
      <header class="today-column-head"><div><span class="eyebrow">01 · 发生了什么</span><h2>{escape(headline)}</h2></div><span class="source {_status_class(account.get('data_quality'))}">{escape(str(account.get('data_quality') or 'unknown'))}</span></header>
      <div class="account-pnl"><small>收盘当日盈亏</small><strong class="{_pnl_class(daily)}">{_money(daily)}</strong></div>
      <div class="account-metric-grid">
        <div><small>日内利润峰值</small><strong>{_money(peak)}</strong></div>
        <div><small>从峰值回吐</small><strong class="amber-text">{_money(giveback)}</strong><em>{_percent(ratio)}</em></div>
      </div>
      <div class="today-subsection"><h3>主要盈亏来源</h3><ul class="attribution-list">{attribution_html}</ul></div>
      <details class="today-details"><summary>数据异常与不可判断事项</summary><ul>{gaps_html}</ul><p>口径：{escape(str(account.get('pnl_source') or 'unknown'))} · 截至 {escape(str(account.get('as_of') or 'unknown'))}</p></details>
    </article>"""


def _today_attention_column(today: Mapping[str, object]) -> str:
    items = _dict_rows(today.get("attention_items"))
    positions = [item for item in items if item.get("type") == "position"][:2]
    opportunities = [item for item in items if item.get("type") == "opportunity"][:1]
    selected = [*positions, *opportunities]
    cards = "".join(_attention_card(item) for item in selected)
    if not cards:
        cards = '<div class="today-empty">没有可展示的结构化关注项。</div>'
    blocked = sum(item.get("data_quality") == "blocked" for item in selected)
    headline = (
        f"{blocked} 个判断阻断，另有 {max(0, len(selected) - blocked)} 项需复核。"
        if blocked
        else f"{len(selected)} 项按重要性统一排序。"
    )
    return f"""<article class="today-column attention-column">
      <header class="today-column-head"><div><span class="eyebrow">02 · 最需要关注</span><h2>{escape(headline)}</h2></div><span class="status">{len(selected)} 项</span></header>
      <div class="attention-stack">{cards}</div>
    </article>"""


def _attention_card(item: Mapping[str, object]) -> str:
    item_type = str(item.get("type") or "position")
    quality = str(item.get("data_quality") or "unknown")
    state = str(item.get("plan_status") or "observation_only")
    route = str(item.get("detail_route") or ("portfolio" if item_type == "position" else "lookup"))
    query = _mapping(item.get("detail_query"))
    evidence = _dict_rows(item.get("evidence"))
    evidence_html = "".join(
        f'<div class="attention-evidence"><b>{escape(str(row.get("claim") or "未提供结论"))}</b><span>{escape(str(row.get("source_ref") or "unknown"))} · {escape(str(row.get("source_time") or "unknown"))}</span></div>'
        for row in evidence[:3]
    ) or '<p class="unknown-text">暂无达到展示门槛的支持证据。</p>'
    counters = _string_rows(item.get("counter_evidence"))
    counter_html = "".join(f"<li>{escape(value)}</li>" for value in counters) or "<li>反证条件尚未结构化。</li>"
    route_label = "打开组合风险" if route == "portfolio" else "打开标的研究"
    return f"""<section class="attention-card {escape(item_type)} {_status_class(quality)}">
      <div class="attention-card-head"><div><strong>{escape(str(item.get('title') or '未命名关注项'))}</strong><span>{'持仓关注' if item_type == 'position' else '研究机会'}</span></div><span class="source {_status_class(state)}">{escape(_today_state_label(state))}</span></div>
      <p><b>发生了什么：</b>{escape(str(item.get('what_happened') or 'unknown'))}</p>
      <p><b>为什么重要：</b>{escape(str(item.get('why_it_matters') or 'unknown'))}</p>
      <div class="attention-meta"><span>计划 {_today_state_label(state)}</span><span>数据 {escape(quality)}</span><span>重要性 {escape(str(item.get('importance_score') or 0))}</span></div>
      <details class="today-details"><summary>支持证据与可能推翻</summary>{evidence_html}<div class="counter-block"><b>可能推翻当前判断</b><ul>{counter_html}</ul></div></details>
      <button class="btn small" type="button" data-view-link="{escape(route)}" data-route-symbol="{escape(str(query.get('symbol') or ''))}" data-route-plan="{escape(str(query.get('plan_id') or ''))}" data-route-intent="{escape(str(query.get('intent') or ''))}">{route_label}</button>
    </section>"""


def _today_decision_column(today: Mapping[str, object]) -> str:
    requirements = _dict_rows(today.get("decision_requirements"))
    rank = {"blocked": 0, "pending_confirmation": 1, "confirmed": 2, "observation_only": 3, "disabled": 4}
    requirements.sort(key=lambda item: rank.get(str(item.get("status")), 9))
    actionable = [
        item
        for item in requirements
        if item.get("status") in {"blocked", "pending_confirmation"}
    ]
    secondary = [item for item in requirements if item not in actionable]
    visible = [*actionable, *secondary[: max(0, 3 - len(actionable))]]
    pending = len(actionable)
    cards = "".join(_decision_card(item, index + 1) for index, item in enumerate(visible))
    if not cards:
        cards = '<div class="today-empty">当前没有待确认规则；继续等待新计划版本。</div>'
    return f"""<article class="today-column decision-column">
      <header class="today-column-head"><div><span class="eyebrow">03 · 我需要决定什么</span><h2>{pending} 项待处理，其余保持观察。</h2></div><span class="status pending">{pending} 项待处理</span></header>
      <div class="decision-stack">{cards}</div>
    </article>"""


def _decision_card(item: Mapping[str, object], index: int) -> str:
    status = str(item.get("status") or "pending_confirmation")
    allowed = set(_string_rows(item.get("allowed_responses")))
    rule_id = str(item.get("rule_id") or "")
    version = str(item.get("rule_version") or "unknown")
    blocking = _string_rows(item.get("blocking_reasons"))
    blocking_html = "".join(f"<li>{escape(value)}</li>" for value in blocking)
    controls: list[str] = []
    if "blocked_acknowledged" in allowed:
        controls.append('<button class="btn primary decision" type="button" data-plan-response="blocked_acknowledged">确认已知悉阻断</button>')
    elif "accepted" in allowed:
        controls.append('<button class="btn primary decision" type="button" data-plan-response="accepted">确认</button>')
    if "disputed" in allowed:
        controls.append('<button class="btn decision" type="button" data-plan-response="disputed">修改</button>')
    if "disabled" in allowed:
        controls.append('<button class="btn decision" type="button" data-plan-response="disabled">暂不启用</button>')
    if not controls:
        controls.append(f'<span class="decision-static-state">{escape(_today_state_label(status))}</span>')
    blocked_note = (
        '<p class="blocked-inline">数据阻断时，任何按钮都不能把本规则变成已确认或提醒候选。</p>'
        if status == "blocked"
        else ""
    )
    details = (
        f'<details class="today-details"><summary>查看阻断原因</summary><ul>{blocking_html}</ul></details>'
        if blocking
        else ""
    )
    return f"""<section class="decision-card {_status_class(status)}" data-plan-id="{escape(rule_id)}" data-plan-version="{escape(version)}">
      <div class="decision-card-index">{index}</div>
      <div class="decision-card-body"><div class="decision-card-title"><strong>{escape(str(item.get('title') or '未命名规则'))}</strong><span class="source {_status_class(status)}" data-response-label>{escape(_today_state_label(status))}</span></div>
      <p>{escape(str(item.get('prompt') or '等待规则状态明确。'))}</p>{details}
      <div class="today-rule-actions" role="group" aria-label="{escape(str(item.get('title') or '规则'))} 操作">{''.join(controls)}</div>
      <p class="decision-feedback" data-rule-feedback aria-live="polite">当前状态：{escape(_today_state_label(status))}；规则版本 {escape(version)}。</p>{blocked_note}</div>
    </section>"""


def _today_data_details(today: Mapping[str, object]) -> str:
    gaps = _string_rows(today.get("data_gaps"))
    rows = "".join(f"<li>{escape(item)}</li>" for item in gaps) or "<li>当前未记录额外缺口。</li>"
    return f"""<details class="today-data-details"><summary>数据详情</summary><div><p><span>回看交易日</span><strong>{escape(str(today.get('review_trade_date') or 'unknown'))}</strong></p><p><span>市场阶段</span><strong>{escape(str(today.get('phase') or 'after_close'))}</strong></p><p><span>AI 状态</span><strong>{escape(str(today.get('ai_status') or 'not_used'))}</strong></p><p><span>交易权限</span><strong>{escape(str(today.get('trade_authority') or 'none'))}</strong></p></div><ul>{rows}</ul></details>"""


def _decision_stage_rail(workspace: Mapping[str, object]) -> str:
    stage = str(workspace.get("run_stage") or "after_close")
    runtime_status = str(workspace.get("runtime_status") or "awaiting_confirmation")
    generated = _clock(workspace.get("source_generated_at"))
    morning = (
        _clock(workspace.get("generated_at"))
        if stage == "morning_recheck"
        else "未执行"
    )
    confirmation = (
        "等待回应"
        if runtime_status == "awaiting_confirmation"
        else "阻断未解除"
        if runtime_status == "blocked_waiting"
        else _runtime_label(workspace)
    )
    return f"""<section class="decision-stage-rail" aria-label="计划状态链">
      <div class="stage-node done"><small>{escape(generated)}</small><strong>盘后计划</strong><em>已形成条件计划</em></div>
      <div class="stage-node {'done' if stage == 'morning_recheck' else 'pending'}"><small>{escape(morning)}</small><strong>晨间复核</strong><em>仅检查现有来源时效</em></div>
      <div class="stage-node current"><small>当前</small><strong>人工确认</strong><em>{escape(confirmation)}</em></div>
      <div class="stage-node blocked"><small>条件满足后</small><strong>手动执行</strong><em>系统不下单</em></div>
      <div class="stage-node pending"><small>T+1 / 5 / 20</small><strong>后验复盘</strong><em>等待样本成熟</em></div>
    </section>"""


def _decision_conclusion(workspace: Mapping[str, object]) -> str:
    evidence = _mapping(workspace.get("decision_evidence"))
    conclusion = _mapping(evidence.get("conclusion"))
    reasons = _dict_rows(conclusion.get("top_reasons"))
    reason_html = "".join(
        '<article class="conclusion-reason">'
        f"<strong>{escape(str(item.get('claim') or '证据主张缺失'))}</strong>"
        f"<small>{escape(str(item.get('plan_impact') or '未声明对计划的影响'))}</small>"
        "</article>"
        for item in reasons
    )
    if not reason_html:
        reason_html = (
            '<article class="conclusion-reason blocked"><strong>决策证据未闭环</strong>'
            "<small>保持等待，不新增风险；请先修复证据来源。</small></article>"
        )
    counter = _string_rows(conclusion.get("counter_evidence"))
    invalidation = _string_rows(conclusion.get("invalidation"))
    disclosure_rows = "".join(
        f"<li>{escape(item)}</li>" for item in [*counter[:2], *invalidation[:2]]
    )
    return f"""<section class="decision-conclusion">
      <div class="conclusion-main">
        <span>今日大结论 · {escape(str(conclusion.get("confidence") or "unknown"))}置信度</span>
        <h2>{escape(str(conclusion.get("overall_stance") or "等待确认"))}</h2>
        <p>{escape(str(conclusion.get("headline") or "尚未形成可授权结论。"))}</p>
      </div>
      <div class="conclusion-style">
        <div><small>科技</small><strong>{escape(str(conclusion.get("technology_stance") or "证据不足"))}</strong></div>
        <div><small>红利</small><strong>{escape(str(conclusion.get("dividend_stance") or "证据不足"))}</strong></div>
      </div>
      <div class="conclusion-reasons">{reason_html}</div>
      <details class="conclusion-invalid">
        <summary>查看反证与结论失效条件</summary>
        <ul>{disclosure_rows or "<li>未提供可验证的失效条件。</li>"}</ul>
      </details>
    </section>"""


def _action_command(
    plan: Mapping[str, object],
    workspace: Mapping[str, object],
) -> str:
    plan_id = str(plan.get("plan_id") or "plan-0")
    version = str(plan.get("plan_version") or "unknown")
    status = str(plan.get("status") or "blocked")
    response = str(plan.get("user_response_status") or "pending")
    name = str(plan.get("name") or plan.get("symbol") or "未命名持仓")
    symbol = str(plan.get("symbol") or "")
    target = name if not symbol or symbol in name else f"{name} {symbol}"
    current_action = str(
        plan.get("current_action") or plan.get("then_action") or "保持原计划"
    )
    next_event = str(
        plan.get("current_next_event")
        or plan.get("next_event")
        or plan.get("if_condition")
        or "等待条件明确"
    )
    acknowledged_block = (
        status == "blocked" and response == "blocked_acknowledged"
    )
    if status == "blocked":
        if acknowledged_block:
            primary_button = (
                '<button class="btn action-primary decision" type="button" disabled>'
                "已知悉，等待数据恢复</button>"
            )
            authority_note = "阻断仍然有效；下一事件发生或数据恢复后才会生成新版本。"
        else:
            primary_button = (
                '<button class="btn action-primary decision" type="button" '
                'data-plan-response="blocked_acknowledged">确认已知悉阻断</button>'
            )
            authority_note = "阻断确认仅记录已知悉；不会进入有效计划或盘中监控。"
    elif status == "voided":
        primary_button = (
            '<button class="btn action-primary decision" type="button" '
            'data-plan-response="rejected">确认作废旧计划</button>'
        )
        authority_note = "作废确认只关闭旧版本，不生成新的执行授权。"
    elif status == "unchanged":
        primary_button = (
            '<button class="btn action-primary decision" type="button" '
            'data-plan-response="accepted">确认沿用</button>'
        )
        authority_note = "确认仅写入本地计划版本；真实交易仍需手动执行。"
    else:
        primary_button = (
            '<button class="btn action-primary decision" type="button" '
            'data-plan-response="accepted">加入今日执行清单</button>'
        )
        authority_note = "确认仅写入本地计划版本；真实交易仍需手动执行。"
    tone = "risk" if status in {"blocked", "voided"} else "watch" if status == "pending" else "act"
    headline = f"继续等待：{current_action}" if acknowledged_block else current_action
    command_label = "当前首要状态" if status == "blocked" else "当前唯一动作"
    response_more = (
        '<div class="action-version-audit compact">'
        f"<p>{escape(authority_note)} 当前版本 {escape(version)}。</p></div>"
        if acknowledged_block
        else f"""
    <details class="action-response-more">
      <summary>更多回应</summary>
      <input class="input action-note" type="text" maxlength="240" data-response-note placeholder="补充说明（可选）">
      <div class="action-secondary">
        <button type="button" data-plan-response="disputed">提出异议</button>
        <button type="button" data-plan-response="rejected">确认作废</button>
        <button type="button" data-plan-response="deferred">稍后</button>
      </div>
      <div class="action-version-audit">
        {_plan_change_display(workspace, plan)}
        <p>{escape(authority_note)}</p>
      </div>
    </details>"""
    )
    return f"""
<section class="action-command {tone}" data-plan-id="{escape(plan_id)}" data-plan-version="{escape(version)}">
  <div class="action-command-copy">
    <span class="action-status">{escape(command_label)} · {escape(_plan_status(status))} · <span data-response-label>{escape(_response_label(response))}</span></span>
    <h2>{escape(headline)}</h2>
    <p>{escape(target)} · 当前未获得执行授权；下一事件：{escape(next_event)}</p>
  </div>
  <div class="action-command-controls">
    {primary_button}
    <button class="btn action-link" type="button" data-open-evidence>查看授权链</button>
    {response_more}
  </div>
</section>"""


def _authority_chain(
    workspace: Mapping[str, object],
    plan: Mapping[str, object] | None,
    gate: Mapping[str, object],
    health: list[dict[str, object]],
    a_share: Mapping[str, object],
) -> str:
    summary = _mapping(workspace.get("portfolio_summary"))
    reasons = _string_rows(plan.get("change_reasons")) if plan else []
    blocked_sources = sum(
        item.get("status") in {"missing", "blocked", "failed", "stale"}
        for item in health
    )
    plan_name = (
        str(plan.get("name") or plan.get("symbol") or "未映射持仓")
        if plan
        else "没有待处理计划"
    )
    plan_state = (
        str(plan.get("current_action") or plan.get("then_action") or "保持原计划")
        if plan
        else "继续沿用已确认计划"
    )
    market_state = (
        f"{a_share.get('label') or 'A股科技'} {_theme_state(a_share)}"
        if a_share
        else "本地确认不可用"
    )
    known_exposure = _value(summary.get("known_exposure_pct"), suffix="%")
    ready = str(summary.get("decision_ready_holdings") or 0)
    total = str(summary.get("holding_count") or len(_dict_rows(workspace.get("portfolio_positions"))))
    items = (
        ("信息变化", f"{len(reasons)} 项计划变化，{blocked_sources} 项来源受限", "green"),
        ("今日环境", f"{gate.get('permission') or '等待确认'} / {market_state}", "blue"),
        ("持仓映射", f"{plan_name} / {plan_state}", "cyan"),
        ("组合预算", f"已知仓位 {known_exposure} / 严格就绪 {ready}/{total}", "amber"),
    )
    html = "".join(
        f'<button class="authority-step {tone}" type="button" data-open-evidence>'
        f"<span><b>{escape(title)}</b><small>{escape(value)}</small></span>"
        "</button>"
        for title, value, tone in items
    )
    return f'<section class="authority-chain-new" aria-label="授权因果链">{html}</section>'


def _holding_impact_strip(workspace: Mapping[str, object]) -> str:
    positions = _dict_rows(workspace.get("portfolio_positions"))
    impact_rows: list[str] = []
    for item in positions[:4]:
        raw_status = str(
            item.get("today_status") or item.get("next_condition") or "等待计划"
        )
        status = (
            _plan_status(raw_status)
            if raw_status in {"ready", "pending", "blocked", "voided", "unchanged"}
            else raw_status
        )
        impact_rows.append(
            '<button class="holding-impact" type="button" data-view-link="portfolio">'
            f'<span>{escape(str(item.get("symbol") or "--"))}</span><div>'
            f'<b>{escape(str(item.get("name") or item.get("symbol") or "未命名持仓"))}</b>'
            f"<small>{escape(status)}</small></div></button>"
        )
    items = "".join(impact_rows)
    if not items:
        items = '<div class="holding-impact empty">没有可用持仓；请通过受控导入流程更新。</div>'
    return (
        '<section class="holding-impact-strip"><h3>持仓影响速览</h3>'
        f'<div class="holding-impact-list">{items}</div></section>'
    )


def _evidence_delta_panel(
    workspace: Mapping[str, object],
    plan: Mapping[str, object] | None,
) -> str:
    evidence = _mapping(workspace.get("decision_evidence"))
    all_items = _dict_rows(evidence.get("items"))
    refs = set(_string_rows(plan.get("evidence_refs"))) if plan else set()
    items = [
        item
        for item in all_items
        if not refs or str(item.get("evidence_id") or "") in refs
    ]
    rows: list[str] = []
    for item in items[:3]:
        status = str(item.get("freshness") or "unknown")
        tone = "negative" if status in {"missing", "blocked", "failed", "stale"} else "positive"
        claim = str(item.get("claim") or "未提供证据主张")
        impact = str(item.get("plan_impact") or "未声明对计划的影响")
        rows.append(
            f'<article class="evidence-delta {tone}"><span class="delta-kind">'
            f"{'受限' if tone == 'negative' else '证据'}</span><div>"
            f"<strong>{escape(claim)}</strong>"
            f"<small>{escape(impact)}<br>来源：{escape(str(item.get('source_ref') or 'unknown'))}"
            f" · {escape(str(item.get('source_time') or '时间未知'))}</small></div>"
            f'<em>{escape(status)}</em></article>'
        )
    if not rows:
        rows.append(
            '<article class="evidence-delta neutral"><span class="delta-kind">无变化</span>'
            "<div><strong>没有记录新的计划变化原因</strong>"
            "<small>没有变化时不制造行动。</small></div><em>unknown</em></article>"
        )
    change_label = "；".join(
        str(item.get("change") or "")
        for item in items[:2]
        if str(item.get("change") or "").strip()
    ) or "没有新增变化"
    return f"""<section class="evidence-command-panel">
      <header><div><h3>为什么今天这样做</h3><span>相对上一版本：{escape(change_label)}</span></div>
      <button class="btn small" type="button" data-open-evidence>查看全部证据链</button></header>
      <div class="evidence-delta-list">{''.join(rows)}</div>
    </section>"""


def _risk_exit_panel(
    workspace: Mapping[str, object],
    plan: Mapping[str, object] | None,
) -> str:
    gate = _mapping(workspace.get("market_gate"))
    summary = _mapping(workspace.get("portfolio_summary"))
    status = str(plan.get("status") or "blocked") if plan else "blocked"
    constraints = _string_rows(plan.get("risk_constraints")) if plan else []
    invalid = str(plan.get("invalid_condition") or "风险线被触发") if plan else "等待新计划"
    until = str(plan.get("until_condition") or "下一次有效复核") if plan else "下一次有效复核"
    next_event = str(plan.get("if_condition") or "等待条件明确") if plan else "等待新的计划变化"
    risk_score = gate.get("risk_score")
    risk_width = max(0, min(100, int(risk_score))) if isinstance(risk_score, (int, float)) else 0
    readiness = (
        f"{summary.get('decision_ready_holdings') or 0}/"
        f"{summary.get('holding_count') or len(_dict_rows(workspace.get('portfolio_positions')))}"
    )
    constraint_html = "".join(
        f"<li>{escape(item)}</li>" for item in constraints[:3]
    ) or "<li>没有可核验的执行后压力模型；保持 unknown。</li>"
    confirmation = "阻断，不能采纳为可执行计划" if status == "blocked" else "等待人工确认"
    return f"""<section class="risk-exit-panel">
      <header><h3>行动后风险与退出</h3><span class="status {_status_class(status)}">{escape(_plan_status(status))}</span></header>
      <div class="risk-what-if">
        <span>当前可核验风险</span>
        <div class="risk-facts">
          <div><small>市场风险分</small><strong>{escape(str(risk_score)) if risk_score is not None else "unknown"}</strong></div>
          <div><small>严格就绪</small><strong>{escape(readiness)}</strong></div>
          <div><small>执行后压力</small><strong>unknown</strong></div>
        </div>
        <div class="budget-track"><span style="width:{risk_width}%"></span></div>
      </div>
      <div class="exit-conditions"><span>退出 / 失效条件</span><div>
        <p><b>INVALID</b>{escape(invalid)}</p>
        <p><b>UNTIL</b>{escape(until)}</p>
      </div></div>
      <ul class="risk-constraints">{constraint_html}</ul>
      <div class="risk-next"><div><b>下一步所需事件</b><small>{escape(next_event)}</small></div>
      <div class="confirm-state {'blocked' if status == 'blocked' else 'pending'}"><b>{escape(confirmation)}</b><small>InsightRadar 不执行交易。</small></div></div>
    </section>"""


def _decision_trust_summary(workspace: Mapping[str, object]) -> str:
    outcome = _mapping(workspace.get("outcome_summary"))
    horizons = _mapping(outcome.get("horizons"))
    matured_decisions = int(_mapping(horizons.get("20d")).get("matured") or 0)
    tracked = int(outcome.get("tracked_signals") or 0)
    evidence = (
        "稳定证据"
        if matured_decisions >= 60
        else "初步证据"
        if matured_decisions >= 20
        else f"样本不足 {matured_decisions}/20"
    )
    return f"""<button class="decision-trust-summary" type="button" data-view-link="review">
      <span class="trust-summary-kicker">系统近期表现 · 点时账本</span>
      <strong>系统净决策价值 <b>unknown</b></strong>
      <span>回撤变化 unknown</span>
      <span>{escape(evidence)} · 跟踪 {tracked}</span>
      <em>打开复盘账本</em>
    </button>"""


def _plan_card(
    plan: Mapping[str, object],
    index: int,
    workspace: Mapping[str, object],
) -> str:
    plan_id = str(plan.get("plan_id") or f"plan-{index}")
    version = str(plan.get("plan_version") or "unknown")
    status = str(plan.get("status") or "blocked")
    response = str(plan.get("user_response_status") or "pending")
    reasons = _string_rows(plan.get("change_reasons"))
    why = "；".join(reasons) or "没有记录变化原因。"
    change_display = _plan_change_display(workspace, plan)
    name = str(plan.get("name") or plan.get("symbol") or "未命名持仓")
    symbol = str(plan.get("symbol") or "")
    generated_time = _clock(plan.get("created_at"))
    if index > 0:
        acknowledged_block = (
            status == "blocked" and response == "blocked_acknowledged"
        )
        if acknowledged_block:
            primary = (
                '<button class="btn decision" type="button" disabled>'
                "已知悉，仍需等待</button>"
            )
        else:
            primary_response = "blocked_acknowledged" if status == "blocked" else "accepted"
            primary_label = (
                "确认已知悉阻断"
                if status == "blocked"
                else "确认作废"
                if status == "voided"
                else "确认沿用"
                if status == "unchanged"
                else "采纳计划"
            )
            primary = (
                f'<button class="btn decision" type="button" '
                f'data-plan-response="{primary_response}">{primary_label}</button>'
            )
        return f"""
<article class="queue-item" data-plan-id="{escape(plan_id)}" data-plan-version="{escape(version)}">
  <div class="queue-number">{index + 1:02d}</div>
  <div><span class="source {_status_class(status)}">{escape(_plan_status(status))}</span><span class="source user" data-response-label>{escape(_response_label(response))}</span><h3>{escape(name)}</h3><small>{escape(symbol)} · {escape(version)}</small></div>
  <div><p><strong>{escape(str(plan.get("current_action") or plan.get("then_action") or "保持原计划"))}</strong></p><p>状态变化：{escape(why)}</p><p>下一条件：{escape(str(plan.get("current_next_event") or plan.get("next_event") or plan.get("if_condition") or "等待条件明确"))}</p></div>
  <div class="queue-actions">{primary}<button class="btn ghost" type="button" data-toggle-plan>查看依据</button></div>
  <div class="queue-detail" hidden>
    <div class="rules"><div class="rule-item"><b>IF · 触发</b><span>{escape(str(plan.get("if_condition") or "等待条件明确"))}</span></div><div class="rule-item"><b>THEN · 动作</b><span>{escape(str(plan.get("then_action") or "保持原计划"))}</span></div><div class="rule-item"><b>UNTIL · 有效期</b><span>{escape(str(plan.get("until_condition") or "下一次有效复核"))}</span></div><div class="rule-item invalid"><b>INVALID · 失效</b><span>{escape(str(plan.get("invalid_condition") or "风险线被触发"))}</span></div></div>
    {_response_controls(plan, compact=True)}
  </div>
</article>"""
    return f"""
<article class="panel change-card" data-plan-id="{escape(plan_id)}" data-plan-version="{escape(version)}">
  <div class="change-title"><div><div class="eyebrow">优先处理 01 · {escape(name)}</div><h2>{escape(str(plan.get("current_action") or plan.get("then_action") or "保持原计划"))}</h2></div><span class="change-type {_status_class(status)}">{escape(_plan_status(status))}</span></div>
  {change_display}
  <div class="reason-box {'danger' if status in {'blocked', 'voided'} else ''}"><strong>为什么变化：</strong> {escape(why)}</div>
  <div class="provenance">
    <div class="prov"><small>行情与指标</small><strong><span class="source rule">规则计算</span> {escape(generated_time)}</strong></div>
    <div class="prov"><small>市场约束</small><strong><span class="source rule">规则计算</span> {escape(generated_time)}</strong></div>
    <div class="prov"><small>非结构化说明</small><strong><span class="source ai">AI未使用</span></strong></div>
    <div class="prov"><small>有效计划</small><strong><span class="source user" data-response-label>{escape(_response_label(response))}</span></strong></div>
  </div>
  <div class="rules">
    <div class="rule-item"><b>IF · 触发</b><span>{escape(str(plan.get("if_condition") or "等待条件明确"))}</span></div>
    <div class="rule-item"><b>THEN · 动作</b><span>{escape(str(plan.get("then_action") or "保持原计划"))}</span></div>
    <div class="rule-item"><b>UNTIL · 有效期</b><span>{escape(str(plan.get("until_condition") or "下一次有效复核"))}</span></div>
    <div class="rule-item invalid"><b>INVALID · 失效</b><span>{escape(str(plan.get("invalid_condition") or "风险线被触发"))}</span></div>
  </div>
  <div class="card-footer"><div class="evidence-row"><span>新证据 {len(reasons)} 项</span><span>规则 {escape(version)}</span><span>AI调用：未使用</span><button class="btn ghost small" type="button" data-open-evidence>查看完整变化链</button></div>
  {_response_controls(plan)}
</div>
</article>"""


def _response_controls(
    plan: Mapping[str, object],
    *,
    compact: bool = False,
) -> str:
    blocked = plan.get("status") == "blocked"
    acknowledged = (
        blocked and plan.get("user_response_status") == "blocked_acknowledged"
    )
    if acknowledged:
        return """<div class="response-box compact">
    <div class="prototype-note">已记录“知悉阻断”，但阻断仍未解除。当前合规动作是继续等待数据恢复或下一事件。</div>
  </div>"""
    primary = (
        '<button type="button" class="btn primary decision" '
        'data-plan-response="blocked_acknowledged">确认已知悉阻断</button>'
        if blocked
        else '<button type="button" class="btn primary decision" '
        'data-plan-response="accepted">采纳为今日计划</button>'
    )
    blocked_note = (
        '<div class="prototype-note">阻断确认仅记录已知悉；不会进入有效计划或盘中监控。'
        "数据恢复并重新生成计划版本后才允许采纳。</div>"
        if blocked
        else ""
    )
    return f"""<div class="response-box {'compact' if compact else ''}">
    <label>补充说明（可选）<input class="input" type="text" maxlength="240" data-response-note value="{escape(str(plan.get("user_response_note") or ""))}"></label>
    <div class="card-actions">
      {primary}
      <button type="button" class="btn decision" data-plan-response="disputed">提出异议</button>
      <button type="button" class="btn danger decision" data-plan-response="rejected">{'作废旧计划' if blocked else '确认作废'}</button>
      <button type="button" class="btn ghost decision" data-plan-response="deferred">稍后</button>
    </div>
    {blocked_note}
  </div>"""


def _risk_card(workspace: Mapping[str, object]) -> str:
    gate = _mapping(workspace.get("market_gate"))
    summary = _mapping(workspace.get("portfolio_summary"))
    positions = _dict_rows(workspace.get("portfolio_positions"))
    unknown_beta = sum(
        str(item.get("beta_classification") or "unknown") == "unknown"
        for item in positions
    )
    unknown_weight = sum(item.get("weight_pct") is None for item in positions)
    score = gate.get("risk_score")
    score_width = max(0, min(100, int(score))) if isinstance(score, (int, float)) else 0
    return f"""<section class="panel risk-meter">
      <div class="metric-title"><span class="eyebrow">组合风险许可</span><strong>{escape(str(gate.get("permission") or "等待确认"))}</strong></div>
      <div class="bar"><span style="width:{score_width}%"></span></div>
      <div class="risk-list">
        <div class="risk-row danger"><span>风险分</span><strong>{escape(str(score)) if score is not None else "unknown"}</strong></div>
        <div class="risk-row danger"><span>Beta未知</span><strong>{unknown_beta} 只</strong></div>
        <div class="risk-row warn"><span>权重未知</span><strong>{unknown_weight} 只</strong></div>
        <div class="risk-row"><span>严格就绪</span><strong>{escape(str(summary.get("decision_ready_holdings") or 0))} / {len(positions)}</strong></div>
      </div>
      <button class="btn small" type="button" data-view-link="portfolio">打开组合风险</button>
    </section>"""


def _handoff_card(workspace: Mapping[str, object]) -> str:
    handoffs = _dict_rows(workspace.get("monitor_handoffs"))
    item = handoffs[0] if handoffs else {}
    runtime = _mapping(workspace.get("intraday_radar"))
    runtime_status = str(runtime.get("status") or "missing")
    authority = str(runtime.get("decision_authority") or "none")
    next_check = _intraday_next_check_label(runtime)
    return f"""<section class="panel handoff">
      <div class="eyebrow">盘中监控交接</div>
      <strong id="handoffState">点时雷达：{escape(runtime_status)}</strong>
      <p id="handoffCopy">{escape(str(item.get("reason") or "分钟轮询已接入本地归档；没有有效计划时仍可保持等待。"))}</p>
      <div class="risk-list">
        <div class="risk-row"><span>最后 source_time</span><strong>{escape(str(runtime.get('source_time') or 'unknown'))}</strong></div>
        <div class="risk-row"><span>最后 fetch_time</span><strong>{escape(str(runtime.get('fetch_time') or 'unknown'))}</strong></div>
        <div class="risk-row"><span>下一次检查</span><strong>{escape(next_check)}</strong></div>
        <div class="risk-row"><span>当前权限</span><strong>{escape(authority)}</strong></div>
      </div>
      <div class="prototype-note">IR-002 固定 shadow_only；状态机记录 activated / escalated / resolved / invalidation，不授予交易建议权限。</div>
    </section>"""


def _data_health_card(workspace: Mapping[str, object]) -> str:
    rows = _dict_rows(workspace.get("data_health"))
    items = "".join(
        f'<div class="risk-row"><span>{escape(str(item.get("label") or item.get("id") or "数据源"))}</span>'
        f'<strong class="{_status_class(item.get("status"))}-text">{escape(str(item.get("status") or "missing"))}</strong></div>'
        for item in rows[:4]
    )
    blocked = sum(
        item.get("status") in {"missing", "blocked", "failed"} for item in rows
    )
    return f"""<section class="panel data-health">
      <div class="eyebrow">数据健康</div>
      <h3>{blocked} 项阻塞不应被隐藏</h3>
      <div class="risk-list">{items}</div>
      <button class="btn small" type="button" data-open-data>查看数据状态</button>
    </section>"""


def _intraday_today_panel(workspace: Mapping[str, object]) -> str:
    runtime = _mapping(workspace.get("intraday_radar"))
    snapshot = _mapping(runtime.get("latest_snapshot"))
    progress_panel = _intraday_progress_panel(runtime)
    if not snapshot:
        next_check = _intraday_next_check_label(runtime)
        return progress_panel + f"""<section class="panel section">
          <div class="section-head"><div><div class="eyebrow">盘前 / 盘中 P0</div><h2>今日雷达尚无点时快照</h2>
          <p>source_time {escape(str(runtime.get('source_time') or 'unknown'))} · fetch_time {escape(str(runtime.get('fetch_time') or 'unknown'))} · next {escape(next_check)}</p></div>
          <span class="status blocked">{escape(str(runtime.get('freshness_status') or 'missing'))}</span></div>
          <div class="risk-list">
            <div class="risk-row"><span>data_status</span><strong>{escape(str(runtime.get('data_status') or 'missing'))}</strong></div>
            <div class="risk-row"><span>analysis / decision / trade</span><strong>{escape(str(runtime.get('analysis_authority') or 'none'))} / {escape(str(runtime.get('decision_authority') or 'blocked'))} / {escape(str(runtime.get('trade_authority') or 'none'))}</strong></div>
            <div class="risk-row"><span>状态事件</span><strong>暂无状态事件</strong></div>
          </div>
          <p class="prototype-note">没有新鲜点时数据时只显示缺口或历史状态，不输出 live ready。</p>
        </section>"""
    exposures = _mapping(snapshot.get("exposure_by_theme"))
    technology_theme_ids = (
        "ai_hardware_semiconductor", "communication_cpo", "pcb",
        "ai_software_apps", "robot", "data_compute",
    )
    technology = (
        sum(float(exposures.get(theme_id) or 0) for theme_id in technology_theme_ids)
        if snapshot.get("portfolio_value") is not None
        and all(
            exposures.get(theme_id) is not None
            for theme_id in technology_theme_ids
            if theme_id in exposures
        )
        else None
    )
    alerts = _dict_rows(runtime.get("timeline"))[-6:]
    next_check = _intraday_next_check_label(runtime)
    alert_rows = "".join(
        '<div class="risk-row">'
        f'<span>{escape(str(item.get("timestamp") or "unknown"))[11:16]} · '
        f'{escape(str(item.get("title") or item.get("type") or "盘中状态"))}</span>'
        f'<strong class="{_severity_class(item.get("severity"))}">'
        f'{escape(str(item.get("event_state") or "activated"))} / {escape(str(item.get("severity") or "info"))}</strong></div>'
        for item in alerts
    ) or '<div class="risk-row"><span>暂无状态事件</span><strong>继续等待</strong></div>'
    return progress_panel + f"""<section class="panel section intraday-primary">
      <div class="section-head"><div><div class="eyebrow">盘前 / 盘中主工作台</div><h2>账户风险与主题结构</h2>
      <p>source_time {escape(str(runtime.get('source_time') or snapshot.get('timestamp') or 'unknown'))} · fetch_time {escape(str(runtime.get('fetch_time') or 'unknown'))} · next {escape(next_check)}</p></div>
      <span class="status {_status_class(runtime.get('status'))}">{escape(str(runtime.get('status') or 'unknown'))}</span></div>
      <div class="metrics">
        <div class="metric"><small>账户当日盈亏</small><strong>{_value(snapshot.get('account_daily_pnl'))}</strong><em>unknown 不按 0</em></div>
        <div class="metric"><small>早盘利润峰值</small><strong>{_value(snapshot.get('account_peak_daily_pnl'))}</strong><em>点时累计</em></div>
        <div class="metric"><small>利润回吐</small><strong>{_ratio(snapshot.get('pnl_giveback_ratio'))}</strong><em>保护预算输入</em></div>
        <div class="metric"><small>科技主题集中</small><strong>{_value(technology, suffix='%')}</strong><em>已知点时市值；缺失不按 0</em></div>
        <div class="metric"><small>数据 / 新鲜度 / 权限</small><strong>{escape(str(runtime.get('data_status') or 'unknown'))} / {escape(str(runtime.get('freshness_status') or 'unknown'))}</strong><em>{escape(str(runtime.get('analysis_authority') or 'none'))} / {escape(str(runtime.get('decision_authority') or 'blocked'))} / trade {escape(str(runtime.get('trade_authority') or 'none'))}</em></div>
      </div>
      <div class="risk-list">{alert_rows}</div>
      <p class="prototype-note">盘后计划、数据健康、证据链与版本账本继续保留在本页下方，作为解释和审计能力。</p>
    </section>"""


def _intraday_portfolio_panel(workspace: Mapping[str, object]) -> str:
    runtime = _mapping(workspace.get("intraday_radar"))
    snapshot = _mapping(runtime.get("latest_snapshot"))
    exposures = _mapping(snapshot.get("exposure_by_theme"))
    exposure_rows = "".join(
        f'<div class="risk-row"><span>{escape(str(theme_id))}</span><strong>{_value(value, suffix="%")}</strong></div>'
        for theme_id, value in sorted(exposures.items(), key=lambda item: float(item[1] or 0), reverse=True)[:8]
    )
    holdings = _dict_rows(snapshot.get("holding_snapshots")) or _dict_rows(
        workspace.get("portfolio_positions")
    )
    holding_options = "".join(
        f'<option value="{escape(str(item.get("symbol") or ""))}" data-theme="{escape(str(item.get("primary_theme_id") or "unknown"))}">'
        f'{escape(str(item.get("symbol") or "unknown"))} · {escape(str(item.get("name") or ""))}</option>'
        for item in holdings
    )
    stale = sum(
        str(item.get("status")) != "fresh"
        for item in _dict_rows(snapshot.get("quote_freshness"))
    )
    freshness = str(runtime.get("freshness_status") or "unknown")
    authority = str(runtime.get("decision_authority") or "none")
    return f"""<section class="panel section intraday-primary">
      <div class="section-head"><div><div class="eyebrow">点时持仓风险</div><h2>主题集中、利润回吐与行情新鲜度</h2></div>
      <span class="status {_status_class(freshness)}">{escape(freshness)} · {escape(authority)} · {stale} 项不新鲜</span></div>
      <div class="metrics">
        <div class="metric"><small>点时组合市值</small><strong>{_value(snapshot.get('portfolio_value'))}</strong></div>
        <div class="metric"><small>持仓快照</small><strong>{len(holdings)}</strong></div>
        <div class="metric"><small>利润回吐</small><strong>{_ratio(snapshot.get('pnl_giveback_ratio'))}</strong></div>
      </div><div class="risk-list">{exposure_rows}</div>
      <details class="response-box execution-ledger"><summary>记录已由用户确认的成交</summary>
        <form id="executionForm" class="form-grid">
          <label>标的<select class="select" id="executionSymbol" required>{holding_options}</select></label>
          <label>主题<input class="input" id="executionTarget" required placeholder="theme_id"></label>
          <label>方向<select class="select" id="executionSide"><option value="sell">sell</option><option value="buy">buy / 接回</option></select></label>
          <label>成交数量<input class="input" id="executionQuantity" type="number" min="0.01" step="0.01" required></label>
          <label>成交前可用数量<input class="input" id="executionAvailable" type="number" min="0" step="0.01" required></label>
          <label>原减仓时间<input class="input" id="executionSoldAt" type="datetime-local" required></label>
          <label>原减仓价格<input class="input" id="executionSalePrice" type="number" min="0.0001" step="0.0001" required></label>
          <label>引用原 sell（接回必填）<select class="select" id="executionReference"><option value="">sell 时留空；buy 时选择真实 sell</option></select></label>
          <label>本次成交时间（接回必填）<input class="input" id="executionExecutedAt" type="datetime-local"></label>
          <label>本次成交价格（接回必填）<input class="input" id="executionPrice" type="number" min="0.0001" step="0.0001"></label>
          <label>证据来源<input class="input" id="executionSource" value="user_confirmed_broker_execution" required></label>
          <label><input id="executionConfirmed" type="checkbox" required> 我确认这是已发生的真实成交，不是计划或模拟</label>
          <button class="btn primary" type="submit">追加到 execution ledger</button>
        </form>
        <p id="executionStatus" class="prototype-note">只追加用户确认事实；不下单，不把缺失数量改成 0。</p>
        <form id="reentryConfirmationForm" class="form-grid">
          <label>真实接回失败 observation<select class="select" id="failedReentryExecution" required><option value="">等待市场 observation 自动形成 failure event</option></select></label>
          <label>确认来源<input class="input" id="reentryConfirmationSource" value="user_confirmed_reentry_override" required></label>
          <label><input id="reentryOverrideConfirmed" type="checkbox" required> 第一次接回已失败并再创新低；我显式确认解除第二次接回复核锁</label>
          <button class="btn" type="submit">追加第二次接回复核确认</button>
        </form>
        <p id="reentryConfirmationStatus" class="prototype-note">确认事件必须引用已发生的第一次 buy，且晚于再创新低；它只解除人工复核锁，不自动买入。</p>
      </details>
    </section>"""


def _intraday_progress_panel(runtime: Mapping[str, object]) -> str:
    progress = _mapping(runtime.get("refresh_progress"))
    phase = str(progress.get("phase") or "waiting")
    provider = str(progress.get("provider") or "session")
    route = str(progress.get("route_display") or "自动/未知")
    trade_date = str(runtime.get("runtime_trade_date") or runtime.get("trade_date") or "unknown")
    route_rows = "".join(
        '<div class="risk-row">'
        f'<span>{escape(str(item.get("provider_id") or "unknown"))}</span>'
        f'<strong>{escape(str(item.get("display_route") or "自动/未知"))} · '
        f'{escape(str(item.get("transport") or "unknown"))} · '
        f'{escape(str(item.get("route_scope") or "unknown"))} · '
        f'TUN 绕过保证 {"是" if item.get("os_tun_bypass_guaranteed") is True else "否/未知"}</strong>'
        '</div>'
        for item in _dict_rows(runtime.get("network_routes"))
    )
    if not route_rows:
        route_rows = (
            '<div class="risk-row"><span>provider diagnostics</span>'
            '<strong>自动/未知</strong></div>'
        )
    return f"""<section class="panel section intraday-progress" id="intradayProgress">
      <div class="section-head"><div><div class="eyebrow">后台真实刷新</div><h2 id="intradayProgressPhase">{escape(phase)}</h2>
      <p id="intradaySessionSummary">{escape(str(runtime.get('session_mode') or 'resolving'))} · 行情日 {escape(trade_date)} · view {escape(str(runtime.get('view_mode') or 'unknown'))}</p></div>
      <span class="status pending" id="intradayProgressStatus">{escape(str(progress.get('status') or runtime.get('status') or 'waiting'))}</span></div>
      <div class="risk-list">
        <div class="risk-row"><span>provider / route</span><strong id="intradayProviderRoute">{escape(provider)} / {escape(route)}</strong></div>
        <div class="risk-row"><span>批次</span><strong id="intradayBatch">{escape(str(progress.get('batch') or 0))} / {escape(str(progress.get('total_batches') or 0))}</strong></div>
        <div class="risk-row"><span>处理进度</span><strong id="intradayCounts">{escape(str(progress.get('processed_symbols') or 0))} / {escape(str(progress.get('total_symbols') or 0))} · 成功 {escape(str(progress.get('succeeded_count') or 0))} · 失败 {escape(str(progress.get('failed_count') or 0))} · 缺失 {escape(str(progress.get('missing_count') or 0))}</strong></div>
        <div class="risk-row"><span>熔断 / 已用时</span><strong id="intradayCircuitElapsed">{escape(str(progress.get('circuit_state') or 'closed'))} / {escape(str(progress.get('elapsed_seconds') or 0))}s</strong></div>
        <div class="risk-row"><span>最近成功 / 下一步</span><strong id="intradayNextAction">{escape(str(progress.get('last_success_time') or '暂无'))} / {escape(str(progress.get('next_action') or '等待后台刷新'))}</strong></div>
      </div><details class="response-box"><summary>provider route diagnostics</summary>
        <div class="risk-list" id="intradayRouteDiagnostics">{route_rows}</div>
        <p class="prototype-note">国内直连仅表示应用客户端禁用系统代理；无法据此保证绕过操作系统 TUN/VPN。</p>
      </details>
    </section>"""


def _intraday_opportunity_panel(workspace: Mapping[str, object]) -> str:
    runtime = _mapping(workspace.get("intraday_radar"))
    states = _mapping(runtime.get("opportunity_states"))
    snapshot = _mapping(runtime.get("latest_snapshot"))
    themes = {
        str(item.get("theme_id")): item
        for item in _dict_rows(snapshot.get("theme_snapshots"))
    }
    candidates = [
        (theme_id, state)
        for theme_id, state in states.items()
        if str(state) in {"观察", "正在形成", "确认", "过热", "失效"}
    ]
    if not candidates:
        return """<section class="panel section"><div class="section-head"><div><div class="eyebrow">机会雷达</div>
        <h2>未出现已确认结构</h2><p>只有 VWAP、广度、同时间成交和龙头跟随同步满足后才升级；继续等待是合规分支。</p></div>
        <span class="status pending">未出现</span></div></section>"""
    cards = "".join(
        '<div class="source-card">'
        f'<small>{escape(str(theme_id))}</small><strong>{escape(str(state))}</strong>'
        f'<em>VWAP {_value(_mapping(themes.get(str(theme_id))).get("vwap_distance"), suffix="%")} · '
        f'量比 {_value(_mapping(themes.get(str(theme_id))).get("volume_ratio_same_time"))} · '
        f'广度 {_ratio(_mapping(themes.get(str(theme_id))).get("breadth_above_vwap"))}</em></div>'
        for theme_id, state in candidates
    )
    return f"""<section class="panel section intraday-primary"><div class="section-head"><div><div class="eyebrow">机会发现</div>
      <h2>相对强势候选</h2><p>确认表示结构满足，不强制推荐买入；账户利润保护线仍可否决新增风险。</p></div>
      <span class="status pending">{len(candidates)} 个候选</span></div><div class="source-grid">{cards}</div></section>"""


def _intraday_replay_panel(workspace: Mapping[str, object]) -> str:
    replay = _mapping(workspace.get("intraday_replay"))
    case = _mapping(replay.get("case"))
    backtest = _mapping(replay.get("backtest"))
    strategies = _dict_rows(backtest.get("strategies"))
    if not strategies:
        return """<section class="panel section"><div class="section-head"><div><div class="eyebrow">IR-001</div>
        <h2>离线回放尚未生成</h2><p>先完成逐分钟点时回放，再评价策略，不用样例曲线填空。</p></div>
        <span class="status blocked">missing</span></div></section>"""
    rows = "".join(
        f'<tr><td>{escape(str(item.get("label") or item.get("strategy_id")))}</td>'
        f'<td>{_value(item.get("final_return_pct"), suffix="%")}</td>'
        f'<td>{_value(item.get("max_profit_giveback"))}</td>'
        f'<td>{_value(item.get("max_drawdown_pct"), suffix="%")}</td>'
        f'<td>{escape(str(item.get("trade_count") or 0))}</td>'
        f'<td>{_value(item.get("reentry_success_rate_pct"), suffix="%")}</td>'
        f'<td>{_value(item.get("improvement_vs_full_hold"))}</td></tr>'
        for item in strategies
    )
    audit = _mapping(replay.get("no_lookahead"))
    return f"""<section class="panel section intraday-primary">
      <div class="section-head"><div><div class="eyebrow">{escape(str(case.get('case_id') or 'IR-001'))} · 逐分钟</div>
      <h2>{escape(str(case.get('title') or '盘中决策验证'))}</h2><p>实际操作改善保持 unknown，直到逐笔成交可核验。</p></div>
      <span class="status ready">点时审计 {escape(str(audit.get('status') or 'unknown'))}</span></div>
      <div class="table-wrap"><table><thead><tr><th>策略</th><th>最终收益</th><th>最大利润回吐</th><th>最大回撤</th><th>交易</th><th>接回成功率</th><th>相对持有改善</th></tr></thead><tbody>{rows}</tbody></table></div>
    </section>"""


def _severity_class(value: object) -> str:
    return {
        "red": "danger-text",
        "orange": "amber-text",
        "yellow": "amber-text",
        "info": "good-text",
    }.get(str(value), "unknown-text")


def _ratio(value: object) -> str:
    return f"{float(value) * 100:.1f}%" if isinstance(value, (int, float)) else "unknown"


def _beta_cell(item: Mapping[str, object]) -> str:
    classification = escape(str(item.get("beta_classification") or "unknown"))
    evidence = _mapping(item.get("beta_evidence"))
    beta = evidence.get("beta")
    if not isinstance(beta, (int, float)):
        reason = escape(str(evidence.get("reason") or "等待自动计算证据"))
        return f"<b>{classification}</b><small>{reason}</small>"
    r_squared = evidence.get("r_squared")
    detail = (
        f"R² {float(r_squared):.2f} · fit {evidence.get('fit_quality') or 'unknown'} · "
        f"{evidence.get('as_of') or 'unknown'} · {evidence.get('quality_status') or 'unknown'}"
    )
    return (
        f"<b>{float(beta):.2f} · {classification}</b>"
        f"<small>{escape(detail)}</small>"
    )


def _portfolio(workspace: Mapping[str, object]) -> str:
    summary = _mapping(workspace.get("portfolio_summary"))
    positions = _dict_rows(workspace.get("portfolio_positions"))
    management_plans = _dict_rows(workspace.get("portfolio_management_plans"))
    pending_management = [
        item
        for item in management_plans
        if item.get("context_status") in {"system_proposed", "stale"}
    ]
    repair_issues = _dict_rows(workspace.get("repair_issues"))
    changes = _today_plans(workspace)
    known_exposure = summary.get("known_exposure_pct")
    unknown_weight = sum(item.get("weight_pct") is None for item in positions)
    unknown_beta = sum(
        str(item.get("beta_classification") or "unknown") == "unknown"
        for item in positions
    )
    complete = sum(item.get("data_completeness") == "ready" for item in positions)
    classified = len(positions) - unknown_beta
    total = max(1, len(positions))
    rows = "".join(
        f"<tr data-name=\"{escape(str(item.get('name') or ''))} {escape(str(item.get('symbol') or ''))}\"><td><b>{escape(str(item.get('name') or item.get('symbol') or '未命名'))}</b>"
        f"<small>{escape(str(item.get('symbol') or ''))}</small></td>"
        f"<td>{_value(item.get('weight_pct'), suffix='%')}</td>"
        f"<td class=\"pnl {'up' if isinstance(item.get('pnl_pct'), (int, float)) and float(item.get('pnl_pct')) >= 0 else 'down'}\">{_value(item.get('pnl_pct'), suffix='%')}</td>"
        f"<td>{_beta_cell(item)}</td>"
        f"<td><span class='source {_status_class(item.get('data_completeness'))}'>{escape(str(item.get('data_completeness') or 'missing'))}</span></td>"
        f"<td><span class='source {_status_class(_mapping(item.get('management_plan')).get('context_status'))}'>{escape(_management_context_label(str(_mapping(item.get('management_plan')).get('context_status') or 'system_proposed')))}</span></td>"
        f"<td><strong>{escape(str(_mapping(item.get('management_plan')).get('suggestion_name') or '等待系统建议'))}</strong>"
        f"<small>下次复核：{escape(str(_mapping(item.get('management_plan')).get('next_review_time') or '下一次 after-close'))}</small></td>"
        f"<td><button class='btn small' type='button' data-open-management='{escape(str(item.get('symbol') or ''))}'>查看并确认</button></td></tr>"
        for item in positions
    )
    if not rows:
        rows = '<tr><td colspan="8">没有可用持仓；请通过受控导入流程更新。</td></tr>'
    known_width = (
        max(0, min(100, int(float(known_exposure))))
        if isinstance(known_exposure, (int, float))
        else 0
    )
    classified_width = int(classified / total * 100)
    ready_width = int(
        float(summary.get("decision_ready_holdings") or 0) / total * 100
    )
    complete_width = int(complete / total * 100)
    cash_label = _value(summary.get("cash"))
    pending_cards = "".join(
        f'<article class="management-card {"warn" if item.get("context_status") == "stale" else ""}">'
        f'<div><small>{escape(str(item.get("name") or item.get("symbol") or "持仓"))}</small>'
        f'<strong>{escape(str(item.get("suggestion_name") or "系统管理建议"))}</strong>'
        f'<p>{escape(str(item.get("stale_reason") or "系统已基于可信结构化数据生成建议，等待你的确认。"))}</p></div>'
        f'<button class="btn primary small" type="button" data-open-management="{escape(str(item.get("symbol") or ""))}">查看并确认</button></article>'
        for item in pending_management
    ) or '<div class="management-empty">当前持仓管理方案均已处理；基础风险分析始终独立运行。</div>'
    anomaly_cards = "".join(
        f'<article class="data-anomaly-card"><div><small>{escape(str(_mapping(item.get("entity")).get("name") or _mapping(item.get("entity")).get("symbol") or "核心数据链路"))}</small>'
        f'<strong>{escape(str(item.get("field_label") or item.get("field") or "核心字段"))} · {escape(str(item.get("status") or "blocked"))}</strong>'
        f'<p>{escape(str(item.get("reason") or "该字段未通过数据质量校验。"))}</p>'
        f'<p><b>字段：</b>{escape(str(item.get("field") or "unknown"))} · '
        f'<b>来源：</b>{escape(str(item.get("source") or "unknown"))}</p></div>'
        f'<button class="btn small danger" type="button" data-open-repair="{escape(str(item.get("issue_id") or ""))}">需要处理 →</button></article>'
        for item in repair_issues
    ) or '<div class="management-empty">当前没有核心数据缺口或持仓级行情隔离。</div>'
    return f"""
<section class="view" id="route-portfolio" data-route-panel="portfolio">
  {_intraday_portfolio_panel(workspace)}
  <div class="metrics">
    <div class="metric"><small>持仓数量</small><strong>{len(positions)}</strong><em>真实 portfolio.json</em></div>
    <div class="metric"><small>已知仓位</small><strong>{_value(known_exposure, suffix='%')}</strong><em>未知不按 0 处理</em></div>
    <div class="metric"><small>未知权重</small><strong class="danger-text">{unknown_weight} 只</strong><em>阻塞完整风险计算</em></div>
    <div class="metric"><small>Beta 证据不足</small><strong>{unknown_beta} 只</strong><em>历史收益率自动计算</em></div>
    <div class="metric"><small>今日必须处理</small><strong>{len(changes)}</strong><em>逐项确认</em></div>
  </div>
  <div class="portfolio-layout">
    <section class="panel section">
      <div class="section-head"><div><h2>组合风险驾驶舱</h2><p>先回答风险和数据缺口，再展示盈亏。</p></div><a class="btn" href="/portfolio-import">导入/更新持仓</a></div>
      <div class="exposure-list">
        <div class="exposure-item"><span>已知仓位</span><div class="bar"><span style="width:{known_width}%"></span></div><b>{_value(known_exposure, suffix='%')}</b></div>
        <div class="exposure-item"><span>Beta 自动分类</span><div class="bar"><span style="width:{classified_width}%"></span></div><b>{classified}/{len(positions)}</b></div>
        <div class="exposure-item"><span>数据完整</span><div class="bar"><span style="width:{complete_width}%"></span></div><b>{complete}/{len(positions)}</b></div>
        <div class="exposure-item"><span>严格就绪</span><div class="bar"><span style="width:{ready_width}%"></span></div><b>{escape(str(summary.get("decision_ready_holdings") or 0))}/{len(positions)}</b></div>
      </div>
    </section>
    <section class="panel section">
      <div class="section-head"><div><h3>风险阻塞项</h3><p>unknown 不能按 0 或正常处理。</p></div></div>
      <div class="risk-list">
        <div class="risk-row danger"><span>Beta 证据不足</span><strong>{unknown_beta} 只</strong></div>
        <div class="risk-row danger"><span>组合现金</span><strong>{escape(cash_label)}</strong></div>
        <div class="risk-row warn"><span>风险对账</span><strong>{escape(str(summary.get("risk_reconciliation_status") or "unknown"))}</strong></div>
        <div class="risk-row"><span>持仓字段完整</span><strong>{complete}/{len(positions)}</strong></div>
      </div>
    </section>
  </div>
  <section class="panel section management-section">
    <div class="section-head"><div><div class="eyebrow">A · 个性化跟踪</div><h2>持仓管理方案待确认</h2><p>系统已经生成建议；确认后用于个性化跟踪，不确认不影响基础风险分析。</p></div><span class="status pending">{len(pending_management)} 项待处理</span></div>
    <div class="management-grid">{pending_cards}</div>
  </section>
  <section class="panel section management-section data-anomaly-section">
    <div class="section-head"><div><div class="eyebrow">B · 数据质量</div><h2>核心数据缺口</h2><p>包括行情数据异常、证券映射、账户核心字段与风险对账；系统数据问题用户无需填写，确认持仓方案不会解除数据隔离。</p></div><span class="status {'blocked' if repair_issues else 'ready'}">{len(repair_issues)} 项待处理</span></div>
    <div class="management-grid">{anomaly_cards}</div>
  </section>
  <section class="panel section holdings-section">
    <div class="section-head"><div><h2>持仓与计划</h2><p>计划变化、风险状态和数据完整度优先于浮动盈亏。</p></div><div class="inline"><input id="holdingSearch" class="input" placeholder="代码或名称"/><button id="holdingFilter" class="btn" type="button">筛选</button></div></div>
    <div class="table-wrap"><table id="holdingsTable"><thead><tr><th>标的</th><th>权重</th><th>浮动盈亏</th><th>风险暴露</th><th>账户字段</th><th>管理状态</th><th>系统建议</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  </section>
</section>"""


def _research(workspace: Mapping[str, object]) -> str:
    tasks = _dict_rows(workspace.get("research_tasks"))
    health = _dict_rows(workspace.get("data_health"))
    gate = _mapping(workspace.get("market_gate"))
    evidence = "".join(
        f'<div class="evidence-item"><strong><span>{escape(str(item.get("title") or "未命名研究"))}</span>'
        f'<span class="source research">{escape(str(item.get("status") or "pending"))}</span></strong>'
        f'<p>来源：{escape(str(item.get("source") or "unknown"))}</p></div>'
        for item in tasks
    )
    if not evidence:
        evidence = '<div class="evidence-item"><strong>没有可展示的研究变化</strong><p>P0 只呈现 after-close 已有证据。</p></div>'
    source_cards = "".join(
        f'<div class="source-card"><small>{escape(str(item.get("label") or item.get("id") or "数据源"))}</small>'
        f'<strong class="{_status_class(item.get("status"))}-text">{escape(str(item.get("status") or "missing"))}</strong>'
        f'<em>{escape(str(item.get("source_time") or "时间未知"))}</em></div>'
        for item in health[:4]
    )
    unavailable = sum(
        item.get("status") in {"missing", "blocked", "failed"} for item in health
    )
    return f"""
<section class="view" id="route-lookup" data-route-panel="lookup">
  {_intraday_opportunity_panel(workspace)}
  <section class="panel section">
    <div class="section-head"><div><h2>先明确研究问题，再调用数据和 AI</h2><p>规则负责可判定状态；AI只在非结构化证据变化时归纳和解释。</p></div><span class="status blocked">P1 尚未接入研究编排</span></div>
    <form id="lookupForm" class="form-grid">
      <input class="input" id="stockCode" placeholder="代码或名称"/>
      <select class="select" id="lookupPurpose"><option>寻找介入条件</option><option>持仓诊断</option><option>异动解释</option><option>基本面研究</option></select>
      <select class="select" id="holdingState"><option>未持有</option><option>已持有</option></select>
      <select class="select" id="holdingPeriod"><option>1—5日</option><option>盘中</option><option>波段</option><option>中长期</option></select>
      <button class="btn primary" type="submit">建立研究意图</button>
    </form>
  </section>
  <div class="lookup-result">
    <section class="panel section">
      <div class="section-head"><div><div class="eyebrow" id="lookupLabel">未选择标的 · 未持有 · 1—5日</div><h2>技术结构与市场许可</h2></div><span class="source rule">真实数据边界</span></div>
      <div class="chart-empty"><strong>技术图表尚未接入此 P0 页面</strong><span>不使用原型示意线或 AI 补写行情；后续由真实 K 线、技术状态和主基准驱动。</span></div>
      <div class="metrics research-metrics">
        <div class="metric"><small>已有研究任务</small><strong>{len(tasks)}</strong></div>
        <div class="metric"><small>市场许可</small><strong>{escape(str(gate.get("permission") or "unknown"))}</strong></div>
        <div class="metric"><small>不可用来源</small><strong class="danger-text">{unavailable}</strong></div>
        <div class="metric"><small>研究编排</small><strong class="amber-text">P1</strong></div>
      </div>
      <div class="source-grid">{source_cards}</div>
    </section>
    <aside class="panel section">
      <div class="eyebrow">当前研究任务</div><h2 class="analysis-title" id="analysisTitle">寻找介入条件</h2>
      <div class="objective-banner" id="objectiveBanner">未持有，因此不输出股数、减仓比例或个性化风险预算。</div>
      <div class="tabs"><button class="tab active" type="button" data-tab="conclusion">结论</button><button class="tab" type="button" data-tab="evidence">证据</button><button class="tab" type="button" data-tab="tracking">跟踪</button></div>
      <div class="tab-panel active" id="tab-conclusion"><div class="rules single-column"><div class="rule-item"><b>当前结论</b><span>当前只建立研究意图，不生成虚构技术结论。</span></div><div class="rule-item"><b>IF</b><span>真实技术、公告、财务及主基准证据完成接入和校验。</span></div><div class="rule-item"><b>THEN</b><span>再生成结构化研究结果和下一复核条件。</span></div><div class="rule-item invalid"><b>INVALID</b><span>任一关键数据 stale、missing 或 blocked 时不得形成确定性结论。</span></div></div></div>
      <div class="tab-panel" id="tab-evidence"><div class="evidence-list">{evidence}<div class="evidence-item"><strong><span>AI 边界</span><span class="source ai">未调用</span></strong><p>AI 不修改规则结果，也不补齐未接入字段。</p></div><div class="evidence-item"><strong><span>用户条件</span><span class="source user">用户</span></strong><p id="userCondition">目的：寻找介入条件；状态：未持有；周期：1—5日。</p></div></div></div>
      <div class="tab-panel" id="tab-tracking"><div class="risk-list"><div class="risk-row"><span>下一次复核</span><strong>真实数据接入后</strong></div><div class="risk-row"><span>AI重复调用</span><strong class="good-text">证据不变则禁止</strong></div><div class="risk-row"><span>真实查询 API</span><strong class="danger-text">P1 待接入</strong></div></div></div>
    </aside>
  </div>
</section>"""


def _review(workspace: Mapping[str, object]) -> str:
    outcome = _mapping(workspace.get("outcome_summary"))
    positions = _dict_rows(workspace.get("portfolio_positions"))
    historical_unknown = [
        item
        for item in positions
        if str(item.get("historical_context_status") or "unknown") != "ready"
    ]
    historical_ready = len(positions) - len(historical_unknown)
    historical_gap_detail = "；".join(
        f"{item.get('name') or item.get('symbol') or '未命名持仓'}："
        + "、".join(_string_rows(item.get("missing_historical_context_fields")))
        for item in historical_unknown
    ) or "无"
    horizons = _mapping(outcome.get("horizons"))
    versions = _dict_rows(workspace.get("plan_version_history"))
    visible_versions = versions[-8:]
    quarantined_versions = [
        item for item in versions if item.get("evaluation_status") == "quarantined"
    ]
    for item in quarantined_versions:
        identity = (item.get("plan_id"), item.get("plan_version"))
        if not any(
            (row.get("plan_id"), row.get("plan_version")) == identity
            for row in visible_versions
        ):
            visible_versions = [item, *visible_versions[-7:]]
    responses = _dict_rows(workspace.get("user_responses"))
    response_by_plan_version = {
        (
            str(item.get("plan_id") or ""),
            str(item.get("plan_version") or ""),
        ): item
        for item in responses
    }
    rows = "".join(
        f"<tr><td>{escape(str(item.get('created_at') or 'unknown'))}</td>"
        f"<td><strong>{escape(str(item.get('symbol') or item.get('plan_id') or 'unknown'))}</strong>"
        f"<small>{escape(_version_change_label(item))}</small></td>"
        f"<td>{escape(str(item.get('then_action') or '未记录动作'))}</td>"
        f"<td>{escape(str(item.get('if_condition') or '未记录触发条件'))}</td>"
        f"<td>{escape(_response_label(str(_mapping(response_by_plan_version.get((str(item.get('plan_id') or ''), str(item.get('plan_version') or '')))).get('response') or 'pending')))}</td>"
        f"<td>{_ledger_evaluation(item)}</td></tr>"
        for item in visible_versions
    )
    if not rows:
        rows = '<tr><td colspan="6">尚无计划版本历史。</td></tr>'
    disputed = sum(item.get("response") == "disputed" for item in responses)
    matured_total = sum(
        int(_mapping(item).get("matured") or 0) for item in horizons.values()
    )
    one_day = _mapping(horizons.get("1d"))
    five_day = _mapping(horizons.get("5d"))
    twenty_day = _mapping(horizons.get("20d"))
    tracked = int(outcome.get("tracked_signals") or 0)
    matured_decisions = int(twenty_day.get("matured") or 0)
    evidence_strength = (
        "稳定证据"
        if matured_decisions >= 60
        else "初步证据"
        if matured_decisions >= 20
        else f"样本不足 {matured_decisions}/20"
    )
    data_state = "blocked"
    return f"""
<section class="view" id="route-review" data-route-panel="review">
  {_intraday_replay_panel(workspace)}
  <div class="review-inline-meta">
    <span>更新于 {escape(str(outcome.get("as_of_trade_date") or workspace.get("generated_at") or "unknown"))}</span>
    <span>跟踪 {tracked}</span><span>计划版本 {len(versions)}</span><span>口径隔离 {len(quarantined_versions)}</span><span>用户异议 {disputed}</span>
  </div>
  <section class="review-value-summary" aria-label="决策价值摘要">
    <div><small>系统净决策价值</small><strong class="unknown-text">unknown</strong><em>缺少连续系统路径与不操作分支</em></div>
    <div><small>最大回撤变化</small><strong class="unknown-text">unknown</strong><em>缺少同窗路径</em></div>
    <div><small>执行偏差</small><strong class="unknown-text">unknown</strong><em>真实成交执行流水未接入</em></div>
    <div><small>证据强度</small><strong class="amber-text">{escape(evidence_strength)}</strong><em>{matured_decisions} 个成熟决策 / {matured_total} 个成熟窗口</em></div>
    <div class="review-data-state {data_state}"><small>数据状态</small><strong>阻塞</strong><em>unknown 不按 0 处理</em></div>
  </section>
  <section class="review-comparison-panel">
    <div class="review-controls">
      <div class="review-segmented" aria-label="比较模式（数据未就绪）">
        <button class="active" type="button" data-review-mode="core" disabled aria-disabled="true">核心决策</button>
        <button type="button" data-review-mode="exposure" disabled aria-disabled="true">仓位暴露</button>
        <button type="button" data-review-mode="market" disabled aria-disabled="true">市场指数</button>
      </div>
      <div class="review-periods" aria-label="时间窗口（数据未就绪）">
        <button type="button" data-review-window="20" disabled aria-disabled="true">20日</button>
        <button class="active" type="button" data-review-window="60" disabled aria-disabled="true">60日</button>
        <button type="button" data-review-window="90" disabled aria-disabled="true">90日</button>
        <button type="button" data-review-window="250" disabled aria-disabled="true">250日</button>
      </div>
    </div>
    <div class="review-chart-head"><div class="review-legend">
      <span><i class="system"></i>系统决策路径</span>
      <span><i class="actual"></i>实际账户路径</span>
      <span><i class="baseline"></i>分段不操作基线</span>
    </div><span>仅定义，当前不可计算</span></div>
    <div class="review-chart-blocked" id="reviewComparisonState">
      <div><strong>决策价值曲线尚未可计算</strong>
      <p>当前只有计划版本、用户响应和信号后验；缺少完整目标组合、真实成交/现金路径、点时代理与分段不操作基线。</p></div>
      <ul>
        <li><span>系统决策路径</span><b>未实现完整目标组合与连续 NAV</b></li>
        <li><span>实际账户路径</span><b>真实成交、现金、费用未接入</b></li>
        <li><span>不操作基线</span><b>逐决策冻结分支尚未实现</b></li>
      </ul>
    </div>
  </section>
  <section class="review-attribution-blocked">
    <div><strong>决策贡献拆解</strong><span id="reviewAttributionWindow">当前窗口 60日</span></div>
    <div class="attribution-unknowns">
      <p><span>防守少亏</span><b>unknown</b></p><em>+</em>
      <p><span>进攻多赚</span><b>unknown</b></p><em>−</em>
      <p><span>机会错失</span><b>unknown</b></p><em>−</em>
      <p><span>交易成本</span><b>unknown</b></p><em>=</em>
      <p class="total"><span>系统净决策价值</span><b>unknown</b></p>
    </div>
    <p>缺失字段保持 unknown；现有命中率不能替代决策价值、回撤效果或执行效果。</p>
  </section>
  <section class="review-ledger-section">
    <div class="section-head"><div><h2>决策复盘账本</h2><p>计划版本、触发条件、用户响应和后验成熟度分别留痕。</p></div><span class="status pending">点时只读</span></div>
    <div class="review-table-wrap"><table class="review-table"><thead><tr>
      <th>创建时间</th><th>对象 / 版本</th><th>系统预案</th><th>触发条件</th><th>用户响应</th><th>后验状态</th>
    </tr></thead><tbody>{rows}</tbody></table></div>
  </section>
  <div class="review-evidence-grid">
    <section class="panel section">
      <div class="section-head"><div><h3>现有后验统计</h3><p>只表示信号窗口成熟度，不等于正式决策价值。</p></div><strong>{matured_total} 个成熟窗口</strong></div>
      <div class="risk-list">
        <div class="risk-row"><span>T+1 命中率</span><strong>{_rate(one_day.get("hit_rate"))}</strong></div>
        <div class="risk-row"><span>T+5 命中率</span><strong>{_rate(five_day.get("hit_rate"))}</strong></div>
        <div class="risk-row"><span>T+20 命中率</span><strong>{_rate(twenty_day.get("hit_rate"))}</strong></div>
      </div>
    </section>
    <section class="panel section">
      <div class="section-head"><div><h3>评价边界</h3><p>只有完整、点时、同窗数据才进入正式评分。</p></div></div>
      <div class="risk-list">
        <div class="risk-row"><span>规则事前声明</span><strong>{len(versions)} 条</strong></div>
        <div class="risk-row"><span>用户确认/异议留痕</span><strong>{len(responses)} 条</strong></div>
        <div class="risk-row"><span>历史买入上下文</span><strong class="{'amber-text' if historical_unknown else ''}">{historical_ready}/{len(positions)} 完整</strong></div>
        <div class="risk-row"><span>真实成交执行流水</span><strong class="danger-text">未接入</strong></div>
        <div class="risk-row"><span>决策价值路径</span><strong class="danger-text">未实现</strong></div>
      </div>
      <p class="prototype-note">历史买入逻辑或初始失效条件缺失只影响策略与执行复盘，不阻断当前风险计划。缺口：{escape(historical_gap_detail)}</p>
    </section>
  </div>
</section>"""


def _evidence_drawer(workspace: Mapping[str, object]) -> str:
    evidence = _mapping(workspace.get("decision_evidence"))
    rows = _dict_rows(evidence.get("items"))
    cards: list[str] = []
    for item in rows:
        supports = "、".join(_string_rows(item.get("supports"))) or "未绑定支持结论"
        opposes = "、".join(_string_rows(item.get("opposes"))) or "无"
        counter = "；".join(_string_rows(item.get("counter_evidence"))) or "未提供"
        gaps = "；".join(_string_rows(item.get("gaps"))) or "无"
        linked = "、".join(_string_rows(item.get("linked_plan_ids"))) or "未绑定计划"
        cards.append(
            '<article class="evidence-chain-item">'
            f'<header><span>{escape(str(item.get("scope") or "unknown"))} · '
            f'{escape(str(item.get("fact_class") or "unknown"))}</span>'
            f'<em class="source {_status_class(item.get("freshness"))}">'
            f'{escape(str(item.get("freshness") or "unknown"))}</em></header>'
            f'<h3>{escape(str(item.get("claim") or "未提供证据主张"))}</h3>'
            f'<p><b>变化：</b>{escape(str(item.get("change") or "unknown"))}</p>'
            f'<p><b>如何影响计划：</b>{escape(str(item.get("plan_impact") or "未声明"))}</p>'
            f'<p><b>支持：</b>{escape(supports)}　<b>反对：</b>{escape(opposes)}</p>'
            f'<p><b>反证：</b>{escape(counter)}</p>'
            f'<p><b>缺口：</b>{escape(gaps)}</p>'
            f'<footer>来源：{escape(str(item.get("source_ref") or "unknown"))} · '
            f'数据时间：{escape(str(item.get("source_time") or "unknown"))} · '
            f'权限：{escape(str(item.get("authority") or "unknown"))}<br>'
            f'关联计划：{escape(linked)}</footer></article>'
        )
    card_html = "".join(cards)
    if not card_html:
        card_html = _empty(
            "没有决策证据",
            "当前报告只有数据状态，不能回答为什么这样行动。",
        )
    return f"""<div class="drawer-backdrop" id="evidence-backdrop" hidden>
      <aside class="drawer evidence-drawer" id="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-drawer-title" tabindex="-1">
        <div class="drawer-head"><div><div class="eyebrow">Decision Evidence Chain</div><h2 id="evidence-drawer-title">完整决策证据链</h2></div>
        <button class="btn small" id="evidence-close" type="button" aria-label="关闭决策证据链">关闭</button></div>
        <div class="prototype-note">这里回答“事实是什么、支持或反对什么结论、为什么影响计划”；来源可用性请在“数据状态”查看。</div>
        <div class="evidence-chain">{card_html}</div>
      </aside>
    </div>"""


def _data_drawer(workspace: Mapping[str, object]) -> str:
    rows = _dict_rows(workspace.get("data_health"))
    cards = "".join(
        f'<article class="timeline-item"><small>{escape(str(item.get("label") or item.get("id") or "未命名来源"))} · '
        f'<span class="source {_status_class(item.get("status"))}">{escape(str(item.get("status") or "missing"))}</span></small>'
        f'<strong>{escape(str(item.get("gap_reason") or "来源在声明的新鲜度窗口内可用。"))}</strong>'
        f'<p>来源：{escape(str(item.get("source_name") or "unknown"))} · 数据时间：{escape(str(item.get("source_time") or "unknown"))}</p>'
        f'<p>抓取时间：{escape(str(item.get("fetched_at") or "unknown"))}</p>'
        f'<p>规则：{escape(str(item.get("freshness_rule") or "unknown"))}</p>'
        f'<p><b>修复动作：</b>{escape(str(item.get("repair_action") or "无需修复"))}</p>'
        f'<p><b>责任链：</b>{escape(str(item.get("owner") or "unknown"))} · '
        f'下次检查：{escape(str(item.get("next_check") or "unknown"))}</p></article>'
        for item in rows
    )
    if not cards:
        cards = _empty("没有数据状态记录", "当前报告缺少统一 data_health 契约。")
    return f"""<div class="drawer-backdrop" id="data-backdrop" hidden>
      <aside class="drawer" id="data-drawer" role="dialog" aria-modal="true" aria-labelledby="data-drawer-title" tabindex="-1">
        <div class="drawer-head"><div><div class="eyebrow">Source Health / Repair</div><h2 id="data-drawer-title">数据状态与降级边界</h2></div>
        <button class="btn small" id="data-status-close" type="button" aria-label="关闭数据状态">关闭</button></div>
        <div class="prototype-note">ready / stale / missing / blocked 均来自真实 payload；没有数据时不生成假值。</div>
        <div class="timeline">{cards}</div>
      </aside>
    </div>"""


def _repair_drawer(workspace: Mapping[str, object]) -> str:
    issues = _dict_rows(workspace.get("repair_issues"))
    generated_at = str(workspace.get("generated_at") or "")
    panels: list[str] = []
    for item in issues:
        issue_id = str(item.get("issue_id") or "")
        entity = _mapping(item.get("entity"))
        known_context = _mapping(item.get("known_context"))
        known_rows = "".join(
            f'<div><small>{escape(str(key))}</small><strong>{escape(_contract_value(value))}</strong></div>'
            for key, value in known_context.items()
        ) or '<div><small>已知上下文</small><strong>unknown</strong></div>'
        method = str(item.get("repair_method") or "")
        if method in {"retry_after_close", "refresh_sources"}:
            repair_action = (
                f'<button class="btn primary" type="button" data-repair-action '
                f'data-repair-issue="{escape(issue_id)}">重新检查并生成</button>'
            )
            save_action = "无需人工保存；系统重抓、校验并生成新计划版本。"
        elif method == "portfolio_import":
            repair_action = '<a class="btn primary" href="/portfolio-import">打开持仓导入</a>'
            save_action = "在持仓导入页预览差异并明确批准保存；保存后自动串行刷新。"
        else:
            repair_action = '<span class="status blocked">当前没有自动修复入口</span>'
            save_action = "保持 blocked，等待受支持的修复方式。"
        panels.append(
            f'<article class="repair-panel" data-repair-panel="{escape(issue_id)}" '
            f'data-workspace-generated-at="{escape(generated_at)}" hidden>'
            '<div class="repair-title"><div>'
            f'<small>{escape(str(entity.get("symbol") or entity.get("type") or "system"))} · '
            f'{escape(str(item.get("reason_code") or "BLOCKED"))}</small>'
            f'<h3>{escape(str(entity.get("name") or "核心数据链路"))} · '
            f'{escape(str(item.get("field_label") or item.get("field") or "核心字段"))}</h3></div>'
            f'<span class="status blocked">{escape(str(item.get("status") or "blocked"))}</span></div>'
            '<section class="repair-section"><h4>问题</h4>'
            f'<p>{escape(str(item.get("reason") or "该字段不可用。"))}</p>'
            f'<p><b>字段名称：</b>{escape(str(item.get("field") or "unknown"))} · '
            f'<b>当前值：</b>{escape(_contract_value(item.get("current_value")))}</p></section>'
            '<section class="repair-section danger"><h4>为什么阻断</h4>'
            f'<p>{escape(str(item.get("criticality_reason") or "核心字段不可使用默认值替代。"))}</p></section>'
            '<section class="repair-section"><h4>当前系统知道什么</h4>'
            '<div class="repair-known-grid">'
            f'<div><small>数据来源</small><strong>{escape(str(item.get("source") or "unknown"))}</strong></div>'
            f'<div><small>price_basis</small><strong>{escape(str(item.get("price_basis") or "unknown"))}</strong></div>'
            f'<div><small>source_time</small><strong>{escape(str(item.get("source_time") or "unknown"))}</strong></div>'
            f'<div><small>fetched_at</small><strong>{escape(str(item.get("fetched_at") or "unknown"))}</strong></div>'
            f'{known_rows}</div></section>'
            '<section class="repair-section"><h4>用户需要做什么</h4>'
            f'<p><b>修复方式：</b>{escape(str(item.get("repair_label") or "保持 blocked"))}</p>'
            f'<p><b>允许人工覆盖：</b>{"是，仅通过受控 UI" if item.get("manual_repair_allowed") is True else "否，不能用人工值覆盖 provider 状态"}</p>'
            f'<p><b>推荐/允许输入格式：</b>{escape(str(item.get("input_format") or "不适用；由系统自动获取"))}</p>'
            f'<p><b>保存动作：</b>{escape(save_action)}</p>'
            f'<p><b>修复后下一步：</b>{escape(str(item.get("next_action") or "重新生成 after-close"))}</p>'
            f'<div class="repair-actions">{repair_action}'
            '<p class="repair-feedback" data-repair-feedback></p></div></section>'
            '</article>'
        )
    body = "".join(panels) or _empty(
        "没有待修复问题",
        "当前工作台没有结构化 repair issue。",
    )
    return f"""<div class="drawer-backdrop" id="repair-backdrop" hidden>
      <aside class="drawer evidence-drawer" id="repair-drawer" role="dialog" aria-modal="true" aria-labelledby="repair-drawer-title" tabindex="-1">
        <div class="drawer-head"><div><div class="eyebrow">Blocked / Repair / Retry</div><h2 id="repair-drawer-title">核心数据修复</h2></div>
        <button class="btn small" id="repair-close" type="button" aria-label="关闭核心数据修复">关闭</button></div>
        <div class="prototype-note">每个问题都绑定字段、来源、时间、修复权限和 retry；unknown 不会被改成 0。</div>
        <div class="repair-drawer-body">{body}</div>
      </aside>
    </div>"""


def _management_drawer(workspace: Mapping[str, object]) -> str:
    plans = _dict_rows(workspace.get("portfolio_management_plans"))
    panels: list[str] = []
    for item in plans:
        symbol = str(item.get("symbol") or "")
        status = str(item.get("context_status") or "system_proposed")
        data_blocked = item.get("data_status") == "data_blocked"
        basis = "".join(
            f"<li>{escape(value)}</li>" for value in _string_rows(item.get("decision_basis"))
        ) or "<li>等待可信结构化依据</li>"
        blocked_note = (
            '<div class="management-data-warning"><strong>技术判断仍暂停</strong>'
            f'<p>{escape(str(item.get("data_issue_reason") or "行情未通过质量校验。"))}</p>'
            f'<p>暂停：{escape("、".join(_string_rows(item.get("blocked_capabilities"))) or "技术价格判断")}；'
            f'仍可用：{escape("、".join(_string_rows(item.get("available_capabilities"))) or "账户与组合分析")}。</p></div>'
            if data_blocked
            else ""
        )
        profit_disabled = "" if item.get("profit_protect_applicable") else " disabled aria-disabled=\"true\""
        panels.append(
            f'<article class="management-panel" data-management-panel="{escape(symbol)}" hidden>'
            f'<div class="management-title"><div><small>{escape(symbol)} · {_management_context_label(status)}</small>'
            f'<h3>{escape(str(item.get("name") or symbol))} · {escape(str(item.get("suggestion_name") or "系统建议"))}</h3></div>'
            f'<span class="source {_status_class(status)}">{escape(_management_context_label(status))}</span></div>'
            f'{blocked_note}'
            '<div class="management-detail-grid">'
            f'<div><small>系统建议</small><strong>{escape(str(item.get("suggestion_name") or "继续观察"))}</strong></div>'
            f'<div><small>数据可信度</small><strong>{escape(str(item.get("data_confidence") or "unknown"))}</strong></div>'
            f'<div><small>触发条件</small><p>{escape(str(item.get("trigger_condition") or "等待下一次复核"))}</p></div>'
            f'<div><small>确认窗口 / 持续时间</small><p>{escape(str(item.get("confirmation_window") or "下一次有效复核"))}</p></div>'
            f'<div><small>触发后动作</small><p>{escape(str(item.get("triggered_action") or "维持当前仓位"))}</p></div>'
            f'<div><small>失效条件</small><p>{escape(str(item.get("invalidation_condition") or "持仓状态发生变化"))}</p></div>'
            f'<div><small>下次复核</small><p>{escape(str(item.get("next_review_time") or "下一次 after-close"))}</p></div>'
            f'<div><small>来源与时间</small><p>{escape(str(item.get("generated_source") or "确定性规则"))} · 数据 {escape(str(item.get("source_time") or "unknown"))} · 生成 {escape(str(item.get("generated_at") or "unknown"))}</p></div>'
            '</div>'
            f'<div class="management-basis"><strong>判断依据</strong><ul>{basis}</ul></div>'
            f'<div class="management-actions" data-management-actions data-symbol="{escape(symbol)}" data-version="{escape(str(item.get("management_plan_version") or ""))}">'
            '<button class="btn primary" type="button" data-management-response="adopt">采用系统建议</button>'
            '<button class="btn" type="button" data-management-adjust>调整</button>'
            '<button class="btn ghost" type="button" data-management-response="uncertain">我不确定，仅按系统规则监控</button>'
            '<p class="management-feedback" data-management-feedback></p>'
            '<form class="management-adjust-form" data-management-form hidden>'
            '<fieldset><legend>选择一种管理方式</legend>'
            '<label><input type="radio" name="review" value="watch" checked>继续观察</label>'
            '<label><input type="radio" name="review" value="risk_review">风险复核</label>'
            f'<label class="{"" if item.get("profit_protect_applicable") else "disabled-option"}"><input type="radio" name="review" value="profit_protect"{profit_disabled}>利润保护</label>'
            '<label><input type="radio" name="review" value="uncertain">暂不确定</label></fieldset>'
            f'<label>触发条件<textarea name="trigger_condition">{escape(str(item.get("trigger_condition") or ""))}</textarea></label>'
            f'<label>持续时间<textarea name="confirmation_window">{escape(str(item.get("confirmation_window") or ""))}</textarea></label>'
            f'<label>触发后动作<textarea name="triggered_action">{escape(str(item.get("triggered_action") or ""))}</textarea></label>'
            f'<label>失效条件<textarea name="invalidation_condition">{escape(str(item.get("invalidation_condition") or ""))}</textarea></label>'
            f'<label>备注（选填）<textarea name="note">{escape(str(item.get("user_note") or ""))}</textarea></label>'
            '<button class="btn primary" type="submit">保存调整并重新生成</button>'
            '</form></div></article>'
        )
    body = "".join(panels) or _empty(
        "没有持仓管理方案",
        "请先生成最新 after-close，系统会基于可信结构化数据形成建议。",
    )
    return f"""<div class="drawer-backdrop" id="management-backdrop" hidden>
      <aside class="drawer evidence-drawer" id="management-drawer" role="dialog" aria-modal="true" aria-labelledby="management-drawer-title" tabindex="-1">
        <div class="drawer-head"><div><div class="eyebrow">Holding Management</div><h2 id="management-drawer-title">查看并确认持仓管理方案</h2></div>
        <button class="btn small" id="management-close" type="button" aria-label="关闭持仓管理方案">关闭</button></div>
        <div class="prototype-note">系统先生成建议，你只需采用、调整或保留不确定。确认不改变系统数据质量状态，也不会自动交易。</div>
        <div class="management-drawer-body">{body}</div>
      </aside>
    </div>"""


def _metric(label: str, value: object, suffix: str) -> str:
    shown = "unknown" if value is None or value == "" else f"{value}{suffix}"
    return f'<article class="metric"><span>{escape(label)}</span><b>{escape(str(shown))}</b></article>'


def _ledger_evaluation(item: Mapping[str, object]) -> str:
    if item.get("evaluation_status") == "quarantined":
        reason = str(item.get("quarantine_reason") or "价格口径待核对")
        return (
            '<span class="ledger-state blocked" title="'
            f'{escape(reason)}">口径异常，已隔离</span>'
        )
    return '<span class="ledger-state pending">后验待成熟</span>'


def _empty(title: str, body: str) -> str:
    return f'<div class="empty-state"><h2>{escape(title)}</h2><p>{escape(body)}</p></div>'


def _stage_label(workspace: Mapping[str, object]) -> str:
    return "晨间复核" if workspace.get("run_stage") == "morning_recheck" else "盘后生成"


def _runtime_label(workspace: Mapping[str, object]) -> str:
    status = workspace.get("runtime_status")
    if status == "awaiting_confirmation":
        return "等待人工确认"
    if status == "blocked_waiting":
        return "阻断未解除"
    return "已完成回应"


def _intraday_next_check_label(runtime: Mapping[str, object]) -> str:
    next_check = runtime.get("next_check_time")
    if next_check:
        return str(next_check)
    missed = runtime.get("missed_checkpoints")
    if isinstance(missed, list) and missed:
        return "已遗漏：" + "、".join(str(item) for item in missed)
    return "今日关键时点已完成"


def _plan_status(value: str) -> str:
    return {
        "new": "新计划",
        "revised": "已修订",
        "voided": "已作废",
        "unchanged": "沿用",
        "blocked": "被阻断",
    }.get(value, value)


def _management_context_label(value: str) -> str:
    return {
        "system_proposed": "系统建议待确认",
        "user_confirmed": "已采用系统建议",
        "user_modified": "已按你的调整确认",
        "stale": "旧方案已失效，待重新确认",
    }.get(value, "系统建议待确认")


def _response_label(value: str) -> str:
    return {
        "pending": "待确认",
        "accepted": "已确认",
        "disputed": "有异议",
        "rejected": "已拒绝",
        "deferred": "稍后决定",
        "disabled": "暂不启用",
        "blocked_acknowledged": "已知悉阻断",
    }.get(value, value)


def _theme_state(item: Mapping[str, object]) -> str:
    change = item.get("day_change")
    if isinstance(change, (int, float)):
        return f"{change:+.2%}"
    return str(item.get("state") or item.get("status") or "unknown")


def _value(value: object, *, suffix: str = "") -> str:
    if value is None or value == "":
        return "unknown"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def _contract_value(value: object) -> str:
    if value is None or value == "":
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _money(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "unknown"
    sign = "+" if float(value) > 0 else ""
    return f"{sign}{float(value):,.0f} 元"


def _percent(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "unknown"
    return f"{float(value):.1%}"


def _pnl_class(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "unknown-text"
    return "danger-text" if float(value) >= 0 else "good-text"


def _today_state_label(value: str) -> str:
    return {
        "blocked": "判断阻断",
        "pending_confirmation": "计划待确认",
        "confirmed": "已确认",
        "modification_requested": "修改中",
        "observation_only": "仅观察",
        "disabled": "暂不启用",
    }.get(value, value or "unknown")


def _rate(value: object) -> str:
    return f"{float(value):.0%}" if isinstance(value, (int, float)) else "Pending"


def _status_class(value: object) -> str:
    clean = str(value or "pending").lower()
    if clean in {"ready", "fresh", "accepted", "confirmed", "unchanged", "reviewed"}:
        return "ready"
    if clean in {"shadow", "stale", "deferred", "revised", "pending", "new", "awaiting_confirmation", "pending_confirmation", "observation_only", "modification_requested"}:
        return "pending"
    return "blocked"


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _dict_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _today_plans(workspace: Mapping[str, object]) -> list[dict[str, object]]:
    value = workspace.get("today_plans")
    if isinstance(value, list):
        return _dict_rows(value)
    return _dict_rows(workspace.get("plan_changes"))


def _string_rows(value: object) -> list[str]:
    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def _clock(value: object) -> str:
    text = str(value or "")
    return text[11:16] if len(text) >= 16 and "T" in text else "时间未知"


def _latest_source_time(workspace: Mapping[str, object]) -> str:
    times = [
        str(item.get("source_time"))
        for item in _dict_rows(workspace.get("data_health"))
        if item.get("source_time")
    ]
    return max(times) if times else "unknown"


def _theme_by_id(
    workspace: Mapping[str, object],
    theme_id: str,
) -> dict[str, object]:
    for item in _dict_rows(workspace.get("theme_observations")):
        if item.get("id") == theme_id:
            return item
    return {}


def _theme_status_copy(item: Mapping[str, object]) -> str:
    status = str(item.get("status") or "unavailable")
    if status in {"fresh", "ready"}:
        return "真实诊断代理；不单独授权动作"
    if status == "stale":
        return "来源已过期；限制计划有效性"
    return "当前不可用；不参与确定性结论"


def _previous_plan(
    workspace: Mapping[str, object],
    plan: Mapping[str, object],
) -> dict[str, object]:
    previous_version = plan.get("previous_version")
    if not previous_version:
        return {}
    plan_id = plan.get("plan_id")
    for item in reversed(_dict_rows(workspace.get("plan_version_history"))):
        if (
            item.get("plan_id") == plan_id
            and item.get("plan_version") == previous_version
        ):
            return item
    return {}


def _plan_rules_equal(
    previous: Mapping[str, object],
    current: Mapping[str, object],
) -> bool:
    rule_fields = (
        "if_condition",
        "then_action",
        "until_condition",
        "invalid_condition",
    )
    return all(
        str(previous.get(field) or "") == str(current.get(field) or "")
        for field in rule_fields
    )


def _plan_change_display(
    workspace: Mapping[str, object],
    plan: Mapping[str, object],
) -> str:
    version = str(plan.get("plan_version") or "unknown")
    previous_version = str(plan.get("previous_version") or "")
    status = str(plan.get("status") or "blocked")
    if not previous_version:
        return (
            '<div class="diff-box state-change"><small>计划版本</small>'
            f"<strong>首次生成 · {escape(version)}</strong></div>"
        )

    previous = _previous_plan(workspace, plan)
    if (
        previous_version == version
        and previous
        and _plan_rules_equal(previous, plan)
    ):
        return (
            '<div class="diff-box state-change"><small>执行状态变化</small>'
            f"<strong>计划内容未变，执行状态变为 {escape(status)}</strong></div>"
        )

    previous_action = str(previous.get("then_action") or "暂无可审计的上一版动作")
    return (
        '<div class="diff-grid"><div class="diff-box"><small>'
        f"上一版计划 · {escape(previous_version)}</small><strong>{escape(previous_action)}</strong>"
        '</div><div class="diff-arrow">→</div><div class="diff-box"><small>'
        f"今日建议计划 · {escape(version)}</small><strong>"
        f"{escape(str(plan.get('then_action') or '保持原计划'))}</strong></div></div>"
    )


def _version_change_label(plan: Mapping[str, object]) -> str:
    version = str(plan.get("plan_version") or "unknown")
    previous_version = str(plan.get("previous_version") or "")
    if not previous_version:
        return f"首次生成 · {version}"
    if previous_version == version:
        return f"计划内容未变；执行状态变为 {plan.get('status') or 'unknown'}"
    return f"{previous_version} → {version}"


def _legacy_workspace(payload: Mapping[str, object]) -> dict[str, object]:
    """Fail-closed compatibility for older report fixtures and archived JSON."""

    decision = _mapping(payload.get("unified_decision"))
    matrix = _mapping(payload.get("market_matrix"))
    themes: list[dict[str, object]] = []
    for group in matrix.get("groups", []) if isinstance(matrix.get("groups"), list) else []:
        if isinstance(group, Mapping):
            themes.extend(_dict_rows(group.get("cards")))
    plans = []
    for item in _dict_rows(decision.get("holding_plans"))[:3]:
        symbol = str(item.get("code") or "unknown")
        plans.append(
            {
                "plan_id": f"legacy:{symbol}",
                "symbol": symbol,
                "name": item.get("name") or symbol,
                "plan_version": "legacy-read-only",
                "status": "blocked",
                "current_branch": "legacy_current",
                "current_action": item.get("position_action") or item.get("action") or "保持原计划",
                "current_next_event": item.get("upside_trigger") or "等待统一契约",
                "if_condition": item.get("upside_trigger") or "等待统一契约",
                "then_action": item.get("position_action") or item.get("action") or "保持原计划",
                "until_condition": item.get("flat_trigger") or "下一次有效复核",
                "invalid_condition": item.get("downside_trigger") or "风险线被触发",
                "risk_constraints": ["旧报告缺少 plan_version，必须重新生成后才能确认"],
                "change_reasons": ["旧版 payload 只读兼容"],
                "user_response_status": "pending",
            }
        )
    return {
        "effective_market_date": decision.get("plan_date") or "unknown",
        "run_stage": "after_close",
        "runtime_status": "awaiting_confirmation",
        "stage_note": "旧版报告只读兼容；重新运行 after-close 可生成统一 P0 契约。",
        "market_gate": {
            "permission": decision.get("stance") or "等待确认",
            "reason": matrix.get("portfolio_translation")
            or "旧版 payload 缺少统一 data_health，保持阻断。",
            "first_action": decision.get("first_action") or "重新生成报告",
            "risk_level": "unknown",
            "status": "blocked",
        },
        "data_health": [],
        "theme_observations": themes,
        "portfolio_summary": {"holding_count": len(plans)},
        "portfolio_positions": [],
        "plan_changes": plans,
        "active_plans": plans,
        "research_tasks": [],
        "user_responses": [],
        "monitor_handoffs": [{"status": "blocked", "reason": "P2 才接入真实 5 分钟盘中监控。"}],
        "outcome_summary": _mapping(payload.get("signal_outcomes")),
    }


def _script() -> str:
    return r"""
window.__insightRadarErrors = [];
document.documentElement.dataset.runtimeErrorCount = "0";
function captureRuntimeError(message) {
  window.__insightRadarErrors.push(String(message));
  document.documentElement.dataset.runtimeErrorCount =
    String(window.__insightRadarErrors.length);
}
window.addEventListener("error", event => {
  captureRuntimeError(event.error?.stack || event.message || "window error");
});
window.addEventListener("unhandledrejection", event => {
  captureRuntimeError(event.reason?.stack || event.reason || "unhandled rejection");
});
const routes = new Set(["today", "portfolio", "lookup", "review"]);
const titles = {
  today:["After close · Weekend ready","今日工作台"],
  portfolio:["Portfolio Risk","组合风险"],
  lookup:["Evidence before conclusion","标的研究"],
  review:["Plan · Attribution · Quality","复盘账本"],
};
const token = document.querySelector('meta[name="insightradar-session-token"]').content;
const toast = document.getElementById("toast");
let lastFocus = null;
function showToast(message, tone="") {
  toast.textContent = message; toast.className = `toast visible ${tone}`;
  window.setTimeout(() => { toast.className = "toast"; }, 2400);
}
function selectRoute(requested) {
  const route = routes.has(requested) ? requested : "today";
  document.querySelectorAll("[data-route-panel]").forEach(panel => panel.classList.toggle("active", panel.dataset.routePanel === route));
  document.querySelectorAll("[data-view]").forEach(button => {
    const active = button.dataset.view === route;
    button.classList.toggle("active", active);
    button.toggleAttribute("aria-current", active);
  });
  document.getElementById("pageEyebrow").textContent = titles[route][0];
  document.getElementById("pageTitle").textContent = titles[route][1];
  const params = new URLSearchParams(location.search);
  if (route === "portfolio" && params.get("symbol")) {
    const query = params.get("symbol").toLowerCase();
    const input = document.getElementById("holdingSearch");
    if (input) input.value = params.get("symbol");
    document.querySelectorAll("#holdingsTable tbody tr").forEach(row => {
      row.style.display = row.dataset.name.toLowerCase().includes(query) ? "" : "none";
    });
  }
  if (route === "lookup" && params.get("symbol")) {
    const select = document.getElementById("stockCode");
    if (select && [...select.options].some(option => option.value === params.get("symbol"))) {
      select.value = params.get("symbol");
    }
  }
  window.scrollTo({top:0, behavior:"auto"});
  window.requestAnimationFrame(() => window.scrollTo({top:0, behavior:"auto"}));
}
function setRoute(route, params={}) {
  const url = new URL(location.href);
  ["symbol", "plan_id", "intent"].forEach(key => url.searchParams.delete(key));
  Object.entries(params).forEach(([key, value]) => { if (value) url.searchParams.set(key, value); });
  url.hash = route;
  history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  selectRoute(route);
}
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => setRoute(button.dataset.view)));
document.querySelectorAll("[data-view-link]").forEach(button => button.addEventListener("click", () => setRoute(button.dataset.viewLink, {
  symbol:button.dataset.routeSymbol,
  plan_id:button.dataset.routePlan,
  intent:button.dataset.routeIntent,
})));
window.addEventListener("hashchange", () => selectRoute(location.hash.slice(1)));
const initialRoute = location.hash.slice(1) || "today";
if (location.hash) selectRoute(initialRoute); else setRoute(initialRoute);
function openDataDrawer() {
  lastFocus = document.activeElement;
  const backdrop = document.getElementById("data-backdrop");
  backdrop.hidden = false;
  document.body.classList.add("drawer-open");
  document.getElementById("data-drawer").focus();
}
function closeDataDrawer() {
  const backdrop = document.getElementById("data-backdrop");
  backdrop.hidden = true; document.body.classList.remove("drawer-open");
  if (lastFocus) lastFocus.focus();
}
function openEvidenceDrawer() {
  lastFocus = document.activeElement;
  document.getElementById("evidence-backdrop").hidden = false;
  document.body.classList.add("drawer-open");
  document.getElementById("evidence-drawer").focus();
}
function closeEvidenceDrawer() {
  document.getElementById("evidence-backdrop").hidden = true;
  document.body.classList.remove("drawer-open");
  if (lastFocus) lastFocus.focus();
}
function openManagementDrawer(symbol) {
  lastFocus = document.activeElement;
  const backdrop = document.getElementById("management-backdrop");
  document.querySelectorAll("[data-management-panel]").forEach(panel => {
    panel.hidden = panel.dataset.managementPanel !== symbol;
  });
  backdrop.hidden = false;
  document.body.classList.add("drawer-open");
  document.getElementById("management-drawer").focus();
}
function closeManagementDrawer() {
  document.getElementById("management-backdrop").hidden = true;
  document.body.classList.remove("drawer-open");
  if (lastFocus) lastFocus.focus();
}
function openRepairDrawer(issueId) {
  lastFocus = document.activeElement;
  const backdrop = document.getElementById("repair-backdrop");
  document.querySelectorAll("[data-repair-panel]").forEach(panel => {
    panel.hidden = panel.dataset.repairPanel !== issueId;
  });
  backdrop.hidden = false;
  document.body.classList.add("drawer-open");
  document.getElementById("repair-drawer").focus();
}
function closeRepairDrawer() {
  document.getElementById("repair-backdrop").hidden = true;
  document.body.classList.remove("drawer-open");
  if (lastFocus) lastFocus.focus();
}
document.getElementById("data-status-open").addEventListener("click", openDataDrawer);
document.querySelectorAll("[data-open-data]").forEach(button => button.addEventListener("click", openDataDrawer));
document.getElementById("data-status-close").addEventListener("click", closeDataDrawer);
document.getElementById("data-backdrop").addEventListener("click", event => { if (event.target.id === "data-backdrop") closeDataDrawer(); });
document.querySelectorAll("[data-open-evidence]").forEach(button => button.addEventListener("click", openEvidenceDrawer));
document.getElementById("evidence-close").addEventListener("click", closeEvidenceDrawer);
document.getElementById("evidence-backdrop").addEventListener("click", event => { if (event.target.id === "evidence-backdrop") closeEvidenceDrawer(); });
document.querySelectorAll("[data-open-management]").forEach(button => button.addEventListener("click", () => openManagementDrawer(button.dataset.openManagement)));
document.getElementById("management-close").addEventListener("click", closeManagementDrawer);
document.getElementById("management-backdrop").addEventListener("click", event => { if (event.target.id === "management-backdrop") closeManagementDrawer(); });
document.querySelectorAll("[data-open-repair]").forEach(button => button.addEventListener("click", () => openRepairDrawer(button.dataset.openRepair)));
document.getElementById("repair-close").addEventListener("click", closeRepairDrawer);
document.getElementById("repair-backdrop").addEventListener("click", event => { if (event.target.id === "repair-backdrop") closeRepairDrawer(); });
document.addEventListener("keydown", event => {
  if (event.key !== "Escape") return;
  if (!document.getElementById("repair-backdrop").hidden) closeRepairDrawer();
  else if (!document.getElementById("management-backdrop").hidden) closeManagementDrawer();
  else if (!document.getElementById("evidence-backdrop").hidden) closeEvidenceDrawer();
  else if (!document.getElementById("data-backdrop").hidden) closeDataDrawer();
});
async function post(path, body) {
  if (!token || token === "__LOCAL_SESSION_TOKEN__") throw new Error("请从 InsightRadar 本地应用打开，静态报告只能只读查看。");
  const response = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json","X-InsightRadar-Token":token}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "本地请求失败");
  return result;
}
async function getJson(path) {
  const response = await fetch(path, {headers:{"X-InsightRadar-Token":token}, cache:"no-store"});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "读取本地状态失败");
  return result;
}
async function recheckRepair(container) {
  const button = container.querySelector("[data-repair-action]");
  const feedback = container.querySelector("[data-repair-feedback]");
  if (button) button.disabled = true;
  if (feedback) feedback.textContent = "正在重新抓取、校验并生成 after-close…";
  try {
    const job = await post("/api/repair-recheck", {
      issue_id:button.dataset.repairIssue,
      workspace_generated_at:container.dataset.workspaceGeneratedAt,
      request_id:refreshRequestId(),
    });
    if (feedback) feedback.textContent = "重新检查已启动；通过后页面会载入新计划，失败则保留 blocked。";
    showToast("重新检查已启动。", "success");
    pollRefresh(job.run_id, container);
  } catch (error) {
    if (feedback) feedback.textContent = `重新检查失败：${error.message}。问题仍保持 blocked。`;
    showToast(`重新检查失败：${error.message}`, "error");
    if (button) button.disabled = false;
  }
}
document.querySelectorAll("[data-repair-action]").forEach(button => button.addEventListener("click", () => {
  recheckRepair(button.closest("[data-repair-panel]"));
}));
async function saveManagement(container, response, form=null) {
  const feedback = container.querySelector("[data-management-feedback]");
  const body = {
    symbol:container.dataset.symbol,
    management_plan_version:container.dataset.version,
    response,
    request_id:refreshRequestId(),
  };
  if (form) {
    const data = new FormData(form);
    body.management_choice = data.get("review");
    body.trigger_condition = data.get("trigger_condition");
    body.confirmation_window = data.get("confirmation_window");
    body.triggered_action = data.get("triggered_action");
    body.invalidation_condition = data.get("invalidation_condition");
    body.note = data.get("note");
  }
  const buttons = [...container.querySelectorAll("button")];
  buttons.forEach(button => { button.disabled = true; });
  if (feedback) feedback.textContent = "正在保存到本地私有上下文…";
  try {
    const result = await post("/api/portfolio-management", body);
    if (feedback) feedback.textContent = "保存成功；正在重新生成 after-close。";
    showToast("管理方案已保存，正在重新生成。", "success");
    if (result.refresh_job?.run_id) pollRefresh(result.refresh_job.run_id);
  } catch (error) {
    if (feedback) feedback.textContent = `保存失败：${error.message}。你的调整仍保留在表单中。`;
    showToast(`保存失败：${error.message}`, "error");
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
}
document.querySelectorAll("[data-management-actions]").forEach(container => {
  const form = container.querySelector("[data-management-form]");
  container.querySelector("[data-management-adjust]").addEventListener("click", () => {
    form.hidden = !form.hidden;
  });
  container.querySelectorAll("[data-management-response]").forEach(button => button.addEventListener("click", () => {
    saveManagement(container, button.dataset.managementResponse);
  }));
  form.addEventListener("submit", event => {
    event.preventDefault();
    saveManagement(container, "modify", form);
  });
});
function renderIntradayProgress(runtime) {
  const progress = runtime?.refresh_progress || {};
  const set = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = String(value); };
  set("intradayProgressPhase", progress.phase || "waiting");
  set("intradayProgressStatus", progress.status || runtime?.status || "waiting");
  set("intradaySessionSummary", `${runtime?.session_mode || "resolving"} · 行情日 ${runtime?.runtime_trade_date || runtime?.trade_date || "unknown"} · view ${runtime?.view_mode || "unknown"}`);
  set("intradayProviderRoute", `${progress.provider || "session"} / ${progress.route_display || "自动/未知"}`);
  set("intradayBatch", `${progress.batch || 0} / ${progress.total_batches || 0}`);
  set("intradayCounts", `${progress.processed_symbols || 0} / ${progress.total_symbols || 0} · 成功 ${progress.succeeded_count || 0} · 失败 ${progress.failed_count || 0} · 缺失 ${progress.missing_count || 0}`);
  set("intradayCircuitElapsed", `${progress.circuit_state || "closed"} / ${progress.elapsed_seconds || 0}s`);
  set("intradayNextAction", `${progress.last_success_time || "暂无"} / ${progress.next_action || "等待后台刷新"}`);
}
if (document.getElementById("intradayProgress")) {
  const pollIntradayRuntime = () => getJson("/api/intraday/runtime")
    .then(renderIntradayProgress)
    .catch(error => captureRuntimeError(`intraday progress: ${error.message}`));
  pollIntradayRuntime();
  window.setInterval(pollIntradayRuntime, 1000);
}
function refreshRequestId() {
  return globalThis.crypto?.randomUUID?.() || `refresh-${Date.now()}-${Math.random()}`;
}
async function pollRefresh(runId, repairContainer=null) {
  try {
    const job = await getJson(`/api/refresh/${runId}`);
    const done = Number(job.completed_steps || 0);
    const total = Number(job.total_steps || 0);
    const failureDetail = String(job.error || "").slice(0, 140);
    document.getElementById("stage-label").textContent =
      job.status === "completed" ? "刷新完成" :
      job.status === "failed" ? `刷新失败：${job.failed_step || "unknown"}${failureDetail ? ` · ${failureDetail}` : ""}` :
      job.status === "interrupted" ? `刷新已中断${failureDetail ? ` · ${failureDetail}` : ""}` :
      `刷新 ${done}/${total} · ${job.current_step || "排队"}`;
    if (job.status === "completed") {
      showToast("数据刷新完成，正在载入新工作台。", "success");
      window.setTimeout(() => location.reload(), 500);
    } else if (job.status === "failed" || job.status === "interrupted") {
      showToast(`刷新未完成：${job.failed_step || job.current_step || "服务中断"}。上一版报告仍保留。`, "error");
      const repairButton = repairContainer?.querySelector("[data-repair-action]");
      const repairFeedback = repairContainer?.querySelector("[data-repair-feedback]");
      if (repairButton) repairButton.disabled = false;
      if (repairFeedback) repairFeedback.textContent = `重新检查未完成：${job.failed_step || job.current_step || "服务中断"}${failureDetail ? ` · ${failureDetail}` : ""}。问题仍保持 blocked。`;
      document.getElementById("refresh-data").disabled = false;
      document.getElementById("refresh-all-data").disabled = false;
    } else {
      window.setTimeout(() => pollRefresh(runId), 900);
    }
  } catch (error) {
    showToast(`读取刷新进度失败：${error.message}`, "error");
    const repairButton = repairContainer?.querySelector("[data-repair-action]");
    const repairFeedback = repairContainer?.querySelector("[data-repair-feedback]");
    if (repairButton) repairButton.disabled = false;
    if (repairFeedback) repairFeedback.textContent = `读取重新检查进度失败：${error.message}。问题仍保持 blocked。`;
    document.getElementById("refresh-data").disabled = false;
    document.getElementById("refresh-all-data").disabled = false;
  }
}
async function startRefresh(mode) {
  const buttons = [
    document.getElementById("refresh-data"),
    document.getElementById("refresh-all-data"),
  ];
  buttons.forEach(button => { button.disabled = true; });
  try {
    const job = await post("/api/refresh", {mode, request_id:refreshRequestId()});
    showToast("刷新任务已启动；页面可安全重载。", "success");
    pollRefresh(job.run_id);
  } catch (error) {
    showToast(`无法启动刷新：${error.message}`, "error");
    buttons.forEach(button => { button.disabled = false; });
  }
}
document.getElementById("refresh-data").addEventListener("click", () => startRefresh("stale"));
document.getElementById("refresh-all-data").addEventListener("click", () => startRefresh("full"));
if (token && token !== "__LOCAL_SESSION_TOKEN__") {
  getJson("/api/refresh/active").then(job => {
    if (["pending","running"].includes(job.status)) {
      document.getElementById("refresh-data").disabled = true;
      document.getElementById("refresh-all-data").disabled = true;
      pollRefresh(job.run_id);
    } else if (["failed","interrupted"].includes(job.status)) {
      pollRefresh(job.run_id);
    }
  }).catch(() => {});
}
document.querySelectorAll("[data-plan-response]").forEach(button => button.addEventListener("click", async () => {
  const card = button.closest("[data-plan-id]");
  const noteInput = card.querySelector("[data-response-note]");
  const note = noteInput ? noteInput.value : "";
  card.querySelectorAll("button").forEach(item => item.disabled = true);
  try {
    const record = await post("/api/plan-response", {plan_id:card.dataset.planId, plan_version:card.dataset.planVersion, response:button.dataset.planResponse, note});
    const label = card.querySelector("[data-response-label]");
    const labels = {accepted:"已确认", disputed:"已请求修改", rejected:"旧计划已确认作废", deferred:"已标记仅观察", disabled:"已暂不启用", blocked_acknowledged:"已知悉阻断"};
    if (label) {
      label.textContent = labels[record.response] || record.response;
      label.className = `source ${record.response === "accepted" ? "user" : record.response === "rejected" ? "blocked" : "ai"}`;
    }
    button.textContent = labels[record.response] || record.response;
    const feedback = card.querySelector("[data-rule-feedback]");
    if (feedback) feedback.textContent = `状态已更新：${labels[record.response] || record.response}；正在读取本地审计流水。`;
    showToast("回应已写入本地审计流水。", "success");
    window.setTimeout(() => window.location.reload(), 350);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    card.querySelectorAll("button").forEach(item => item.disabled = false);
  }
}));
document.getElementById("morning-recheck").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const result = await post("/api/morning-recheck", {});
    document.getElementById("stage-label").textContent = "晨间复核";
    showToast(result.stage_note || "晨间复核完成。", "success");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
  }
});
document.querySelectorAll("[data-toggle-plan]").forEach(button => button.addEventListener("click", () => {
  const detail = button.closest("[data-plan-id]").querySelector(".queue-detail");
  detail.hidden = !detail.hidden;
  button.textContent = detail.hidden ? "查看依据" : "收起依据";
}));
const executionForm = document.getElementById("executionForm");
if (executionForm) {
  const symbol = document.getElementById("executionSymbol");
  const target = document.getElementById("executionTarget");
  const reference = document.getElementById("executionReference");
  const syncTheme = () => {
    const option = symbol.options[symbol.selectedIndex];
    if (option && option.dataset.theme) target.value = option.dataset.theme;
  };
  symbol.addEventListener("change", syncTheme);
  syncTheme();
  fetch("/api/executions")
    .then(response => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
    .then(payload => {
      (payload.executions || []).filter(item => item.side === "sell").forEach(item => {
        const option = document.createElement("option");
        option.value = item.execution_id;
        option.textContent = `${item.sold_at || "unknown"} · ${item.symbol} · 剩余以服务端账本校验`;
        reference.appendChild(option);
      });
    })
    .catch(error => { document.getElementById("executionStatus").textContent = `加载 sell 引用失败：${error.message}`; });
  executionForm.addEventListener("submit", async event => {
    event.preventDefault();
    const status = document.getElementById("executionStatus");
    try {
      const record = await post("/api/execution", {
        symbol:symbol.value,
        target_id:target.value,
        side:document.getElementById("executionSide").value,
        quantity:Number(document.getElementById("executionQuantity").value),
        available_quantity:Number(document.getElementById("executionAvailable").value),
        sold_at:document.getElementById("executionSoldAt").value,
        sale_price:Number(document.getElementById("executionSalePrice").value),
        executed_at:document.getElementById("executionExecutedAt").value || null,
        execution_price:Number(document.getElementById("executionPrice").value) || null,
        reference_execution_id:reference.value || null,
        source:document.getElementById("executionSource").value,
        user_confirmed:document.getElementById("executionConfirmed").checked,
      });
      status.textContent = `已追加 ${record.execution_id}；guard ${record.guard?.status || "unknown"} 已立即持久生效。`;
      showToast("真实成交已追加到本地 ledger。", "success");
    } catch (error) {
      status.textContent = `写入失败：${error.message}`;
      showToast(status.textContent, "error");
    }
  });
}
const reentryConfirmationForm = document.getElementById("reentryConfirmationForm");
if (reentryConfirmationForm) {
  const failedSelect = document.getElementById("failedReentryExecution");
  const confirmationStatus = document.getElementById("reentryConfirmationStatus");
  fetch("/api/executions")
    .then(response => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
    .then(payload => {
      const executions = new Map((payload.executions || []).map(item => [item.execution_id, item]));
      (payload.reentry_failures || []).forEach(item => {
        const sale = executions.get(item.referenced_sell_execution_id) || {};
        const option = document.createElement("option");
        option.value = item.failure_id;
        option.dataset.symbol = item.symbol;
        option.dataset.target = item.target_id;
        option.dataset.soldAt = sale.sold_at || "";
        option.textContent = `${item.source_time || "unknown"} · ${item.symbol} · ${item.failure_id}`;
        failedSelect.appendChild(option);
      });
    })
    .catch(error => { confirmationStatus.textContent = `加载接回成交失败：${error.message}`; });
  reentryConfirmationForm.addEventListener("submit", async event => {
    event.preventDefault();
    const option = failedSelect.options[failedSelect.selectedIndex];
    try {
      const record = await post("/api/reentry-confirmation", {
        symbol:option.dataset.symbol,
        target_id:option.dataset.target,
        sold_at:option.dataset.soldAt,
        failure_observation_id:option.value,
        source:document.getElementById("reentryConfirmationSource").value,
        user_confirmed:document.getElementById("reentryOverrideConfirmed").checked,
      });
      confirmationStatus.textContent = `已追加 ${record.confirmation_id}；下一次点时刷新可进入第二次人工复核。`;
      showToast("第二次接回复核确认已追加；仍不会自动买入。", "success");
    } catch (error) {
      confirmationStatus.textContent = `确认失败：${error.message}`;
      showToast(confirmationStatus.textContent, "error");
    }
  });
}
const filterButton = document.getElementById("holdingFilter");
if (filterButton) filterButton.addEventListener("click", () => {
  const query = document.getElementById("holdingSearch").value.trim().toLowerCase();
  document.querySelectorAll("#holdingsTable tbody tr").forEach(row => {
    row.style.display = !query || row.dataset.name.toLowerCase().includes(query) ? "" : "none";
  });
  showToast(query ? "已筛选持仓" : "已显示全部持仓");
});
const lookupForm = document.getElementById("lookupForm");
if (lookupForm) lookupForm.addEventListener("submit", event => {
  event.preventDefault();
  const code = document.getElementById("stockCode").value || "未选择标的";
  const purpose = document.getElementById("lookupPurpose").value;
  const state = document.getElementById("holdingState").value;
  const period = document.getElementById("holdingPeriod").value;
  document.getElementById("lookupLabel").textContent = `${code} · ${state} · ${period}`;
  document.getElementById("analysisTitle").textContent = purpose;
  document.getElementById("objectiveBanner").textContent = state === "未持有"
    ? "未持有，因此不输出股数、减仓比例或个性化风险预算。"
    : "已持有；后续必须结合真实成本、权重、Beta和风险预算生成个性化计划。";
  document.getElementById("userCondition").textContent = `目的：${purpose}；状态：${state}；周期：${period}。`;
  showToast("研究意图已更新；P1 数据编排尚未接入。");
});
document.querySelectorAll(".tab").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach(item => item.classList.toggle("active", item === button));
  document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.toggle("active", panel.id === `tab-${button.dataset.tab}`));
}));
const reviewModeCopy = {
  core:["决策价值曲线尚未可计算","当前只有计划版本、用户响应和信号后验；缺少完整目标组合、真实成交/现金路径、点时代理与分段不操作基线。"],
  exposure:["仓位暴露试算尚未授权","缺少完整系统目标组合、点时现金收益代理和冻结成本模型；当前不能生成正式或探索性暴露曲线。"],
  market:["外部指数比较尚未接入","缺少点时参考目录、跨市场汇率与同窗总回报路径；指数也不能替代不操作基线。"],
};
document.querySelectorAll("[data-review-mode]").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll("[data-review-mode]").forEach(item => item.classList.toggle("active", item === button));
  const state = document.getElementById("reviewComparisonState");
  const copy = reviewModeCopy[button.dataset.reviewMode] || reviewModeCopy.core;
  if (state) {
    state.querySelector("strong").textContent = copy[0];
    state.querySelector("p").textContent = copy[1];
  }
}));
document.querySelectorAll("[data-review-window]").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll("[data-review-window]").forEach(item => item.classList.toggle("active", item === button));
  const label = document.getElementById("reviewAttributionWindow");
  if (label) label.textContent = `当前窗口 ${button.dataset.reviewWindow}日`;
}));
"""


def _css() -> str:
    return """
:root{color-scheme:dark;--bg:#071522;--sidebar:#06111c;--panel:#091a28;--panel2:#0d2030;--panel3:#10263a;--line:#294055;--line2:#3d586f;--text:#f3f0e8;--muted:#91a4b5;--blue:#69a9e9;--blue2:#a9d2f7;--amber:#e6b653;--amber2:#f1c56f;--danger:#ff6262;--good:#25c89a;--violet:#c7b9ed;--shadow:none;--radius:9px}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font:14px/1.55 "Segoe UI","Noto Sans SC","Microsoft YaHei",sans-serif}body{background:var(--bg);overflow-x:hidden;-webkit-font-smoothing:antialiased}button,input,select{font:inherit}button{cursor:pointer}button:disabled{opacity:.48;cursor:not-allowed}a{color:inherit}button:focus-visible,input:focus-visible,select:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.app{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;padding:30px 20px 24px;border-right:1px solid var(--line);background:var(--sidebar);z-index:30}.brand{display:flex;align-items:center;gap:11px;padding:0 8px 28px;font-size:19px;font-weight:820}.brand-mark{display:grid;place-items:center;width:36px;height:36px;border:1px solid #49657d;border-radius:8px;color:var(--blue2);background:#0a1b29}.brand small{display:block;color:var(--muted);font-size:9px;font-weight:650;letter-spacing:.08em;text-transform:uppercase}.nav{display:grid;gap:8px}.nav button{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:58px;padding:0 15px;border:0;border-radius:9px;color:var(--muted);font-size:16px;text-align:left;background:transparent}.nav button:hover{color:var(--text);background:#0c1b29}.nav button.active{color:var(--text);background:#1b344b}.nav button small{font-size:10px;color:#6f8496}.nav .count{min-width:23px;padding:1px 6px;border:1px solid var(--line);border-radius:999px;text-align:center}.sidebar-card{position:absolute;right:20px;bottom:18px;left:20px;padding:12px;border:1px solid var(--line);border-radius:9px;color:var(--muted);font-size:11px;background:#081725}.sidebar-card strong{display:block;margin-bottom:5px;color:var(--text)}
.content{min-width:0;padding:27px 32px 80px}.topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;max-width:1340px;margin:0 auto 14px}.eyebrow{color:var(--blue);font-size:10px;font-weight:820;letter-spacing:.14em;text-transform:uppercase}h1{margin:3px 0 0;font-size:clamp(28px,3vw,43px);line-height:1.15;letter-spacing:-.04em}h2,h3,p{margin-top:0}.top-actions,.inline,.data-state,.legend,.evidence-row,.card-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.chip,.tag,.source,.status{display:inline-flex;align-items:center;gap:6px;min-height:26px;padding:4px 9px;border:1px solid var(--line);border-radius:999px;color:var(--muted);font-size:10px;background:#0a1a28}.source.rule,.source.ready{color:var(--blue2);border-color:#315b7b;background:#0b2031}.source.ai,.source.pending{color:var(--amber2);border-color:#6d5b32;background:#211d15}.source.user{color:var(--good);border-color:#285e54;background:#0b2926}.source.research{color:var(--violet);border-color:#4f4968;background:#1d1b2a}.source.blocked{color:var(--danger);border-color:#6f3f45;background:#1d1820}
.stage{max-width:1340px;margin:0 auto}.view{display:none}.view.active{display:block}.panel{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);box-shadow:var(--shadow)}.section{padding:18px 20px}.section-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}.section-head h2,.section-head h3{margin:0}.section-head p{margin:3px 0 0;color:var(--muted);font-size:11px}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:36px;padding:8px 13px;border:1px solid var(--line2);border-radius:7px;color:var(--text);text-decoration:none;background:#0a1a28}.btn:hover{border-color:#5b7690;background:#10263a}.btn.primary{border-color:var(--text);color:#09131d;font-weight:820;background:var(--text)}.btn.ghost{border-color:transparent;color:var(--muted);background:transparent}.btn.danger{color:var(--danger);border-color:#6f3f45}.btn.small{min-height:31px;padding:6px 10px;font-size:11px}
.decision-stage-rail{min-height:72px;border:1px solid var(--line);border-radius:var(--radius);background:#081725;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));overflow:hidden;scrollbar-width:none}.decision-stage-rail::-webkit-scrollbar{display:none}.stage-node{min-width:0;padding:11px 16px;border-left:1px solid var(--line);border-bottom:3px solid transparent;display:grid;align-content:center;gap:2px}.stage-node:first-child{border-left:0}.stage-node small{color:#7d92a4;font-size:10px;font-weight:700}.stage-node strong{font-size:14px}.stage-node em{overflow:hidden;color:var(--muted);font-size:10px;font-style:normal;text-overflow:ellipsis;white-space:nowrap}.stage-node.done{color:#9fc8bc}.stage-node.current{border-bottom-color:var(--good);background:#10263a}.stage-node.blocked strong{color:var(--danger)}.stage-node.pending strong{color:var(--amber)}
.decision-conclusion{margin-top:14px;padding:22px;border:1px solid #355a73;border-radius:var(--radius);background:#081a29;display:grid;grid-template-columns:minmax(240px,.9fr) minmax(220px,.65fr) minmax(360px,1.35fr);gap:18px;align-items:stretch}.conclusion-main span,.conclusion-style small{color:var(--blue);font-size:10px;font-weight:750;letter-spacing:.06em}.conclusion-main h2{margin:6px 0 5px;font-size:29px}.conclusion-main p{margin:0;color:var(--muted);font-size:11px;line-height:1.6}.conclusion-style{display:grid;gap:8px}.conclusion-style>div{padding:11px 13px;border:1px solid var(--line);border-radius:7px;background:#0a1d2c}.conclusion-style strong{display:block;margin-top:3px}.conclusion-reasons{display:grid;gap:7px}.conclusion-reason{padding:9px 11px;border-left:3px solid var(--good);background:#0a1d2c}.conclusion-reason.blocked{border-left-color:var(--danger)}.conclusion-reason strong,.conclusion-reason small{display:block}.conclusion-reason strong{font-size:12px}.conclusion-reason small{margin-top:2px;color:var(--muted);font-size:10px}.conclusion-invalid{grid-column:1/-1;border-top:1px solid var(--line);padding-top:9px;color:var(--muted);font-size:10px}.conclusion-invalid summary{color:var(--blue);cursor:pointer}.conclusion-invalid ul{margin:8px 0 0;padding-left:18px}
.action-command{min-height:166px;margin-top:14px;padding:28px 25px 27px 28px;border:1px solid var(--line);border-left:4px solid var(--good);border-radius:var(--radius);background:var(--panel);display:flex;align-items:center;justify-content:space-between;gap:34px}.action-command.watch{border-left-color:var(--amber)}.action-command.risk{border-left-color:var(--danger)}.action-command-copy{min-width:0;max-width:880px}.action-status{color:var(--good);font-size:14px;font-weight:750}.action-command.watch .action-status{color:var(--amber)}.action-command.risk .action-status{color:var(--danger)}.action-command h2{margin:13px 0 0;font-size:clamp(28px,2.4vw,38px);line-height:1.2;letter-spacing:-.035em}.action-command p{margin:8px 0 0;color:var(--muted);font-size:14px}.action-command-controls{flex:0 0 290px;display:grid;grid-template-columns:1fr 1fr;justify-items:stretch;gap:7px}.action-primary{grid-column:1/-1;min-height:55px;border-color:#2bc49b;background:#20a987;font-size:15px;font-weight:750}.action-command.risk .action-primary{border-color:#8a4b50;background:#6b353b}.action-primary:hover{background:#25bb94}.action-command.risk .action-primary:hover{background:#7c4046}.action-link{min-height:28px;border-color:transparent;color:var(--blue);background:transparent}.action-response-more{position:relative;color:var(--muted);font-size:10px}.action-response-more summary{min-height:28px;display:grid;place-items:center;border:1px solid var(--line);border-radius:999px;cursor:pointer;list-style:none}.action-response-more summary::-webkit-details-marker{display:none}.action-response-more[open]{grid-column:1/-1}.action-note{width:100%;min-height:34px!important;margin-top:7px;font-size:11px}.action-secondary{margin-top:6px;display:grid;grid-template-columns:repeat(3,1fr);gap:5px}.action-secondary button{min-height:28px;padding:3px 5px;border:1px solid var(--line);border-radius:5px;color:var(--muted);background:#0a1a28;font-size:10px}.action-secondary button:hover{color:var(--text);border-color:var(--line2)}
.authority-chain-new{min-height:98px;margin-top:14px;border:1px solid #466143;border-radius:var(--radius);background:#081926;display:grid;grid-template-columns:.95fr 1.25fr 1.2fr 1fr;overflow:hidden}.authority-step{min-width:0;padding:16px 24px;border:0;border-left:1px solid var(--line);background:transparent;color:var(--text);text-align:left}.authority-step:first-child{border-left:0}.authority-step:hover{background:#0b2030}.authority-step span{min-width:0;display:grid;gap:6px}.authority-step b{font-size:15px}.authority-step small{overflow:hidden;color:var(--muted);font-size:12px;line-height:1.45}.authority-step.green b{color:var(--good)}.authority-step.blue b{color:var(--blue)}.authority-step.cyan b{color:#42c6d2}.authority-step.amber b{color:var(--amber)}
.holding-impact-strip{min-height:68px;margin-top:14px;padding:0 22px;border:1px solid var(--line);border-radius:var(--radius);background:#081725;display:grid;grid-template-columns:155px minmax(0,1fr);align-items:center}.holding-impact-strip h3{margin:0;color:#b8c5cf;font-size:15px}.holding-impact-list{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}.holding-impact{min-width:0;min-height:48px;padding:0 16px;border:0;border-left:1px solid var(--line);background:transparent;color:var(--text);display:grid;align-content:center;gap:2px;text-align:left}.holding-impact:hover{background:#0b2030}.holding-impact>span{overflow:hidden;color:var(--blue);font-size:10px;font-weight:750;text-overflow:ellipsis;white-space:nowrap}.holding-impact b{display:block;overflow:hidden;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.holding-impact small{display:block;overflow:hidden;color:var(--muted);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.holding-impact.empty{display:flex;align-items:center;border-left:0;color:var(--muted)}
.decision-support{margin-top:14px;display:grid;grid-template-columns:minmax(0,1.08fr) minmax(0,1fr);gap:14px}.evidence-command-panel,.risk-exit-panel{min-width:0;padding:21px 22px;border:1px solid var(--line);border-radius:var(--radius);background:#081521}.evidence-command-panel>header,.risk-exit-panel>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.evidence-command-panel h3,.risk-exit-panel h3{margin:0;font-size:20px}.evidence-command-panel header span{display:block;margin-top:4px;color:var(--muted);font-size:11px}.evidence-delta-list{margin-top:15px;display:grid;gap:9px}.evidence-delta{min-height:69px;padding:10px 14px;border:1px solid var(--line);border-radius:8px;background:#0a1a28;display:grid;grid-template-columns:56px minmax(0,1fr) auto;align-items:center;gap:10px}.evidence-delta .delta-kind{color:var(--good);font-size:12px;font-weight:750}.evidence-delta.negative .delta-kind,.evidence-delta.negative em{color:var(--danger)}.evidence-delta.neutral .delta-kind,.evidence-delta.neutral em{color:var(--muted)}.evidence-delta strong{display:block;font-size:13px}.evidence-delta small{display:block;margin-top:3px;color:var(--muted);font-size:10px}.evidence-delta em{color:var(--good);font-size:11px;font-style:normal;font-weight:700}
.risk-what-if{margin-top:15px;padding:15px 16px 12px;border:1px solid var(--line);border-radius:8px;background:#0a1a28}.risk-what-if>span,.exit-conditions>span{color:#8aa0b2;font-size:11px;font-weight:750;letter-spacing:.03em}.risk-facts{margin-top:10px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}.risk-facts>div{padding:0 16px;border-left:1px solid var(--line)}.risk-facts>div:first-child{padding-left:0;border-left:0}.risk-facts small{display:block;color:var(--muted);font-size:10px}.risk-facts strong{display:block;margin-top:4px;font-size:20px}.budget-track{height:5px;margin-top:11px;background:#1a3549;overflow:hidden}.budget-track span{display:block;height:100%;background:var(--good)}.exit-conditions{margin-top:12px;padding:13px 16px;border:1px solid var(--line);border-radius:8px;background:#0a1a28}.exit-conditions>div{margin-top:9px;display:grid;grid-template-columns:1fr 1fr;gap:10px}.exit-conditions p{margin:0;color:var(--muted);font-size:11px}.exit-conditions b{display:block;margin-bottom:3px;color:var(--danger);font-size:10px}.risk-constraints{margin:12px 0 0;padding:0 0 0 18px;color:var(--muted);font-size:11px}.risk-next{margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:10px}.risk-next>div{min-height:65px;padding:11px 13px;border:1px solid var(--line);border-radius:8px;background:#0a1a28;display:grid;align-content:center;gap:4px}.risk-next b{font-size:12px}.risk-next small{color:var(--muted);font-size:10px}.confirm-state.blocked{border-color:#6f3f45;background:#1d1820}.confirm-state.blocked b{color:var(--danger)}.confirm-state.pending{border-color:#6d5b32;background:#211d15}.confirm-state.pending b{color:var(--amber)}
.decision-trust-summary{position:relative;width:100%;min-height:58px;margin-top:14px;padding:0 18px;border:1px solid var(--line);border-radius:8px;background:#081725;color:var(--muted);display:flex;align-items:center;gap:22px;text-align:left}.decision-trust-summary:hover{border-color:#3a5871;background:#0a1b2a}.decision-trust-summary .trust-summary-kicker{color:var(--blue);font-size:12px;font-weight:700}.decision-trust-summary strong{color:var(--text);font-size:14px}.decision-trust-summary strong b{margin-left:5px;color:var(--muted);font-size:16px}.decision-trust-summary span{font-size:12px}.decision-trust-summary em{margin-left:auto;color:var(--blue);font-size:11px;font-style:normal}.remaining-plans{margin-top:20px}.authority-disclaimer{margin-top:14px;color:var(--muted);font-size:11px}
.review-inline-meta{min-height:34px;display:flex;justify-content:flex-end;align-items:center;gap:8px;flex-wrap:wrap}.review-inline-meta span{padding:6px 9px;border:1px solid var(--line);border-radius:7px;color:var(--muted);font-size:10px;background:#091a28}.review-inline-meta span:first-child{margin-right:auto;border-color:transparent;background:transparent}
.review-value-summary{min-height:92px;margin-top:12px;border:1px solid var(--line);border-radius:8px;background:#081827;display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) minmax(150px,.8fr);overflow:hidden}.review-value-summary>div{min-width:0;padding:14px 18px;border-left:1px solid var(--line);display:grid;align-content:center;gap:3px}.review-value-summary>div:first-child{border-left:0}.review-value-summary small{color:var(--muted);font-size:11px}.review-value-summary strong{font-size:22px}.review-value-summary em{overflow:hidden;color:#71879a;font-size:9px;font-style:normal;text-overflow:ellipsis;white-space:nowrap}.unknown-text{color:var(--muted)!important}.review-data-state.blocked{background:#1d1820}.review-data-state.blocked strong{color:var(--danger)}
.review-comparison-panel{margin-top:14px;border:1px solid var(--line);border-radius:8px;background:#081827;overflow:hidden}.review-controls{min-height:54px;padding:8px 12px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px}.review-segmented,.review-periods{display:flex;gap:3px}.review-periods{margin-left:auto}.review-segmented button,.review-periods button{min-height:32px;padding:0 12px;border:1px solid transparent;border-radius:5px;color:var(--muted);background:transparent;font-size:11px}.review-segmented button:hover,.review-periods button:hover{color:var(--text);background:#0d2030}.review-segmented button.active,.review-periods button.active{color:var(--text);border-color:#315b7b;background:#10263a}.review-chart-head{min-height:45px;padding:0 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:14px;color:var(--muted);font-size:10px}.review-legend{display:flex;gap:18px;flex-wrap:wrap}.review-legend span{display:flex;align-items:center;gap:6px}.review-legend i{width:18px;height:2px;background:#5f9fff}.review-legend i.actual{background:#f29a42}.review-legend i.baseline{background:#929da7}.review-chart-blocked{min-height:360px;padding:42px;display:grid;grid-template-columns:minmax(0,.85fr) minmax(320px,1.15fr);align-items:center;gap:38px;background:#071522}.review-chart-blocked strong{font-size:23px}.review-chart-blocked p{max-width:560px;margin:9px 0 0;color:var(--muted);line-height:1.7}.review-chart-blocked ul{margin:0;padding:0;list-style:none;display:grid;gap:10px}.review-chart-blocked li{padding:13px 15px;border:1px solid var(--line);border-radius:7px;background:#091a28;display:flex;justify-content:space-between;gap:15px;color:var(--muted);font-size:11px}.review-chart-blocked li span{color:var(--text);font-weight:700}.review-chart-blocked li b{color:var(--danger);font-weight:600;text-align:right}
.review-attribution-blocked{min-height:92px;margin-top:14px;padding:13px 16px;border:1px solid var(--line);border-radius:8px;background:#081827;display:grid;grid-template-columns:130px minmax(0,1fr) 230px;align-items:center;gap:14px}.review-attribution-blocked>div:first-child{padding-right:14px;border-right:1px solid var(--line)}.review-attribution-blocked>div:first-child strong,.review-attribution-blocked>div:first-child span{display:block}.review-attribution-blocked>div:first-child span{margin-top:5px;color:var(--muted);font-size:10px}.attribution-unknowns{min-width:0;display:grid;grid-template-columns:repeat(4,minmax(80px,1fr) 18px) minmax(116px,1.2fr);align-items:center}.attribution-unknowns p{margin:0;display:grid;justify-items:center;gap:4px}.attribution-unknowns span{color:var(--muted);font-size:10px}.attribution-unknowns b{color:var(--muted);font-size:15px}.attribution-unknowns em{color:var(--muted);font-style:normal;text-align:center}.attribution-unknowns .total{min-height:52px;border-left:1px solid var(--line)}.review-attribution-blocked>p{margin:0;color:var(--muted);font-size:10px;line-height:1.55}.review-ledger-section{margin-top:15px}.review-table-wrap{overflow:auto;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.review-table{min-width:920px;table-layout:fixed}.review-table td,.review-table th{height:44px;padding:0 13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.review-table td small{display:block}.ledger-state.pending{color:var(--amber)}.ledger-state.blocked{color:var(--danger)}.review-evidence-grid{margin-top:14px;display:grid;grid-template-columns:1fr 1fr;gap:14px}
.today-phase-banner{min-height:48px;margin-bottom:12px;padding:10px 14px;border:1px solid #4a5437;border-radius:var(--radius);color:var(--muted);background:#121d22;display:flex;align-items:center;gap:9px}.today-phase-banner strong{color:var(--text)}.today-phase-banner em{margin-left:auto;font-style:normal}.today-phase-banner .phase-dot{width:8px;height:8px;border-radius:50%;background:var(--amber)}.today-phase-banner.after_close{border-color:#3d586f;background:#0a1a28}.today-phase-banner.after_close .phase-dot{background:var(--blue)}
.today-workbench-grid{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.08fr) minmax(0,1.14fr);gap:12px;align-items:start}.today-column{min-width:0;border:1px solid var(--line);border-top:3px solid var(--blue);border-radius:var(--radius);background:var(--panel);overflow:hidden}.what-column{border-top-color:var(--danger)}.attention-column{border-top-color:var(--amber)}.decision-column{border-top-color:var(--blue)}.today-column-head{min-height:107px;padding:18px 18px 14px;border-bottom:1px solid var(--line);display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.today-column-head h2{max-width:410px;margin:8px 0 0;font-size:22px;line-height:1.42;letter-spacing:-.02em}.today-column-head>.source,.today-column-head>.status{flex:0 0 auto}
.account-pnl{padding:18px;border-bottom:1px solid var(--line)}.account-pnl small,.account-metric-grid small{display:block;color:var(--muted);font-size:11px}.account-pnl strong{display:block;margin-top:6px;font-size:34px;line-height:1}.account-metric-grid{margin:12px 18px;display:grid;grid-template-columns:1fr 1fr;gap:8px}.account-metric-grid>div{min-height:74px;padding:11px;border:1px solid var(--line);border-radius:7px;background:#0a1d2c}.account-metric-grid strong{display:block;margin-top:5px;font-size:17px}.account-metric-grid em{display:block;margin-top:3px;color:var(--amber);font-size:11px;font-style:normal}.today-subsection{padding:8px 18px 16px}.today-subsection h3{margin:0 0 8px;color:var(--muted);font-size:11px}.attribution-list{margin:0;padding:0;list-style:none}.attribution-list li{padding:8px 0;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:10px;font-size:11px}.attribution-list li:first-child{border-top:0}.attribution-list span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.attribution-list strong{flex:0 0 auto}
.attention-stack,.decision-stack{padding:10px;display:grid;gap:10px}.attention-card{padding:13px;border:1px solid var(--line);border-radius:7px;background:#0a1a28}.attention-card.blocked{border-color:#6f3f45;background:#171923}.attention-card.opportunity{border-color:#56603d;background:#151d20}.attention-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.attention-card-head>div{min-width:0}.attention-card-head strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:15px}.attention-card-head>div>span{display:block;margin-top:3px;color:var(--muted);font-size:9px}.attention-card p{margin:10px 0 0;color:var(--muted);font-size:11px;line-height:1.65}.attention-card p b{color:var(--text)}.attention-card>.btn{margin-top:10px}.attention-meta{margin-top:10px;display:flex;gap:5px;flex-wrap:wrap}.attention-meta span{padding:3px 6px;border:1px solid var(--line);border-radius:5px;color:var(--muted);font-size:9px}.attention-evidence{padding:8px 0;border-top:1px solid var(--line)}.attention-evidence:first-child{border-top:0}.attention-evidence b,.attention-evidence span{display:block}.attention-evidence b{font-size:10px}.attention-evidence span{margin-top:3px;color:var(--muted);font-size:9px}.counter-block{margin-top:8px;padding-top:8px;border-top:1px solid #6f3f45;color:var(--muted);font-size:10px}.counter-block>b{color:var(--danger)}.counter-block ul{margin:5px 0 0;padding-left:16px}
.today-details{margin-top:9px;color:var(--muted);font-size:10px}.what-column>.today-details{margin:0;padding:12px 18px 16px;border-top:1px solid var(--line)}.today-details summary{min-height:28px;color:var(--blue2);font-weight:700;cursor:pointer}.today-details ul{margin:7px 0 0;padding-left:17px}.today-details p{margin:7px 0 0!important}.today-empty{min-height:120px;padding:20px;display:grid;place-items:center;text-align:center;border:1px dashed var(--line);border-radius:7px;color:var(--muted)}
.decision-card{padding:12px;border:1px solid var(--line);border-radius:7px;background:#0a1a28;display:grid;grid-template-columns:30px minmax(0,1fr);gap:10px}.decision-card.blocked{border-color:#6f3f45;background:#171923}.decision-card-index{width:26px;height:26px;border:1px solid var(--line2);border-radius:5px;display:grid;place-items:center;color:var(--blue2);font-size:11px;font-weight:800}.decision-card.blocked .decision-card-index{color:var(--danger);border-color:#6f3f45}.decision-card-title{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.decision-card-title strong{font-size:13px;line-height:1.45}.decision-card-body>p{margin:7px 0 0;color:var(--muted);font-size:10px;line-height:1.65}.today-rule-actions{margin-top:10px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.today-rule-actions .btn{min-height:32px;padding:5px 6px;font-size:10px}.today-rule-actions .btn.primary{grid-column:auto}.decision-feedback{color:#70879a!important;font-size:9px!important}.blocked-inline{color:var(--danger)!important}.decision-static-state{grid-column:1/-1;padding:6px 8px;border:1px solid var(--line);border-radius:5px;color:var(--muted);text-align:center}.today-data-details{margin-top:10px;border:1px solid var(--line);border-radius:var(--radius);background:#081725;color:var(--muted)}.today-data-details>summary{min-height:42px;padding:10px 14px;color:var(--blue2);font-weight:700;cursor:pointer}.today-data-details>div{padding:0 14px 12px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.today-data-details p{margin:0;padding:9px;border:1px solid var(--line);border-radius:6px;background:#0a1a28}.today-data-details span,.today-data-details strong{display:block}.today-data-details span{font-size:9px}.today-data-details strong{margin-top:3px;color:var(--text);font-size:11px}.today-data-details>ul{margin:0;padding:0 30px 14px;font-size:10px}
.runtime-strip{display:grid;grid-template-columns:minmax(230px,1.05fr) repeat(3,minmax(160px,.72fr));overflow:hidden;margin-bottom:12px}.runtime-cell{padding:13px 16px;border-left:1px solid var(--line)}.runtime-cell:first-child{border-left:0}.runtime-cell small{display:block;color:var(--muted)}.runtime-cell strong{display:block;margin:4px 0 1px}.runtime-cell em{color:var(--muted);font-size:10px;font-style:normal}.market-gate{display:grid;grid-template-columns:minmax(190px,.9fr) repeat(2,minmax(180px,1fr)) minmax(180px,.75fr);overflow:hidden}.market-gate>div{padding:16px 18px;border-left:1px solid var(--line)}.market-gate>div:first-child{border-left:0}.market-gate strong{display:block;margin:6px 0 3px;font-size:18px}.market-gate small{color:var(--muted)}.danger-text,.blocked-text{color:var(--danger)!important}.amber-text,.pending-text{color:var(--amber)!important}.fresh{color:var(--blue2)!important}.good-text,.ready-text{color:var(--good)!important}.theme-line{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:13px;margin-top:10px;padding:12px 15px;border:1px solid rgba(221,168,76,.25);border-radius:13px;color:var(--muted);background:rgba(221,168,76,.055)}.theme-line strong{color:var(--amber)}
.today-layout{display:grid;grid-template-columns:minmax(0,1.46fr) minmax(320px,.58fr);gap:14px;margin-top:18px}.change-card{padding:18px 20px}.change-title{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:15px}.change-title h2{margin:2px 0 0;font-size:25px}.change-type{font-size:11px;font-weight:820}.change-type.pending{color:var(--amber)}.change-type.blocked{color:var(--danger)}.change-type.ready{color:var(--good)}.diff-grid{display:grid;grid-template-columns:1fr 42px 1fr;gap:10px;align-items:stretch}.diff-box{padding:13px 14px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.02)}.diff-box.state-change{margin-bottom:10px}.diff-box small{display:block;margin-bottom:5px;color:var(--muted)}.diff-box strong{font-size:15px}.diff-arrow{display:grid;place-items:center;color:var(--muted);font-size:19px}.reason-box{margin-top:10px;padding:12px 14px;border-left:3px solid var(--amber);color:#d6e0e9;background:rgba(221,168,76,.065)}.reason-box.danger{border-color:var(--danger);background:rgba(223,116,110,.065)}.provenance{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:10px}.prov{padding:10px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.018)}.prov small{display:block;color:var(--muted)}.prov strong{display:block;margin-top:3px;font-size:11px}.rules{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin-top:12px;border:1px solid var(--line);border-radius:12px;overflow:hidden}.rules.single-column{grid-template-columns:1fr}.rule-item{padding:12px 13px;border-left:1px solid var(--line)}.rule-item:first-child{border-left:0}.rule-item b{display:block;margin-bottom:6px;color:var(--blue2);font-size:10px;letter-spacing:.08em}.rule-item.invalid b{color:var(--danger)}.rule-item span{font-size:11px;color:#d4dee7}.card-footer{display:flex;justify-content:space-between;gap:12px;align-items:flex-end;margin-top:14px}.evidence-row{color:var(--muted);font-size:10px}.response-box{display:grid;grid-template-columns:minmax(180px,1fr) auto;gap:10px;align-items:end}.response-box>.prototype-note{grid-column:1/-1;margin-top:0}.response-box label{color:var(--muted);font-size:10px}.response-box .input{display:block;width:100%;margin-top:4px}.response-box.compact{margin-top:12px}.queue{display:grid;gap:10px;margin-top:10px}.queue-item{display:grid;grid-template-columns:42px minmax(180px,.65fr) minmax(240px,1.2fr) auto;gap:14px;align-items:center;padding:14px 16px;border:1px solid var(--line);border-radius:14px;background:rgba(12,27,41,.83)}.queue-number{color:var(--blue);font-size:20px;font-weight:820}.queue-item h3{margin:3px 0 0;font-size:17px}.queue-item p{margin:0;color:var(--muted);font-size:11px}.queue-item p strong{color:var(--text)}.queue-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.queue-detail{grid-column:2/-1}.queue-detail[hidden]{display:none}
.side-stack{display:grid;gap:12px;align-content:start}.risk-meter,.handoff,.data-health{padding:18px 19px}.metric-title{display:flex;justify-content:space-between;align-items:center;gap:10px}.metric-title strong{font-size:17px}.bar{height:9px;margin:10px 0 5px;border-radius:999px;background:#142637;overflow:hidden}.bar span{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--blue),#9cc5ea)}.risk-list{display:grid;margin-top:8px}.risk-row{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-top:1px solid var(--line);color:var(--muted);font-size:11px}.risk-row strong{color:var(--text);text-align:right}.risk-row.warn strong{color:var(--amber)}.risk-row.danger strong{color:var(--danger)}.handoff{border-color:rgba(112,172,228,.28);background:rgba(112,172,228,.05)}.handoff strong{display:block;margin:4px 0;color:var(--amber)}.handoff p,.data-health p{margin:0;color:var(--muted);font-size:11px}
.metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px}.metric{padding:15px 16px;border:1px solid var(--line);border-radius:14px;background:rgba(12,27,41,.82)}.metric small{display:block;color:var(--muted)}.metric strong{display:block;margin:5px 0 2px;font-size:22px}.metric em{color:var(--muted);font-size:10px;font-style:normal}.portfolio-layout{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(300px,.55fr);gap:14px;margin-top:14px}.exposure-list{display:grid;gap:10px}.exposure-item{display:grid;grid-template-columns:130px 1fr 62px;align-items:center;gap:12px}.exposure-item span{color:var(--muted);font-size:11px}.exposure-item b{text-align:right;font-size:11px}.holdings-section,.ledger-section{margin-top:14px}.table-wrap{max-width:100%;overflow:auto;border:1px solid var(--line);border-radius:13px}table{width:100%;border-collapse:collapse;min-width:880px}th,td{padding:12px 13px;border-top:1px solid var(--line);text-align:left;vertical-align:middle}th{border-top:0;color:var(--muted);font-size:9px;letter-spacing:.08em;text-transform:uppercase;background:rgba(255,255,255,.025)}td small{display:block;color:var(--muted)}.pnl.up{color:var(--danger)}.pnl.down{color:var(--good)}
.form-grid{display:grid;grid-template-columns:minmax(220px,1fr) repeat(3,minmax(150px,.45fr)) auto;gap:8px}.input,.select{min-height:39px;padding:8px 11px;border:1px solid var(--line2);border-radius:10px;color:var(--text);background:rgba(4,13,22,.68)}.lookup-result{display:grid;grid-template-columns:minmax(0,1.18fr) minmax(350px,.72fr);gap:14px;margin-top:14px}.chart-empty{min-height:245px;display:grid;place-content:center;gap:8px;padding:28px;text-align:center;border:1px dashed var(--line2);border-radius:13px;color:var(--muted);background:rgba(4,13,22,.45)}.chart-empty strong{color:var(--text);font-size:16px}.research-metrics{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:12px}.objective-banner{padding:11px 12px;border-left:3px solid var(--blue);color:var(--muted);background:rgba(112,172,228,.065)}.analysis-title{margin:4px 0 11px}.evidence-list{display:grid;gap:8px;margin-top:12px}.evidence-item{padding:11px 12px;border:1px solid var(--line);border-radius:11px;background:rgba(255,255,255,.018)}.evidence-item strong{display:flex;justify-content:space-between;gap:10px}.evidence-item p{margin:5px 0 0;color:var(--muted);font-size:10px}.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}.tab{min-height:31px;padding:6px 10px;border:1px solid var(--line);border-radius:9px;color:var(--muted);background:transparent}.tab.active{color:var(--text);border-color:rgba(112,172,228,.45);background:rgba(112,172,228,.08)}.tab-panel{display:none;margin-top:10px}.tab-panel.active{display:block}.source-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:12px}.source-card{padding:11px;border:1px solid var(--line);border-radius:11px;background:rgba(255,255,255,.018)}.source-card small{display:block;color:var(--muted)}.source-card strong{display:block;margin:4px 0}.source-card em{font-size:10px;font-style:normal;color:var(--muted)}
.review-top{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px}.score-card{padding:16px;border:1px solid var(--line);border-radius:14px;background:rgba(12,27,41,.82)}.score-card small{display:block;color:var(--muted)}.score-card strong{display:block;margin-top:5px;font-size:22px}.score-card .date-score{font-size:15px}.ledger{overflow:auto;border:1px solid var(--line);border-radius:13px}.maturity{display:grid;grid-template-columns:repeat(10,1fr);gap:5px;margin:12px 0}.maturity i{height:8px;border-radius:999px;background:rgba(255,255,255,.08)}.maturity i.done{background:var(--blue)}.maturity i.current{background:var(--amber)}
.management-section{margin-top:14px}.management-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.management-card,.data-anomaly-card{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:14px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.02)}.management-card.warn{border-color:rgba(229,169,92,.38)}.management-card small,.data-anomaly-card small{display:block;color:var(--muted)}.management-card strong,.data-anomaly-card strong{display:block;margin:4px 0}.management-card p,.data-anomaly-card p{margin:5px 0 0;color:var(--muted);font-size:11px}.management-empty{grid-column:1/-1;padding:18px;border:1px dashed var(--line2);border-radius:12px;color:var(--muted)}.data-anomaly-section{border-color:rgba(223,116,110,.2)}.management-drawer-body{margin-top:18px}.management-title{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.management-title small{color:var(--muted)}.management-title h3{margin:5px 0 0;font-size:19px}.management-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:14px}.management-detail-grid>div{padding:12px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.02)}.management-detail-grid small{display:block;color:var(--muted)}.management-detail-grid strong,.management-detail-grid p{display:block;margin:5px 0 0}.management-detail-grid p{color:var(--muted);font-size:11px}.management-basis,.management-data-warning{margin-top:12px;padding:12px 14px;border:1px solid var(--line);border-radius:11px}.management-basis ul{margin:8px 0 0;padding-left:18px;color:var(--muted)}.management-data-warning{border-color:rgba(223,116,110,.42);background:rgba(223,116,110,.06)}.management-data-warning p{margin:6px 0 0;color:var(--muted)}.management-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:15px}.management-actions>.management-feedback{flex-basis:100%;margin:0;color:var(--muted)}.management-adjust-form{flex-basis:100%;display:grid;gap:9px;margin-top:5px;padding:14px;border:1px solid var(--line2);border-radius:12px;background:rgba(4,13,22,.5)}.management-adjust-form[hidden]{display:none}.management-adjust-form fieldset{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:0;padding:12px;border:1px solid var(--line);border-radius:10px}.management-adjust-form legend{padding:0 6px;color:var(--muted)}.management-adjust-form label{display:grid;gap:5px;color:var(--muted);font-size:11px}.management-adjust-form fieldset label{display:flex;align-items:center;gap:7px}.management-adjust-form textarea{min-height:68px;resize:vertical;padding:9px;border:1px solid var(--line2);border-radius:9px;color:var(--text);background:rgba(4,13,22,.68)}.disabled-option{opacity:.45}.drawer-backdrop{position:fixed;inset:0;display:flex;justify-content:flex-end;background:rgba(0,0,0,.58);backdrop-filter:blur(3px);z-index:100}.drawer-backdrop[hidden]{display:none}.drawer{width:min(560px,94vw);height:100%;overflow:auto;padding:24px;border-left:1px solid var(--line2);background:#091724;box-shadow:-20px 0 55px rgba(0,0,0,.35);outline:0}.evidence-drawer{width:min(720px,96vw)}.drawer-head{display:flex;justify-content:space-between;gap:15px;align-items:flex-start}.drawer h2{margin:5px 0 0}.timeline,.evidence-chain{display:grid;gap:10px;margin-top:18px}.timeline-item{position:relative;padding:13px 14px 13px 18px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.02)}.timeline-item:before{content:"";position:absolute;left:8px;top:18px;width:5px;height:5px;border-radius:50%;background:var(--blue)}.timeline-item small{display:block;color:var(--muted)}.timeline-item strong{display:block;margin-top:4px}.timeline-item p{margin:7px 0 0;color:var(--muted);font-size:10px}.evidence-chain-item{padding:15px 16px;border:1px solid var(--line);border-radius:9px;background:#0a1a28}.evidence-chain-item header{display:flex;justify-content:space-between;gap:12px;color:var(--blue);font-size:10px;text-transform:uppercase}.evidence-chain-item header em{font-style:normal}.evidence-chain-item h3{margin:9px 0;font-size:15px}.evidence-chain-item p{margin:6px 0;color:var(--muted);font-size:11px}.evidence-chain-item p b{color:var(--text)}.evidence-chain-item footer{margin-top:10px;padding-top:9px;border-top:1px solid var(--line);color:#7f93a4;font-size:10px}.toast{position:fixed;right:22px;bottom:22px;z-index:120;transform:translateY(18px);opacity:0;padding:10px 13px;border:1px solid var(--line2);border-radius:11px;background:#102536;box-shadow:var(--shadow);transition:.18s;pointer-events:none}.toast.visible{transform:translateY(0);opacity:1}.toast.success{border-color:rgba(121,184,174,.45)}.toast.error{border-color:rgba(223,116,110,.45)}.mobile-nav{display:none}.prototype-note{margin-top:12px;padding:11px 13px;border:1px dashed rgba(137,169,198,.25);border-radius:12px;color:var(--muted);font-size:10px}.empty-state{min-height:220px;display:grid;place-content:center;padding:22px;text-align:center;border:1px dashed var(--line2);border-radius:var(--radius);color:var(--muted);background:rgba(12,27,41,.6)}.empty-state h2{margin-bottom:6px;color:var(--text)}
.repair-drawer-body{margin-top:18px}.repair-title{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.repair-title small{color:var(--muted)}.repair-title h3{margin:5px 0 0;font-size:20px}.repair-section{margin-top:12px;padding:14px;border:1px solid var(--line);border-radius:11px;background:rgba(255,255,255,.02)}.repair-section.danger{border-color:rgba(223,116,110,.42);background:rgba(223,116,110,.06)}.repair-section h4{margin:0 0 7px;color:var(--blue2)}.repair-section p{margin:6px 0;color:var(--muted);font-size:11px}.repair-section p b{color:var(--text)}.repair-known-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.repair-known-grid>div{min-width:0;padding:10px;border:1px solid var(--line);border-radius:9px;background:#081725}.repair-known-grid small,.repair-known-grid strong{display:block}.repair-known-grid small{color:var(--muted)}.repair-known-grid strong{margin-top:4px;overflow-wrap:anywhere;font-size:11px}.repair-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:12px}.repair-feedback{flex-basis:100%;margin:0!important;color:var(--muted)}
@media(max-width:1120px){.today-workbench-grid,.today-layout,.portfolio-layout,.lookup-result,.decision-support,.review-evidence-grid,.decision-conclusion{grid-template-columns:1fr}.today-workbench-grid{gap:14px}.conclusion-invalid{grid-column:1}.side-stack{grid-template-columns:repeat(3,minmax(0,1fr))}.metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.form-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.form-grid .btn{grid-column:1/-1}.review-top{grid-template-columns:repeat(3,minmax(0,1fr))}.authority-chain-new{grid-template-columns:repeat(2,minmax(0,1fr))}.authority-step:nth-child(3){border-left:0;border-top:1px solid var(--line)}.authority-step:nth-child(4){border-top:1px solid var(--line)}.review-value-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.review-value-summary>div:nth-child(3),.review-value-summary>div:nth-child(5){border-top:1px solid var(--line)}.review-value-summary>div:nth-child(3),.review-value-summary>div:nth-child(5){border-left:0}.review-data-state{grid-column:1/-1}.review-chart-blocked{grid-template-columns:1fr;min-height:420px}.review-attribution-blocked{grid-template-columns:120px minmax(0,1fr)}.review-attribution-blocked>p{grid-column:1/-1;padding-top:10px;border-top:1px solid var(--line)}}
@media(max-width:820px){.app{display:block}.sidebar{display:none}.content{padding:16px 12px 90px}.topbar{display:block;margin-bottom:14px}.top-actions{margin-top:10px}.runtime-strip,.market-gate{grid-template-columns:repeat(2,minmax(0,1fr))}.runtime-cell:first-child,.market-gate>div:first-child{grid-column:1/-1}.runtime-cell:nth-child(2),.market-gate>div:nth-child(2){border-left:0}.theme-line{grid-template-columns:1fr}.decision-stage-rail{display:flex;overflow-x:auto}.stage-node{flex:0 0 142px}.action-command{min-height:0;padding:23px 18px 19px;display:grid;gap:22px}.action-command-controls{width:100%;display:grid}.authority-chain-new{display:block}.authority-step{width:100%;min-height:75px;border-top:1px solid var(--line);border-left:0}.authority-step:first-child{border-top:0}.holding-impact-strip{padding:16px;display:block}.holding-impact-strip h3{margin-bottom:12px}.holding-impact-list{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.holding-impact{padding:0;border-left:0}.evidence-command-panel,.risk-exit-panel{padding:18px 16px}.rules,.provenance,.source-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.rule-item:nth-child(3),.prov:nth-child(3){border-left:0}.queue-item{grid-template-columns:34px 1fr}.queue-item>:nth-child(3),.queue-actions,.queue-detail{grid-column:2}.queue-actions{justify-content:flex-start}.side-stack{grid-template-columns:1fr}.metrics,.review-top{grid-template-columns:repeat(2,minmax(0,1fr))}.decision-trust-summary{padding:12px 14px;flex-wrap:wrap;gap:7px 14px}.decision-trust-summary .trust-summary-kicker{flex-basis:100%}.decision-trust-summary em{margin-left:0}.review-inline-meta{justify-content:flex-start}.review-inline-meta span:first-child{flex-basis:100%;margin-right:0;padding-left:0}.review-controls{display:grid}.review-periods{margin-left:0;overflow:auto}.review-chart-blocked{padding:28px 20px}.review-attribution-blocked{display:block;overflow:auto}.review-attribution-blocked>div:first-child{padding:0 0 10px;border-right:0;border-bottom:1px solid var(--line)}.attribution-unknowns{min-width:700px;margin-top:12px}.review-attribution-blocked>p{min-width:330px;margin-top:12px}.mobile-nav{position:fixed;right:0;bottom:0;left:0;z-index:80;display:grid;grid-template-columns:repeat(4,1fr);padding:7px 8px calc(7px + env(safe-area-inset-bottom));border-top:1px solid var(--line);background:#06111c}.mobile-nav button{display:block;min-height:43px;border:0;border-radius:9px;color:var(--muted);background:transparent;text-align:center}.mobile-nav button.active{color:var(--text);background:#132a3e}.mobile-nav button span{display:inline}.card-footer,.response-box{display:block}.card-actions{margin-top:10px}}
@media(max-width:520px){.runtime-strip,.market-gate,.rules,.provenance,.source-grid,.metrics,.review-top,.form-grid,.research-metrics,.review-value-summary{display:block}.runtime-cell,.market-gate>div,.rule-item,.prov,.source-card,.metric,.score-card,.review-value-summary>div{border-left:0;border-top:1px solid var(--line);margin-top:7px}.runtime-cell:first-child,.market-gate>div:first-child,.rule-item:first-child,.review-value-summary>div:first-child{border-top:0}.action-command h2{font-size:28px}.holding-impact-list{grid-template-columns:1fr}.evidence-command-panel>header,.risk-exit-panel>header{display:block}.evidence-command-panel>header .btn{margin-top:10px}.evidence-delta{grid-template-columns:56px minmax(0,1fr)}.evidence-delta em{grid-column:2}.risk-facts,.exit-conditions>div,.risk-next{grid-template-columns:1fr}.risk-facts>div{padding:9px 0;border-top:1px solid var(--line);border-left:0}.risk-facts>div:first-child{border-top:0}.review-chart-head{display:grid;padding:10px}.review-chart-blocked{padding:24px 14px}.review-chart-blocked li{display:grid}.review-value-summary>div{margin-top:0}.diff-grid{grid-template-columns:1fr}.diff-arrow{transform:rotate(90deg)}.card-footer,.section-head{display:block}.card-actions,.section-head>.inline{margin-top:10px}.change-title h2{font-size:21px}.content{padding-left:10px;padding-right:10px}.top-actions .chip:first-child{display:none}.btn,.input,.select{min-height:44px}}
@media(max-width:820px){.today-phase-banner{align-items:flex-start;flex-wrap:wrap}.today-phase-banner em{margin-left:0}.today-column-head{min-height:0}.today-data-details>div{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:520px){.today-column-head{padding:15px;display:block}.today-column-head>.source,.today-column-head>.status{margin-top:10px}.today-column-head h2{font-size:20px}.account-pnl{padding:15px}.account-metric-grid{margin:10px 15px;grid-template-columns:1fr}.attention-stack,.decision-stack{padding:8px}.today-rule-actions{grid-template-columns:1fr}.decision-card-title{display:block}.decision-card-title .source{margin-top:6px}.today-data-details>div{grid-template-columns:1fr}}
@media(max-width:1120px){.management-grid{grid-template-columns:1fr}}
@media(max-width:620px){.management-detail-grid,.management-adjust-form fieldset,.repair-known-grid{grid-template-columns:1fr}.management-card,.data-anomaly-card{align-items:flex-start;flex-direction:column}}
"""
