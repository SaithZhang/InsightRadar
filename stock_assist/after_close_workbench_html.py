"""Self-contained V3 HTML renderer for the after-close decision workspace."""

from __future__ import annotations

from html import escape
import json
from typing import Mapping

from stock_assist.branding import PRODUCT_NAME
from stock_assist.decision_workspace import overlay_plan_responses


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
    safe_json = json.dumps(workspace, ensure_ascii=False, default=str).replace("</", "<\\/")
    positions = _dict_rows(workspace.get("portfolio_positions"))
    plans = _dict_rows(workspace.get("plan_changes"))
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
        {_nav("today", "今日计划", str(len(plans)), True)}
        {_nav("portfolio", "组合风险", f"{len(positions)} 持仓")}
        {_nav("lookup", "标的研究", "按意图")}
        {_nav("review", "复盘账本", "T+1/5/20")}
      </nav>
      <div class="sidebar-card"><strong>本地单用户工作台</strong>真实本地数据 · 无交易权<br>规则决定状态，AI只做解释。</div>
    </aside>
    <main class="content">
      <header class="topbar">
        <div><div id="pageEyebrow" class="eyebrow">08:30 Decision Workspace</div><h1 id="pageTitle">今日计划</h1></div>
        <div class="top-actions">
          <span class="chip">数据截至 {escape(source_time)}</span>
          <span class="chip" id="stage-label">{escape(_stage_label(workspace))}</span>
          <button class="btn small" id="morning-recheck" type="button">晨间增量复核</button>
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
  {_data_drawer(workspace)}
  <div class="toast" id="toast" role="status" aria-live="polite"></div>
  <script type="application/json" id="workspace-data">{safe_json}</script>
  <script>{_script()}</script>
</body>
</html>"""


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
    gate = _mapping(workspace.get("market_gate"))
    plans = _dict_rows(workspace.get("plan_changes"))
    health = _dict_rows(workspace.get("data_health"))
    ready_count = sum(item.get("status") == "ready" for item in health)
    stale_count = sum(item.get("status") == "stale" for item in health)
    blocked_count = sum(
        item.get("status") in {"missing", "blocked", "failed"} for item in health
    )
    a_share = _theme_by_id(workspace, "a_share_technology")
    overseas = _theme_by_id(workspace, "us_technology")
    first = plans[0] if plans else None
    queue = plans[1:]
    generated_time = _clock(workspace.get("source_generated_at"))
    morning_time = (
        _clock(workspace.get("generated_at"))
        if workspace.get("run_stage") == "morning_recheck"
        else "尚未执行"
    )
    primary = (
        _plan_card(first, 0, workspace)
        if first
        else _empty(
            "今天没有需要处理的计划变化",
            "继续沿用上一份已确认计划；没有变化时不重复制造行动。",
        )
    )
    queue_html = "".join(
        _plan_card(item, index + 1, workspace) for index, item in enumerate(queue)
    )
    if queue_html:
        queue_html = f'<div class="queue">{queue_html}</div>'
    data_summary = (
        f"{ready_count} 可用 / {stale_count} 过期 / {blocked_count} 阻塞"
    )
    theme_state = _theme_state(a_share) if a_share else "暂无可用观测"
    return f"""
<section class="view active" id="today" data-route-panel="today">
  <section class="panel runtime-strip" aria-label="计划生成链路">
    <div class="runtime-cell"><div class="eyebrow">计划生成链路</div><strong>昨日盘后计划 → 今晨增量复核</strong><em>今晨不是重新编一个观点</em></div>
    <div class="runtime-cell"><small>盘后 Core</small><strong>{escape(generated_time)} 已生成</strong><em>持仓、市场、公告、研究变化</em></div>
    <div class="runtime-cell"><small>晨间增量</small><strong>{escape(morning_time)}</strong><em>仅复核现有来源时效；未接入实时刷新</em></div>
    <div class="runtime-cell"><small>决策权</small><strong class="good-text">{escape(_runtime_label(workspace))}</strong><em>AI无自动交易或策略决定权</em></div>
  </section>
  <section class="panel market-gate">
    <div><div class="eyebrow">市场约束</div><strong class="danger-text">{escape(str(gate.get("permission") or "等待确认"))}</strong><small>{escape(str(gate.get("reason") or "没有足够证据形成市场许可。"))}</small></div>
    <div><small>A股科技 · 诊断代理</small><strong>{escape(_theme_state(a_share) if a_share else "不可用")}</strong><small>{escape(_theme_status_copy(a_share))}</small></div>
    <div><small>海外科技 · 诊断代理</small><strong class="amber-text">{escape(_theme_state(overseas) if overseas else "不可用")}</strong><small>{escape(_theme_status_copy(overseas))}</small></div>
    <div><small>数据可信度</small><strong class="fresh">{escape(data_summary)}</strong><small>缺口不由 AI 或默认值补齐</small></div>
  </section>
  <div class="theme-line"><span class="eyebrow">持仓相关主题</span><strong>{escape(str(a_share.get("label") or "A股科技"))} {escape(theme_state)}</strong><span>· 诊断观察不等于买入许可；市场约束仍优先。</span><button class="btn small" type="button" data-open-data>查看口径</button></div>
  <div class="today-layout">
    <div>
      {primary}
      {queue_html}
    </div>
    <aside class="side-stack">
      {_risk_card(workspace)}
      {_data_health_card(workspace)}
      {_handoff_card(workspace)}
    </aside>
  </div>
</section>"""


def _decision_chain(workspace: Mapping[str, object]) -> str:
    stage = str(workspace.get("run_stage") or "after_close")
    reviewed = workspace.get("runtime_status") != "awaiting_confirmation"
    return f"""<section class="decision-chain" aria-label="决策链">
      <div class="chain-step done"><span>1</span><div><b>盘后生成</b><small>形成条件计划</small></div></div>
      <div class="chain-line"></div>
      <div class="chain-step {'done' if stage == 'morning_recheck' else 'current'}"><span>2</span><div><b>晨间复核</b><small>检查来源时效</small></div></div>
      <div class="chain-line"></div>
      <div class="chain-step {'done' if reviewed else 'current'}"><span>3</span><div><b>人工确认</b><small>接受 / 异议 / 拒绝 / 稍后</small></div></div>
    </section>"""


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
    risks = _string_rows(plan.get("risk_constraints"))
    why = "；".join(reasons) or "没有记录变化原因。"
    change_display = _plan_change_display(workspace, plan)
    name = str(plan.get("name") or plan.get("symbol") or "未命名持仓")
    symbol = str(plan.get("symbol") or "")
    generated_time = _clock(plan.get("created_at"))
    if index > 0:
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
        return f"""
<article class="queue-item" data-plan-id="{escape(plan_id)}" data-plan-version="{escape(version)}">
  <div class="queue-number">{index + 1:02d}</div>
  <div><span class="source {_status_class(status)}">{escape(_plan_status(status))}</span><span class="source user" data-response-label>{escape(_response_label(response))}</span><h3>{escape(name)}</h3><small>{escape(symbol)} · {escape(version)}</small></div>
  <div><p><strong>{escape(str(plan.get("then_action") or "保持原计划"))}</strong></p><p>状态变化：{escape(why)}</p><p>下一条件：{escape(str(plan.get("if_condition") or "等待条件明确"))}</p></div>
  <div class="queue-actions"><button class="btn decision" type="button" data-plan-response="{primary_response}">{escape(primary_label)}</button><button class="btn ghost" type="button" data-toggle-plan>查看依据</button></div>
  <div class="queue-detail" hidden>
    <div class="rules"><div class="rule-item"><b>IF · 触发</b><span>{escape(str(plan.get("if_condition") or "等待条件明确"))}</span></div><div class="rule-item"><b>THEN · 动作</b><span>{escape(str(plan.get("then_action") or "保持原计划"))}</span></div><div class="rule-item"><b>UNTIL · 有效期</b><span>{escape(str(plan.get("until_condition") or "下一次有效复核"))}</span></div><div class="rule-item invalid"><b>INVALID · 失效</b><span>{escape(str(plan.get("invalid_condition") or "风险线被触发"))}</span></div></div>
    {_response_controls(plan, compact=True)}
  </div>
</article>"""
    return f"""
<article class="panel change-card" data-plan-id="{escape(plan_id)}" data-plan-version="{escape(version)}">
  <div class="change-title"><div><div class="eyebrow">优先处理 01 · {escape(name)}</div><h2>{escape(str(plan.get("then_action") or "保持原计划"))}</h2></div><span class="change-type {_status_class(status)}">{escape(_plan_status(status))}</span></div>
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
  <div class="card-footer"><div class="evidence-row"><span>新证据 {len(reasons)} 项</span><span>规则 {escape(version)}</span><span>AI调用：未使用</span><button class="btn ghost small" type="button" data-open-data>查看完整变化链</button></div>
  {_response_controls(plan)}
</div>
</article>"""


def _response_controls(
    plan: Mapping[str, object],
    *,
    compact: bool = False,
) -> str:
    blocked = plan.get("status") == "blocked"
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
    return f"""<section class="panel handoff">
      <div class="eyebrow">盘中监控交接</div>
      <strong id="handoffState">尚未形成今日有效计划</strong>
      <p id="handoffCopy">{escape(str(item.get("reason") or "P2 才接入真实 5 分钟盘中监控。"))}</p>
      <div class="prototype-note">目标交互：状态变化、去重、冷却、人工确认。当前真实 5 分钟轮询与通知尚未实现。</div>
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


def _portfolio(workspace: Mapping[str, object]) -> str:
    summary = _mapping(workspace.get("portfolio_summary"))
    positions = _dict_rows(workspace.get("portfolio_positions"))
    changes = _dict_rows(workspace.get("plan_changes"))
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
        f"<td>{escape(str(item.get('beta_classification') or 'unknown'))}</td>"
        f"<td><span class='source {_status_class(item.get('data_completeness'))}'>{escape(str(item.get('data_completeness') or 'missing'))}</span></td>"
        f"<td><span class='source {_status_class(item.get('today_status'))}'>{escape(_plan_status(str(item.get('today_status') or 'blocked')))}</span></td>"
        f"<td><strong>{escape(str(item.get('current_plan_version') or '暂无'))}</strong>"
        f"<small>{escape(str(item.get('next_condition') or '等待形成规则计划'))}</small></td>"
        f"<td><button class='btn small' type='button' data-open-data>打开</button></td></tr>"
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
    return f"""
<section class="view" id="portfolio" data-route-panel="portfolio">
  <div class="metrics">
    <div class="metric"><small>持仓数量</small><strong>{len(positions)}</strong><em>真实 portfolio.json</em></div>
    <div class="metric"><small>已知仓位</small><strong>{_value(known_exposure, suffix='%')}</strong><em>未知不按 0 处理</em></div>
    <div class="metric"><small>未知权重</small><strong class="danger-text">{unknown_weight} 只</strong><em>阻塞完整风险计算</em></div>
    <div class="metric"><small>Beta 未分类</small><strong>{unknown_beta} 只</strong><em>不按代码推断</em></div>
    <div class="metric"><small>今日必须处理</small><strong>{len(changes)}</strong><em>逐项确认</em></div>
  </div>
  <div class="portfolio-layout">
    <section class="panel section">
      <div class="section-head"><div><h2>组合风险驾驶舱</h2><p>先回答风险和数据缺口，再展示盈亏。</p></div><a class="btn" href="/portfolio-import">导入/更新持仓</a></div>
      <div class="exposure-list">
        <div class="exposure-item"><span>已知仓位</span><div class="bar"><span style="width:{known_width}%"></span></div><b>{_value(known_exposure, suffix='%')}</b></div>
        <div class="exposure-item"><span>Beta 已分类</span><div class="bar"><span style="width:{classified_width}%"></span></div><b>{classified}/{len(positions)}</b></div>
        <div class="exposure-item"><span>数据完整</span><div class="bar"><span style="width:{complete_width}%"></span></div><b>{complete}/{len(positions)}</b></div>
        <div class="exposure-item"><span>严格就绪</span><div class="bar"><span style="width:{ready_width}%"></span></div><b>{escape(str(summary.get("decision_ready_holdings") or 0))}/{len(positions)}</b></div>
      </div>
    </section>
    <section class="panel section">
      <div class="section-head"><div><h3>风险阻塞项</h3><p>unknown 不能按 0 或正常处理。</p></div></div>
      <div class="risk-list">
        <div class="risk-row danger"><span>Beta 未知</span><strong>{unknown_beta} 只</strong></div>
        <div class="risk-row danger"><span>组合现金</span><strong>{escape(cash_label)}</strong></div>
        <div class="risk-row warn"><span>风险对账</span><strong>{escape(str(summary.get("risk_reconciliation_status") or "unknown"))}</strong></div>
        <div class="risk-row"><span>持仓字段完整</span><strong>{complete}/{len(positions)}</strong></div>
      </div>
    </section>
  </div>
  <section class="panel section holdings-section">
    <div class="section-head"><div><h2>持仓与计划</h2><p>计划变化、风险状态和数据完整度优先于浮动盈亏。</p></div><div class="inline"><input id="holdingSearch" class="input" placeholder="代码或名称"/><button id="holdingFilter" class="btn" type="button">筛选</button></div></div>
    <div class="table-wrap"><table id="holdingsTable"><thead><tr><th>标的</th><th>权重</th><th>浮动盈亏</th><th>风险暴露</th><th>数据状态</th><th>今日状态</th><th>当前计划</th><th></th></tr></thead>
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
<section class="view" id="lookup" data-route-panel="lookup">
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
    horizons = _mapping(outcome.get("horizons"))
    versions = _dict_rows(workspace.get("plan_version_history"))
    responses = _dict_rows(workspace.get("user_responses"))
    response_by_plan_version = {
        (
            str(item.get("plan_id") or ""),
            str(item.get("plan_version") or ""),
        ): item
        for item in responses
    }
    rows = "".join(
        f"<tr><td><strong>{escape(str(item.get('symbol') or item.get('plan_id') or 'unknown'))}</strong>"
        f"<small>{escape(str(item.get('plan_id') or ''))}</small></td>"
        f"<td>{escape(_version_change_label(item))}</td>"
        f"<td>{escape(str(item.get('then_action') or '未记录动作'))}</td>"
        f"<td>{escape('；'.join(_string_rows(item.get('change_reasons'))) or '无变化原因')}</td>"
        f"<td>尚无盘中触发流水</td>"
        f"<td>{escape(_response_label(str(_mapping(response_by_plan_version.get((str(item.get('plan_id') or ''), str(item.get('plan_version') or '')))).get('response') or 'pending')))}</td>"
        f"<td>后验待成熟</td></tr>"
        for item in versions[-8:]
    )
    if not rows:
        rows = '<tr><td colspan="7">尚无计划版本历史。</td></tr>'
    disputed = sum(item.get("response") == "disputed" for item in responses)
    matured_total = sum(
        int(_mapping(item).get("matured") or 0) for item in horizons.values()
    )
    maturity_done = min(10, int((matured_total / max(1, int(outcome.get("tracked_signals") or 1))) * 10))
    maturity_bars = "".join(
        '<i class="done"></i>' if index < maturity_done else "<i></i>"
        for index in range(10)
    )
    one_day = _mapping(horizons.get("1d"))
    five_day = _mapping(horizons.get("5d"))
    twenty_day = _mapping(horizons.get("20d"))
    return f"""
<section class="view" id="review" data-route-panel="review">
  <div class="review-top">
    <div class="score-card"><small>已跟踪信号</small><strong>{escape(str(outcome.get("tracked_signals") or 0))}</strong></div>
    <div class="score-card"><small>待成熟信号</small><strong>{escape(str(outcome.get("pending_signals") or 0))}</strong></div>
    <div class="score-card"><small>计划版本记录</small><strong>{len(versions)}</strong></div>
    <div class="score-card"><small>用户异议</small><strong>{disputed}</strong></div>
    <div class="score-card"><small>数据截至</small><strong class="date-score">{escape(str(outcome.get("as_of_trade_date") or "unknown"))}</strong></div>
  </div>
  <section class="panel section ledger-section">
    <div class="section-head"><div><h2>计划—变化—执行账本</h2><p>策略质量、用户执行和数据完整度分别评价，不用单日盈亏盖棺定论。</p></div><span class="status pending">P0 只读版本链</span></div>
    <div class="ledger"><table><thead><tr><th>对象</th><th>计划版本</th><th>盘前计划</th><th>新证据与变化</th><th>实际触发</th><th>用户响应</th><th>后验状态</th></tr></thead><tbody>{rows}</tbody></table></div>
  </section>
  <div class="portfolio-layout">
    <section class="panel section">
      <div class="section-head"><div><h2>后验统计成熟度</h2><p>使用已有 signal_outcomes；样本不足继续保持 pending。</p></div><strong>{matured_total} 个成熟窗口</strong></div>
      <div class="maturity">{maturity_bars}</div>
      <div class="risk-list">
        <div class="risk-row"><span>T+1 命中率</span><strong>{_rate(one_day.get("hit_rate"))}</strong></div>
        <div class="risk-row"><span>T+5 命中率</span><strong>{_rate(five_day.get("hit_rate"))}</strong></div>
        <div class="risk-row"><span>T+20 命中率</span><strong>{_rate(twenty_day.get("hit_rate"))}</strong></div>
        <div class="risk-row"><span>市场环境分层</span><strong>未接入此账本</strong></div>
      </div>
    </section>
    <section class="panel section">
      <div class="section-head"><div><h3>评价边界</h3><p>只展示可核验事实。</p></div></div>
      <div class="risk-list">
        <div class="risk-row"><span>规则事前声明</span><strong>{len(versions)} 条</strong></div>
        <div class="risk-row"><span>用户确认/异议留痕</span><strong>{len(responses)} 条</strong></div>
        <div class="risk-row"><span>真实成交执行流水</span><strong class="danger-text">未接入</strong></div>
        <div class="risk-row"><span>完整复盘编排</span><strong class="amber-text">P1 待建设</strong></div>
      </div>
    </section>
  </div>
</section>"""


def _data_drawer(workspace: Mapping[str, object]) -> str:
    rows = _dict_rows(workspace.get("data_health"))
    cards = "".join(
        f'<article class="timeline-item"><small>{escape(str(item.get("label") or item.get("id") or "未命名来源"))} · '
        f'<span class="source {_status_class(item.get("status"))}">{escape(str(item.get("status") or "missing"))}</span></small>'
        f'<strong>{escape(str(item.get("gap_reason") or "来源在声明的新鲜度窗口内可用。"))}</strong>'
        f'<p>来源：{escape(str(item.get("source_name") or "unknown"))} · 数据时间：{escape(str(item.get("source_time") or "unknown"))}</p>'
        f'<p>抓取时间：{escape(str(item.get("fetched_at") or "unknown"))}</p>'
        f'<p>规则：{escape(str(item.get("freshness_rule") or "unknown"))}</p></article>'
        for item in rows
    )
    if not cards:
        cards = _empty("没有数据状态记录", "当前报告缺少统一 data_health 契约。")
    return f"""<div class="drawer-backdrop" id="data-backdrop" hidden>
      <aside class="drawer" id="data-drawer" role="dialog" aria-modal="true" aria-labelledby="data-drawer-title" tabindex="-1">
        <div class="drawer-head"><div><div class="eyebrow">Evidence / Status / Change Log</div><h2 id="data-drawer-title">数据状态与降级边界</h2></div>
        <button class="btn small" id="data-status-close" type="button" aria-label="关闭数据状态">关闭</button></div>
        <div class="prototype-note">ready / stale / missing / blocked 均来自真实 payload；没有数据时不生成假值。</div>
        <div class="timeline">{cards}</div>
      </aside>
    </div>"""


def _metric(label: str, value: object, suffix: str) -> str:
    shown = "unknown" if value is None or value == "" else f"{value}{suffix}"
    return f'<article class="metric"><span>{escape(label)}</span><b>{escape(str(shown))}</b></article>'


def _empty(title: str, body: str) -> str:
    return f'<div class="empty-state"><h2>{escape(title)}</h2><p>{escape(body)}</p></div>'


def _stage_label(workspace: Mapping[str, object]) -> str:
    return "晨间复核" if workspace.get("run_stage") == "morning_recheck" else "盘后生成"


def _runtime_label(workspace: Mapping[str, object]) -> str:
    return "等待人工确认" if workspace.get("runtime_status") == "awaiting_confirmation" else "已完成回应"


def _plan_status(value: str) -> str:
    return {
        "new": "新计划",
        "revised": "已修订",
        "voided": "已作废",
        "unchanged": "沿用",
        "blocked": "被阻断",
    }.get(value, value)


def _response_label(value: str) -> str:
    return {
        "pending": "待确认",
        "accepted": "已确认",
        "disputed": "有异议",
        "rejected": "已拒绝",
        "deferred": "稍后决定",
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


def _rate(value: object) -> str:
    return f"{float(value):.0%}" if isinstance(value, (int, float)) else "Pending"


def _status_class(value: object) -> str:
    clean = str(value or "pending").lower()
    if clean in {"ready", "accepted", "unchanged", "reviewed"}:
        return "ready"
    if clean in {"stale", "deferred", "revised", "pending", "new", "awaiting_confirmation"}:
        return "pending"
    return "blocked"


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _dict_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


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
  today:["08:30 Decision Workspace","今日计划"],
  portfolio:["Portfolio Risk Cockpit","组合风险"],
  lookup:["Research by Intent","标的研究"],
  review:["Review · Strategy ≠ Execution","复盘账本"],
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
  window.scrollTo({top:0, behavior:"auto"});
  window.requestAnimationFrame(() => window.scrollTo({top:0, behavior:"auto"}));
}
function setRoute(route) {
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  selectRoute(route);
}
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => setRoute(button.dataset.view)));
document.querySelectorAll("[data-view-link]").forEach(button => button.addEventListener("click", () => setRoute(button.dataset.viewLink)));
window.addEventListener("hashchange", () => setRoute(location.hash.slice(1)));
const initialRoute = location.hash.slice(1) || "today";
setRoute(initialRoute);
function openDrawer() {
  lastFocus = document.activeElement;
  const backdrop = document.getElementById("data-backdrop");
  backdrop.hidden = false;
  document.body.classList.add("drawer-open");
  document.getElementById("data-drawer").focus();
}
function closeDrawer() {
  const backdrop = document.getElementById("data-backdrop");
  backdrop.hidden = true; document.body.classList.remove("drawer-open");
  if (lastFocus) lastFocus.focus();
}
document.getElementById("data-status-open").addEventListener("click", openDrawer);
document.querySelectorAll("[data-open-data]").forEach(button => button.addEventListener("click", openDrawer));
document.getElementById("data-status-close").addEventListener("click", closeDrawer);
document.getElementById("data-backdrop").addEventListener("click", event => { if (event.target.id === "data-backdrop") closeDrawer(); });
document.addEventListener("keydown", event => { if (event.key === "Escape" && !document.getElementById("data-backdrop").hidden) closeDrawer(); });
async function post(path, body) {
  if (!token || token === "__LOCAL_SESSION_TOKEN__") throw new Error("请从 InsightRadar 本地应用打开，静态报告只能只读查看。");
  const response = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json","X-InsightRadar-Token":token}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "本地请求失败");
  return result;
}
document.querySelectorAll("[data-plan-response]").forEach(button => button.addEventListener("click", async () => {
  const card = button.closest("[data-plan-id]");
  const noteInput = card.querySelector("[data-response-note]");
  const note = noteInput ? noteInput.value : "";
  card.querySelectorAll("button").forEach(item => item.disabled = true);
  try {
    const record = await post("/api/plan-response", {plan_id:card.dataset.planId, plan_version:card.dataset.planVersion, response:button.dataset.planResponse, note});
    const label = card.querySelector("[data-response-label]");
    const labels = {accepted:"已写入今日计划版本", disputed:"异议已记录", rejected:"旧计划已确认作废", deferred:"已标记稍后处理", blocked_acknowledged:"已知悉阻断"};
    if (label) {
      label.textContent = labels[record.response] || record.response;
      label.className = `source ${record.response === "accepted" ? "user" : record.response === "rejected" ? "blocked" : "ai"}`;
    }
    button.textContent = labels[record.response] || record.response;
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
"""


def _css() -> str:
    return """
:root{color-scheme:dark;--bg:#06101a;--sidebar:#050d16;--panel:#0c1a28;--panel2:#102233;--panel3:#142a3d;--line:rgba(137,169,198,.16);--line2:rgba(137,169,198,.29);--text:#f4f1e9;--muted:#91a6b8;--blue:#70ace4;--blue2:#a9d2f7;--amber:#dda84c;--amber2:#f1c56f;--danger:#df746e;--good:#79b8ae;--violet:#c7b9ed;--shadow:0 18px 56px rgba(0,0,0,.31);--radius:16px}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font:14px/1.55 Inter,"Segoe UI","Microsoft YaHei",sans-serif}body{background:radial-gradient(circle at 78% -18%,rgba(43,91,137,.22),transparent 38%),linear-gradient(180deg,#081521 0,#07111b 58%,#050c13 100%);overflow-x:hidden}button,input,select{font:inherit}button{cursor:pointer}button:disabled{opacity:.48;cursor:not-allowed}a{color:inherit}button:focus-visible,input:focus-visible,select:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.app{display:grid;grid-template-columns:228px minmax(0,1fr);min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;padding:22px 16px;border-right:1px solid var(--line);background:rgba(5,13,22,.92);backdrop-filter:blur(18px);z-index:30}.brand{display:flex;align-items:center;gap:11px;padding:0 8px 24px;font-size:16px;font-weight:820}.brand-mark{display:grid;place-items:center;width:32px;height:32px;border:1px solid rgba(112,172,228,.42);border-radius:10px;color:var(--blue2);background:rgba(112,172,228,.1)}.brand small{display:block;color:var(--muted);font-size:9px;font-weight:650;letter-spacing:.08em;text-transform:uppercase}.nav{display:grid;gap:7px}.nav button{display:flex;align-items:center;justify-content:space-between;width:100%;padding:11px 12px;border:0;border-radius:11px;color:var(--muted);text-align:left;background:transparent}.nav button:hover{color:var(--text);background:rgba(255,255,255,.035)}.nav button.active{color:var(--text);background:linear-gradient(90deg,rgba(112,172,228,.17),rgba(112,172,228,.035))}.nav button small{font-size:10px;color:#6f8496}.nav .count{min-width:23px;padding:1px 6px;border:1px solid var(--line);border-radius:999px;text-align:center}.sidebar-card{position:absolute;right:16px;bottom:18px;left:16px;padding:12px;border:1px solid var(--line);border-radius:13px;color:var(--muted);font-size:11px;background:rgba(255,255,255,.022)}.sidebar-card strong{display:block;margin-bottom:5px;color:var(--text)}
.content{min-width:0;padding:24px clamp(18px,3vw,44px) 80px}.topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;max-width:1340px;margin:0 auto 19px}.eyebrow{color:var(--blue);font-size:10px;font-weight:820;letter-spacing:.14em;text-transform:uppercase}h1{margin:3px 0 0;font-size:clamp(25px,3vw,38px);line-height:1.15;letter-spacing:-.025em}h2,h3,p{margin-top:0}.top-actions,.inline,.data-state,.legend,.evidence-row,.card-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.chip,.tag,.source,.status{display:inline-flex;align-items:center;gap:6px;min-height:26px;padding:4px 9px;border:1px solid var(--line);border-radius:999px;color:var(--muted);font-size:10px;background:rgba(255,255,255,.025)}.chip::before,.status-dot{content:"";width:6px;height:6px;border-radius:50%;background:var(--blue);box-shadow:0 0 10px rgba(112,172,228,.55)}.source.rule,.source.ready{color:var(--blue2);border-color:rgba(112,172,228,.34);background:rgba(112,172,228,.08)}.source.ai,.source.pending{color:var(--amber2);border-color:rgba(221,168,76,.36);background:rgba(221,168,76,.08)}.source.user{color:var(--good);border-color:rgba(121,184,174,.36);background:rgba(121,184,174,.08)}.source.research{color:var(--violet);border-color:rgba(199,185,237,.3);background:rgba(199,185,237,.07)}.source.blocked{color:var(--danger);border-color:rgba(223,116,110,.32);background:rgba(223,116,110,.07)}
.stage{max-width:1340px;margin:0 auto}.view{display:none}.view.active{display:block}.panel{border:1px solid var(--line);border-radius:var(--radius);background:linear-gradient(155deg,rgba(16,34,51,.97),rgba(8,20,31,.97));box-shadow:var(--shadow)}.section{padding:18px 20px}.section-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}.section-head h2,.section-head h3{margin:0}.section-head p{margin:3px 0 0;color:var(--muted);font-size:11px}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:36px;padding:8px 13px;border:1px solid var(--line2);border-radius:10px;color:var(--text);text-decoration:none;background:rgba(255,255,255,.03)}.btn:hover{border-color:#49657e;background:rgba(255,255,255,.055)}.btn.primary{border-color:var(--text);color:#09131d;font-weight:820;background:var(--text)}.btn.ghost{border-color:transparent;color:var(--muted);background:transparent}.btn.danger{color:var(--danger);border-color:rgba(223,116,110,.29)}.btn.small{min-height:31px;padding:6px 10px;font-size:11px}
.runtime-strip{display:grid;grid-template-columns:minmax(230px,1.05fr) repeat(3,minmax(160px,.72fr));overflow:hidden;margin-bottom:12px}.runtime-cell{padding:13px 16px;border-left:1px solid var(--line)}.runtime-cell:first-child{border-left:0}.runtime-cell small{display:block;color:var(--muted)}.runtime-cell strong{display:block;margin:4px 0 1px}.runtime-cell em{color:var(--muted);font-size:10px;font-style:normal}.market-gate{display:grid;grid-template-columns:minmax(190px,.9fr) repeat(2,minmax(180px,1fr)) minmax(180px,.75fr);overflow:hidden}.market-gate>div{padding:16px 18px;border-left:1px solid var(--line)}.market-gate>div:first-child{border-left:0}.market-gate strong{display:block;margin:6px 0 3px;font-size:18px}.market-gate small{color:var(--muted)}.danger-text,.blocked-text{color:var(--danger)!important}.amber-text,.pending-text{color:var(--amber)!important}.fresh{color:var(--blue2)!important}.good-text,.ready-text{color:var(--good)!important}.theme-line{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:13px;margin-top:10px;padding:12px 15px;border:1px solid rgba(221,168,76,.25);border-radius:13px;color:var(--muted);background:rgba(221,168,76,.055)}.theme-line strong{color:var(--amber)}
.today-layout{display:grid;grid-template-columns:minmax(0,1.46fr) minmax(320px,.58fr);gap:14px;margin-top:18px}.change-card{padding:18px 20px}.change-title{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:15px}.change-title h2{margin:2px 0 0;font-size:25px}.change-type{font-size:11px;font-weight:820}.change-type.pending{color:var(--amber)}.change-type.blocked{color:var(--danger)}.change-type.ready{color:var(--good)}.diff-grid{display:grid;grid-template-columns:1fr 42px 1fr;gap:10px;align-items:stretch}.diff-box{padding:13px 14px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.02)}.diff-box.state-change{margin-bottom:10px}.diff-box small{display:block;margin-bottom:5px;color:var(--muted)}.diff-box strong{font-size:15px}.diff-arrow{display:grid;place-items:center;color:var(--muted);font-size:19px}.reason-box{margin-top:10px;padding:12px 14px;border-left:3px solid var(--amber);color:#d6e0e9;background:rgba(221,168,76,.065)}.reason-box.danger{border-color:var(--danger);background:rgba(223,116,110,.065)}.provenance{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:10px}.prov{padding:10px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.018)}.prov small{display:block;color:var(--muted)}.prov strong{display:block;margin-top:3px;font-size:11px}.rules{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin-top:12px;border:1px solid var(--line);border-radius:12px;overflow:hidden}.rules.single-column{grid-template-columns:1fr}.rule-item{padding:12px 13px;border-left:1px solid var(--line)}.rule-item:first-child{border-left:0}.rule-item b{display:block;margin-bottom:6px;color:var(--blue2);font-size:10px;letter-spacing:.08em}.rule-item.invalid b{color:var(--danger)}.rule-item span{font-size:11px;color:#d4dee7}.card-footer{display:flex;justify-content:space-between;gap:12px;align-items:flex-end;margin-top:14px}.evidence-row{color:var(--muted);font-size:10px}.response-box{display:grid;grid-template-columns:minmax(180px,1fr) auto;gap:10px;align-items:end}.response-box>.prototype-note{grid-column:1/-1;margin-top:0}.response-box label{color:var(--muted);font-size:10px}.response-box .input{display:block;width:100%;margin-top:4px}.response-box.compact{margin-top:12px}.queue{display:grid;gap:10px;margin-top:10px}.queue-item{display:grid;grid-template-columns:42px minmax(180px,.65fr) minmax(240px,1.2fr) auto;gap:14px;align-items:center;padding:14px 16px;border:1px solid var(--line);border-radius:14px;background:rgba(12,27,41,.83)}.queue-number{color:var(--blue);font-size:20px;font-weight:820}.queue-item h3{margin:3px 0 0;font-size:17px}.queue-item p{margin:0;color:var(--muted);font-size:11px}.queue-item p strong{color:var(--text)}.queue-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.queue-detail{grid-column:2/-1}.queue-detail[hidden]{display:none}
.side-stack{display:grid;gap:12px;align-content:start}.risk-meter,.handoff,.data-health{padding:18px 19px}.metric-title{display:flex;justify-content:space-between;align-items:center;gap:10px}.metric-title strong{font-size:17px}.bar{height:9px;margin:10px 0 5px;border-radius:999px;background:#142637;overflow:hidden}.bar span{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--blue),#9cc5ea)}.risk-list{display:grid;margin-top:8px}.risk-row{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-top:1px solid var(--line);color:var(--muted);font-size:11px}.risk-row strong{color:var(--text);text-align:right}.risk-row.warn strong{color:var(--amber)}.risk-row.danger strong{color:var(--danger)}.handoff{border-color:rgba(112,172,228,.28);background:rgba(112,172,228,.05)}.handoff strong{display:block;margin:4px 0;color:var(--amber)}.handoff p,.data-health p{margin:0;color:var(--muted);font-size:11px}
.metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px}.metric{padding:15px 16px;border:1px solid var(--line);border-radius:14px;background:rgba(12,27,41,.82)}.metric small{display:block;color:var(--muted)}.metric strong{display:block;margin:5px 0 2px;font-size:22px}.metric em{color:var(--muted);font-size:10px;font-style:normal}.portfolio-layout{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(300px,.55fr);gap:14px;margin-top:14px}.exposure-list{display:grid;gap:10px}.exposure-item{display:grid;grid-template-columns:130px 1fr 62px;align-items:center;gap:12px}.exposure-item span{color:var(--muted);font-size:11px}.exposure-item b{text-align:right;font-size:11px}.holdings-section,.ledger-section{margin-top:14px}.table-wrap{max-width:100%;overflow:auto;border:1px solid var(--line);border-radius:13px}table{width:100%;border-collapse:collapse;min-width:880px}th,td{padding:12px 13px;border-top:1px solid var(--line);text-align:left;vertical-align:middle}th{border-top:0;color:var(--muted);font-size:9px;letter-spacing:.08em;text-transform:uppercase;background:rgba(255,255,255,.025)}td small{display:block;color:var(--muted)}.pnl.up{color:var(--danger)}.pnl.down{color:var(--good)}
.form-grid{display:grid;grid-template-columns:minmax(220px,1fr) repeat(3,minmax(150px,.45fr)) auto;gap:8px}.input,.select{min-height:39px;padding:8px 11px;border:1px solid var(--line2);border-radius:10px;color:var(--text);background:rgba(4,13,22,.68)}.lookup-result{display:grid;grid-template-columns:minmax(0,1.18fr) minmax(350px,.72fr);gap:14px;margin-top:14px}.chart-empty{min-height:245px;display:grid;place-content:center;gap:8px;padding:28px;text-align:center;border:1px dashed var(--line2);border-radius:13px;color:var(--muted);background:rgba(4,13,22,.45)}.chart-empty strong{color:var(--text);font-size:16px}.research-metrics{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:12px}.objective-banner{padding:11px 12px;border-left:3px solid var(--blue);color:var(--muted);background:rgba(112,172,228,.065)}.analysis-title{margin:4px 0 11px}.evidence-list{display:grid;gap:8px;margin-top:12px}.evidence-item{padding:11px 12px;border:1px solid var(--line);border-radius:11px;background:rgba(255,255,255,.018)}.evidence-item strong{display:flex;justify-content:space-between;gap:10px}.evidence-item p{margin:5px 0 0;color:var(--muted);font-size:10px}.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}.tab{min-height:31px;padding:6px 10px;border:1px solid var(--line);border-radius:9px;color:var(--muted);background:transparent}.tab.active{color:var(--text);border-color:rgba(112,172,228,.45);background:rgba(112,172,228,.08)}.tab-panel{display:none;margin-top:10px}.tab-panel.active{display:block}.source-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:12px}.source-card{padding:11px;border:1px solid var(--line);border-radius:11px;background:rgba(255,255,255,.018)}.source-card small{display:block;color:var(--muted)}.source-card strong{display:block;margin:4px 0}.source-card em{font-size:10px;font-style:normal;color:var(--muted)}
.review-top{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px}.score-card{padding:16px;border:1px solid var(--line);border-radius:14px;background:rgba(12,27,41,.82)}.score-card small{display:block;color:var(--muted)}.score-card strong{display:block;margin-top:5px;font-size:22px}.score-card .date-score{font-size:15px}.ledger{overflow:auto;border:1px solid var(--line);border-radius:13px}.maturity{display:grid;grid-template-columns:repeat(10,1fr);gap:5px;margin:12px 0}.maturity i{height:8px;border-radius:999px;background:rgba(255,255,255,.08)}.maturity i.done{background:var(--blue)}.maturity i.current{background:var(--amber)}
.drawer-backdrop{position:fixed;inset:0;display:flex;justify-content:flex-end;background:rgba(0,0,0,.58);backdrop-filter:blur(3px);z-index:100}.drawer-backdrop[hidden]{display:none}.drawer{width:min(560px,94vw);height:100%;overflow:auto;padding:24px;border-left:1px solid var(--line2);background:#091724;box-shadow:-20px 0 55px rgba(0,0,0,.35);outline:0}.drawer-head{display:flex;justify-content:space-between;gap:15px;align-items:flex-start}.drawer h2{margin:5px 0 0}.timeline{display:grid;gap:10px;margin-top:18px}.timeline-item{position:relative;padding:13px 14px 13px 18px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.02)}.timeline-item:before{content:"";position:absolute;left:8px;top:18px;width:5px;height:5px;border-radius:50%;background:var(--blue)}.timeline-item small{display:block;color:var(--muted)}.timeline-item strong{display:block;margin-top:4px}.timeline-item p{margin:7px 0 0;color:var(--muted);font-size:10px}.toast{position:fixed;right:22px;bottom:22px;z-index:120;transform:translateY(18px);opacity:0;padding:10px 13px;border:1px solid var(--line2);border-radius:11px;background:#102536;box-shadow:var(--shadow);transition:.18s;pointer-events:none}.toast.visible{transform:translateY(0);opacity:1}.toast.success{border-color:rgba(121,184,174,.45)}.toast.error{border-color:rgba(223,116,110,.45)}.mobile-nav{display:none}.prototype-note{margin-top:12px;padding:11px 13px;border:1px dashed rgba(137,169,198,.25);border-radius:12px;color:var(--muted);font-size:10px}.empty-state{min-height:220px;display:grid;place-content:center;padding:22px;text-align:center;border:1px dashed var(--line2);border-radius:var(--radius);color:var(--muted);background:rgba(12,27,41,.6)}.empty-state h2{margin-bottom:6px;color:var(--text)}
@media(max-width:1120px){.today-layout,.portfolio-layout,.lookup-result{grid-template-columns:1fr}.side-stack{grid-template-columns:repeat(3,minmax(0,1fr))}.metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.form-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.form-grid .btn{grid-column:1/-1}.review-top{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:820px){.app{display:block}.sidebar{display:none}.content{padding:16px 12px 90px}.topbar{display:block;margin-bottom:14px}.top-actions{margin-top:10px}.runtime-strip,.market-gate{grid-template-columns:repeat(2,minmax(0,1fr))}.runtime-cell:first-child,.market-gate>div:first-child{grid-column:1/-1}.runtime-cell:nth-child(2),.market-gate>div:nth-child(2){border-left:0}.theme-line{grid-template-columns:1fr}.rules,.provenance,.source-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.rule-item:nth-child(3),.prov:nth-child(3){border-left:0}.queue-item{grid-template-columns:34px 1fr}.queue-item>:nth-child(3),.queue-actions,.queue-detail{grid-column:2}.queue-actions{justify-content:flex-start}.side-stack{grid-template-columns:1fr}.metrics,.review-top{grid-template-columns:repeat(2,minmax(0,1fr))}.mobile-nav{position:fixed;right:0;bottom:0;left:0;z-index:80;display:grid;grid-template-columns:repeat(4,1fr);padding:7px 8px calc(7px + env(safe-area-inset-bottom));border-top:1px solid var(--line);background:rgba(5,13,22,.96);backdrop-filter:blur(16px)}.mobile-nav button{display:block;min-height:43px;border:0;border-radius:9px;color:var(--muted);background:transparent;text-align:center}.mobile-nav button.active{color:var(--text);background:rgba(112,172,228,.1)}.mobile-nav button span{display:inline}.card-footer,.response-box{display:block}.card-actions{margin-top:10px}}
@media(max-width:520px){.runtime-strip,.market-gate,.rules,.provenance,.source-grid,.metrics,.review-top,.form-grid,.research-metrics{display:block}.runtime-cell,.market-gate>div,.rule-item,.prov,.source-card,.metric,.score-card{border-left:0;border-top:1px solid var(--line);margin-top:7px}.runtime-cell:first-child,.market-gate>div:first-child,.rule-item:first-child{border-top:0}.diff-grid{grid-template-columns:1fr}.diff-arrow{transform:rotate(90deg)}.card-footer,.section-head{display:block}.card-actions,.section-head>.inline{margin-top:10px}.change-title h2{font-size:21px}.content{padding-left:10px;padding-right:10px}.top-actions .chip:first-child{display:none}.btn,.input,.select{min-height:44px}}
"""
