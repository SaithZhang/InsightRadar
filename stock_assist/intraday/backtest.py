"""Counterfactual strategy comparison for one archived intraday case."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Iterable, Mapping

from stock_assist.intraday.contracts import IntradaySnapshot, ThemeSnapshot


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    label: str
    initial_reduction_pct: int = 0
    sell_trigger: str = "none"
    reentry_mode: str = "none"


STRATEGIES = (
    StrategySpec("full_hold", "全程持有"),
    StrategySpec("open_reduce_30", "开盘减30%", 30, "open"),
    StrategySpec("open_reduce_50", "开盘减50%", 50, "open"),
    StrategySpec("open_reduce_70", "开盘减70%", 70, "open"),
    StrategySpec("giveback_threshold_reduce", "回吐阈值减仓", 50, "giveback"),
    StrategySpec("vwap_failure_reduce", "VWAP失效减仓", 50, "vwap_failure"),
    StrategySpec(
        "drop_3_unconditional_reentry",
        "跌3%无条件接回",
        50,
        "open",
        "drop_3_unconditional",
    ),
    StrategySpec(
        "drop_3_structural_reentry",
        "跌3%且结构修复后接回",
        50,
        "open",
        "drop_3_structural",
    ),
    StrategySpec("no_same_day_reentry", "当天不接回", 50, "open", "none"),
)


def compare_strategies(
    snapshots: Iterable[IntradaySnapshot],
    *,
    technology_theme_ids: Iterable[str],
    actual_operations: Iterable[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Run deterministic portfolio simulations over the same point-time series."""

    rows = list(snapshots)
    if not rows:
        raise ValueError("intraday backtest requires at least one snapshot")
    tech_ids = set(technology_theme_ids)
    initial = rows[0]
    initial_holdings = {
        item.symbol: item
        for item in initial.holding_snapshots
        if item.shares is not None and item.price is not None
    }
    if len(initial_holdings) != len(initial.holding_snapshots):
        raise ValueError("all IR-001 holdings need point-in-time price and shares")
    tech_symbols = {
        item.symbol
        for item in initial.holding_snapshots
        if item.primary_theme_id in tech_ids
    }
    inferred_cash = (initial.portfolio_value or 0) - sum(
        float(item.market_value or 0) for item in initial.holding_snapshots
    )
    previous_close_equity = inferred_cash + sum(
        float(item.shares or 0) * float(item.pre_close or item.price or 0)
        for item in initial.holding_snapshots
    )
    results = [
        _simulate(
            spec,
            rows,
            initial_holdings=initial_holdings,
            tech_symbols=tech_symbols,
            tech_ids=tech_ids,
            initial_cash=inferred_cash,
            previous_close_equity=previous_close_equity,
        )
        for spec in STRATEGIES
    ]
    full_hold = next(item for item in results if item["strategy_id"] == "full_hold")
    for item in results:
        item["improvement_vs_full_hold"] = round(
            float(item["final_pnl"]) - float(full_hold["final_pnl"]), 2
        )
    actual = list(actual_operations)
    if not actual:
        actual_comparison: dict[str, object] = {
            "status": "unknown",
            "improvement_vs_actual": None,
            "reason": "未提供可核验的逐笔实际委托、成交和接回记录，不以代理策略冒充实际操作。",
        }
        for item in results:
            item["improvement_vs_actual"] = None
    else:
        actual_comparison = {
            "status": "not_implemented",
            "improvement_vs_actual": None,
            "reason": "case 包含实际操作，但当前版本尚未实现券商逐笔成交重放。",
        }
        for item in results:
            item["improvement_vs_actual"] = None
    return {
        "metric_definitions": {
            "final_return_pct": "相对按昨收重建的期初账户权益。",
            "max_profit_giveback": "账户当日利润峰值减去其后最低利润。",
            "max_drawdown_pct": "策略权益曲线相对此前峰值的最大跌幅。",
            "sold_too_early_rate_pct": "卖出后标的组合若曾较卖价再涨2%以上，则该笔计为卖飞。",
            "reentry_success_rate_pct": "接回后至收盘保持盈利且未从接回价再跌3%的接回比例。",
        },
        "previous_close_equity": round(previous_close_equity, 2),
        "strategies": results,
        "actual_comparison": actual_comparison,
    }


def _simulate(
    spec: StrategySpec,
    snapshots: list[IntradaySnapshot],
    *,
    initial_holdings: Mapping[str, object],
    tech_symbols: set[str],
    tech_ids: set[str],
    initial_cash: float,
    previous_close_equity: float,
) -> dict[str, object]:
    quantities = {
        symbol: float(getattr(holding, "shares"))
        for symbol, holding in initial_holdings.items()
    }
    original_quantities = dict(quantities)
    cash = initial_cash
    sold_quantities: dict[str, float] = {symbol: 0.0 for symbol in tech_symbols}
    sell_prices: dict[str, float] = {}
    trades: list[dict[str, object]] = []
    equity_curve: list[float] = []
    profit_curve: list[float] = []
    reentries: list[dict[str, object]] = []
    sold = False
    reentered = False

    for snapshot in snapshots:
        prices = {
            item.symbol: item.price
            for item in snapshot.holding_snapshots
            if item.price is not None
        }
        theme = _technology_theme(snapshot, tech_ids)
        should_sell = not sold and _sell_triggered(spec, snapshot, theme)
        if should_sell:
            fraction = spec.initial_reduction_pct / 100
            for symbol in tech_symbols:
                price = prices.get(symbol)
                if price is None:
                    continue
                quantity = original_quantities[symbol] * fraction
                quantities[symbol] -= quantity
                sold_quantities[symbol] += quantity
                cash += quantity * price
                sell_prices[symbol] = price
            trades.append(
                {
                    "timestamp": snapshot.timestamp.isoformat(timespec="minutes"),
                    "side": "reduce",
                    "fraction_pct": spec.initial_reduction_pct,
                    "reason": spec.sell_trigger,
                }
            )
            sold = True

        if sold and not reentered and _reentry_triggered(spec, snapshot, theme):
            cost = 0.0
            for symbol in tech_symbols:
                price = prices.get(symbol)
                quantity = sold_quantities[symbol]
                if price is None or quantity <= 0:
                    continue
                cost += quantity * price
            if cost <= cash + 1e-6:
                for symbol in tech_symbols:
                    quantity = sold_quantities[symbol]
                    if quantity <= 0:
                        continue
                    quantities[symbol] += quantity
                    sold_quantities[symbol] = 0.0
                cash -= cost
                reentered = True
                reentries.append(
                    {
                        "timestamp": snapshot.timestamp.isoformat(timespec="minutes"),
                        "cost": cost,
                        "prices": {symbol: prices.get(symbol) for symbol in tech_symbols},
                    }
                )
                trades.append(
                    {
                        "timestamp": snapshot.timestamp.isoformat(timespec="minutes"),
                        "side": "reentry",
                        "reason": spec.reentry_mode,
                    }
                )

        equity = cash + sum(
            quantity * float(prices.get(symbol) or 0)
            for symbol, quantity in quantities.items()
        )
        equity_curve.append(equity)
        profit_curve.append(equity - previous_close_equity)

    final_equity = equity_curve[-1]
    final_pnl = final_equity - previous_close_equity
    profit_peak = max(profit_curve)
    max_profit_giveback = max(
        peak - value
        for index, value in enumerate(profit_curve)
        for peak in [max(profit_curve[: index + 1])]
    )
    max_drawdown = max(
        (peak - value) / peak * 100 if peak > 0 else 0
        for index, value in enumerate(equity_curve)
        for peak in [max(equity_curve[: index + 1])]
    )
    sold_count = 0
    sold_too_early = 0
    if sell_prices:
        sold_count = len(sell_prices)
        for symbol, sale_price in sell_prices.items():
            later_prices = [
                float(item.price)
                for snapshot in snapshots
                for item in snapshot.holding_snapshots
                if item.symbol == symbol and item.price is not None
            ]
            if later_prices and max(later_prices) >= sale_price * 1.02:
                sold_too_early += 1
    successful_reentries = 0
    for entry in reentries:
        entry_prices = entry["prices"]
        success = True
        for symbol, entry_price in entry_prices.items():
            if entry_price is None:
                continue
            later = [
                float(item.price)
                for snapshot in snapshots
                if snapshot.timestamp.isoformat(timespec="minutes") >= entry["timestamp"]
                for item in snapshot.holding_snapshots
                if item.symbol == symbol and item.price is not None
            ]
            if not later or later[-1] <= float(entry_price) or min(later) <= float(entry_price) * 0.97:
                success = False
        successful_reentries += int(success)
    return {
        "strategy_id": spec.strategy_id,
        "label": spec.label,
        "final_equity": round(final_equity, 2),
        "final_pnl": round(final_pnl, 2),
        "final_return_pct": round(final_pnl / previous_close_equity * 100, 4),
        "profit_peak": round(profit_peak, 2),
        "max_profit_giveback": round(max_profit_giveback, 2),
        "max_drawdown_pct": round(max_drawdown, 4),
        "sold_too_early_rate_pct": round(sold_too_early / sold_count * 100, 2) if sold_count else 0.0,
        "trade_count": len(trades),
        "reentry_success_rate_pct": round(successful_reentries / len(reentries) * 100, 2) if reentries else None,
        "trades": trades,
    }


def _sell_triggered(
    spec: StrategySpec,
    snapshot: IntradaySnapshot,
    theme: ThemeSnapshot | None,
) -> bool:
    if spec.sell_trigger == "none":
        return False
    if spec.sell_trigger == "open":
        return snapshot.timestamp.time() >= time(9, 25)
    if spec.sell_trigger == "giveback":
        return (snapshot.pnl_giveback_ratio or 0) >= 0.2
    if spec.sell_trigger == "vwap_failure":
        return bool(
            theme
            and theme.vwap_distance is not None
            and theme.return_from_open is not None
            and theme.vwap_distance <= -0.3
            and theme.return_from_open <= -0.3
        )
    return False


def _reentry_triggered(
    spec: StrategySpec,
    snapshot: IntradaySnapshot,
    theme: ThemeSnapshot | None,
) -> bool:
    if theme is None or spec.reentry_mode == "none":
        return False
    dropped = theme.return_from_open is not None and theme.return_from_open <= -3
    if spec.reentry_mode == "drop_3_unconditional":
        return dropped
    if spec.reentry_mode == "drop_3_structural":
        return bool(
            dropped
            and theme.no_new_low is True
            and theme.higher_low is True
            and (theme.reclaimed_vwap or theme.reclaimed_rebound_high)
            and (theme.breadth_above_vwap or 0) >= 0.6
        )
    return False


def _technology_theme(
    snapshot: IntradaySnapshot,
    theme_ids: set[str],
) -> ThemeSnapshot | None:
    return next(
        (item for item in snapshot.theme_snapshots if item.theme_id in theme_ids),
        None,
    )
