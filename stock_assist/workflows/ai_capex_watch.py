"""AI infrastructure CapEx and optical-transmission report workflow."""

from __future__ import annotations

from datetime import date
from html import escape
import json
from pathlib import Path

from stock_assist.ai_capex_watch import score_ai_capex_watch
from stock_assist.branding import PRODUCT_NAME
from stock_assist.paths import CONFIG_DIR
from stock_assist.report_payload import create_report_payload


DEFAULT_CONFIG_PATH = CONFIG_DIR / "ai_capex_watch.json"


def build_ai_capex_watch_bundle(
    config_path: Path | None = None,
    *,
    as_of: str | None = None,
) -> tuple[dict[str, object], str, str]:
    path = config_path or DEFAULT_CONFIG_PATH
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{path}不是JSON object")
    target_day = date.fromisoformat(as_of) if as_of else date.today()
    result = score_ai_capex_watch(config, target_day)
    payload = create_report_payload(
        kind="ai_capex_watch",
        workflow="ai-capex-watch",
        title="AI资本开支与光模块传导监控",
        config=str(path),
        **result,
        methodology=[
            "只让评分日以前、未过期且标记为official的披露参与评分；用户转述和研报推断不参与。",
            "CapEx动量比较同口径指引修正、支出扩张、上调广度和AI/数据中心关联，不直接汇总不同会计口径的美元总额。",
            "光模块传导必须经过网络收入/投入、800G/1.6T需求和供应商财务兑现；缺失环节显示为数据缺口。",
            "分数只调整产业论点置信度，未经回放校准不得覆盖risk-watch仓位预算或自动触发交易。",
        ],
        disclaimer="本报告是只读研究监控，不构成投资建议；强产业景气不等于当前股价低估。",
    )
    return payload, _render_markdown(payload), _render_html(payload)


def _render_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# AI资本开支与光模块传导监控",
        "",
        f"> 截至 {payload.get('as_of')}；{payload.get('conclusion')}",
        "",
        "## 核心指标",
        "",
        "| 指标 | 分数 | 覆盖 | 状态 | 解释 |",
        "|---|---:|---:|---|---|",
    ]
    for item in payload.get("metrics", []):
        if isinstance(item, dict):
            score = "待验证" if item.get("score") is None else f"{float(item['score']):.0f}/100"
            lines.append(
                f"| {item.get('label')} | {score} | {float(item.get('coverage') or 0):.0%} | {_state_label(item.get('state'))} | {item.get('detail')} |"
            )
    lines.extend(["", "## 今日指引", ""])
    lines.extend(f"- {item}" for item in payload.get("actions", []))
    lines.extend(["", "## 云厂商CapEx拆解", ""])
    for item in payload.get("companies", []):
        if not isinstance(item, dict):
            continue
        guide = _guide_text(item)
        lines.append(
            f"- **{item.get('name')}（{item.get('ticker')}）**：{guide}；方向 {item.get('guidance_direction')}。"
            f"[{item.get('source_label', '官方来源')}]({item.get('source_url')})"
        )
    lines.extend(["", "## 光模块传导证据", ""])
    for item in payload.get("optical_evidence", []):
        if isinstance(item, dict):
            lines.append(
                f"- **{item.get('metric_name')}**：{item.get('detail')}。"
                f"[{item.get('source_label', '官方来源')}]({item.get('source_url')})"
            )
    lines.extend(["", "## 中际待验证清单", ""])
    for item in payload.get("supplier_checks", []):
        if isinstance(item, dict):
            lines.append(f"- {item.get('label')}：{item.get('status')}；{item.get('decision_use')}")
    lines.extend(["", "## 数据缺口", ""])
    lines.extend(f"- {item}" for item in payload.get("data_gaps", []))
    lines.extend(["", "## 方法与边界", ""])
    lines.extend(f"- {item}" for item in payload.get("methodology", []))
    lines.extend(["", f"> {payload.get('disclaimer')}", ""])
    return "\n".join(lines)


def _render_html(payload: dict[str, object]) -> str:
    metrics = "".join(_metric_card(item) for item in payload.get("metrics", []) if isinstance(item, dict))
    actions = "".join(f"<li>{escape(str(item))}</li>" for item in payload.get("actions", []))
    companies = "".join(_company_row(item) for item in payload.get("companies", []) if isinstance(item, dict))
    evidence = "".join(_evidence_row(item) for item in payload.get("optical_evidence", []) if isinstance(item, dict))
    checks = "".join(
        f"<li><b>{escape(str(item.get('label','')))}</b> · {escape(str(item.get('status','')))} · {escape(str(item.get('decision_use','')))}</li>"
        for item in payload.get("supplier_checks", []) if isinstance(item, dict)
    )
    gaps = "".join(f"<li>{escape(str(item))}</li>" for item in payload.get("data_gaps", []))
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI资本开支监控</title>
<style>:root{{--bg:#071018;--panel:#111d27;--line:#263b49;--text:#edf6f8;--muted:#91a8b4;--cyan:#58d6d2;--green:#56d39a;--yellow:#f3c969}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.65 system-ui,"Microsoft YaHei",sans-serif}}main{{width:min(1080px,calc(100% - 28px));margin:auto;padding:28px 0}}h1{{font-size:30px;margin:4px 0}}a{{color:var(--cyan)}}.muted{{color:var(--muted)}}.hero,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:20px;margin:16px 0}}.hero{{border-color:#2f7478}}.hero b{{display:block;font-size:20px;color:var(--cyan);margin-top:8px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card{{background:#0b1720;border:1px solid var(--line);border-radius:12px;padding:15px}}.card strong{{display:block;font-size:28px;color:var(--cyan)}}.bar{{height:7px;background:#20333f;border-radius:10px;overflow:hidden;margin-top:9px}}.fill{{height:100%;background:linear-gradient(90deg,var(--cyan),var(--green))}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}ul{{padding-left:20px}}@media(max-width:720px){{.cards{{grid-template-columns:1fr}}.table{{overflow-x:auto}}h1{{font-size:24px}}}}</style></head><body><main>
<div class="muted">{escape(PRODUCT_NAME)} · AI CAPEX WATCH · {escape(str(payload.get('generated_at','')))}</div><h1>AI资本开支与光模块传导监控</h1>
<section class="hero"><span>截至 {escape(str(payload.get('as_of','')))}</span><b>{escape(str(payload.get('conclusion','')))}</b></section>
<section class="cards">{metrics}</section>
<section class="panel"><h2>今日指引</h2><ul>{actions}</ul></section>
<section class="panel"><h2>云厂商CapEx</h2><div class="table"><table><thead><tr><th>公司</th><th>当前指引/实际</th><th>方向</th><th>来源</th></tr></thead><tbody>{companies}</tbody></table></div></section>
<section class="panel"><h2>光模块传导证据</h2><div class="table"><table><thead><tr><th>指标</th><th>证据</th><th>来源</th></tr></thead><tbody>{evidence}</tbody></table></div></section>
<section class="panel"><h2>中际待验证清单</h2><ul>{checks}</ul></section>
<section class="panel"><h2>数据缺口与边界</h2><ul>{gaps}</ul></section>
</main></body></html>"""


def _metric_card(item: dict[str, object]) -> str:
    score = item.get("score")
    shown = "待验证" if score is None else f"{float(score):.0f}"
    width = 0.0 if score is None else max(0.0, min(100.0, float(score)))
    return (
        '<article class="card">'
        f'<span>{escape(str(item.get("label","")))}</span><strong>{shown}</strong>'
        f'<div>{escape(_state_label(item.get("state")))} · 覆盖 {float(item.get("coverage") or 0):.0%}</div>'
        f'<div class="bar"><div class="fill" style="width:{width:.1f}%"></div></div>'
        f'<p class="muted">{escape(str(item.get("detail","")))}</p></article>'
    )


def _company_row(item: dict[str, object]) -> str:
    url = escape(str(item.get("source_url", "")), quote=True)
    label = escape(str(item.get("source_label", "官方来源")))
    return (
        f"<tr><td><b>{escape(str(item.get('name','')))}</b><br>{escape(str(item.get('ticker','')))}</td>"
        f"<td>{escape(_guide_text(item))}</td><td>{escape(str(item.get('guidance_direction','')))}</td>"
        f'<td><a href="{url}">{label}</a></td></tr>'
    )


def _evidence_row(item: dict[str, object]) -> str:
    url = escape(str(item.get("source_url", "")), quote=True)
    label = escape(str(item.get("source_label", "官方来源")))
    return (
        f"<tr><td><b>{escape(str(item.get('metric_name','')))}</b></td>"
        f"<td>{escape(str(item.get('detail','')))}</td><td><a href=\"{url}\">{label}</a></td></tr>"
    )


def _guide_text(item: dict[str, object]) -> str:
    low = item.get("guidance_low_billion_usd")
    high = item.get("guidance_high_billion_usd")
    period = item.get("guidance_period", "")
    if isinstance(low, (int, float)) or isinstance(high, (int, float)):
        low = high if low is None else low
        high = low if high is None else high
        shown = f"{float(low):.1f}" if float(low) == float(high) else f"{float(low):.1f}–{float(high):.1f}"
        return f"{period} 指引 {shown} 十亿美元"
    actual = item.get("actual_capex_billion_usd")
    if isinstance(actual, (int, float)):
        return f"{item.get('actual_period','')} 实际 {float(actual):.1f} 十亿美元"
    return "未披露可比金额"


def _state_label(value: object) -> str:
    return {
        "positive": "正向",
        "positive_low_confidence": "正向·低覆盖",
        "neutral": "中性",
        "negative": "负向",
        "negative_low_confidence": "负向·低覆盖",
        "insufficient": "证据不足",
        "pending": "待验证",
        "partial": "部分验证",
    }.get(str(value), str(value))
