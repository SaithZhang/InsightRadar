"""Provider adapters that feed the local intraday archive."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Iterable

from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.data_sources.eastmoney_klines import fetch_klines
from stock_assist.intraday.contracts import MinuteBar, PointQuote


AMAZINGDATA_SOURCE = "Galaxy AmazingData"


def fetch_amazingdata_minute_bars(
    client: AmazingDataClient,
    symbols: Iterable[str],
    *,
    start: date,
    end: date,
    fetched_at: datetime | None = None,
) -> list[MinuteBar]:
    """Fetch one-minute K-lines with one already-authenticated client."""

    codes = [str(item).upper() for item in symbols]
    if not codes:
        return []
    period = client.ad.constant.Period.min1.value
    raw = client._call_sdk(
        client.market_data.query_kline,
        code_list=codes,
        begin_date=int(start.strftime("%Y%m%d")),
        end_date=int(end.strftime("%Y%m%d")),
        period=period,
    )
    captured_at = fetched_at or datetime.now()
    result: list[MinuteBar] = []
    for code in codes:
        frame = raw.get(code) if isinstance(raw, dict) else None
        if frame is None or getattr(frame, "empty", True):
            continue
        for _, row in frame.iterrows():
            timestamp = _datetime(row.get("kline_time"))
            if timestamp is None:
                continue
            values = [_float(row.get(key)) for key in ("open", "high", "low", "close")]
            if any(value is None or value <= 0 for value in values):
                continue
            result.append(
                MinuteBar(
                    symbol=code,
                    timestamp=timestamp,
                    open=float(values[0]),
                    high=float(values[1]),
                    low=float(values[2]),
                    close=float(values[3]),
                    volume=_float(row.get("volume")) or 0.0,
                    amount=_float(row.get("amount")) or 0.0,
                    source_time=timestamp,
                    fetched_at=captured_at,
                    source=f"{AMAZINGDATA_SOURCE} query_kline/min1",
                )
            )
    return result


def fetch_amazingdata_auction_quotes(
    client: AmazingDataClient,
    symbols: Iterable[str],
    *,
    trade_date: date,
    fetched_at: datetime | None = None,
) -> list[PointQuote]:
    """Return the last positive auction quote visible no later than 09:26."""

    codes = [str(item).upper() for item in symbols]
    if not codes:
        return []
    stamp = int(trade_date.strftime("%Y%m%d"))
    raw = client.query_snapshot(codes, begin_date=stamp, end_date=stamp)
    frames = raw.get(stamp, raw) if isinstance(raw, dict) else {}
    captured_at = fetched_at or datetime.now()
    result: list[PointQuote] = []
    cutoff = datetime.combine(trade_date, time(9, 26, 0))
    for code in codes:
        frame = frames.get(code) if isinstance(frames, dict) else None
        if frame is None or getattr(frame, "empty", True):
            continue
        candidates: list[tuple[datetime, object]] = []
        for _, row in frame.iterrows():
            timestamp = _datetime(row.get("trade_time"))
            price = _float(row.get("last"))
            if timestamp is not None and timestamp <= cutoff and price is not None and price > 0:
                candidates.append((timestamp, row))
        if not candidates:
            continue
        timestamp, row = max(candidates, key=lambda item: item[0])
        result.append(
            PointQuote(
                symbol=code,
                timestamp=timestamp,
                price=float(row.get("last")),
                pre_close=_float(row.get("pre_close")),
                open=_float(row.get("open")),
                high=_float(row.get("high")),
                low=_float(row.get("low")),
                volume=_float(row.get("volume")),
                amount=_float(row.get("amount")),
                source_time=timestamp,
                fetched_at=captured_at,
                source=f"{AMAZINGDATA_SOURCE} query_snapshot",
                phase=str(row.get("trading_phase_code") or ""),
            )
        )
    return result


def fetch_amazingdata_latest_quotes(
    client: AmazingDataClient,
    symbols: Iterable[str],
    *,
    as_of: datetime,
    fetched_at: datetime | None = None,
) -> list[PointQuote]:
    """Return each symbol's latest positive quote visible at ``as_of``."""

    codes = [str(item).upper() for item in symbols]
    if not codes:
        return []
    stamp = int(as_of.strftime("%Y%m%d"))
    raw = client.query_snapshot(codes, begin_date=stamp, end_date=stamp)
    frames = raw.get(stamp, raw) if isinstance(raw, dict) else {}
    captured_at = fetched_at or datetime.now()
    result: list[PointQuote] = []
    for code in codes:
        frame = frames.get(code) if isinstance(frames, dict) else None
        if frame is None or getattr(frame, "empty", True):
            continue
        candidates: list[tuple[datetime, object]] = []
        for _, row in frame.iterrows():
            timestamp = _datetime(row.get("trade_time"))
            price = _float(row.get("last"))
            if timestamp is not None and timestamp <= as_of and price is not None and price > 0:
                candidates.append((timestamp, row))
        if not candidates:
            continue
        timestamp, row = max(candidates, key=lambda item: item[0])
        result.append(
            PointQuote(
                symbol=code,
                timestamp=timestamp,
                price=float(row.get("last")),
                pre_close=_float(row.get("pre_close")),
                open=_float(row.get("open")),
                high=_float(row.get("high")),
                low=_float(row.get("low")),
                volume=_float(row.get("volume")),
                amount=_float(row.get("amount")),
                source_time=timestamp,
                fetched_at=captured_at,
                source=f"{AMAZINGDATA_SOURCE} query_snapshot",
                phase=str(row.get("trading_phase_code") or ""),
            )
        )
    return result


def fetch_eastmoney_minute_bars(
    symbols: Iterable[str],
    *,
    start: date,
    end: date,
    fetched_at: datetime | None = None,
) -> tuple[list[MinuteBar], dict[str, str]]:
    """Public fallback for symbols missing from the primary archive.

    Each symbol fails independently.  The caller receives both usable bars and
    a per-symbol error map so one provider failure cannot blank the full page.
    """

    captured_at = fetched_at or datetime.now()
    bars: list[MinuteBar] = []
    failures: dict[str, str] = {}
    for raw_symbol in symbols:
        symbol = str(raw_symbol).upper()
        try:
            candles = fetch_klines(_eastmoney_secid(symbol), "1m", limit=3000)
        except Exception as exc:
            failures[symbol] = f"{type(exc).__name__}: {exc}"
            continue
        for candle in candles:
            if not start <= candle.time.date() <= end:
                continue
            bars.append(
                MinuteBar(
                    symbol=symbol,
                    timestamp=candle.time,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    amount=candle.amount,
                    source_time=candle.time,
                    fetched_at=captured_at,
                    source="Eastmoney public kline/1m fallback",
                )
            )
        if not any(item.symbol == symbol for item in bars):
            failures[symbol] = "Eastmoney returned no bars inside the requested date window."
    return bars, failures


def _eastmoney_secid(symbol: str) -> str:
    code, _, suffix = symbol.partition(".")
    if suffix == "SH":
        return f"1.{code}"
    if suffix == "SZ":
        return f"0.{code}"
    raise ValueError(f"unsupported A-share symbol for Eastmoney: {symbol}")


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
