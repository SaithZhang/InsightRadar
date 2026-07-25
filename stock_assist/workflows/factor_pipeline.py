"""Report bundle for the personal daily factor-model pipeline."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from stock_assist.factor_pipeline import run_factor_pipeline
from stock_assist.report_payload import create_report_payload, markdown_sections


DEFAULT_CONFIG = Path("configs/factor_pipeline.json")


def build_factor_pipeline_bundle(config_path: Path | None = None) -> tuple[dict[str, Any], str, str]:
    result = run_factor_pipeline(config_path or DEFAULT_CONFIG)
    markdown = render_markdown(result)
    payload = create_report_payload(
        kind="factor_pipeline",
        workflow="factor-pipeline",
        title="个人量化模型日更流水线",
        result=result,
        data_gaps=result["data_gaps"],
        sections=markdown_sections(markdown),
    )
    return payload, markdown, render_html(result)


def render_markdown(result: dict[str, Any]) -> str:
    candidate = result["candidate"]
    metrics = candidate.get("validation_metrics", {})
    gate_lines = [f"- {name}: {'通过' if passed else '未通过'}" for name, passed in candidate.get("gate_results", {}).items()]
    rank_lines = [
        f"- {item['rank']}. {item['code']}：{item['score']:+.5f}（收盘 {item['close']:.2f}）"
        for item in result["latest_ranking"]
    ]
    return "\n".join(
        [
            "# InsightRadar 个人量化模型日更流水线",
            "",
            "## 今日结论",
            f"- 模型：Ridge v1；候选版本 {result['candidate_version']}。",
            f"- 股票池血缘：{result['universe_id']}（{result['universe_mode']}）；manifest {result['universe_manifest_hash'][:12]}。",
            f"- 候选验证：{candidate['validation_status']}；冠军版本：{result['champion_version'] or '暂无'}。",
            f"- 晋级结果：{'已晋级' if result['promotion']['promoted'] else '未晋级'}（{result['promotion']['reason']}）。",
            f"- 数据账本：{result['observation_rows']} 行，成熟标签 {result['mature_rows']} 行，待成熟 {result['pending_rows']} 行；本次新增 {result['ingest']['new_rows']} 行、成熟 {result['ingest']['matured_labels']} 个标签。",
            f"- 样本外：{metrics.get('period_count', 0)} 日；RankIC {_pct(metrics.get('rank_ic_mean'))}；扣费Top-Bottom {_pct(metrics.get('net_top_bottom_mean'))}。",
            f"- 本地训练耗时：{result['runtime_seconds']:.2f} 秒；估算新增算力费用：¥{result['estimated_training_cost_cny']:.2f}。",
            "",
            "## 每日迭代机制",
            "- T日盘后写入特征与评分，但标签保持 pending。",
            "- 到T+5交易日后，写入相对中证1000真实收益，标签才允许进入训练集。",
            "- 每日用最近约252个交易日成熟样本全量重训候选模型；固定算法、可复现、可回滚。",
            "- 原始账本保留8个因子；Ridge v1使用其中7个，暂时排除与流动性高度共线的Amihud因子。",
            "- 候选必须同时通过RankIC、IC胜率、扣费分层、单调性、条件数和VIF门槛，才覆盖冠军模型。",
            "- 未通过的候选只进入模型注册表，绝不进入正式评分。",
            "",
            "## 晋级门槛",
            *(gate_lines or ["- 样本不足，尚未执行门槛判断。"]),
            "",
            f"## 最新排名（{result['ranking_mode']}，非交易指令）",
            *(rank_lines or ["- 暂无可用模型排名。"]),
            "",
            "## 数据缺口",
            *[f"- {gap}" for gap in result["data_gaps"]],
        ]
    )


def render_html(result: dict[str, Any]) -> str:
    candidate = result["candidate"]
    metrics = candidate.get("validation_metrics", {})
    cards = [
        ("候选模型", candidate["validation_status"]),
        ("冠军模型", result["champion_version"] or "暂无"),
        ("成熟标签", str(result["mature_rows"])),
        ("股票池", result["universe_id"]),
    ]
    card_html = "".join(f"<article><span>{escape(k)}</span><strong>{escape(v)}</strong></article>" for k, v in cards)
    gates = "".join(
        f"<li class=\"{'ok' if passed else 'bad'}\">{escape(name)}：{'通过' if passed else '未通过'}</li>"
        for name, passed in candidate.get("gate_results", {}).items()
    ) or "<li>样本不足</li>"
    rows = "".join(
        f"<tr><td>{item['rank']}</td><td>{escape(item['code'])}</td><td>{item['score']:+.5f}</td></tr>"
        for item in result["latest_ranking"]
    ) or '<tr><td colspan="3">暂无排名</td></tr>'
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>个人量化模型流水线</title><style>
body{{margin:0;background:#08100f;color:#eaf2ef;font-family:system-ui,'Microsoft YaHei',sans-serif}}main{{max-width:980px;margin:auto;padding:26px 18px}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}article,.panel{{background:#111b19;border:1px solid #294039;border-radius:14px;padding:16px;margin-bottom:14px}}article span{{display:block;color:#91a59f;font-size:13px}}article strong{{display:block;margin-top:8px;font-size:21px;color:#65dda0}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #294039}}.ok{{color:#65dda0}}.bad{{color:#ff7c8d}}@media(max-width:650px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main><h1>个人量化模型日更流水线</h1><p>日线 · {escape(result['as_of'])} · 本地CPU · 候选/冠军双轨</p><section class="cards">{card_html}</section><section class="panel"><h2>今日结论</h2><p>候选模型{'已' if result['promotion']['promoted'] else '未'}晋级：{escape(result['promotion']['reason'])}。没有冠军时，排名仅用于诊断。</p></section><section class="panel"><h2>晋级门槛</h2><ul>{gates}</ul></section><section class="panel"><h2>最新诊断排名</h2><table><thead><tr><th>#</th><th>代码</th><th>分数</th></tr></thead><tbody>{rows}</tbody></table></section></main></body></html>"""


def _pct(value: Any) -> str:
    return "NA" if value is None else f"{float(value) * 100:+.2f}%"
