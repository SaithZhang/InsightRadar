"""Provider adapters that feed the local intraday archive."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import time as time_module
from typing import Callable, Iterable

from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.data_sources.eastmoney_klines import fetch_klines
from stock_assist.intraday.contracts import MinuteBar, PointQuote
from stock_assist.intraday.network import (
    build_urllib_opener,
    provider_policy,
    sanitized_error_type,
)


AMAZINGDATA_SOURCE = "Galaxy AmazingData"


@dataclass
class EndpointCircuitBreaker:
    failure_threshold: int = 3
    state: str = "closed"
    consecutive_failures: int = 0
    last_error_type: str | None = None

    def allow_request(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.last_error_type = None

    def record_failure(self, exc: BaseException) -> None:
        signature = sanitized_error_type(exc)
        self.consecutive_failures = (
            self.consecutive_failures + 1
            if signature == self.last_error_type
            else 1
        )
        self.last_error_type = signature
        if self.consecutive_failures >= self.failure_threshold:
            self.state = "open"


def fetch_amazingdata_minute_bars(
    client: AmazingDataClient,
    symbols: Iterable[str],
    *,
    start: date,
    end: date,
    fetched_at: datetime | None = None,
    timeout_seconds: float | None = None,
) -> list[MinuteBar]:
    """Fetch one-minute K-lines with one already-authenticated client."""

    codes = [str(item).upper() for item in symbols]
    if not codes:
        return []
    period = client.ad.constant.Period.min1.value
    query_kwargs: dict[str, object] = {}
    if timeout_seconds is not None:
        query_kwargs["timeout"] = max(0.1, timeout_seconds)
    raw = client._call_sdk(
        client.market_data.query_kline,
        code_list=codes,
        begin_date=int(start.strftime("%Y%m%d")),
        end_date=int(end.strftime("%Y%m%d")),
        period=period,
        **query_kwargs,
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
    timeout_seconds: float | None = None,
) -> list[PointQuote]:
    """Return the last positive auction quote visible no later than 09:26."""

    codes = [str(item).upper() for item in symbols]
    if not codes:
        return []
    stamp = int(trade_date.strftime("%Y%m%d"))
    raw = client.query_snapshot(
        codes,
        begin_date=stamp,
        end_date=stamp,
        timeout=timeout_seconds,
    )
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
    timeout_seconds: float | None = None,
) -> list[PointQuote]:
    """Return each symbol's latest positive quote visible at ``as_of``."""

    codes = [str(item).upper() for item in symbols]
    if not codes:
        return []
    stamp = int(as_of.strftime("%Y%m%d"))
    raw = client.query_snapshot(
        codes,
        begin_date=stamp,
        end_date=stamp,
        timeout=timeout_seconds,
    )
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
    candle_fetcher: Callable[..., object] = fetch_klines,
    circuit_breaker: EndpointCircuitBreaker | None = None,
    include_diagnostics: bool = False,
    total_timeout_seconds: float = 20.0,
    monotonic_fn: Callable[[], float] = time_module.monotonic,
) -> tuple[list[MinuteBar], dict[str, str]] | tuple[list[MinuteBar], dict[str, str], dict[str, object]]:
    """Public fallback for symbols missing from the primary archive.

    Each symbol fails independently.  The caller receives both usable bars and
    a per-symbol error map so one provider failure cannot blank the full page.
    """

    captured_at = fetched_at or datetime.now()
    bars: list[MinuteBar] = []
    failures: dict[str, str] = {}
    policy = provider_policy("eastmoney_push2his")
    opener = build_urllib_opener(policy)
    breaker = circuit_breaker or EndpointCircuitBreaker(
        failure_threshold=policy.circuit_breaker_policy.failure_threshold
    )
    started = monotonic_fn()
    attempts = 0
    symbol_rows = [str(item).upper() for item in symbols]
    timed_out = False
    for index, symbol in enumerate(symbol_rows):
        if monotonic_fn() - started >= total_timeout_seconds:
            timed_out = True
            failures.update(
                {item: "refresh_total_timeout" for item in symbol_rows[index:]}
            )
            break
        if not breaker.allow_request():
            failures.update(
                {
                    item: "provider_unavailable_due_to_circuit_breaker"
                    for item in symbol_rows[index:]
                }
            )
            break
        attempts += 1
        try:
            candles = candle_fetcher(
                _eastmoney_secid(symbol),
                "1m",
                limit=3000,
                timeout=policy.timeout_seconds,
                opener=opener,
            )
        except Exception as exc:
            breaker.record_failure(exc)
            failures[symbol] = sanitized_error_type(exc)
            continue
        breaker.record_success()
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
    diagnostics: dict[str, object] = {
        **policy.safe_diagnostic(),
        "provider": "eastmoney_push2his",
        "elapsed_ms": max(0, int((monotonic_fn() - started) * 1000)),
        "status": "partial" if failures else "success",
        "sanitized_error_type": breaker.last_error_type,
        "attempt_count": attempts,
        "circuit_state": breaker.state,
        "timed_out": timed_out,
    }
    if include_diagnostics:
        return bars, failures, diagnostics
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
