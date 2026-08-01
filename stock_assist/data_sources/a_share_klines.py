"""Resilient public K-line routing for A-share indexes."""

from __future__ import annotations

from datetime import datetime
import json
from urllib.parse import urlencode
from urllib.request import Request

from stock_assist.data_sources.eastmoney_klines import Candle, fetch_klines as fetch_eastmoney_klines
from stock_assist.intraday.network import (
    build_urllib_opener,
    provider_policy,
    sanitized_error_type,
)


TENCENT_BASE = "https://ifzq.gtimg.cn/appstock/app"
TENCENT_PERIODS = {
    "1m": "m1",
    "5m": "m5",
    "15m": "m15",
    "30m": "m30",
    "60m": "m60",
    "day": "day",
    "week": "week",
    "month": "month",
}


def fetch_public_klines(
    *,
    secid: str,
    tencent_code: str,
    interval: str,
    limit: int = 500,
) -> tuple[list[Candle], str]:
    """Use Tencent public K-lines first and Eastmoney as a transparent fallback."""
    errors: list[str] = []
    try:
        return fetch_tencent_klines(tencent_code, interval, limit), "Tencent public K-line"
    except Exception as exc:
        errors.append(f"Tencent: {sanitized_error_type(exc)}")
    try:
        return fetch_eastmoney_klines(secid, interval, limit), "Eastmoney public K-line fallback"
    except Exception as exc:
        errors.append(f"Eastmoney: {sanitized_error_type(exc)}")
    raise RuntimeError("; ".join(errors))


def fetch_tencent_klines(code: str, interval: str, limit: int = 500, timeout: int = 15) -> list[Candle]:
    period = TENCENT_PERIODS.get(interval)
    if period is None:
        raise ValueError(f"Unsupported Tencent K-line interval: {interval}")
    count = max(20, min(int(limit), 1000))
    if interval in {"1m", "5m", "15m", "30m", "60m"}:
        endpoint = f"{TENCENT_BASE}/kline/mkline"
        query = {"param": f"{code},{period},,{count}"}
    else:
        endpoint = f"{TENCENT_BASE}/fqkline/get"
        query = {"param": f"{code},{period},,,{count},qfq"}
    request = Request(
        f"{endpoint}?{urlencode(query)}",
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
    )
    opener = build_urllib_opener(provider_policy("tencent"))
    with opener.open(request, timeout=timeout) as response:
        payload = json.load(response)
    block = (payload.get("data") or {}).get(code) if isinstance(payload, dict) else None
    raw_rows = None
    if isinstance(block, dict):
        raw_rows = block.get(period) or block.get(f"qfq{period}") or block.get(f"hfq{period}")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise RuntimeError(f"Tencent returned no {interval} K-lines for {code}")
    rows = [_parse_tencent_row(row) for row in raw_rows if isinstance(row, list)]
    return [row for row in rows if row.close > 0 and row.high > 0 and row.low > 0]


def _parse_tencent_row(values: list[object]) -> Candle:
    if len(values) < 6:
        raise ValueError(f"Invalid Tencent K-line row: {values!r}")
    timestamp = str(values[0])
    if "-" in timestamp:
        time_format = "%Y-%m-%d"
    elif len(timestamp) == 8:
        time_format = "%Y%m%d"
    else:
        time_format = "%Y%m%d%H%M"
    close = float(values[2])
    volume = float(values[5])
    return Candle(
        time=datetime.strptime(timestamp, time_format),
        open=float(values[1]),
        close=close,
        high=float(values[3]),
        low=float(values[4]),
        volume=volume,
        amount=close * volume,
    )
