"""Global market snapshots for report context."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests


@dataclass(frozen=True)
class MarketIndexSnapshot:
    region: str
    symbol: str
    name: str
    price: float | None
    change_pct: float | None
    source: str = "Yahoo Finance chart"
    error: str = ""


@dataclass(frozen=True)
class MarketDailyBar:
    day: date
    close: float
    volume: float | None = None


MARKET_GROUPS = {
    "A股": [
        ("000001.SS", "上证指数"),
        ("399001.SZ", "深证成指"),
        ("399006.SZ", "创业板指"),
    ],
    "美股": [
        ("^GSPC", "标普500"),
        ("^IXIC", "纳斯达克"),
        ("^DJI", "道琼斯"),
    ],
    "韩国": [
        ("^KS11", "KOSPI"),
        ("^KQ11", "KOSDAQ"),
    ],
}


def fetch_global_market_groups(timeout: float = 6.0) -> dict[str, list[MarketIndexSnapshot]]:
    """Fetch a compact cross-market snapshot.

    This is intentionally best-effort: market context should enrich the report
    without blocking local portfolio analysis when a public endpoint is down.
    """

    requests_to_make = [
        (region, symbol, name)
        for region, items in MARKET_GROUPS.items()
        for symbol, name in items
    ]
    with ThreadPoolExecutor(
        max_workers=len(requests_to_make),
        thread_name_prefix="global-market",
    ) as executor:
        futures = {
            (region, symbol): executor.submit(
                _fetch_yahoo_chart,
                symbol,
                name,
                region,
                timeout,
            )
            for region, symbol, name in requests_to_make
        }
        return {
            region: [futures[(region, symbol)].result() for symbol, _name in items]
            for region, items in MARKET_GROUPS.items()
        }


def fetch_yahoo_history(symbol: str, *, range_name: str = "1y", timeout: float = 10.0) -> list[MarketDailyBar]:
    """Fetch adjusted-enough daily closes for cross-market regime comparison."""

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    response = requests.get(
        url,
        params={"range": range_name, "interval": "1d", "events": "div,splits"},
        headers={"User-Agent": "InsightRadar/0.1"},
        timeout=timeout,
    )
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    bars = _history_bars(result)
    if len(bars) < 20:
        raise RuntimeError(f"Yahoo Finance returned only {len(bars)} usable bars for {symbol}")
    return bars


def _history_bars(result: dict[str, object]) -> list[MarketDailyBar]:
    meta = result.get("meta")
    timezone_name = meta.get("exchangeTimezoneName") if isinstance(meta, dict) else None
    try:
        exchange_timezone = ZoneInfo(str(timezone_name))
    except (ZoneInfoNotFoundError, ValueError):
        offset_seconds = int(meta.get("gmtoffset") or 0) if isinstance(meta, dict) else 0
        exchange_timezone = timezone(timedelta(seconds=offset_seconds))
    timestamps = result.get("timestamp")
    indicators = result.get("indicators")
    quote_rows = indicators.get("quote") if isinstance(indicators, dict) else None
    quote = (
        quote_rows[0]
        if isinstance(quote_rows, list)
        and quote_rows
        and isinstance(quote_rows[0], dict)
        else {}
    )
    closes = quote.get("close")
    volumes = quote.get("volume")
    bars: list[MarketDailyBar] = []
    for index, timestamp in enumerate(
        timestamps if isinstance(timestamps, list) else []
    ):
        close = _to_float(
            closes[index]
            if isinstance(closes, list) and index < len(closes)
            else None
        )
        if close is None or close <= 0:
            continue
        volume = _to_float(
            volumes[index]
            if isinstance(volumes, list) and index < len(volumes)
            else None
        )
        local_day = (
            datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            .astimezone(exchange_timezone)
            .date()
        )
        bars.append(MarketDailyBar(day=local_day, close=close, volume=volume))
    return bars


def flatten_snapshots(groups: dict[str, list[MarketIndexSnapshot]]) -> Iterable[MarketIndexSnapshot]:
    for items in groups.values():
        yield from items


def _fetch_yahoo_chart(
    symbol: str,
    name: str,
    region: str,
    timeout: float,
) -> MarketIndexSnapshot:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": "5d", "interval": "1d"}
    headers = {"User-Agent": "InsightRadar/0.1"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        meta = result.get("meta", {})
        closes = [
            _to_float(value)
            for value in result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        ]
        closes = [value for value in closes if value is not None and value > 0]
        price = _to_float(meta.get("regularMarketPrice"))
        previous = _to_float(meta.get("previousClose"))
        if closes:
            price = price or closes[-1]
            previous = previous or (closes[-2] if len(closes) >= 2 else None)
        if price is None:
            price = _to_float(meta.get("chartPreviousClose"))
        change_pct = (price / previous - 1) if price is not None and previous not in (None, 0) else None
        return MarketIndexSnapshot(region, symbol, name, price, change_pct)
    except Exception as exc:
        return MarketIndexSnapshot(region, symbol, name, None, None, error=str(exc))


def _to_float(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
