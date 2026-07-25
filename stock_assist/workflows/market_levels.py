"""Multi-timeframe A-share index level indicator workflow."""

from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path

from stock_assist.branding import PRODUCT_NAME
from stock_assist.data_sources.a_share_klines import fetch_public_klines
from stock_assist.data_sources.eastmoney_klines import resample_minutes
from stock_assist.market_levels import TimeframeAnalysis, analyze_timeframe, synthesize_market_view
from stock_assist.paths import CONFIG_DIR
from stock_assist.report_payload import create_report_payload


DEFAULT_CONFIG_PATH = CONFIG_DIR / "market_levels.json"
TIMEFRAMES = ("month", "week", "day", "60m", "15m", "3m")


def build_market_levels_bundle(config_path: Path | None = None) -> tuple[dict[str, object], str, str]:
    config, gaps = _load_config(config_path)
    target = config.get("target") if isinstance(config.get("target"), dict) else {}
    secid = str(target.get("secid") or "1.000001")
    code = str(target.get("code") or "000001.SH")
    tencent_code = str(target.get("tencent_code") or _tencent_code(code))
    label = str(target.get("label") or "上证指数")
    limit = _positive_int(config.get("history_limit"), 500)
    analyses: list[TimeframeAnalysis] = []
    for timeframe in TIMEFRAMES:
        try:
            if timeframe == "3m":
                one_minute, source = fetch_public_klines(
                    secid=secid, tencent_code=tencent_code, interval="1m", limit=min(limit, 1000)
                )
                candles = resample_minutes(one_minute, 3)
                dates = {item.time.date() for item in one_minute}
                note = f"{source}；由1分钟线聚合为3分钟线。"
                if len(dates) < 2:
                    note += " 当前公开源仅覆盖当日，不能据此判断跨日3分钟背驰。"
                    gaps.append("3分钟线公开源仅覆盖当日，跨日结构未确认。")
            else:
                candles, source = fetch_public_klines(
                    secid=secid, tencent_code=tencent_code, interval=timeframe, limit=limit
                )
                note = f"{source}；当前周期最后一根K线可能尚未收盘。"
            analyses.append(analyze_timeframe(timeframe, candles, note))
        except Exception as exc:
            gaps.append(f"{timeframe} 数据/分析不可用：{exc}")
    synthesis = synthesize_market_view(analyses)
    payload = create_report_payload(
        kind="market_levels",
        workflow="market-levels",
        title=f"{label}多周期点位指示",
        config=str(config_path or DEFAULT_CONFIG_PATH),
        summary_cards=_summary_cards(synthesis, analyses),
        analysis=synthesis,
        target={"secid": secid, "code": code, "tencent_code": tencent_code, "label": label},
        timeframes=[item.to_dict() for item in analyses],
        components=[
            {"type": "summary_cards", "id": "summary", "items": "summary_cards"},
            {"type": "level_ladder", "id": "levels", "title": "多周期点位阶梯", "items": "timeframes"},
            {"type": "response_matrix", "id": "responses", "title": "走势应对矩阵", "items": "timeframes"},
            {"type": "data_gaps", "id": "data_gaps", "title": "Data Gaps", "items": "data_gaps"},
        ],
        methodology=[
            "缠论近似：局部分型 -> 交替笔 -> 最近三段价格重叠区（中枢）。程序结果不是人工严格画笔的替代。",
            "力度：MACD零轴、DIF/DEA与柱体扩张/收敛；价格创新低而柱体未创新低仅标记为背驰候选。",
            "点位：分型前低、均线、ATR、滚动高低点和波段回撤聚类；少于两类证据重合不报重点区间。",
            "所有结论都用守住、跌破、重新站回三类条件表达，不输出确定性涨跌预测。",
        ],
        data_gaps=gaps,
        disclaimer="仅供技术结构交流，不构成投资建议；未收盘K线会随行情变化。",
    )
    return payload, _render_markdown(payload), _render_html(payload)


def _load_config(path: Path | None) -> tuple[dict[str, object], list[str]]:
    actual = path or DEFAULT_CONFIG_PATH
    if not actual.exists():
        return {}, [f"未找到配置 {actual}，已使用上证指数默认参数。"]
    try:
        payload = json.loads(actual.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"配置解析失败：{exc}；已使用默认参数。"]
    if not isinstance(payload, dict):
        return {}, ["配置不是 JSON object，已使用默认参数。"]
    return payload, []


def _summary_cards(synthesis: dict[str, object], analyses: list[TimeframeAnalysis]) -> list[dict[str, object]]:
    confluence = synthesis.get("confluence_zone") if isinstance(synthesis.get("confluence_zone"), dict) else None
    confirmation = synthesis.get("confirmation_zone") if isinstance(synthesis.get("confirmation_zone"), dict) else None
    next_support = synthesis.get("next_support_zone") if isinstance(synthesis.get("next_support_zone"), dict) else None
    zone = f"{confluence['lower']:.0f}-{confluence['upper']:.0f}" if confluence else "证据不足"
    observed_low = synthesis.get("observed_intraday_low")
    return [
        {"id": "support", "label": "最高共振低点区", "value": zone, "tone": "ok", "note": "3/15/60分钟共同指向"},
        {"id": "observed", "label": "上午实际低点", "value": f"{float(observed_low):.2f}" if observed_low is not None else "NA", "tone": "ok", "note": "日K截至当前的最低点"},
        {"id": "confirmation", "label": "反弹确认区", "value": f"{confirmation['lower']:.0f}-{confirmation['upper']:.0f}" if confirmation else "待确认", "tone": "warn", "note": "站稳后再上调反弹级别"},
        {"id": "next", "label": "跌破后的大级别区", "value": f"{next_support['lower']:.0f}-{next_support['upper']:.0f}" if next_support else "待确认", "tone": "risk", "note": "月线与周线重合"},
    ]


def _render_markdown(payload: dict[str, object]) -> str:
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    confluence = analysis.get("confluence_zone") if isinstance(analysis.get("confluence_zone"), dict) else None
    confirmation = analysis.get("confirmation_zone") if isinstance(analysis.get("confirmation_zone"), dict) else None
    next_support = analysis.get("next_support_zone") if isinstance(analysis.get("next_support_zone"), dict) else None
    observed_low = analysis.get("observed_intraday_low")
    lines = [
        f"# {target.get('label', '大盘')}多周期点位指示",
        "",
        f"> 生成时间：{payload.get('generated_at', datetime.now().isoformat(timespec='seconds'))}。仅作结构交流，不预测走势。",
        "",
        "## 最终结论",
        "",
        f"- **上午低点：{float(observed_low):.2f}；最高共振低点区：{float(confluence['lower']):.0f}-{float(confluence['upper']):.0f}，核心约 {float(confluence['midpoint']):.0f}。**" if confluence and observed_low is not None else "- 点位证据不足。",
        f"- 定性：{analysis.get('verdict', '待确认')}。这是当前多周期最高共振区，不是已回测的统计高胜率。",
        "",
        "## 预案",
        "",
    ]
    for condition in analysis.get("conditions", []):
        lines.append(f"- {condition}")
    if next_support:
        lines.append(f"- 下一级：若失效，转看 {float(next_support['lower']):.0f}-{float(next_support['upper']):.0f}，重点仍是3800附近的大级别承接。")
    lines.extend(["", "## 参考K线", "", "| 周期 | 截止 | 结论 |", "|---|---|---|"])
    for item in analysis.get("reference_klines", []):
        if isinstance(item, dict):
            lines.append(f"| {item.get('timeframe')} | {item.get('as_of')} | {item.get('signal')} |")
    gaps = payload.get("data_gaps") or []
    if gaps:
        lines.extend(["", "## 数据缺口", ""])
        lines.extend(f"- {item}" for item in gaps)
    lines.extend(["", f"> {payload.get('disclaimer', '')}", ""])
    return "\n".join(lines)


def _timeframe_markdown(item: dict[str, object]) -> list[str]:
    lines = [
        f"### {item.get('label')}（截至 {item.get('as_of')}）",
        "",
        f"- 最新点位：{float(item.get('latest') or 0):.2f}；阶段：{item.get('phase')}；笔：{item.get('stroke_direction')}。",
        f"- MACD：{item.get('macd_state')}；背驰：{item.get('divergence')}。",
    ]
    center = item.get("center")
    if isinstance(center, dict):
        lines.append(f"- 中枢近似：{float(center['lower']):.2f}-{float(center['upper']):.2f}，当前在{center['relation']}。")
    supports = item.get("support_zones") or []
    if supports:
        lines.append("- 支撑区：" + "；".join(_zone_text(zone) for zone in supports if isinstance(zone, dict)) + "。")
    else:
        lines.append("- 支撑区：没有两类以上证据重合，不给伪精确点位。")
    resistances = item.get("resistance_zones") or []
    if resistances:
        lines.append("- 确认/压力区：" + "；".join(_zone_text(zone) for zone in resistances if isinstance(zone, dict)) + "。")
    lines.extend(f"- 应对：{text}" for text in item.get("response", []))
    if item.get("data_note"):
        lines.append(f"- 数据说明：{item.get('data_note')}")
    lines.append("")
    return lines


def _zone_text(zone: dict[str, object]) -> str:
    evidence = "/".join(str(item) for item in zone.get("evidence", []))
    return f"{float(zone['lower']):.2f}-{float(zone['upper']):.2f}（{evidence}）"


def _render_html(payload: dict[str, object]) -> str:
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    cards = "".join(
        f'<article class="card {escape(str(item.get("tone", "warn")))}"><small>{escape(str(item.get("label", "")))}</small><strong>{escape(str(item.get("value", "")))}</strong><span>{escape(str(item.get("note", "")))}</span></article>'
        for item in payload.get("summary_cards", []) if isinstance(item, dict)
    )
    rows = "".join(_timeframe_html(item) for item in payload.get("timeframes", []) if isinstance(item, dict))
    conditions = "".join(f"<li>{escape(str(item))}</li>" for item in analysis.get("conditions", []))
    references = "".join(
        f"<tr><td>{escape(str(item.get('timeframe','')))}</td><td>{escape(str(item.get('as_of','')))}</td><td>{escape(str(item.get('signal','')))}</td></tr>"
        for item in analysis.get("reference_klines", []) if isinstance(item, dict)
    )
    confluence = analysis.get("confluence_zone") if isinstance(analysis.get("confluence_zone"), dict) else None
    observed_low = analysis.get("observed_intraday_low")
    headline = (
        f"上午低点 {float(observed_low):.2f} 已落入 {float(confluence['lower']):.0f}-{float(confluence['upper']):.0f} 最高共振区"
        if confluence and observed_low is not None else "当前点位证据不足"
    )
    gaps = "".join(f"<li>{escape(str(item))}</li>" for item in payload.get("data_gaps", [])) or "<li>本次未识别到阻断性数据缺口。</li>"
    method = "".join(f"<li>{escape(str(item))}</li>" for item in payload.get("methodology", []))
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(str(target.get('label', '大盘')))}多周期点位指示</title>
<style>
:root{{--bg:#080c11;--panel:#111922;--line:#263341;--text:#edf5f2;--muted:#92a6aa;--ok:#59dfa0;--warn:#f2c66d;--risk:#ff7b76}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 system-ui,"Microsoft YaHei",sans-serif}}main{{width:min(1180px,calc(100% - 28px));margin:auto;padding:28px 0 50px}}h1{{margin:4px 0;font-size:32px}}h2{{font-size:18px}}.muted,small{{color:var(--muted)}}.decision{{margin:20px 0;padding:22px;border:1px solid #2f805e;border-radius:14px;background:linear-gradient(135deg,#10251d,#111922)}}.decision strong{{display:block;font-size:28px;color:var(--ok);line-height:1.3}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0}}.card,.panel,.tf{{background:linear-gradient(180deg,#15202a,#0e151c);border:1px solid var(--line);border-radius:12px;padding:16px}}.card{{display:flex;min-height:112px;flex-direction:column;gap:8px}}.card strong{{font-size:20px}}.card.ok{{border-color:#245b47}}.card.warn{{border-color:#6f5a2c}}.card.risk{{border-color:#713c3c}}.panel{{margin:14px 0}}.ladder{{display:grid;gap:12px;margin-top:12px}}.tf header{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}.tf h3{{margin:0;font-size:18px}}.badge{{border:1px solid var(--line);border-radius:99px;padding:3px 9px;color:var(--muted)}}.zones{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}}.zone{{background:#0a1118;border-radius:8px;padding:10px}}ul{{margin:8px 0;padding-left:20px}}li{{margin:5px 0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}details{{margin-top:12px;color:var(--muted)}}summary{{cursor:pointer;font-weight:800;color:var(--text)}}@media(max-width:760px){{.cards,.zones{{grid-template-columns:1fr}}h1{{font-size:25px}}.decision strong{{font-size:22px}}main{{width:min(100% - 18px,1180px)}}.table-wrap{{overflow-x:auto}}}}
</style></head><body><main>
<div class="muted">{escape(PRODUCT_NAME)} · MARKET LEVELS · {escape(str(payload.get('generated_at','')))}</div>
<h1>{escape(str(target.get('label','大盘')))}多周期点位指示</h1><p class="muted">用多周期结构定义如何应对，不把技术分析写成预测。</p>
<section class="decision"><small>最终结论</small><strong>{escape(headline)}</strong><span>{escape(str(analysis.get('win_rate_status','')))}</span></section>
<section class="cards">{cards}</section>
<section class="panel"><h2>预案</h2><ul>{conditions}</ul></section>
<section class="panel"><h2>参考K线</h2><div class="table-wrap"><table><thead><tr><th>周期</th><th>截止</th><th>结论</th></tr></thead><tbody>{references}</tbody></table></div></section>
<details class="panel"><summary>查看六周期详细计算</summary><section class="ladder">{rows}</section></details>
<details class="panel"><summary>方法口径与数据缺口</summary><h2>方法口径</h2><ul>{method}</ul><h2>数据缺口</h2><ul>{gaps}</ul></details>
<p class="muted">{escape(str(payload.get('disclaimer','')))}</p>
</main></body></html>"""


def _timeframe_html(item: dict[str, object]) -> str:
    supports = item.get("support_zones") or []
    resistances = item.get("resistance_zones") or []
    support_html = "".join(f"<li>{escape(_zone_text(zone))}</li>" for zone in supports if isinstance(zone, dict)) or "<li>证据不足，不报点位</li>"
    resistance_html = "".join(f"<li>{escape(_zone_text(zone))}</li>" for zone in resistances if isinstance(zone, dict)) or "<li>证据不足</li>"
    responses = "".join(f"<li>{escape(str(text))}</li>" for text in item.get("response", []))
    center = item.get("center")
    center_text = "未形成可识别重叠区"
    if isinstance(center, dict):
        center_text = f"{float(center['lower']):.2f}-{float(center['upper']):.2f} · {center['relation']}"
    return f"""<article class="tf"><header><div><h3>{escape(str(item.get('label')))}</h3><div class="muted">截至 {escape(str(item.get('as_of')))} · {item.get('bars')} 根K线</div></div><span class="badge">{float(item.get('latest') or 0):.2f}</span></header>
<p><b>{escape(str(item.get('phase')))}</b> · {escape(str(item.get('stroke_direction')))}<br><span class="muted">MACD：{escape(str(item.get('macd_state')))}；{escape(str(item.get('divergence')))}</span></p>
<div class="zones"><div class="zone"><b>支撑区</b><ul>{support_html}</ul></div><div class="zone"><b>确认/压力区</b><ul>{resistance_html}</ul></div></div>
<div class="muted">中枢近似：{escape(center_text)}</div><ul>{responses}</ul><div class="muted">{escape(str(item.get('data_note','')))}</div></article>"""


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _tencent_code(code: str) -> str:
    symbol, _, market = code.partition(".")
    prefix = "sh" if market.upper() == "SH" else "sz"
    return f"{prefix}{symbol}"
