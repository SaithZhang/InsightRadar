"""Build no-lookahead account, holding, and theme snapshots from archives."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Iterable, Mapping

from stock_assist.intraday.contracts import (
    HoldingSnapshot,
    IntradaySnapshot,
    MinuteBar,
    PointQuote,
    QuoteFreshness,
    ThemeSnapshot,
)


class IntradaySnapshotBuilder:
    """Turn archived observations into one point-in-time decision snapshot."""

    def __init__(
        self,
        *,
        case: Mapping[str, object],
        themes: Iterable[Mapping[str, object]],
        bars_by_date: Mapping[date, Mapping[str, list[MinuteBar]]],
        quotes: Iterable[PointQuote],
        benchmark: str = "000300.SH",
        max_quote_age_seconds: int = 120,
    ) -> None:
        self.case = dict(case)
        self.themes = [dict(item) for item in themes]
        self.bars_by_date = {
            day: {symbol.upper(): list(rows) for symbol, rows in values.items()}
            for day, values in bars_by_date.items()
        }
        self.quotes = sorted(quotes, key=lambda item: (item.timestamp, item.symbol))
        self.benchmark = benchmark.upper()
        self.max_quote_age_seconds = max_quote_age_seconds
        self.holdings = [
            dict(item)
            for item in self.case.get("holdings", [])
            if isinstance(item, Mapping)
        ]
        self.cash = _float(self.case.get("cash"))

    def build(
        self,
        timestamp: datetime,
        *,
        previous: Iterable[IntradaySnapshot] = (),
    ) -> IntradaySnapshot:
        day_bars = self.bars_by_date.get(timestamp.date(), {})
        history = list(previous)
        quote_by_symbol = self._quotes_at(timestamp)
        holdings = tuple(
            self._holding_snapshot(item, timestamp, day_bars, quote_by_symbol)
            for item in self.holdings
        )
        theme_snapshots = tuple(
            self._theme_snapshot(item, timestamp, day_bars, quote_by_symbol)
            for item in self.themes
        )
        market_values = [
            item.market_value for item in holdings if item.market_value is not None
        ]
        portfolio_value = (
            sum(market_values) + self.cash
            if self.cash is not None and len(market_values) == len(holdings)
            else None
        )
        daily_pnls = [item.day_pnl for item in holdings if item.day_pnl is not None]
        daily_pnl = sum(daily_pnls) if len(daily_pnls) == len(holdings) else None
        declared_peak = _float(self.case.get("initial_account_peak_daily_pnl"))
        timed_declared_peaks = [
            _float(item.get("value"))
            for item in self.case.get("account_peak_observations", [])
            if isinstance(item, Mapping)
            and _datetime(item.get("source_time")) is not None
            and _datetime(item.get("source_time")) <= timestamp
        ]
        known_peaks = [
            item.account_peak_daily_pnl
            for item in history
            if item.account_peak_daily_pnl is not None
        ]
        pnl_values = [
            item.account_daily_pnl
            for item in history
            if item.account_daily_pnl is not None
        ]
        peak_candidates = [
            value
            for value in [declared_peak, *timed_declared_peaks, daily_pnl, *known_peaks, *pnl_values]
            if value is not None
        ]
        peak = max(peak_candidates) if peak_candidates else None
        giveback = (
            max(0.0, min(1.0, (peak - daily_pnl) / peak))
            if peak is not None and peak > 0 and daily_pnl is not None
            else None
        )
        exposure = self._exposure_by_theme(holdings, portfolio_value)
        freshness = self._freshness(timestamp, holdings, theme_snapshots)
        source_times = tuple(
            sorted(
                {
                    *(
                        source_time
                        for item in holdings
                        for source_time in item.source_times
                    ),
                    *(
                        source_time
                        for item in theme_snapshots
                        for source_time in item.source_times
                    ),
                }
            )
        )
        fetched_at = tuple(
            sorted(
                {
                    *(value for item in holdings for value in item.fetched_at),
                    *(value for item in theme_snapshots for value in item.fetched_at),
                }
            )
        )
        gaps: list[str] = []
        if portfolio_value is None:
            gaps.append("组合现金或持仓市值不完整，portfolio_value 保持 unknown。")
        if daily_pnl is None:
            gaps.append("持仓昨收或数量不完整，account_daily_pnl 保持 unknown。")
        missing_themes = [item.theme_id for item in theme_snapshots if item.state == "unavailable"]
        if missing_themes:
            gaps.append("主题点时数据不可用：" + "、".join(missing_themes))
        return IntradaySnapshot(
            timestamp=timestamp,
            portfolio_value=portfolio_value,
            account_daily_pnl=daily_pnl,
            account_peak_daily_pnl=peak,
            pnl_giveback_ratio=giveback,
            exposure_by_theme=exposure,
            quote_freshness=freshness,
            theme_snapshots=theme_snapshots,
            holding_snapshots=holdings,
            source_times=source_times,
            fetched_at=fetched_at,
            data_gaps=tuple(gaps),
        )

    def _holding_snapshot(
        self,
        holding: Mapping[str, object],
        timestamp: datetime,
        day_bars: Mapping[str, list[MinuteBar]],
        quote_by_symbol: Mapping[str, PointQuote],
    ) -> HoldingSnapshot:
        symbol = str(holding.get("symbol") or holding.get("code") or "").upper()
        bars = _through(day_bars.get(symbol, []), timestamp)
        quote = quote_by_symbol.get(symbol)
        point = _point_metrics(bars, quote)
        shares = _float(holding.get("shares"))
        price = point.get("price")
        pre_close = _float(holding.get("pre_close")) or _float(
            quote.pre_close if quote else None
        )
        market_value = shares * price if shares is not None and price is not None else None
        day_pnl = (
            shares * (price - pre_close)
            if shares is not None and price is not None and pre_close is not None
            else None
        )
        source_time = point.get("source_time")
        return HoldingSnapshot(
            symbol=symbol,
            name=str(holding.get("name") or symbol),
            shares=shares,
            available=_float(holding.get("available")),
            primary_theme_id=str(holding.get("primary_theme_id") or "unknown"),
            price=price,
            pre_close=pre_close,
            open=point.get("open"),
            market_value=market_value,
            day_pnl=day_pnl,
            return_pct=_pct_change(price, pre_close),
            return_from_open=_pct_change(price, point.get("open")),
            vwap_distance=point.get("vwap_distance"),
            session_low=point.get("session_low"),
            no_new_low=point.get("no_new_low"),
            higher_low=point.get("higher_low"),
            reclaimed_vwap=point.get("reclaimed_vwap"),
            reclaimed_rebound_high=point.get("reclaimed_rebound_high"),
            source_times=(source_time,) if isinstance(source_time, datetime) else (),
            fetched_at=(point["fetched_at"],) if isinstance(point.get("fetched_at"), datetime) else (),
        )

    def _theme_snapshot(
        self,
        theme: Mapping[str, object],
        timestamp: datetime,
        day_bars: Mapping[str, list[MinuteBar]],
        quote_by_symbol: Mapping[str, PointQuote],
    ) -> ThemeSnapshot:
        theme_id = str(theme.get("theme_id") or "unknown")
        etf = str(theme.get("representative_etf") or "").upper()
        raw_symbols = theme.get("representative_symbols")
        symbols = tuple(
            str(item).upper() for item in raw_symbols if str(item)
        ) if isinstance(raw_symbols, list) else ()
        etf_bars = _through(day_bars.get(etf, []), timestamp)
        etf_quote = quote_by_symbol.get(etf)
        point = _point_metrics(etf_bars, etf_quote)
        pre_close = _float(etf_quote.pre_close if etf_quote else None)
        rep_points = [
            _point_metrics(_through(day_bars.get(symbol, []), timestamp), quote_by_symbol.get(symbol))
            for symbol in symbols
        ]
        usable = [item for item in rep_points if item.get("price") is not None]
        benchmark_point = _point_metrics(
            _through(day_bars.get(self.benchmark, []), timestamp),
            quote_by_symbol.get(self.benchmark),
        )
        from_open = _pct_change(point.get("price"), point.get("open"))
        benchmark_from_open = _pct_change(
            benchmark_point.get("price"), benchmark_point.get("open")
        )
        relative_strength = (
            from_open - benchmark_from_open
            if from_open is not None and benchmark_from_open is not None
            else None
        )
        external_item = _external_item(self.case, theme_id)
        external = _float(external_item.get("return_pct")) if external_item else None
        external_source_time = _datetime(external_item.get("source_time")) if external_item else None
        source_times = tuple(
            sorted(
                {
                    item
                    for item in [
                        point.get("source_time"),
                        benchmark_point.get("source_time"),
                        *(row.get("source_time") for row in usable),
                        external_source_time,
                    ]
                    if isinstance(item, datetime)
                }
            )
        )
        fetched_at = tuple(
            sorted(
                {
                    item
                    for item in [
                        point.get("fetched_at"),
                        benchmark_point.get("fetched_at"),
                        *(row.get("fetched_at") for row in usable),
                        external_source_time,
                    ]
                    if isinstance(item, datetime)
                }
            )
        )
        component_source_times = {
            "etf": point.get("source_time") if isinstance(point.get("source_time"), datetime) else None,
            "benchmark": (
                benchmark_point.get("source_time")
                if isinstance(benchmark_point.get("source_time"), datetime) else None
            ),
            "representatives": max(
                (
                    row.get("source_time")
                    for row in usable
                    if isinstance(row.get("source_time"), datetime)
                ),
                default=None,
            ),
            "external_mapping": external_source_time,
        }
        component_freshness = {
            key: _component_freshness(timestamp, value, self.max_quote_age_seconds)
            for key, value in component_source_times.items()
        }
        state = (
            "unavailable"
            if point.get("price") is None
            else "auction_gap"
            if not etf_bars
            else "above_vwap"
            if (point.get("vwap_distance") or 0) >= 0
            else "below_vwap"
        )
        return ThemeSnapshot(
            theme_id=theme_id,
            representative_etf=etf,
            representative_symbols=symbols,
            gap_pct=_pct_change(point.get("open"), pre_close),
            return_pct=_pct_change(point.get("price"), pre_close),
            return_from_open=from_open,
            vwap_distance=point.get("vwap_distance"),
            volume_ratio_same_time=self._volume_ratio(etf, timestamp, etf_bars),
            breadth_above_open=_breadth(usable, "return_from_open"),
            breadth_above_vwap=_breadth(usable, "vwap_distance"),
            breadth_new_high=_boolean_breadth(usable, "at_new_high"),
            leader_confirmation=(
                any(
                    (item.get("return_from_open") or -999) >= 1.0
                    and (item.get("vwap_distance") or -999) >= 0
                    for item in usable
                )
                if usable and etf_bars
                else None
            ),
            external_mapping_return=external,
            relative_strength=relative_strength,
            state=state,
            no_new_low=point.get("no_new_low"),
            higher_low=point.get("higher_low"),
            reclaimed_vwap=point.get("reclaimed_vwap"),
            reclaimed_rebound_high=point.get("reclaimed_rebound_high"),
            source_times=source_times,
            fetched_at=fetched_at,
            price=_float(point.get("price")),
            minutes_without_new_low=_minutes_without_new_low(etf_bars),
            component_source_times=component_source_times,
            component_freshness=component_freshness,
        )

    def _volume_ratio(
        self,
        symbol: str,
        timestamp: datetime,
        current: list[MinuteBar],
    ) -> float | None:
        if not current:
            return None
        current_volume = sum(item.volume for item in current)
        prior_totals: list[float] = []
        for day in sorted(day for day in self.bars_by_date if day < timestamp.date())[-5:]:
            rows = self.bars_by_date[day].get(symbol, [])
            same_time = [
                item for item in rows if item.timestamp.time() <= timestamp.time()
            ]
            if same_time:
                prior_totals.append(sum(item.volume for item in same_time))
        baseline = sum(prior_totals) / len(prior_totals) if prior_totals else None
        return current_volume / baseline if baseline and baseline > 0 else None

    def _quotes_at(self, timestamp: datetime) -> dict[str, PointQuote]:
        result: dict[str, PointQuote] = {}
        for quote in self.quotes:
            if quote.timestamp <= timestamp:
                result[quote.symbol.upper()] = quote
        return result

    def _exposure_by_theme(
        self,
        holdings: tuple[HoldingSnapshot, ...],
        portfolio_value: float | None,
    ) -> dict[str, float | None]:
        theme_values: dict[str, float] = defaultdict(float)
        for item in holdings:
            if item.market_value is not None:
                theme_values[item.primary_theme_id] += item.market_value
        result: dict[str, float | None] = {
            theme_id: value / portfolio_value * 100 if portfolio_value else None
            for theme_id, value in theme_values.items()
        }
        result["cash"] = self.cash / portfolio_value * 100 if self.cash is not None and portfolio_value else None
        return result

    def _freshness(
        self,
        timestamp: datetime,
        holdings: tuple[HoldingSnapshot, ...],
        themes: tuple[ThemeSnapshot, ...],
    ) -> tuple[QuoteFreshness, ...]:
        symbols = {
            item.symbol: item.source_times[-1] if item.source_times else None
            for item in holdings
        }
        symbols.update(
            {
                item.representative_etf: item.component_source_times.get("etf")
                for item in themes
            }
        )
        fetched_lookup = {
            **{
                item.symbol: item.fetched_at[-1]
                for item in holdings
                if item.fetched_at
            },
            **{
                item.representative_etf: item.fetched_at[-1]
                for item in themes
                if item.fetched_at
            },
        }
        result: list[QuoteFreshness] = []
        for symbol, source_time in sorted(symbols.items()):
            age = (timestamp - source_time).total_seconds() if source_time else None
            status = (
                "missing"
                if source_time is None
                else "fresh"
                if age is not None and age <= self.max_quote_age_seconds
                else "stale"
            )
            result.append(
                QuoteFreshness(
                    symbol=symbol,
                    status=status,
                    source_time=source_time,
                    fetched_at=fetched_lookup.get(symbol, timestamp),
                    age_seconds=age,
                    max_age_seconds=self.max_quote_age_seconds,
                    source="local point-in-time archive",
                    gap_reason=None if status == "fresh" else "没有达到声明的新鲜度窗口。",
                )
            )
        return tuple(result)


def _component_freshness(
    timestamp: datetime,
    source_time: datetime | None,
    max_age_seconds: int,
) -> str:
    if source_time is None:
        return "missing"
    age = (timestamp - source_time).total_seconds()
    return "fresh" if 0 <= age <= max_age_seconds else "stale"


def _point_metrics(bars: list[MinuteBar], quote: PointQuote | None) -> dict[str, object]:
    if not bars:
        if quote is None:
            return {}
        return {
            "price": quote.price,
            "open": quote.open or quote.price,
            "source_time": quote.source_time,
            "fetched_at": quote.fetched_at,
            "return_from_open": _pct_change(quote.price, quote.open or quote.price),
            "vwap_distance": None,
            "session_low": quote.low or quote.price,
            "no_new_low": None,
            "higher_low": None,
            "reclaimed_vwap": None,
            "reclaimed_rebound_high": None,
            "at_new_high": None,
        }
    current = bars[-1]
    cumulative_volume = sum(item.volume for item in bars)
    cumulative_amount = sum(item.amount for item in bars)
    vwap = cumulative_amount / cumulative_volume if cumulative_volume > 0 else None
    previous = bars[:-1]
    no_new_low = current.low >= min((item.low for item in previous[-5:]), default=current.low)
    higher_low = (
        min(item.low for item in bars[-3:]) > min(item.low for item in bars[-6:-3])
        if len(bars) >= 6
        else None
    )
    rebound_high = max((item.high for item in previous[-5:]), default=None)
    return {
        "price": current.close,
        "open": bars[0].open,
        "source_time": current.source_time,
        "fetched_at": current.fetched_at,
        "return_from_open": _pct_change(current.close, bars[0].open),
        "vwap_distance": _pct_change(current.close, vwap),
        "session_low": min(item.low for item in bars),
        "no_new_low": no_new_low,
        "higher_low": higher_low,
        "reclaimed_vwap": current.close >= vwap if vwap is not None else None,
        "reclaimed_rebound_high": current.close >= rebound_high if rebound_high is not None else None,
        "at_new_high": current.high >= max(item.high for item in bars),
    }


def _minutes_without_new_low(bars: list[MinuteBar]) -> int | None:
    if not bars:
        return None
    session_low = min(item.low for item in bars)
    last_low = max(item.timestamp for item in bars if item.low <= session_low)
    return max(0, int((bars[-1].timestamp - last_low).total_seconds() // 60))


def _through(rows: Iterable[MinuteBar], timestamp: datetime) -> list[MinuteBar]:
    return [item for item in rows if item.timestamp <= timestamp]


def _breadth(rows: list[dict[str, object]], key: str) -> float | None:
    values = [item.get(key) for item in rows if item.get(key) is not None]
    return sum(float(value) >= 0 for value in values) / len(values) if values else None


def _boolean_breadth(rows: list[dict[str, object]], key: str) -> float | None:
    values = [item.get(key) for item in rows if item.get(key) is not None]
    return sum(bool(value) for value in values) / len(values) if values else None


def _external_item(case: Mapping[str, object], theme_id: str) -> Mapping[str, object] | None:
    mapping = case.get("external_mapping_returns")
    item = mapping.get(theme_id) if isinstance(mapping, Mapping) else None
    return item if isinstance(item, Mapping) else None


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _pct_change(value: object, base: object) -> float | None:
    numerator = _float(value)
    denominator = _float(base)
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator - 1) * 100


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
