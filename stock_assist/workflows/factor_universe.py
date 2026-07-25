"""Sync and report point-in-time index membership intervals."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from stock_assist.report_payload import create_report_payload, markdown_sections
from stock_assist.universe import sync_index_membership


DEFAULT_OUTPUT = Path("data/factor_universe/csi1000_membership.csv")


def build_factor_universe_bundle(
    index_code: str = "000852.SH",
    output_path: Path | None = None,
) -> tuple[dict[str, Any], str, str]:
    result = sync_index_membership(index_code, output_path or DEFAULT_OUTPUT)
    markdown = render_markdown(result)
    payload = create_report_payload(
        kind="factor_universe",
        workflow="factor-universe-sync",
        title="历史时点指数股票池",
        result=result,
        data_gaps=result["data_gaps"],
        sections=markdown_sections(markdown),
    )
    return payload, markdown, render_html(result)


def render_markdown(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# InsightRadar 历史时点指数股票池",
            "",
            "## 同步结论",
            f"- 指数：{result['index_code']}；股票池：{result['universe_id']}。",
            f"- 成员区间 {result['interval_rows']} 条；历史涉及 {result['unique_codes']} 只；当前开放区间 {result['open_intervals']} 条。",
            f"- 最早纳入日期：{result['earliest_in_date']}；数据获取时间：{result['retrieved_at']}。",
            f"- 血缘哈希：`{result['manifest_hash']}`。",
            f"- 本地契约：`{result['membership_path']}`。",
            "",
            "## 使用边界",
            "- 因子先使用历史代码并集计算滚动特征，再按当日成员区间过滤，避免新入成分缺失回看窗口。",
            "- 退出日期按半开区间处理：纳入日有效，退出日不再进入横截面。",
            "- 旧的个人20股账本继续使用独立 universe_id，不会与历史中证1000静默混训。",
            "",
            "## 数据缺口",
            *[f"- {item}" for item in result["data_gaps"]],
        ]
    )


def render_html(result: dict[str, Any]) -> str:
    gaps = "".join(f"<li>{escape(item)}</li>" for item in result["data_gaps"])
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>InsightRadar 历史股票池</title><style>
body{{margin:0;background:#08100f;color:#eaf2ef;font-family:system-ui,'Microsoft YaHei',sans-serif}}main{{max-width:940px;margin:auto;padding:28px 18px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}article,.panel{{background:#111b19;border:1px solid #294039;border-radius:14px;padding:16px;margin-bottom:14px}}span{{display:block;color:#91a59f;font-size:13px}}strong{{font-size:24px;color:#65dda0}}code{{word-break:break-all;color:#f0bd62}}@media(max-width:650px){{.cards{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>历史时点指数股票池</h1><p>成分区间 · PIT过滤 · 可复现血缘</p><section class="cards"><article><span>历史代码</span><strong>{result['unique_codes']}</strong></article><article><span>成员区间</span><strong>{result['interval_rows']}</strong></article><article><span>当前开放</span><strong>{result['open_intervals']}</strong></article></section><section class="panel"><h2>同步完成</h2><p>{escape(result['index_code'])} 已保存为 {escape(result['universe_id'])}。</p><p>manifest：<code>{escape(result['manifest_hash'])}</code></p></section><section class="panel"><h2>数据缺口</h2><ul>{gaps}</ul></section></main></body></html>"""
