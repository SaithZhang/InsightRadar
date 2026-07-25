"""Crypto monitoring report workflow."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from stock_assist.data_sources.hyperliquid import (
    HyperliquidError,
    MarketPosition,
    PerpMarket,
    PerpPosition,
    fetch_account_state,
    fetch_liquidation_risk,
    fetch_market_snapshot,
    fetch_top_positions,
    parse_positions,
)
from stock_assist.paths import CONFIG_DIR
from stock_assist.reports import bullet


DEFAULT_CONFIG_PATH = CONFIG_DIR / "crypto_watchlist.json"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "crypto_watchlist.example.json"


def build_crypto_monitor_report(config_path: Path | None = None) -> str:
    path = config_path or DEFAULT_CONFIG_PATH
    config, gaps = _load_config(path)
    dex = str(config.get("dex", ""))
    symbols = [str(item).upper() for item in config.get("symbols", [])] or ["BTC", "ETH", "HYPE", "SOL"]
    addresses = [item for item in config.get("addresses", []) if isinstance(item, dict)]
    rules = config.get("alert_rules", {}) if isinstance(config.get("alert_rules"), dict) else {}
    radar = config.get("market_radar", {}) if isinstance(config.get("market_radar"), dict) else {}

    try:
        markets = fetch_market_snapshot(dex=dex)
    except HyperliquidError as exc:
        markets = {}
        gaps.append(str(exc))

    lines = [
        "# 加密资产监控：Hyperliquid",
        "",
        "## 数据状态",
        bullet(
            [
                f"配置文件：{path}",
                f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Hyperliquid dex：{dex or '主市场'}",
                "数据源：Hyperliquid Info API，只读；不需要私钥，不执行交易。",
            ]
            + gaps
        ),
        "",
        "## 市场概览",
        _format_market_overview(symbols, markets),
        "",
        "## 市场异动雷达",
        _format_market_radar(symbols, markets, radar, rules, addresses),
        "",
        "## 地址仓位",
    ]

    if addresses:
        for item in addresses:
            lines.extend(_format_address_block(item, markets, rules, dex))
    else:
        lines.append("- 暂无完整地址；请在配置文件 addresses 中填入 0x 开头完整地址。")

    lines.extend(
        [
            "",
            "## 风险提醒",
            bullet(
                [
                    "开发版监控只读查询公开数据，不能替代交易风控。",
                    "RWA/HIP-3 市场需要指定对应 dex，例如 trade.xyz 使用 dex=xyz。",
                    "单地址公开后容易失效；市场异动雷达用于发现换地址后的类似行为。",
                    "优先关注：名义仓位、未实现盈亏、距强平价、资金费率、OI 和 24h 成交额。",
                ]
            ),
            "",
            "## 下一步",
            "- 如需长期跟踪，把示例配置复制为 configs/crypto_watchlist.json 后调整观察地址和阈值。",
            "- 后续可接入定时任务，把接近强平或仓位突增的报告推送到晨报/盘中提醒。",
        ]
    )
    return "\n".join(lines)


def _load_config(path: Path) -> tuple[dict[str, Any], list[str]]:
    gaps: list[str] = []
    if not path.exists():
        gaps.append(f"未找到正式配置，已使用示例配置：{EXAMPLE_CONFIG_PATH}")
        path = EXAMPLE_CONFIG_PATH
    if not path.exists():
        gaps.append("示例配置也不存在，使用内置默认观察列表。")
        return {}, gaps
    return json.loads(path.read_text(encoding="utf-8")), gaps


def _format_market_overview(symbols: list[str], markets: dict[str, PerpMarket]) -> str:
    rows: list[str] = []
    for symbol in symbols:
        market = _find_market(symbol, markets)
        if market is None:
            rows.append(f"{symbol}：未命中 Hyperliquid perp 市场")
            continue
        rows.append(
            f"{symbol}：mark {_fmt(market.mark_px)}，24h {_fmt_pct(market.change_24h_pct)}，"
            f"funding {_fmt_pct(_scale_pct(market.funding))}，OI {_fmt(market.open_interest)}，"
            f"24h成交额 {_fmt(market.day_notional_volume)}"
        )
    return bullet(rows)


def _format_market_radar(
    symbols: list[str],
    markets: dict[str, PerpMarket],
    radar: dict[str, Any],
    rules: dict[str, Any],
    addresses: list[dict[str, Any]],
) -> str:
    if radar.get("enabled", True) is False:
        return "- 未启用。"

    known_addresses = {
        str(item.get("address", "")).strip().lower()
        for item in addresses
        if str(item.get("address", "")).strip().startswith("0x")
    }
    limit = int(_to_float(radar.get("top_positions_limit")) or 5)
    risk_limit = int(_to_float(radar.get("liquidation_risk_limit")) or 5)
    min_notional = _to_float(radar.get("min_notional")) or _to_float(rules.get("position_notional_gt"))
    max_distance_pct = _to_float(radar.get("max_distance_pct")) or _to_float(
        rules.get("liquidation_distance_pct_lt")
    )

    lines: list[str] = []
    for symbol in symbols:
        market = _find_market(symbol, markets)
        if market is None:
            lines.append(f"### {symbol}")
            lines.append("- 未命中市场，跳过异动扫描。")
            continue

        lines.append(f"### {symbol}")
        try:
            top_positions = fetch_top_positions(market.coin, limit=limit)
            risk_positions = fetch_liquidation_risk(
                market.coin,
                limit=risk_limit,
                min_notional=min_notional,
                max_distance_pct=max_distance_pct,
            )
        except HyperliquidError as exc:
            lines.append(f"- 异动扫描失败：{exc}")
            continue

        lines.append("- 最大仓位：")
        if top_positions:
            for item in top_positions[:limit]:
                lines.append(f"  - {_format_market_position(item, market, known_addresses)}")
        else:
            lines.append("  - 暂无。")

        lines.append("- 清算风险：")
        if risk_positions:
            for item in risk_positions[:risk_limit]:
                lines.append(f"  - {_format_market_position(item, market, known_addresses)}")
        else:
            lines.append("  - 暂无命中阈值。")
    return "\n".join(lines)


def _format_address_block(
    item: dict[str, Any],
    markets: dict[str, PerpMarket],
    rules: dict[str, Any],
    dex: str,
) -> list[str]:
    label = str(item.get("label") or "未命名地址")
    address = str(item.get("address") or "").strip()
    lines = [f"### {label}"]
    if not address or address.endswith("..."):
        lines.append("- 数据缺口：地址不完整，无法查询 Hyperliquid 仓位。")
        return lines

    try:
        state = fetch_account_state(address, dex=dex)
        positions = parse_positions(state, markets)
    except HyperliquidError as exc:
        lines.append(f"- 查询失败：{exc}")
        return lines

    margin = state.get("marginSummary", {}) if isinstance(state.get("marginSummary"), dict) else {}
    lines.append(
        f"- 账户：{_short_addr(address)}；账户权益 {_fmt_float_text(margin.get('accountValue'))}；"
        f"总名义仓位 {_fmt_float_text(margin.get('totalNtlPos'))}；保证金占用 {_fmt_float_text(margin.get('totalMarginUsed'))}"
    )
    if not positions:
        lines.append("- 当前无永续合约持仓。")
        return lines

    for position in positions:
        lines.append(_format_position(position, rules))
    return lines


def _format_position(position: PerpPosition, rules: dict[str, Any]) -> str:
    flags: list[str] = []
    notional_limit = _to_float(rules.get("position_notional_gt"))
    liq_limit = _to_float(rules.get("liquidation_distance_pct_lt"))
    if (
        notional_limit is not None
        and position.position_value is not None
        and position.position_value >= notional_limit
    ):
        flags.append("大额仓位")
    if (
        liq_limit is not None
        and position.liquidation_distance_pct is not None
        and position.liquidation_distance_pct <= liq_limit
    ):
        flags.append("接近强平")
    flag_text = f"；信号：{','.join(flags)}" if flags else ""
    return (
        f"- {position.coin} {position.side}：名义 {_fmt(position.position_value)}，size {_fmt(position.size)}，"
        f"mark {_fmt(position.mark_px)}，entry {_fmt(position.entry_px)}，liq {_fmt(position.liquidation_px)}，"
        f"距强平 {_fmt_pct(position.liquidation_distance_pct)}，uPnL {_fmt(position.unrealized_pnl)}，"
        f"ROE {_fmt_pct(_scale_pct(position.return_on_equity))}，杠杆 {position.leverage or '未披露'}{flag_text}"
    )


def _format_market_position(
    position: MarketPosition,
    market: PerpMarket,
    known_addresses: set[str],
) -> str:
    notional = position.notional
    if notional is None and position.abs_size is not None and market.mark_px is not None:
        notional = position.abs_size * market.mark_px
    known = "；已知观察地址" if position.user in known_addresses else ""
    distance = f"，距清算 {_fmt_pct(position.distance_pct)}" if position.distance_pct is not None else ""
    leverage = f"，杠杆 {_fmt(position.leverage)}x" if position.leverage is not None else ""
    return (
        f"{_short_addr(position.user)} {position.side}：size {_fmt(position.abs_size)}，"
        f"名义 {_fmt(notional)}，entry {_fmt(position.entry_px)}{distance}{leverage}{known}"
    )


def _find_market(symbol: str, markets: dict[str, PerpMarket]) -> PerpMarket | None:
    direct = markets.get(symbol)
    if direct is not None:
        return direct
    for coin, market in markets.items():
        if coin.split(":")[-1] == symbol:
            return market
    return None


def _short_addr(address: str) -> str:
    if len(address) <= 12:
        return address
    return f"{address[:6]}...{address[-4:]}"


def _fmt(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:,.4f}" if abs(value) < 1 else f"{value:,.2f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:+.2f}%"


def _scale_pct(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100


def _fmt_float_text(value: object) -> str:
    parsed = _to_float(value)
    return _fmt(parsed)


def _to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
