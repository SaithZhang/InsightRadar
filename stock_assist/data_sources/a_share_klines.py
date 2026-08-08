"""Resilient public K-line routing for A-share indexes."""

from __future__ import annotations

import json
from datetime import date, datetime
from urllib.parse import urlencode
from urllib.request import Request
from zoneinfo import ZoneInfo

import pandas as pd

from stock_assist.data_sources.contracts import ProviderResult
from stock_assist.data_sources.eastmoney_klines import Candle
from stock_assist.data_sources.eastmoney_klines import (
    fetch_klines as fetch_eastmoney_klines,
)
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
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


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


def fetch_tencent_daily_result(
    code: str,
    *,
    expected_trade_date: date,
    limit: int = 260,
    fetched_at: datetime | None = None,
) -> ProviderResult[pd.DataFrame]:
    """Fetch one whole forward-adjusted daily series as a typed repair fallback."""

    fetched = fetched_at or datetime.now(tz=SHANGHAI_TZ)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=SHANGHAI_TZ)
    try:
        tencent_code = _tencent_security_code(code)
        rows = fetch_tencent_klines(tencent_code, "day", limit)
    except Exception as exc:
        return ProviderResult(
            provider="tencent",
            schema_version="daily-ohlcv/v1",
            source_time=None,
            fetched_at=fetched,
            trade_date=None,
            status="invalid",
            gaps=(),
            errors=(f"{code}:tencent_daily:{sanitized_error_type(exc)}",),
            price_basis="forward_adjusted",
            data=pd.DataFrame(),
        )

    future_count = sum(row.time.date() > expected_trade_date for row in rows)
    completed = [row for row in rows if row.time.date() <= expected_trade_date]
    if not completed:
        return ProviderResult(
            provider="tencent",
            schema_version="daily-ohlcv/v1",
            source_time=None,
            fetched_at=fetched,
            trade_date=None,
            status="empty",
            gaps=(f"{code}:missing_series",),
            errors=(),
            price_basis="forward_adjusted",
            data=pd.DataFrame(),
        )

    frame = pd.DataFrame(
        {
            "code": [code] * len(completed),
            "trade_date": pd.to_datetime([row.time.date() for row in completed]),
            "open": [row.open for row in completed],
            "high": [row.high for row in completed],
            "low": [row.low for row in completed],
            "close": [row.close for row in completed],
            "volume": [row.volume for row in completed],
            "amount": [row.amount for row in completed],
        }
    ).sort_values("trade_date", kind="stable")
    frame = frame.drop_duplicates(subset=["trade_date"], keep="last").reset_index(drop=True)
    trade_date = frame["trade_date"].iloc[-1].date()
    gaps: list[str] = []
    if future_count:
        gaps.append(f"{code}:future_rows_dropped:{future_count}")
    if trade_date < expected_trade_date:
        gaps.append(f"{code}:stale_trade_date:{trade_date.isoformat()}<{expected_trade_date.isoformat()}")
    closes = pd.to_numeric(frame["close"], errors="coerce")
    largest_gap = float(closes.pct_change().abs().dropna().max()) if len(closes) > 1 else 0.0
    if largest_gap > 0.35:
        gaps.append(f"{code}:price_discontinuity:{largest_gap:.6f}")
        status = "quarantined"
    elif gaps:
        status = "partial"
    else:
        status = "ok"
    return ProviderResult(
        provider="tencent",
        schema_version="daily-ohlcv/v1",
        source_time=None,
        fetched_at=fetched,
        trade_date=trade_date,
        status=status,
        gaps=tuple(gaps),
        errors=(),
        price_basis="forward_adjusted",
        data=frame,
    )


def _tencent_security_code(code: str) -> str:
    symbol, separator, market = code.upper().partition(".")
    if not separator or not symbol.isdigit() or market not in {"SH", "SZ"}:
        raise ValueError("unsupported_a_share_code")
    return ("sh" if market == "SH" else "sz") + symbol


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
