"""Core style-rotation diagnostic workflow."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from stock_assist.data_sources.a_share_klines import fetch_public_klines
from stock_assist.paths import CONFIG_DIR
from stock_assist.report_payload import create_report_payload
from stock_assist.reports import markdown_report_to_html
from stock_assist.style_rotation import build_style_rotation_matrix


DEFAULT_CONFIG_PATH = CONFIG_DIR / "style_rotation.json"


def build_style_rotation_bundle(
    config_path: Path | None = None,
    *,
    as_of: str | None = None,
) -> tuple[dict[str, object], str, str]:
    actual = config_path or DEFAULT_CONFIG_PATH
    config = json.loads(actual.read_text(encoding="utf-8"))
    target_date = date.fromisoformat(as_of) if as_of else date.today()
    history_limit = int(config.get("history_limit") or 160)
    targets: list[dict[str, object]] = []
    benchmark = config.get("benchmark") if isinstance(config.get("benchmark"), dict) else {}
    targets.append(benchmark)
    for style in config.get("styles", []) if isinstance(config.get("styles"), list) else []:
        if isinstance(style, dict) and isinstance(style.get("members"), list):
            targets.extend(member for member in style["members"] if isinstance(member, dict))
    series = {}
    sources: dict[str, str] = {}
    gaps: list[str] = []
    for target in targets:
        code = str(target.get("code") or "")
        try:
            bars, source = fetch_public_klines(
                secid=str(target.get("secid") or ""),
                tencent_code=str(target.get("tencent_code") or ""),
                interval="day",
                limit=history_limit,
            )
            series[code] = [bar for bar in bars if bar.time.date() <= target_date and bar.close > 0]
            sources[code] = source
        except Exception as exc:
            gaps.append(f"{target.get('name') or code}日线不可用：{exc}")
    matrix = build_style_rotation_matrix(
        config,
        series,
        as_of=target_date,
        sources=sources,
        source_gaps=gaps,
    )
    payload = create_report_payload(
        kind="style_rotation",
        workflow="style-rotation",
        title="科技—金融—高股息风格确认矩阵",
        config=str(actual),
        summary_cards=[
            {"id": "status", "label": "Rotation", "value": matrix.get("style_rotation_status"), "tone": "warn", "note": "多证据、持续性确认"},
            {"id": "leader", "label": "Leader", "value": matrix.get("leader_style") or "待确认", "tone": "ok", "note": f"持续 {matrix.get('confirmation_days', 0)} 个交易日"},
            {"id": "weakening", "label": "Weakening", "value": matrix.get("weakening_style") or "待确认", "tone": "warn", "note": "20日相对强弱最低"},
            {"id": "coverage", "label": "Calibration", "value": "未回测", "tone": "warn", "note": "diagnostic_unbacktested"},
        ],
        components=[
            {"type": "summary_cards", "id": "summary", "items": "summary_cards"},
            {"type": "style_matrix", "id": "styles", "items": "styles"},
            {"type": "evidence_ledger", "id": "evidence", "items": "positive_evidence"},
            {"type": "data_gaps", "id": "data_gaps", "items": "data_gaps"},
        ],
        **matrix,
        data_gaps=gaps,
        disclaimer="风格矩阵只提供诊断证据，不单独授权买入、加仓或切换风险预算；ETF成交额代理不等于份额、净申购或国家队买卖。",
    )
    markdown = _render_markdown(payload)
    return payload, markdown, markdown_report_to_html(markdown)


def _render_markdown(payload: dict[str, object]) -> str:
    questions = payload.get("questions") if isinstance(payload.get("questions"), dict) else {}
    lines = [
        "# 科技—金融—高股息风格确认矩阵",
        "",
        "## 结论",
        f"- 状态：{payload.get('style_rotation_status') or '数据不足'}",
        f"- 领先风格：{payload.get('leader_style') or '待确认'}；走弱风格：{payload.get('weakening_style') or '待确认'}；持续 {payload.get('confirmation_days', 0)} 个交易日。",
        f"- 科技对比：{questions.get('technology_vs_financial_dividend') or '数据不足'}",
        f"- 单日还是轮动：{questions.get('single_day_or_rotation') or '数据不足'}",
        f"- 是否足以改变风险预算：{'是，仍需risk-watch审核' if questions.get('enough_to_change_risk_budget') else '否'}。",
        f"- 校准：{payload.get('calibration') or 'diagnostic_unbacktested'}。",
        "",
        "## 固定口径矩阵",
        "| 风格 | 固定口径 | 5日超额 | 20日超额 | 60日超额 | 上涨宽度 | MA20上方 | MA60上方 | 成交确认 | 覆盖率 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for style in payload.get("styles", []) if isinstance(payload.get("styles"), list) else []:
        if not isinstance(style, dict):
            continue
        rs = style.get("relative_strength") if isinstance(style.get("relative_strength"), dict) else {}
        breadth = style.get("breadth") if isinstance(style.get("breadth"), dict) else {}
        turnover = style.get("turnover") if isinstance(style.get("turnover"), dict) else {}
        lines.append(
            f"| {style.get('style_label')} | {style.get('definition')} | {_pct(rs.get('5d'))} | {_pct(rs.get('20d'))} | {_pct(rs.get('60d'))} | "
            f"{_pct(breadth.get('up_ratio'))} | {_pct(breadth.get('above_ma20_ratio'))} | {_pct(breadth.get('above_ma60_ratio'))} | "
            f"{turnover.get('confirmation') or 'unavailable'} | {_pct(style.get('coverage_ratio'))} |"
        )
    lines.extend(["", "## 正向证据"])
    lines.extend(f"- {item.get('family')}：{item.get('detail')}" for item in payload.get("positive_evidence", []) if isinstance(item, dict))
    if not payload.get("positive_evidence"):
        lines.append("- 暂无满足独立证据合同的正向确认。")
    lines.extend(["", "## 反向证据与阻断"])
    lines.extend(f"- {item.get('family')}：{item.get('detail')}" for item in payload.get("negative_evidence", []) if isinstance(item, dict))
    lines.extend(f"- 阻断：{item}" for item in payload.get("blocked_conclusions", []) if str(item))
    lines.extend(["", "## 数据覆盖与来源"])
    coverage = payload.get("source_coverage") if isinstance(payload.get("source_coverage"), dict) else {}
    lines.append(f"- 数据截至：{payload.get('as_of') or '待确认'}；基准：{coverage.get('benchmark') or '待确认'}。")
    lines.append("- ETF资金活跃度采用公开K线收盘价×成交量近似成交额占比；不是官方逐日成交额、ETF份额、净申购或国家队行为。")
    lines.append("- 盈利预测修正当前无固定点时源，状态保持unavailable，不补0。")
    gaps = payload.get("data_gaps") if isinstance(payload.get("data_gaps"), list) else []
    lines.extend(f"- 数据缺口：{item}" for item in gaps)
    lines.extend(["", "> 风格矩阵不自动执行交易，也不能单独授权买入或改变风险预算。"])
    return "\n".join(lines)


def _pct(value: object) -> str:
    return f"{float(value):.2%}" if isinstance(value, (int, float)) else "未提供"
