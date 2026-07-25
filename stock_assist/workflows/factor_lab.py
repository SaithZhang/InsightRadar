"""InsightRadar factor-lab workflow and report renderers."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from stock_assist.factor_lab import FactorLabConfig, build_factor_panel, load_price_history, run_walk_forward
from stock_assist.report_payload import create_report_payload, markdown_sections
from stock_assist.universe import resolve_universe


DEFAULT_CONFIG = Path("configs/factor_lab.json")


def build_factor_lab_bundle(config_path: Path | None = None) -> tuple[dict[str, Any], str, str]:
    config = FactorLabConfig.load(config_path or DEFAULT_CONFIG)
    universe = resolve_universe(config)
    prices, data_gaps = load_price_history(config, universe)
    panel = build_factor_panel(prices, config.benchmark, config.horizon_days, universe)
    result = run_walk_forward(panel, config)
    result["universe_id"] = universe.universe_id
    result["universe_mode"] = universe.mode
    result["universe_manifest_hash"] = universe.manifest_hash
    if not universe.is_point_in_time:
        data_gaps.append("当前为显式试验股票池，不代表完整中证1000成分，也不能复刻任何私募产品。")
    if result["validation_status"] == "insufficient_sample":
        data_gaps.append("样本期数或股票数不足，当前排名只用于研究观察，不可称为有效策略。")
    elif result["validation_status"] == "failed_validation":
        data_gaps.append("样本外验收未通过：IC、分层收益、成本或共线性至少一项不达标；禁止据此进入模拟盘或实盘。")
    if not universe.is_point_in_time:
        data_gaps.append("显式股票池使用当前名单回看历史，存在生存者偏差；累计相对收益不能单独证明选股因子有效。")
    markdown = render_markdown(config, result, data_gaps, str(prices.attrs.get("source", "unknown")))
    payload = create_report_payload(
        kind="factor_lab",
        workflow="factor-lab",
        title="本地多因子滚动检验",
        config={
            "universe_name": config.universe_name,
            "universe_type": config.universe_type,
            "universe_id": universe.universe_id,
            "universe_mode": universe.mode,
            "universe_manifest_hash": universe.manifest_hash,
            "benchmark": config.benchmark,
            "horizon_days": config.horizon_days,
            "rebalance_days": config.rebalance_days,
            "transaction_cost_bps": config.transaction_cost_bps,
        },
        result=result,
        data_gaps=data_gaps,
        sections=markdown_sections(markdown),
    )
    return payload, markdown, render_html(config, result, data_gaps)


def render_markdown(config: FactorLabConfig, result: dict[str, Any], gaps: list[str], source: str) -> str:
    status_map = {"passed_pilot": "通过首轮门槛，可继续纸面跟踪", "failed_validation": "未通过样本外门槛", "insufficient_sample": "样本不足"}
    status = status_map.get(result["validation_status"], "状态未知")
    ranking = result.get("latest_ranking", [])
    rank_lines = [f"- {item['rank']}. {item['code']}：评分 {item['score']:+.4f}，收盘 {item['close']:.2f}" for item in ranking]
    weight_lines = [
        f"- {name}: 权重 {value:+.6f}，VIF {result.get('factor_vif', {}).get(name, float('nan')):.2f}"
        for name, value in result.get("factor_weights", {}).items()
    ]
    quintiles = result.get("quintile_average_returns", [])
    quintile_text = " / ".join(f"Q{index + 1} {_pct(value)}" for index, value in enumerate(quintiles)) or "NA"
    gap_lines = [f"- {item}" for item in gaps] or ["- 无"]
    return "\n".join(
        [
            "# InsightRadar 本地多因子滚动检验",
            "",
            "## 明确结论",
            f"- 状态：{status}；这不是明日涨跌预测，也不是自动交易指令。",
            f"- 股票池：{config.universe_name}（{result.get('universe_mode')}），当前 {result.get('universe_size_current', 0)} 只；基准 {config.benchmark}。",
            f"- 股票池血缘：{result.get('universe_id')}；manifest {str(result.get('universe_manifest_hash', ''))[:12]}。",
            f"- 样本外期数：{result['period_count']}；平均 RankIC {_pct(result.get('rank_ic_mean'))}；IC为正比例 {_pct(result.get('rank_ic_positive_rate'))}。",
            f"- 因子判别力：平均Top-Bottom {_pct(result.get('average_long_short_return'))}；五分组 {quintile_text}；单调性 {_pct(result.get('quintile_monotonicity'))}。",
            f"- 诊断项：计入单边 {config.transaction_cost_bps:.0f}bp 后，Top组合累计相对收益 {_pct(result.get('net_top_excess_total'))}，最大回撤 {_pct(result.get('net_top_excess_max_drawdown'))}；该项受股票池偏差污染，不能单独作为通过依据。",
            "- 应对：只有样本外IC、分层收益和换手成本同时过关，才进入模拟盘；否则改因子，不加仓验证。",
            "",
            "## 最新研究排名（诊断用，不是买入名单）",
            *(rank_lines or ["- 暂无可用排名。"]),
            "",
            "## 模型与参考K线",
            f"- 参考K线：日线，截止 {result['as_of']}；预测标签为未来 {config.horizon_days} 个交易日相对中证1000收益。",
            f"- 数据源：{source}；每 {config.rebalance_days} 个交易日调仓；训练窗口最多 {config.train_window_days} 日；标签隔离 {config.horizon_days} 日。",
            "- 预处理：逐日横截面MAD去极值、排序标准化；模型：滚动岭回归；不使用未来数据训练当期模型。",
            "- 因子：20-5动量、5日反转、60日趋势、20日低波、下行风险、流动性、Amihud冲击、量能异常。",
            "",
            "## 当前模型权重",
            *(weight_lines or ["- 暂无可用权重。"]),
            "",
            "## 数据缺口与边界",
            *gap_lines,
            "- 未做行业/市值中性化、涨跌停可交易性和真实冲击成本建模；这些是进入模拟盘前的硬门槛。",
            "- 截图中的私募净值不能反推出其因子；本模块只实现公开原则下的可复现实验。",
        ]
    )


def render_html(config: FactorLabConfig, result: dict[str, Any], gaps: list[str]) -> str:
    cards = [
        ("验证状态", {"passed_pilot": "首轮通过", "failed_validation": "未通过", "insufficient_sample": "样本不足"}.get(result["validation_status"], "未知")),
        ("平均 RankIC", _pct(result.get("rank_ic_mean"))),
        ("平均 Top-Bottom", _pct(result.get("average_long_short_return"))),
        ("最大回撤", _pct(result.get("net_top_excess_max_drawdown"))),
    ]
    card_html = "".join(f'<article><span>{escape(label)}</span><strong>{escape(value)}</strong></article>' for label, value in cards)
    rows = "".join(
        f"<tr><td>{item['rank']}</td><td>{escape(item['code'])}</td><td>{item['score']:+.4f}</td><td>{item['close']:.2f}</td></tr>"
        for item in result.get("latest_ranking", [])
    ) or '<tr><td colspan="4">暂无可用排名</td></tr>'
    gap_html = "".join(f"<li>{escape(gap)}</li>" for gap in gaps) or "<li>无</li>"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>InsightRadar 因子实验室</title><style>
body{{margin:0;background:#08100f;color:#e9f2ef;font-family:system-ui,'Microsoft YaHei',sans-serif}}main{{max-width:980px;margin:auto;padding:28px 18px}}h1{{font-size:28px}}.lead{{color:#9db1aa}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}}article,.panel{{background:#111b19;border:1px solid #263a35;border-radius:14px;padding:16px}}article span{{display:block;color:#91a59f;font-size:13px}}article strong{{display:block;font-size:24px;margin-top:8px;color:#66e0a3}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px;border-bottom:1px solid #263a35;text-align:left}}.warn{{border-left:4px solid #f0bd62}}@media(max-width:650px){{.cards{{grid-template-columns:repeat(2,1fr)}}table{{font-size:13px}}}}
</style></head><body><main><h1>本地多因子滚动检验</h1><p class="lead">日线 · 截止 {escape(result['as_of'])} · 未来{config.horizon_days}日相对收益 · 结论先行</p><section class="cards">{card_html}</section><section class="panel"><h2>明确结论</h2><p>当前是可复现的研究原型，不是明日涨跌预测。只有样本外 RankIC、分层收益、回撤与扣费后收益同时稳定，才进入模拟盘。</p></section><section class="panel"><h2>最新研究排名</h2><table><thead><tr><th>#</th><th>代码</th><th>模型分</th><th>收盘</th></tr></thead><tbody>{rows}</tbody></table></section><section class="panel warn"><h2>数据缺口</h2><ul>{gap_html}<li>尚未完成行业/市值中性化、涨跌停成交约束和真实冲击成本。</li></ul></section></main></body></html>"""


def _pct(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{float(value) * 100:+.2f}%"
