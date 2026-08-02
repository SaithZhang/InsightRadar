"""After-close portfolio guidance workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from stock_assist.after_close_workbench import build_market_matrix_contract
from stock_assist.after_close_workbench_html import render_after_close_workbench
from stock_assist.data_sources.cninfo import latest_profit_notice
from stock_assist.data_sources.contracts import ProviderResult
from stock_assist.data_sources.global_markets import (
    MarketIndexSnapshot,
    fetch_global_market_groups,
)
from stock_assist.data_sources.xysz import (
    AmazingDataClient,
    AmazingDataError,
    daily_kline_result_for_code,
)
from stock_assist.decision_workspace import build_decision_workspace
from stock_assist.execution_plans import build_holding_execution_plans
from stock_assist.holding_decision import HoldingDecision, build_holding_decision
from stock_assist.paths import CONFIG_DIR, DATA_DIR, REPORT_DIR
from stock_assist.portfolio import Holding, Portfolio, load_portfolio
from stock_assist.report_payload import (
    create_report_payload,
    first_markdown_title,
    markdown_sections,
    section_items,
)
from stock_assist.reports import bullet
from stock_assist.signal_outcomes import (
    CODE_PATTERN,
    load_outcome_snapshot,
    outcome_markdown_lines,
    refresh_signal_outcomes,
)
from stock_assist.unified_decision import (
    build_unified_decision,
    inject_unified_decision,
)
from stock_assist.workflows.influencer_sentiment import load_thread_sentiments
from stock_assist.workflows.influencer_skills import (
    InfluencerObservation,
    load_observations,
)


@dataclass(frozen=True)
class HoldingSignal:
    holding: Holding
    action: str
    reason: str
    data_gap: str = ""
    position_action: str = ""
    upside_trigger: str = ""
    downside_trigger: str = ""
    flat_trigger: str = ""
    priority: str = "中"
    decision_contract: dict[str, object] | None = None


LITHIUM_PEERS = {
    "002240.SZ": "盛新锂能",
    "002497.SZ": "雅化集团",
    "002466.SZ": "天齐锂业",
    "002460.SZ": "赣锋锂业",
    "002192.SZ": "融捷股份",
    "002738.SZ": "中矿资源",
    "300390.SZ": "天华新能",
}

PEER_GROUPS = {
    "688126.SH": {
        "name": "半导体材料",
        "codes": {
            "688126.SH": "沪硅产业",
            "688019.SH": "安集科技",
            "300666.SZ": "江丰电子",
            "688233.SH": "神工股份",
        },
        "anchor": "半导体材料国产替代、订单验证和估值承接。",
    },
    "002240.SZ": {
        "name": "锂矿/锂盐",
        "codes": LITHIUM_PEERS,
        "anchor": "锂盐价格、业绩预告兑现和同业估值锚。",
    },
    "688008.SH": {
        "name": "AI/存储硬件",
        "codes": {
            "688008.SH": "澜起科技",
            "688041.SH": "海光信息",
            "688256.SH": "寒武纪",
            "603986.SH": "兆易创新",
        },
        "anchor": "AI算力、存储周期和国产芯片估值承接。",
    },
    "002463.SZ": {
        "name": "AI服务器PCB",
        "codes": {
            "002463.SZ": "沪电股份",
            "300308.SZ": "中际旭创",
            "300502.SZ": "新易盛",
            "002916.SZ": "深南电路",
        },
        "anchor": "AI服务器链条、订单兑现和高位趋势承接。",
    },
    "601899.SH": {
        "name": "金铜资源",
        "codes": {
            "601899.SH": "紫金矿业",
            "603993.SH": "洛阳钼业",
            "600547.SH": "山东黄金",
            "000975.SZ": "山金国际",
        },
        "anchor": "铜金价格、资源品风险偏好和全球流动性。",
    },
}

EVENT_CALENDAR_PATH = CONFIG_DIR / "event_calendar.json"
EVENT_CALENDAR_EXAMPLE_PATH = CONFIG_DIR / "event_calendar.example.json"


def build_after_close_report(
    client: AmazingDataClient | None = None,
    portfolio: Portfolio | None = None,
    lookback_days: int = 90,
) -> str:
    portfolio = portfolio or load_portfolio()
    observations = load_observations()
    thread_sentiments = load_thread_sentiments()
    market_groups = fetch_global_market_groups()
    gaps: list[str] = []
    optional_gaps: list[str] = []
    signals: list[HoldingSignal] = []
    active_client: AmazingDataClient | None = None

    if portfolio.missing:
        if portfolio.source_note:
            gaps.append(f"持仓文件不可用：{portfolio.source_note}（{portfolio.source}）")
        else:
            gaps.append(f"未找到持仓文件：{portfolio.source}")
    if not portfolio.holdings:
        gaps.append("当前没有可分析持仓；请先维护 data/portfolio.manual.tsv 或 data/portfolio.json")
    if not observations:
        optional_gaps.append("未采集大V观点流水：data/influencer_observations.jsonl")
    gaps.extend(_portfolio_snapshot_gaps(portfolio))
    market_gap_lines = _global_market_gap_lines(market_groups)
    if market_gap_lines:
        gaps.extend(market_gap_lines)

    if portfolio.holdings and portfolio.context_missing:
        gaps.append(f"未找到组合上下文文件：{portfolio.context_source}，买入逻辑、初始风控线、调仓记录和复盘状态待补。")
    if portfolio.holdings and not portfolio.context_missing:
        missing_current_context = [
            holding.name or holding.code
            for holding in portfolio.holdings
            if not _current_decision_context_complete(holding)
        ]
        if missing_current_context:
            gaps.append(
                "部分持仓当前风险上下文未补全："
                + ", ".join(missing_current_context)
            )
        missing_historical_context = [
            holding.name or holding.code
            for holding in portfolio.holdings
            if not _historical_context_complete(holding)
        ]
        if missing_historical_context:
            optional_gaps.append(
                "部分持仓历史买入上下文未知（仅影响复盘，不阻断当前风险计划）："
                + ", ".join(missing_historical_context)
            )
    event_config, event_config_gaps = _load_event_calendar()
    gaps.extend(event_config_gaps)

    if portfolio.holdings:
        try:
            active_client = client or AmazingDataClient()
            signals = _build_signals(active_client, portfolio.holdings, lookback_days)
        except AmazingDataError as exc:
            gaps.append(f"AmazingData 不可用：{exc}")
            signals = [_signal_from_broker_snapshot(holding) for holding in portfolio.holdings]

    try:
        outcome_snapshot = refresh_signal_outcomes(
            active_client,
            [
                {
                    "signal_date": date.today().isoformat(),
                    "code": signal.holding.code,
                    "name": signal.holding.name or signal.holding.code,
                    "action": signal.action,
                    "priority": signal.priority,
                    "reason": signal.reason,
                }
                for signal in signals
            ],
        )
    except Exception as exc:
        gaps.append(f"信号后验刷新失败：{exc}")
        outcome_snapshot = load_outcome_snapshot()

    for signal in signals:
        if signal.data_gap:
            gaps.append(f"{signal.holding.name or signal.holding.code}：{signal.data_gap}")

    lines = [
        "# 盘后持仓操作指引",
        "",
        "## 数据缺口",
        "__CORE_DATA_GAPS__",
        "",
        "## Core可靠性",
        "__CORE_RELIABILITY__",
        "",
        "## 可选扩展缺口",
        "__OPTIONAL_EXTENSION_GAPS__",
        "",
        "## 跨市场宏观温度",
        _global_market_section(market_groups),
        "",
        "## 持仓动作",
    ]
    if signals:
        for signal in signals:
            title = signal.holding.name or signal.holding.code
            lines.extend(
                [
                    f"### {title}（{signal.holding.code}）",
                    f"- 建议动作：{signal.action}",
                    f"- 核心理由：{signal.reason}",
                    f"- 原始逻辑：{signal.holding.thesis or '未填写'}",
                    f"- 风险线：{signal.holding.risk_line or '未填写'}",
                ]
            )
            if signal.data_gap:
                lines.append(f"- 待补数据：{signal.data_gap}")
            if signal.position_action:
                lines.append(f"- 仓位动作：{signal.position_action}")
            if signal.upside_trigger:
                lines.append(f"- 上行条件：{signal.upside_trigger}")
            if signal.downside_trigger:
                lines.append(f"- 下行条件：{signal.downside_trigger}")
            if signal.flat_trigger:
                lines.append(f"- 震荡处理：{signal.flat_trigger}")
            if signal.priority:
                lines.append(f"- 明日优先级：{signal.priority}")
            if signal.decision_contract:
                lines.append(
                    "- 决策契约："
                    + json.dumps(
                        signal.decision_contract,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
    else:
        lines.append("- 暂无持仓动作。")

    lines.extend(["", "## 信号后验评分", bullet(outcome_markdown_lines(outcome_snapshot))])

    broker_lines = _broker_snapshot_lines(portfolio)
    if broker_lines:
        lines.extend(["", "## 券商持仓快照", bullet(broker_lines)])

    context_lines = _portfolio_context_lines(portfolio)
    if context_lines:
        lines.extend(["", "## 组合上下文与复盘状态", bullet(context_lines)])

    hypothesis_lines = _research_hypothesis_lines(portfolio)
    if hypothesis_lines:
        lines.extend(["", "## 研究假设与反证", bullet(hypothesis_lines)])

    research_delta_lines = _research_delta_lines(portfolio)
    if research_delta_lines:
        lines.extend(["", "## 研报观点变化", bullet(research_delta_lines)])

    peer_lines: list[str] = []
    if active_client is not None:
        try:
            peer_lines = _peer_comparison_lines(active_client, portfolio)
        except AmazingDataError as exc:
            gaps.append(f"同业比较数据不可用：{exc}")
        except Exception as exc:
            gaps.append(f"同业比较解析失败：{exc}")
    if peer_lines:
        lines.extend(["", "## 同业比较证据", bullet(peer_lines)])

    profit_notice_lines: list[str] = []
    if active_client is not None:
        try:
            profit_notice_lines = _profit_notice_peer_lines(active_client, portfolio)
        except AmazingDataError as exc:
            gaps.append(f"业绩预告数据不可用：{exc}")
        except Exception as exc:
            gaps.append(f"业绩预告解析失败：{exc}")
    if profit_notice_lines:
        lines.extend(["", "## 业绩预告与同业定价", bullet(profit_notice_lines)])

    fresh_filing_lines = _fresh_cninfo_filing_lines(portfolio)
    if fresh_filing_lines:
        lines.extend(["", "## 巨潮最新公告直连", bullet(fresh_filing_lines)])

    event_lines = _event_calendar_lines(portfolio, event_config, fresh_filing_lines)
    if event_lines:
        lines.extend(["", "## 事件日历与公告 watchlist", bullet(event_lines)])

    lines.extend(
        [
            "",
            "## 外部观点观察",
            bullet(_external_view_lines(observations, portfolio, active_client)),
            "",
            "## 大V回复情绪",
            bullet(
                [
                    f"{item.thread.author} / {item.thread.observation_id}：{item.label}，score={item.score:.2f}，"
                    f"支持 {item.supportive} / 质疑 {item.skeptical} / 疑问 {item.questions} / 噪音 {item.noise}"
                    for item in thread_sentiments[-5:]
                ]
            ),
        ]
    )
    lines.extend(
        [
            "",
            "## 明日检查清单",
            "- 先检查隔夜宏观、行业消息和个股公告，再执行动作。",
            "- 若价格触发风险线，优先执行减仓或退出纪律。",
            "- 若没有新增证据，不因单日波动放大仓位。",
        ]
    )
    gaps = _dedupe_text(gaps)
    reliability = _build_core_reliability(
        portfolio,
        [
            {
                "name": f"{signal.holding.name or signal.holding.code}（{signal.holding.code}）",
                "action": signal.action,
                "reason": signal.reason,
                "position_action": signal.position_action,
                "upside_trigger": signal.upside_trigger,
                "downside_trigger": signal.downside_trigger,
                "flat_trigger": signal.flat_trigger,
            }
            for signal in signals
        ],
        outcome_snapshot,
        gaps,
        optional_gaps,
    )
    return (
        "\n".join(lines)
        .replace("__CORE_DATA_GAPS__", bullet(gaps))
        .replace("__CORE_RELIABILITY__", bullet(_core_reliability_lines(reliability)))
        .replace("__OPTIONAL_EXTENSION_GAPS__", bullet(optional_gaps))
    )


def build_after_close_bundle(
    client: AmazingDataClient | None = None,
    portfolio: Portfolio | None = None,
    lookback_days: int = 90,
    report_dir: Path = REPORT_DIR,
) -> tuple[dict[str, object], str, str]:
    """Build the after-close payload plus the current Markdown/HTML renderers."""

    resolved_portfolio = portfolio or load_portfolio()
    base_markdown = build_after_close_report(client=client, portfolio=resolved_portfolio, lookback_days=lookback_days)
    preliminary = build_after_close_payload(
        base_markdown,
        portfolio=resolved_portfolio,
        report_dir=report_dir,
    )
    unified_decision = preliminary["unified_decision"]
    if isinstance(unified_decision, dict):
        budget = unified_decision.get("risk_budget") if isinstance(unified_decision.get("risk_budget"), dict) else {}
        actions = unified_decision.get("holding_plans") if isinstance(unified_decision.get("holding_plans"), list) else []
        unified_decision["holding_execution_plans"] = build_holding_execution_plans(
            [item for item in actions if isinstance(item, dict)],
            resolved_portfolio.holdings,
            budget,
        )
    markdown = inject_unified_decision(base_markdown, unified_decision)
    payload = build_after_close_payload(
        markdown,
        portfolio=resolved_portfolio,
        report_dir=report_dir,
        unified_decision=unified_decision,
    )
    return payload, markdown, render_after_close_workbench(payload, markdown)


def build_after_close_payload(
    markdown: str,
    portfolio: Portfolio | None = None,
    *,
    report_dir: Path = REPORT_DIR,
    unified_decision: dict[str, object] | None = None,
) -> dict[str, object]:
    sections = markdown_sections(markdown)
    data_gaps = _meaningful_data_gaps(
        section_items(sections, ("数据缺口", "鏁版嵁缂哄彛"), fallback_first=True)
    )
    optional_gaps = _meaningful_data_gaps(section_items(sections, ("可选扩展缺口",)))
    action_lines = _payload_action_lines(markdown)
    outcome_snapshot = load_outcome_snapshot()
    reliability = _build_core_reliability(
        portfolio or load_portfolio(),
        action_lines,
        outcome_snapshot,
        data_gaps,
        optional_gaps,
    )
    unified_decision = unified_decision or build_unified_decision(
        action_lines,
        reliability,
        report_dir=report_dir,
    )
    generated_at = datetime.now()
    market_matrix = build_market_matrix_contract(
        unified_decision,
        report_dir=report_dir,
        generated_at=generated_at,
    )
    outcome_1d = outcome_snapshot.get("horizons", {}).get("1d", {}) if isinstance(outcome_snapshot.get("horizons"), dict) else {}
    matured_1d = int(outcome_1d.get("matured", 0) or 0) if isinstance(outcome_1d, dict) else 0
    hit_rate_1d = outcome_1d.get("hit_rate") if isinstance(outcome_1d, dict) else None
    resolved_portfolio = portfolio or load_portfolio()
    payload = create_report_payload(
        kind="after_close",
        workflow="after-close",
        title=first_markdown_title(markdown, "盘后持仓操作指引"),
        generated_at=generated_at.isoformat(timespec="seconds"),
        summary_cards=[
            {
                "id": "tomorrow_plan",
                "label": "Tomorrow",
                "value": str(unified_decision.get("stance") or "等待确认"),
                "tone": "warn" if unified_decision.get("stance") != "条件进攻" else "ok",
                "note": str(unified_decision.get("first_action") or "补齐数据前不新增仓位。"),
            },
            {
                "id": "data_gaps",
                "label": "Data Gaps",
                "value": str(len(data_gaps)),
                "tone": "warn" if data_gaps else "ok",
                "note": "Missing inputs remain explicit in the report.",
            },
            {
                "id": "actions",
                "label": "Actions",
                "value": str(len(action_lines)),
                "tone": "warn" if action_lines else "ok",
                "note": "Conditional holding-level actions parsed from the report.",
            },
            {
                "id": "decision_ready_coverage",
                "label": "Decision-ready",
                "value": f"{int(reliability['decision_ready_holdings'])}/{int(reliability['holding_count'])}",
                "tone": "ok" if reliability["decision_ready_coverage"] == 1.0 else "warn",
                "note": "Strict coverage requires current holdings, complete snapshot fields, current risk context, action branches, and evaluated market data; unknown entry history limits review only.",
            },
            {
                "id": "sections",
                "label": "Sections",
                "value": str(len(sections)),
                "tone": "ok",
                "note": "Markdown sections are available for native clients.",
            },
            {
                "id": "outcomes",
                "label": "1D Outcomes",
                "value": f"{float(hit_rate_1d):.0%}" if isinstance(hit_rate_1d, (int, float)) else "Pending",
                "tone": "ok" if matured_1d else "warn",
                "note": f"{matured_1d} matured samples; pending samples are not scored early.",
            },
        ],
        components=[
            {"type": "summary_cards", "id": "summary", "items": "summary_cards"},
            {
                "type": "unified_decision",
                "id": "tomorrow_plan",
                "title": "明日统一指引",
                "items": "unified_decision",
            },
            {"type": "section_list", "id": "sections", "title": "Report Sections", "items": "sections"},
            {"type": "action_list", "id": "actions", "title": "Holding Actions", "items": "actions"},
            {
                "type": "reliability_scorecard",
                "id": "core_reliability",
                "title": "Core Reliability",
                "items": "reliability",
            },
            {
                "type": "signal_outcome_scorecard",
                "id": "signal_outcomes",
                "title": "Signal Outcomes",
                "items": "signal_outcomes",
            },
            {"type": "data_gaps", "id": "data_gaps", "title": "Data Gaps", "items": "data_gaps"},
        ],
        sections=sections,
        actions=action_lines,
        unified_decision=unified_decision,
        market_matrix=market_matrix,
        reliability=reliability,
        signal_outcomes=outcome_snapshot,
        data_gaps=data_gaps,
        renderers={
            "markdown": "reports/*-after-close.md",
            "html": "reports/*-after-close.html",
        },
    )
    payload["decision_workspace"] = build_decision_workspace(
        payload,
        resolved_portfolio,
        generated_at=generated_at,
    )
    return payload


def _portfolio_snapshot_gaps(portfolio: Portfolio) -> list[str]:
    if portfolio.missing or not portfolio.holdings:
        return []
    gaps: list[str] = []
    if not portfolio.as_of:
        gaps.append(f"持仓快照 {portfolio.source} 缺少 as_of，无法确认是否覆盖最新用户状态。")
    for holding in portfolio.holdings:
        missing = _holding_snapshot_missing_fields(holding)
        if missing:
            gaps.append(
                f"{holding.name or holding.code}持仓快照缺少{'、'.join(missing)}；"
                "对应的成本/盈利保护判断将降级，禁止用0值代替。"
            )
    return gaps


def _holding_snapshot_missing_fields(holding: Holding) -> list[str]:
    missing: list[str] = []
    if holding.shares is None:
        missing.append("股数")
    if holding.cost is None or holding.cost <= 0:
        missing.append("成本")
    if holding.market_price is None or holding.market_price <= 0:
        missing.append("券商市价")
    if holding.pnl_pct is None:
        missing.append("单票盈亏")
    if holding.market_value is None and holding.weight_pct is None:
        missing.append("市值/仓位")
    return missing


_CONTEXT_PLACEHOLDER_MARKERS = ("待补", "未提供", "未知")


def _has_context_placeholder(value: str) -> bool:
    return any(marker in value for marker in _CONTEXT_PLACEHOLDER_MARKERS)


def _missing_current_context_fields(holding: Holding) -> list[str]:
    missing: list[str] = []
    if not holding.risk_line.strip() or _has_context_placeholder(holding.risk_line):
        missing.append("当前风险规则")
    if not holding.review_status.strip():
        missing.append("当前复盘状态")
    elif holding.review_status == "needs_context":
        missing.append("当前持仓上下文")
    elif holding.review_status == "stale_context":
        missing.append("当前风险规则与持仓快照冲突")
    return missing


def _missing_historical_context_fields(holding: Holding) -> list[str]:
    missing: list[str] = []
    if not holding.thesis.strip() or _has_context_placeholder(holding.thesis):
        missing.append("原始买入逻辑")
    if (
        not holding.initial_risk_line.strip()
        or _has_context_placeholder(holding.initial_risk_line)
        or holding.review_status == "stale_context"
    ):
        missing.append("原始买入失效条件")
    return missing


def _current_decision_context_complete(holding: Holding) -> bool:
    """Return whether current risk review inputs are usable now."""

    return not _missing_current_context_fields(holding)


def _historical_context_complete(holding: Holding) -> bool:
    """Return whether entry-time thesis and invalidation are auditable."""

    return not _missing_historical_context_fields(holding)


def _build_core_reliability(
    portfolio: Portfolio,
    actions: list[dict[str, object]],
    outcome_snapshot: dict[str, object],
    data_gaps: list[str],
    optional_gaps: list[str],
) -> dict[str, object]:
    effective_optional_gaps = list(optional_gaps)
    missing_historical_context = [
        holding.name or holding.code
        for holding in portfolio.holdings
        if not _historical_context_complete(holding)
    ]
    if missing_historical_context:
        effective_optional_gaps.append(
            "部分持仓历史买入上下文未知（仅影响复盘，不阻断当前风险计划）："
            + ", ".join(missing_historical_context)
        )
    market_as_of = str(outcome_snapshot.get("as_of_trade_date") or "")
    holding_rows: list[dict[str, object]] = []
    structural_ready = 0
    decision_ready = 0
    current_context_ready = 0
    historical_context_ready = 0
    for holding in portfolio.holdings:
        action = next(
            (
                item
                for item in actions
                if holding.code in str(item.get("name", ""))
                or (holding.name and holding.name in str(item.get("name", "")))
            ),
            {},
        )
        action_fields = (
            "action",
            "reason",
            "position_action",
            "upside_trigger",
            "downside_trigger",
            "flat_trigger",
        )
        action_complete = all(str(action.get(field, "")).strip() for field in action_fields)
        if action_complete:
            structural_ready += 1
        missing_snapshot_fields = _holding_snapshot_missing_fields(holding)
        missing_current_context_fields = _missing_current_context_fields(holding)
        missing_historical_context_fields = _missing_historical_context_fields(holding)
        current_context_complete = not missing_current_context_fields
        historical_context_complete = not missing_historical_context_fields
        if current_context_complete:
            current_context_ready += 1
        if historical_context_complete:
            historical_context_ready += 1
        ready = bool(
            action_complete
            and market_as_of
            and portfolio.as_of
            and current_context_complete
            and not missing_snapshot_fields
            and portfolio.risk_reconciliation_status != "blocked"
        )
        if ready:
            decision_ready += 1
        holding_rows.append(
            {
                "code": holding.code,
                "name": holding.name or holding.code,
                "action_complete": action_complete,
                "context_complete": current_context_complete,
                "current_context_complete": current_context_complete,
                "historical_context_complete": historical_context_complete,
                "missing_current_context_fields": missing_current_context_fields,
                "missing_historical_context_fields": missing_historical_context_fields,
                "missing_snapshot_fields": missing_snapshot_fields,
                "decision_ready": ready,
                "risk_reconciliation_status": portfolio.risk_reconciliation_status,
            }
        )
    count = len(portfolio.holdings)
    return {
        "portfolio_source": str(portfolio.source),
        "portfolio_as_of": portfolio.as_of or None,
        "portfolio_source_note": portfolio.source_note,
        "risk_reconciliation_status": portfolio.risk_reconciliation_status,
        "market_as_of_trade_date": market_as_of or None,
        "holding_count": count,
        "structural_action_holdings": structural_ready,
        "structural_action_coverage": round(structural_ready / count, 4) if count else 0.0,
        "decision_ready_holdings": decision_ready,
        "decision_ready_coverage": round(decision_ready / count, 4) if count else 0.0,
        "current_context_ready_holdings": current_context_ready,
        "historical_context_ready_holdings": historical_context_ready,
        "holdings": holding_rows,
        "data_gaps": _dedupe_text(data_gaps),
        "optional_extension_gaps": _dedupe_text(effective_optional_gaps),
        "definition": (
            "严格就绪要求当前持仓快照有as_of、股数/成本/市价/盈亏或仓位字段，"
            "当前风险规则与复盘状态可用，行情已评估，且动作包含仓位、上行、下行和震荡分支。"
            "原始买入逻辑和初始失效条件缺失只影响历史复盘质量，不阻断当前风险计划。"
            "显式标记为blocked的持仓/风险预算对账会阻断严格就绪。"
        ),
    }


def _core_reliability_lines(reliability: dict[str, object]) -> list[str]:
    count = int(reliability.get("holding_count", 0) or 0)
    structural = int(reliability.get("structural_action_holdings", 0) or 0)
    ready = int(reliability.get("decision_ready_holdings", 0) or 0)
    current_context_value = reliability.get("current_context_ready_holdings", 0)
    historical_context_value = reliability.get("historical_context_ready_holdings", 0)
    current_context = (
        current_context_value if isinstance(current_context_value, int) else 0
    )
    historical_context = (
        historical_context_value if isinstance(historical_context_value, int) else 0
    )
    lines = [
        f"结构化动作覆盖 {structural}/{count}；严格决策就绪 {ready}/{count}。",
        f"当前风险上下文 {current_context}/{count}；历史买入上下文 {historical_context}/{count}（仅影响复盘）。",
        f"持仓快照：{reliability.get('portfolio_source')}；截至 {reliability.get('portfolio_as_of') or '未标注'}。",
        f"行情评估截至：{reliability.get('market_as_of_trade_date') or '未取得有效交易日'}。",
        f"持仓/风险预算对账：{reliability.get('risk_reconciliation_status') or 'unverified'}。",
        str(reliability.get("definition", "")),
    ]
    optional = reliability.get("optional_extension_gaps", [])
    if isinstance(optional, list) and optional:
        lines.append(f"可选扩展缺口（不阻塞Core）：{'；'.join(str(item) for item in optional)}")
    return [line for line in lines if line]


def _meaningful_data_gaps(items: list[str]) -> list[str]:
    placeholders = {"暂无", "无", "暂无数据缺口", "- 暂无"}
    return _dedupe_text([item for item in items if item.strip() not in placeholders])


def _dedupe_text(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item and item.strip()))


def _payload_action_lines(markdown: str) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_action_section = False

    def flush() -> None:
        nonlocal current
        if current and (current.get("action") or current.get("reason")):
            actions.append(current)
        current = None

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if in_action_section:
                flush()
            in_action_section = line[3:].strip() == "持仓动作"
            continue
        if not in_action_section:
            continue
        if line.startswith("### "):
            flush()
            current = {"name": line[4:].strip()}
            continue
        if current is None:
            continue
        if "建议动作" in line or "寤鸿" in line:
            current["action"] = line.split("：", 1)[-1].split("锛?", 1)[-1].strip()
        elif "核心理由" in line or "鏍稿績" in line:
            current["reason"] = line.split("：", 1)[-1].split("锛?", 1)[-1].strip()
        elif line.startswith("- 仓位动作："):
            current["position_action"] = line.split("：", 1)[-1].strip()
        elif line.startswith("- 上行条件："):
            current["upside_trigger"] = line.split("：", 1)[-1].strip()
        elif line.startswith("- 下行条件："):
            current["downside_trigger"] = line.split("：", 1)[-1].strip()
        elif line.startswith("- 震荡处理："):
            current["flat_trigger"] = line.split("：", 1)[-1].strip()
        elif line.startswith("- 明日优先级："):
            current["priority"] = line.split("：", 1)[-1].strip()
    if in_action_section:
        flush()
    return actions


def _signal_from_broker_snapshot(holding: Holding) -> HoldingSignal:
    risk_reasons = []
    action = "持有/复核"
    if holding.pnl_pct is not None and holding.pnl_pct <= -15:
        risk_reasons.append(f"总盈亏 {holding.pnl_pct:.2f}%，回撤较深")
        action = "减仓/退出复核"
    if holding.day_pnl_pct is not None and holding.day_pnl_pct <= -3:
        risk_reasons.append(f"当日盈亏 {holding.day_pnl_pct:.2f}%，单日承压")
        action = "降低仓位复核" if action == "持有/复核" else action
    if holding.weight_pct is not None and holding.weight_pct >= 20:
        risk_reasons.append(f"仓位 {holding.weight_pct:.2f}%，单票权重偏高")
    if holding.pnl_pct is not None and holding.pnl_pct >= 40:
        risk_reasons.append(f"浮盈 {holding.pnl_pct:.2f}%，注意止盈纪律")
        action = "持有但上移止盈线" if action == "持有/复核" else action
    reason = "；".join(risk_reasons) if risk_reasons else "券商快照未触发硬性风险，等待行情/逻辑复核。"
    return HoldingSignal(
        holding=holding,
        action=action,
        reason=reason,
        data_gap="未接入实时行情和公告，当前仅基于券商复制持仓快照。",
    )


def _global_market_section(groups: dict[str, list[MarketIndexSnapshot]]) -> str:
    lines: list[str] = []
    for region, snapshots in groups.items():
        lines.append(f"### {region}")
        valid_changes = [item.change_pct for item in snapshots if item.change_pct is not None]
        tone = _market_tone(valid_changes)
        lines.append(f"- 区域状态：{tone}")
        for item in snapshots:
            if item.price is None:
                lines.append(f"- {item.name}（{item.symbol}）：数据暂缺")
            else:
                lines.append(
                    f"- {item.name}（{item.symbol}）：{item.price:,.2f}，涨跌 {_fmt_signed_pct(item.change_pct)}"
                )
    return "\n".join(lines)


def _global_market_gap_lines(groups: dict[str, list[MarketIndexSnapshot]]) -> list[str]:
    gaps = []
    for item in [snapshot for snapshots in groups.values() for snapshot in snapshots]:
        if item.error:
            gaps.append(f"{item.region}/{item.name} 宏观行情暂缺：{item.error}")
    return gaps


def _market_tone(changes: list[float | None]) -> str:
    values = [value for value in changes if value is not None]
    if not values:
        return "数据不足"
    avg = sum(values) / len(values)
    if avg >= 0.01:
        return "风险偏好较强"
    if avg <= -0.01:
        return "风险偏好偏弱"
    if avg >= 0:
        return "震荡偏强"
    return "震荡偏弱"


def _broker_snapshot_lines(portfolio: Portfolio) -> list[str]:
    lines = []
    for holding in portfolio.holdings:
        if holding.market_value is None and holding.pnl_pct is None and holding.day_pnl_pct is None:
            continue
        lines.append(
            f"{holding.name or holding.code}：仓位 {_format_optional_number(holding.weight_pct, '.2f', '％')}，"
            f"成本 {_format_optional_number(holding.cost, '.3f')}，"
            f"市价 {_format_optional_number(holding.market_price, '.3f')}，"
            f"总盈亏 {_format_optional_number(holding.pnl_pct, '.2f', '％')}，"
            f"当日 {_format_optional_number(holding.day_pnl_pct, '.2f', '％')}，"
            f"市值 {_format_optional_number(holding.market_value, '.0f')}。"
        )
    return lines


def _format_optional_number(value: float | None, format_spec: str, suffix: str = "") -> str:
    if value is None:
        return "未提供"
    return f"{value:{format_spec}}{suffix}"


def _portfolio_context_lines(portfolio: Portfolio) -> list[str]:
    lines: list[str] = []
    for holding in portfolio.holdings:
        adjustments = "；".join(
            _format_adjustment_record(record)
            for record in holding.adjustment_records[-3:]
            if record.date or record.action or record.reason or record.risk_line_after
        )
        if not any(
            [
                holding.thesis,
                holding.initial_risk_line,
                holding.risk_line,
                holding.horizon,
                holding.review_status,
                adjustments,
            ]
        ):
            continue
        lines.append(
            f"{holding.name or holding.code}（{holding.code}）："
            f"买入逻辑={holding.thesis or '待补'}；"
            f"初始风控线={holding.initial_risk_line or '待补'}；"
            f"当前风控线={holding.risk_line or '待补'}；"
            f"周期={holding.horizon or '待定'}；"
            f"复盘状态={holding.review_status or '待复盘'}；"
            f"最近调仓={adjustments or '暂无记录'}。"
        )
    return lines


def _research_hypothesis_lines(portfolio: Portfolio) -> list[str]:
    lines: list[str] = []
    for holding in portfolio.holdings:
        catalysts = "；".join(holding.catalysts)
        falsification = "；".join(holding.falsification_signals)
        if not any([catalysts, falsification, holding.observation_window, holding.next_review_date]):
            continue
        lines.append(
            f"{holding.name or holding.code}（{holding.code}）："
            f"催化剂={catalysts or '待补'}；"
            f"反证条件={falsification or '待补'}；"
            f"观察窗口={holding.observation_window or '待定'}；"
            f"下次复盘={holding.next_review_date or '待定'}。"
        )
    return lines


def _research_delta_lines(portfolio: Portfolio) -> list[str]:
    path = DATA_DIR / "research_deltas.jsonl"
    if not path.exists():
        return ["暂无研报观点变化；可先运行 `.venv\\Scripts\\python -m stock_assist.cli research-monitor`。"]
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    if not rows:
        return ["研报观点变化文件为空。"]
    holding_tokens = _portfolio_match_tokens(portfolio)
    relevant = [row for row in rows if _delta_matches_portfolio(row, holding_tokens)]
    selected = (relevant or rows)[-8:]
    lines = []
    for row in selected:
        matched = "、".join(str(value) for value in row.get("matched", []) if str(value).strip())
        lines.append(
            f"{row.get('report_date', '')}｜{row.get('delta', '待验证')}｜置信度 {float(row.get('confidence') or 0):.2f}｜"
            f"命中 {matched or '观察主题'}｜{row.get('title', '')}｜来源 {row.get('org', '')}｜"
            f"状态 {row.get('source_status', 'metadata_only')}｜{row.get('url', '')}"
        )
    return lines


def _portfolio_match_tokens(portfolio: Portfolio) -> set[str]:
    tokens: set[str] = set()
    for holding in portfolio.holdings:
        if holding.code:
            tokens.add(holding.code)
            tokens.add(holding.code.split(".")[0])
        if holding.name:
            tokens.add(holding.name)
    return tokens


def _delta_matches_portfolio(row: dict[str, object], tokens: set[str]) -> bool:
    if not tokens:
        return False
    values = [str(row.get("stock_code", "")), str(row.get("stock_name", ""))]
    matched = row.get("matched", [])
    if isinstance(matched, list):
        values.extend(str(item) for item in matched)
    haystack = " ".join(values)
    return any(token and token in haystack for token in tokens)


def _peer_comparison_lines(client: AmazingDataClient, portfolio: Portfolio) -> list[str]:
    holding_codes = {holding.code for holding in portfolio.holdings}
    selected_groups = {
        holding.code: PEER_GROUPS[holding.code]
        for holding in portfolio.holdings
        if holding.code in PEER_GROUPS
    }
    if not selected_groups:
        return []

    all_codes: list[str] = []
    for group in selected_groups.values():
        for code in group["codes"]:
            if code not in all_codes:
                all_codes.append(code)

    calendar = client.calendar
    end_date = calendar[-1]
    begin_date = calendar[max(0, len(calendar) - 30)]
    raw_kline = client.query_daily_kline(all_codes, begin_date, end_date)
    equity = client.get_equity_structure(all_codes)
    notices = client.get_profit_notice(all_codes)
    if not isinstance(notices, pd.DataFrame):
        notices = pd.DataFrame()
    if not notices.empty:
        notices = notices.copy()
        notices["REPORTING_PERIOD_I"] = pd.to_numeric(notices.get("REPORTING_PERIOD"), errors="coerce")
        notices = notices[notices["REPORTING_PERIOD_I"] >= 20250101]

    lines: list[str] = []
    for holding_code, group in selected_groups.items():
        codes = dict(group["codes"])
        rows = []
        for code, name in codes.items():
            frame = _frame_for_code(raw_kline, code)
            close = _latest_close(raw_kline, code)
            change_5 = _pct_change(frame, 5)
            change_20 = _pct_change(frame, 20)
            shares = _latest_total_shares_yi(equity, code)
            market_cap = close * shares if close is not None and shares is not None else None
            annual_pe = _profit_notice_annual_pe(notices, code, market_cap)
            role = "持仓" if code in holding_codes else "同业"
            rows.append(
                f"{name}({code},{role}) 5日{_fmt_signed_pct(change_5)} / 20日{_fmt_signed_pct(change_20)}"
                f" / 市值{_fmt_yi(market_cap)} / 预告PE {_fmt_multiple(annual_pe)}"
            )
        lines.append(
            f"{group['name']}｜锚点：{group['anchor']}｜持仓 {holding_code}｜"
            + "；".join(rows)
        )
    return lines


def _format_adjustment_record(record: object) -> str:
    date = getattr(record, "date", "")
    action = getattr(record, "action", "")
    reason = getattr(record, "reason", "")
    risk_line_after = getattr(record, "risk_line_after", "")
    parts = [part for part in [date, action, reason] if part]
    if risk_line_after:
        parts.append(f"风控线调整为 {risk_line_after}")
    return " / ".join(parts)


def _profit_notice_peer_lines(client: AmazingDataClient, portfolio: Portfolio) -> list[str]:
    holding_codes = {holding.code for holding in portfolio.holdings}
    has_lithium_holding = bool(holding_codes & set(LITHIUM_PEERS))
    codes = list(LITHIUM_PEERS) if has_lithium_holding else [holding.code for holding in portfolio.holdings]
    if not codes:
        return []

    overrides = _load_profit_notice_overrides()
    notices = client.get_profit_notice(codes)
    if not isinstance(notices, pd.DataFrame) or notices.empty:
        notices = pd.DataFrame()

    calendar = client.calendar
    end_date = calendar[-1]
    begin_date = calendar[max(0, len(calendar) - 30)]
    raw_kline = client.query_daily_kline(codes, begin_date, end_date)
    equity = client.get_equity_structure(codes)

    if not notices.empty:
        notices = notices.copy()
        notices["REPORTING_PERIOD_I"] = pd.to_numeric(notices.get("REPORTING_PERIOD"), errors="coerce")
        notices = notices[notices["REPORTING_PERIOD_I"] >= 20250101]
    if notices.empty and not overrides:
        return []

    lines: list[str] = []
    for code in codes:
        notice = _latest_profit_notice(notices, code)
        override = overrides.get(code)
        if override and (
            notice is None
            or str(override.get("reporting_period", "")) >= str(notice.get("REPORTING_PERIOD", ""))
        ):
            notice_name = str(override.get("name") or LITHIUM_PEERS.get(code, code))
            period = str(override.get("reporting_period") or "")
            summary = str(override.get("summary") or "")
            profit_min = _optional_float(override.get("profit_min_yi"))
            profit_max = _optional_float(override.get("profit_max_yi"))
            deduct_min = _optional_float(override.get("deduct_profit_min_yi"))
            deduct_max = _optional_float(override.get("deduct_profit_max_yi"))
            source = "手工公告覆盖"
        elif notice is not None:
            notice_name = str(notice.get("SECURITY_NAME") or LITHIUM_PEERS.get(code, code))
            period = str(notice.get("REPORTING_PERIOD") or "")
            summary = str(notice.get("P_SUMMARY") or "").replace("预计:", "")
            profit_min = _wan_to_yi(notice.get("NET_PROFIT_MIN"))
            profit_max = _wan_to_yi(notice.get("NET_PROFIT_MAX"))
            deduct_min = None
            deduct_max = None
            source = "AmazingData"
            if profit_min is not None and profit_max is not None:
                summary = f"归母净利润 {profit_min:.1f}-{profit_max:.1f} 亿元"
        else:
            continue

        profit_mid = (profit_min + profit_max) / 2 if profit_min is not None and profit_max is not None else None
        close = _latest_close(raw_kline, code)
        shares = _latest_total_shares_yi(equity, code)
        market_cap = close * shares if close is not None and shares is not None else None
        annual_pe = market_cap / (profit_mid * 2) if market_cap and profit_mid and profit_mid > 0 else None
        held = "持仓" if code in holding_codes else "同业"
        valuation = ""
        if market_cap is not None and annual_pe is not None:
            valuation = f"，市值约 {market_cap:.0f} 亿，年化归母PE约 {annual_pe:.1f}x"
        elif market_cap is not None:
            valuation = f"，市值约 {market_cap:.0f} 亿"
        deduct = ""
        if deduct_min is not None and deduct_max is not None:
            deduct = f"，扣非 {deduct_min:.1f}-{deduct_max:.1f} 亿"
        lines.append(
            f"{notice_name}（{code}，{held}）：{period} 业绩预告，"
            f"{summary or '净利润区间未披露'}{deduct}{valuation}；来源 {source}。"
        )
    if has_lithium_holding and any("雅化集团" in line for line in lines):
        lines.append(
            "锂矿同业锚：雅化预告后先一字涨停再放量跌停，说明市场正在杀业绩兑现交易；"
            "盛新预告需结合雅化和板块承接判断，不能只看单票同比。"
        )
    return lines


def _fresh_cninfo_filing_lines(portfolio: Portfolio) -> list[str]:
    lines: list[str] = []
    for holding in portfolio.holdings:
        try:
            notice = latest_profit_notice(holding.code, days=3)
        except Exception as exc:
            lines.append(f"{holding.name or holding.code}：巨潮公告查询失败：{exc}")
            continue
        if notice is None:
            continue
        lines.append(
            f"{holding.name or notice.name or holding.code}：巨潮已披露 {notice.date}《{notice.title}》，"
            f"PDF：{notice.pdf_url}"
        )
    return lines


def _load_event_calendar() -> tuple[dict[str, object], list[str]]:
    gaps: list[str] = []
    path = EVENT_CALENDAR_PATH
    if not path.exists():
        gaps.append(f"未找到正式事件日历：{path}，已使用示例事件配置。")
        path = EVENT_CALENDAR_EXAMPLE_PATH
    if not path.exists():
        return {"events": [], "lookahead_days": 14}, gaps + ["示例事件日历也不存在。"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"events": [], "lookahead_days": 14}, gaps + [f"事件日历 JSON 解析失败：{exc}"]
    if not isinstance(payload, dict):
        return {"events": [], "lookahead_days": 14}, gaps + ["事件日历格式不是 JSON object。"]
    return payload, gaps


def _event_calendar_lines(
    portfolio: Portfolio,
    config: dict[str, object],
    fresh_filing_lines: list[str],
) -> list[str]:
    holding_codes = {holding.code for holding in portfolio.holdings}
    today = date.today()
    lookahead_days = int(_optional_float(config.get("lookahead_days")) or 14)
    horizon_end = today + timedelta(days=lookahead_days)
    raw_events = config.get("events", [])
    events = raw_events if isinstance(raw_events, list) else []
    lines: list[str] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        event_date = _parse_date(str(item.get("date", "")))
        if event_date is None or event_date < today or event_date > horizon_end:
            continue
        symbols = [str(symbol) for symbol in item.get("symbols", []) if str(symbol)]
        if symbols and holding_codes and not (set(symbols) & holding_codes or any("." not in symbol for symbol in symbols)):
            continue
        days_left = (event_date - today).days
        importance = str(item.get("importance") or "medium")
        title = str(item.get("title") or "未命名事件")
        market = str(item.get("market") or "未标注市场")
        watch = str(item.get("watch") or "待补观察项")
        source = str(item.get("source") or "manual")
        symbol_text = ", ".join(symbols) if symbols else "全市场"
        lines.append(
            f"{event_date:%Y-%m-%d}（T+{days_left}，{importance}）：{title}｜市场={market}｜标的={symbol_text}｜观察={watch}｜来源={source}"
        )
    for filing in fresh_filing_lines:
        lines.append(f"公告监控：{filing}")
    if not lines:
        lines.append(f"未来 {lookahead_days} 天暂无命中持仓的手工事件；请维护 {EVENT_CALENDAR_PATH}。")
    return lines


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _latest_profit_notice(notices: pd.DataFrame, code: str) -> pd.Series | None:
    if notices.empty or "MARKET_CODE" not in notices.columns:
        return None
    code_notices = notices[notices["MARKET_CODE"].astype(str) == code].sort_values(
        ["REPORTING_PERIOD_I", "ANN_DATE"], ascending=False
    )
    return None if code_notices.empty else code_notices.iloc[0]


def _load_profit_notice_overrides() -> dict[str, dict[str, object]]:
    path = DATA_DIR / "profit_notice_overrides.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return {}
    return {
        str(item.get("code")): item
        for item in payload
        if isinstance(item, dict) and item.get("code")
    }


def _latest_close(raw_kline: object, code: str) -> float | None:
    frame = _frame_for_code(raw_kline, code)
    if frame.empty or "close" not in frame.columns:
        return None
    values = pd.to_numeric(frame["close"], errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else None


def _latest_total_shares_yi(equity: object, code: str) -> float | None:
    if isinstance(equity, dict):
        frame = equity.get(code)
    elif isinstance(equity, pd.DataFrame):
        frame = equity[equity["MARKET_CODE"].astype(str) == code] if "MARKET_CODE" in equity.columns else equity
    else:
        frame = None
    if not isinstance(frame, pd.DataFrame) or frame.empty or "TOT_SHARE" not in frame.columns:
        return None
    frame = frame.copy()
    frame["CHANGE_DATE_I"] = pd.to_numeric(frame.get("CHANGE_DATE"), errors="coerce")
    frame = frame.sort_values("CHANGE_DATE_I")
    values = pd.to_numeric(frame["TOT_SHARE"], errors="coerce").dropna()
    return float(values.iloc[-1]) / 10000 if not values.empty else None


def _profit_notice_annual_pe(notices: pd.DataFrame, code: str, market_cap: float | None) -> float | None:
    if market_cap is None:
        return None
    notice = _latest_profit_notice(notices, code)
    if notice is None:
        return None
    profit_min = _wan_to_yi(notice.get("NET_PROFIT_MIN"))
    profit_max = _wan_to_yi(notice.get("NET_PROFIT_MAX"))
    if profit_min is None or profit_max is None:
        return None
    profit_mid = (profit_min + profit_max) / 2
    if profit_mid <= 0:
        return None
    return market_cap / (profit_mid * 2)


def _pct_change(frame: pd.DataFrame, days: int) -> float | None:
    if frame.empty:
        return None
    close_col = _pick_column(frame, ["close", "收盘价", "S_DQ_CLOSE"])
    if close_col is None:
        return None
    closes = pd.to_numeric(frame[close_col], errors="coerce").dropna()
    closes = closes[closes > 0]
    if len(closes) <= days:
        return None
    base = float(closes.iloc[-days - 1])
    if base <= 0:
        return None
    return float(closes.iloc[-1]) / base - 1


def _fmt_signed_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:+.1%}"


def _fmt_yi(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.0f}亿"


def _fmt_multiple(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.1f}x"


def _wan_to_yi(value: object) -> float | None:
    number = _optional_float(value)
    return number / 10000 if number is not None else None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _external_view_lines(
    observations: list[InfluencerObservation],
    portfolio: Portfolio,
    client: AmazingDataClient | None = None,
) -> list[str]:
    if not observations:
        return []

    holding_codes = {holding.code for holding in portfolio.holdings}
    holding_names = {holding.name for holding in portfolio.holdings if holding.name}
    peer_codes = _configured_peer_codes()
    aftertests = _external_price_aftertests(observations[-10:], client)
    lines: list[str] = []
    for item in observations[-10:]:
        matched_symbols = [
            symbol
            for symbol in item.symbols
            if symbol in holding_codes or symbol in holding_names
        ]
        peer_hits = [symbol for symbol in item.symbols if symbol in peer_codes and symbol not in matched_symbols]
        mapping = "命中持仓" if matched_symbols else "未命中当前持仓"
        if peer_hits and not matched_symbols:
            mapping = "命中同业/产业锚"
        if not portfolio.holdings:
            mapping = "暂无持仓，先作为观察池线索"
        source_risk = "一手" if item.source_type == "first_party" else "需复核"
        impact = ", ".join(item.symbols or item.industries or item.themes) or "未映射"
        source = item.source_url or "待补一手链接"
        aftertest = _format_aftertest(item, aftertests)
        verification = "；".join(item.verification[:2]) if item.verification else "补一手来源和价格后验"
        lines.append(
            f"{item.author}：{item.summary.rstrip('。')}；影响 {impact}；"
            f"{mapping}；来源{source_risk}；链接 {source}；"
            f"价格后验 {aftertest}；待验证 {verification}；置信度 {item.confidence}。"
        )
    return lines


def _configured_peer_codes() -> set[str]:
    codes: set[str] = set()
    for group in PEER_GROUPS.values():
        codes.update(str(code) for code in group["codes"])
    return codes


def _external_price_aftertests(
    observations: list[InfluencerObservation],
    client: AmazingDataClient | None,
) -> dict[tuple[str, str], str]:
    if client is None:
        return {}
    symbols = sorted(
        {
            symbol
            for item in observations
            for symbol in item.symbols
            if _is_a_share_symbol(symbol)
        }
    )
    if not symbols:
        return {}
    try:
        calendar = client.calendar
        end_date = calendar[-1]
        begin_date = calendar[max(0, len(calendar) - 120)]
        raw = client.query_daily_kline(symbols, begin_date, end_date)
    except AmazingDataError:
        return {}

    results: dict[tuple[str, str], str] = {}
    for item in observations:
        for symbol in item.symbols:
            if not _is_a_share_symbol(symbol):
                continue
            result = _price_aftertest_for_symbol(raw, symbol, item.date)
            if result:
                results[(item.id, symbol)] = result
    return results


def _price_aftertest_for_symbol(raw_kline: object, symbol: str, observation_date: str) -> str:
    frame = _frame_for_code(raw_kline, symbol)
    if frame.empty:
        return ""
    close_col = _pick_column(frame, ["close", "收盘价", "S_DQ_CLOSE"])
    if close_col is None:
        return ""
    closes = pd.to_numeric(frame[close_col], errors="coerce")
    dates = _date_series(frame)
    data = pd.DataFrame({"date": dates, "close": closes}).dropna()
    data = data[data["close"] > 0].sort_values("date")
    if data.empty:
        return ""
    obs_date = _parse_date(observation_date)
    if obs_date is None:
        return ""
    after = data[data["date"] >= pd.Timestamp(obs_date)]
    if after.empty:
        return ""
    start = float(after.iloc[0]["close"])
    latest = float(data.iloc[-1]["close"])
    if start <= 0:
        return ""
    change = latest / start - 1
    return f"{symbol} 观察日至今 {_fmt_signed_pct(change)}"


def _date_series(frame: pd.DataFrame) -> pd.Series:
    date_col = _pick_column(frame, ["date", "trade_date", "交易日期", "TRADE_DATE", "datetime", "time"])
    if date_col is not None:
        values = frame[date_col]
        numeric = pd.to_numeric(values, errors="coerce")
        if numeric.notna().any():
            return pd.to_datetime(numeric.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
        return pd.to_datetime(values, errors="coerce")
    return pd.Series(pd.date_range(end=pd.Timestamp.today().normalize(), periods=len(frame)), index=frame.index)


def _format_aftertest(item: InfluencerObservation, aftertests: dict[tuple[str, str], str]) -> str:
    results = [aftertests[(item.id, symbol)] for symbol in item.symbols if (item.id, symbol) in aftertests]
    non_a_share = [symbol for symbol in item.symbols if not _is_a_share_symbol(symbol)]
    parts = results[:3]
    if non_a_share and not results:
        parts.append("非A股行情待接入")
    if not parts:
        parts.append("待观察")
    return "；".join(parts)


def _is_a_share_symbol(symbol: str) -> bool:
    return symbol.endswith(".SZ") or symbol.endswith(".SH")


def _build_signals(
    client: AmazingDataClient,
    holdings: list[Holding],
    lookback_days: int,
) -> list[HoldingSignal]:
    calendar = client.calendar
    end_date = calendar[-1]
    begin_date = calendar[max(0, len(calendar) - lookback_days)]
    result = client.query_daily_kline_result(
        [holding.code for holding in holdings],
        begin_date,
        end_date,
    )
    return [
        _signal_for_holding(
            holding,
            daily_kline_result_for_code(result, holding.code),
        )
        for holding in holdings
    ]


def _frame_for_code(raw: object, code: str) -> pd.DataFrame:
    if isinstance(raw, dict):
        value = raw.get(code)
        if value is None:
            value = raw.get(code.replace(".", "_"))
        if isinstance(value, pd.DataFrame):
            return value
    if isinstance(raw, pd.DataFrame):
        if "code" in raw.columns:
            return raw[raw["code"].astype(str) == code]
        return raw
    return pd.DataFrame()


def _legacy_basic_signal_for_holding(holding: Holding, frame: pd.DataFrame) -> HoldingSignal:
    if frame.empty:
        return HoldingSignal(holding, "等待", "未取到该股票行情。", "补充日线行情")

    close_col = _pick_column(frame, ["close", "收盘价", "S_DQ_CLOSE"])
    if close_col is None:
        return HoldingSignal(holding, "等待", "行情缺少收盘价字段。", "确认 AmazingData K 线字段映射")

    closes = pd.to_numeric(frame[close_col], errors="coerce").dropna()
    closes = closes[closes > 0]
    if len(closes) < 20:
        return HoldingSignal(holding, "等待", "有效行情不足 20 个交易日。", "补齐更长历史行情")

    last = float(closes.iloc[-1])
    ma20 = float(closes.tail(20).mean())
    ma60 = float(closes.tail(min(60, len(closes))).mean())
    change_5 = last / float(closes.tail(6).iloc[0]) - 1 if len(closes) >= 6 else 0.0

    if last < ma20 and ma20 < ma60:
        return HoldingSignal(holding, "降低仓位", f"价格低于 20 日线且 20 日线弱于中期均线，收盘价 {last:.2f}。")
    if last > ma20 and change_5 > 0.05:
        return HoldingSignal(holding, "持有观察", f"短期走强但不追高，5 日涨幅 {change_5:.1%}。")
    return HoldingSignal(holding, "持有/等待", f"趋势未给出强动作信号，收盘价 {last:.2f}，20 日均线 {ma20:.2f}。")


def _pick_column(frame: pd.DataFrame, names: list[str]) -> str | None:
    lowered = {str(column).lower(): str(column) for column in frame.columns}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _legacy_signal_for_holding(holding: Holding, frame: pd.DataFrame) -> HoldingSignal:
    if frame.empty:
        return HoldingSignal(
            holding,
            "等待数据，不做主动交易",
            "未取到该股票行情，无法判断趋势位置。",
            "补充日线行情",
            "不加仓，等数据恢复后再复核。",
            "取回行情并确认站上20日线后再恢复正常观察。",
            "若账户已有仓位且个股放量下跌，按风控线先降风险。",
            "只做风险监控，不做方向判断。",
            "高",
        )

    close_col = _pick_column(frame, ["close", "收盘价", "S_DQ_CLOSE"])
    if close_col is None:
        return HoldingSignal(
            holding,
            "等待数据，不做主动交易",
            "行情缺少收盘价字段，不能计算20日线和回撤。",
            "确认 AmazingData K 线字段映射",
            "不加仓，先修复行情字段。",
            "字段恢复后再判断是否站上20日线。",
            "若盘中跌破你的人工风控线，按人工风控线处理。",
            "维持观察。",
            "高",
        )

    closes = pd.to_numeric(frame[close_col], errors="coerce").dropna()
    closes = closes[closes > 0]
    if len(closes) < 20:
        return HoldingSignal(
            holding,
            "等待数据，不做主动交易",
            "有效行情不足20个交易日，趋势参考不稳定。",
            "补齐更长历史行情",
            "不加仓，先补足行情长度。",
            "行情补足且站上20日线后再恢复趋势判断。",
            "若跌破成本或人工风控线，先降风险。",
            "只观察价格和成交额。",
            "中",
        )

    last = float(closes.iloc[-1])
    broker_price = holding.market_price
    if (
        broker_price is not None
        and broker_price > 0
        and abs(last / broker_price - 1.0) > 0.35
    ):
        return HoldingSignal(
            holding,
            "等待数据，不做主动交易",
            (
                f"日线收盘价 {last:.2f} 与券商快照 {broker_price:.2f} "
                "偏差超过35%，疑似复权或标的映射口径不一致。"
            ),
            "行情复权/映射口径待核对",
            "不使用当前均线或价格阈值生成仓位动作。",
            "同一标的、同一复权口径的收盘价与券商快照完成对账后再恢复判断。",
            "若账户已有人工风控线，只按人工风控线处理，不采用当前模型阈值。",
            "继续等待数据修复，不补仓、不追涨。",
            "高",
        )
    ma20 = float(closes.tail(20).mean())
    ma60 = float(closes.tail(min(60, len(closes))).mean())
    prev = float(closes.tail(6).iloc[0]) if len(closes) >= 6 else last
    change_5 = last / prev - 1 if prev > 0 else 0.0
    weight = holding.weight_pct or 0.0
    pnl_pct = holding.pnl_pct or 0.0
    high_weight = weight >= 40
    profit_protect = pnl_pct >= 35
    below_ma20 = last < ma20
    above_ma20 = last >= ma20
    ma20_gap = abs(last / ma20 - 1) if ma20 > 0 else 0.0

    if below_ma20 and ma20 < ma60:
        return HoldingSignal(
            holding,
            "降低仓位",
            f"收盘价 {last:.2f} 低于20日线 {ma20:.2f}，且20日线弱于中期均线 {ma60:.2f}，趋势处在弱势区。",
            "",
            "不加仓；若明日不能收回20日线，先降1/4到1/3仓位。",
            f"若放量站回20日线 {ma20:.2f} 上方，再改为持有观察。",
            f"若跌破20日线 {ma20:.2f} 且板块同步转弱，执行降仓。",
            "横盘但仍低于20日线时，只观察不补仓。",
            "高",
        )

    if high_weight:
        return HoldingSignal(
            holding,
            "高仓位持有，优先降集中度",
            f"当前仓位约 {weight:.1f}%，单票集中度偏高；即使趋势未坏，也不适合继续加仓。",
            "",
            "不加仓；冲高但量能不足时，优先把仓位降到更舒服的区间。",
            f"若放量站稳20日线 {ma20:.2f} 且板块继续强，可保留核心仓位。",
            f"若跌破20日线 {ma20:.2f} 或单日回撤扩大，先降1/4仓位。",
            "围绕20日线震荡时，以降低集中度为主，不做追买。",
            "高",
        )

    if profit_protect:
        return HoldingSignal(
            holding,
            "持有，保护浮盈",
            f"当前浮盈约 {pnl_pct:.1f}%，核心任务不是追高，而是保护已有利润。",
            "",
            "继续持有核心仓位；不追高，止盈线跟随20日线或人工风控线上移。",
            f"若放量创新高且不跌回20日线 {ma20:.2f}，继续持有。",
            f"若跌破20日线 {ma20:.2f} 且AI硬件链同步转弱，先减1/3锁定利润。",
            "缩量震荡时持有，等待方向确认。",
            "高",
        )

    if above_ma20 and change_5 > 0.05:
        return HoldingSignal(
            holding,
            "持有观察，不追高",
            f"收盘价 {last:.2f} 在20日线 {ma20:.2f} 上方，5日涨幅 {change_5:.1%}，短线已经偏热。",
            "",
            "持有，不追高；等待回踩不破20日线或新的基本面证据。",
            f"若回踩20日线 {ma20:.2f} 后重新转强，可继续持有。",
            f"若跌破20日线 {ma20:.2f} 且放量，降仓复核。",
            "缩量震荡时不加仓。",
            "中",
        )

    if below_ma20:
        return HoldingSignal(
            holding,
            "持有但不加仓",
            f"收盘价 {last:.2f} 低于20日线 {ma20:.2f}，趋势确认不足；暂未触发硬性减仓，但不能主动追买。",
            "",
            "不加仓；等重新站回20日线后再提高信心。",
            f"若放量站回20日线 {ma20:.2f} 上方，继续持有观察。",
            f"若跌破前20日技术支撑或板块明显转弱，先降1/4仓位。",
            "若围绕20日线下方震荡，保持仓位不动，等待确认。",
            "中",
        )

    return HoldingSignal(
        holding,
        "持有观察",
        f"收盘价 {last:.2f} 仍在20日线 {ma20:.2f} 附近，未触发减仓，也没有足够强的加仓确认。",
        "",
        "维持仓位，不主动加仓。",
        f"若放量站稳20日线 {ma20:.2f} 且涨幅扩散，可继续持有。",
        f"若跌破20日线 {ma20:.2f} 且回撤超过3%，降仓复核。",
        "窄幅震荡时等待，不因单日波动改变仓位。",
        "中" if ma20_gap < 0.03 else "低",
    )


def _signal_for_holding(
    holding: Holding,
    frame: ProviderResult[pd.DataFrame],
) -> HoldingSignal:  # type: ignore[no-redef]
    decision = build_holding_decision(holding, frame)
    return _decision_to_signal(holding, decision)


def _decision_to_signal(
    holding: Holding,
    decision: HoldingDecision,
) -> HoldingSignal:
    repair = decision.branch("repair_observe")
    risk = decision.branch("risk_reduce_review")
    waiting = decision.branch("continue_waiting")
    return HoldingSignal(
        holding=holding,
        action=decision.action,
        reason=decision.reason,
        data_gap=decision.data_gap,
        position_action=decision.position_action,
        upside_trigger=(
            f"{repair.trigger} 持续条件：{repair.persistence} "
            f"动作：{repair.action} 失效：{repair.invalidation}"
        ),
        downside_trigger=(
            f"{risk.trigger} 持续条件：{risk.persistence} "
            f"动作：{risk.action} 失效：{risk.invalidation}"
        ),
        flat_trigger=(
            f"{waiting.trigger} 持续条件：{waiting.persistence} "
            f"动作：{waiting.action} 失效：{waiting.invalidation}"
        ),
        priority=decision.priority,
        decision_contract=decision.to_contract(),
    )


def _legacy_signal_from_broker_snapshot(holding: Holding) -> HoldingSignal:
    weight = holding.weight_pct or 0.0
    pnl_pct = holding.pnl_pct or 0.0
    day_pnl_pct = holding.day_pnl_pct or 0.0
    reasons: list[str] = []
    if weight >= 40:
        reasons.append(f"仓位约 {weight:.1f}%，单票集中度偏高")
    if pnl_pct >= 35:
        reasons.append(f"浮盈约 {pnl_pct:.1f}%，需要保护利润")
    if day_pnl_pct <= -3:
        reasons.append(f"当日下跌 {day_pnl_pct:.1f}%，短线承压")
    if pnl_pct <= -8:
        reasons.append(f"总盈亏 {pnl_pct:.1f}%，接近亏损纪律")
    reason = "；".join(reasons) if reasons else "仅有券商持仓快照，缺少趋势和公告确认。"
    if pnl_pct <= -8 or day_pnl_pct <= -3:
        action = "减仓复核"
        position_action = "先按人工风控线降风险，不补仓。"
        priority = "高"
    elif weight >= 40:
        action = "高仓位持有，优先降集中度"
        position_action = "不加仓；冲高但量能不足时，优先降低集中度。"
        priority = "高"
    elif pnl_pct >= 35:
        action = "持有，保护浮盈"
        position_action = "继续持有核心仓位，同时上移止盈线。"
        priority = "高"
    else:
        action = "持有观察"
        position_action = "维持仓位，等行情数据恢复后再判断趋势。"
        priority = "中"
    return HoldingSignal(
        holding=holding,
        action=action,
        reason=reason,
        data_gap="未接入实时行情和公告，当前仅基于券商复制持仓快照。",
        position_action=position_action,
        upside_trigger="日线行情与复权口径恢复后，再按技术结构形成修复条件。",
        downside_trigger="若跌破人工风控线或单日放量下跌，先降风险。",
        flat_trigger="震荡时不加仓，优先等数据恢复。",
        priority=priority,
    )


def _signal_from_broker_snapshot(holding: Holding) -> HoldingSignal:  # type: ignore[no-redef]
    """Fail closed when the provider is unavailable; broker P&L is not a level."""

    return _decision_to_signal(
        holding,
        build_holding_decision(
            holding,
            ProviderResult(
                provider="amazingdata",
                schema_version="daily-ohlcv/v1",
                source_time=None,
                fetched_at=datetime.now().astimezone(),
                trade_date=None,
                status="empty",
                gaps=(f"{holding.code}:missing_series",),
                errors=(),
                price_basis="unknown",
                data=pd.DataFrame(
                    columns=[
                        "code",
                        "trade_date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "amount",
                    ]
                ),
            ),
        ),
    )


def _payload_action_lines(markdown: str) -> list[dict[str, object]]:  # type: ignore[no-redef]
    actions: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    field_map = {
        "建议动作": "action",
        "核心理由": "reason",
        "仓位动作": "position_action",
        "上行条件": "upside_trigger",
        "下行条件": "downside_trigger",
        "震荡处理": "flat_trigger",
        "明日优先级": "priority",
    }
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            if current and (current.get("action") or current.get("reason")):
                actions.append(current)
            name = line[4:].strip()
            code_match = CODE_PATTERN.search(name)
            current = {"name": name}
            if code_match:
                current["code"] = code_match.group("code")
            continue
        if current is None or not line.startswith("- "):
            continue
        text = line[2:].strip()
        if text.startswith("决策契约："):
            try:
                contract = json.loads(text[len("决策契约：") :].strip())
            except json.JSONDecodeError:
                contract = None
            if isinstance(contract, dict):
                current["decision_contract"] = contract
            continue
        for label, field in field_map.items():
            prefix = f"{label}："
            if text.startswith(prefix):
                current[field] = text[len(prefix) :].strip()
                break
    if current and (current.get("action") or current.get("reason")):
        actions.append(current)
    return actions
