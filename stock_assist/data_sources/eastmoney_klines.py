"""Public Eastmoney K-line adapter used by the market-levels workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from urllib.parse import urlencode
from urllib.request import OpenerDirector, Request

from stock_assist.intraday.network import build_urllib_opener, provider_policy


EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EASTMONEY_UT = "fb5fd1943c7b386f172d6893dbfba10b"
KLINE_PERIODS = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "day": 101,
    "week": 102,
    "month": 103,
}


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    close: float
    high: float
    low: float
    volume: float
    amount: float


def fetch_klines(
    secid: str,
    interval: str,
    limit: int = 500,
    timeout: float = 3,
    *,
    opener: OpenerDirector | None = None,
) -> list[Candle]:
    """Fetch unadjusted index K-lines. Raises a readable error on missing data."""
    period = KLINE_PERIODS.get(interval)
    if period is None:
        raise ValueError(f"Unsupported K-line interval: {interval}")
    query = {
        "secid": secid,
        "klt": str(period),
        "fqt": "0",
        "lmt": str(max(1, limit)),
        "end": "20500101",
        "iscca": "1",
        "ut": EASTMONEY_UT,
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    request = Request(
        f"{EASTMONEY_KLINE_URL}?{urlencode(query)}",
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
    )
    direct_opener = opener or build_urllib_opener(provider_policy("eastmoney_push2his"))
    with direct_opener.open(request, timeout=timeout) as response:
        payload = json.load(response)
    data = payload.get("data") if isinstance(payload, dict) else None
    raw_rows = data.get("klines") if isinstance(data, dict) else None
    if not isinstance(raw_rows, list) or not raw_rows:
        raise RuntimeError(f"Eastmoney returned no {interval} K-lines for {secid}")
    rows = [_parse_row(str(raw)) for raw in raw_rows]
    return [row for row in rows if row.close > 0 and row.high > 0 and row.low > 0]


def resample_minutes(candles: list[Candle], minutes: int) -> list[Candle]:
    """Aggregate one-minute candles into clock-aligned N-minute candles."""
    if minutes <= 1:
        return list(candles)
    buckets: dict[datetime, list[Candle]] = {}
    for candle in candles:
        minute = (candle.time.minute // minutes) * minutes
        key = candle.time.replace(minute=minute, second=0, microsecond=0)
        buckets.setdefault(key, []).append(candle)
    result: list[Candle] = []
    for key in sorted(buckets):
        group = buckets[key]
        result.append(
            Candle(
                time=key,
                open=group[0].open,
                close=group[-1].close,
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                volume=sum(item.volume for item in group),
                amount=sum(item.amount for item in group),
            )
        )
    return result


def _parse_row(raw: str) -> Candle:
    values = raw.split(",")
    if len(values) < 7:
        raise ValueError(f"Invalid Eastmoney K-line row: {raw[:80]}")
    timestamp = values[0]
    time_format = "%Y-%m-%d %H:%M" if " " in timestamp else "%Y-%m-%d"
    return Candle(
        time=datetime.strptime(timestamp, time_format),
        open=float(values[1]),
        close=float(values[2]),
        high=float(values[3]),
        low=float(values[4]),
        volume=float(values[5]),
        amount=float(values[6]),
    )
