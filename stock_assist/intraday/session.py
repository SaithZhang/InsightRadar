"""A-share trading-session resolution backed by the provider calendar."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable, Iterable

from stock_assist.intraday.archive import MinuteArchive


@dataclass(frozen=True)
class TradingSessionResolution:
    calendar_date: date
    current_exchange_trade_date: date | None
    latest_completed_trade_date: date | None
    runtime_trade_date: date | None
    display_trade_date: date | None
    session_mode: str
    view_mode: str
    analysis_authority: str
    decision_authority: str
    trade_authority: str
    realtime_decision_available: bool
    resolution_source: str
    data_gaps: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        for field in (
            "calendar_date",
            "current_exchange_trade_date",
            "latest_completed_trade_date",
            "runtime_trade_date",
            "display_trade_date",
        ):
            value = payload[field]
            payload[field] = value.isoformat() if isinstance(value, date) else None
        payload["data_gaps"] = list(self.data_gaps)
        return payload


def resolve_trading_session(
    now: datetime,
    *,
    client: object | None,
    archive: MinuteArchive,
    trade_date_probe: Callable[[date], date | None] | None = None,
) -> TradingSessionResolution:
    """Resolve calendar/runtime dates without using weekday guesses."""

    today = now.date()
    calendar_dates: tuple[date, ...] = ()
    gaps: list[str] = []
    if client is not None:
        try:
            calendar_dates = _calendar_dates(getattr(client, "calendar"))
        except Exception as exc:
            gaps.append(f"AmazingData calendar unavailable: {type(exc).__name__}")
    source = "Galaxy AmazingData calendar"
    if not calendar_dates:
        calendar_dates = tuple(day for day in archive.available_dates() if day <= today)
        source = "local immutable minute archive"
        if calendar_dates:
            gaps.append("交易日历不可用；当前仅能依据本地真实行情日期解析。")
    if not calendar_dates:
        probe = trade_date_probe or (
            lambda target: _probe_latest_trade_date(target, client=client)
        )
        try:
            probed = probe(today)
        except Exception as exc:
            probed = None
            gaps.append(f"真实行情日期探测失败：{type(exc).__name__}")
        if probed is not None and probed <= today:
            calendar_dates = (probed,)
            source = "bounded completed A-share K-line date probe"
            gaps.append("交易日历与本地档案不可用；当前日期来自有界真实K线探测。")
    eligible = tuple(day for day in calendar_dates if day <= today)
    is_exchange_day = today in calendar_dates
    current_trade_date = today if is_exchange_day else None
    if is_exchange_day and now.time() >= time(15, 0):
        latest_completed = today
    else:
        prior = [day for day in eligible if day < today]
        latest_completed = prior[-1] if prior else None
    if is_exchange_day:
        runtime_trade_date = today
        session_mode = (
            "preopen"
            if now.time() < time(9, 15)
            else "live"
            if now.time() < time(15, 0)
            else "after_close"
        )
        view_mode = "current_session"
        analysis_authority = "live_shadow"
        decision_authority = "shadow_only"
        realtime_decision_available = True
    else:
        runtime_trade_date = latest_completed
        session_mode = "non_trading_day"
        view_mode = "historical_review"
        analysis_authority = "historical_shadow"
        decision_authority = "historical_shadow_only"
        realtime_decision_available = False
    if runtime_trade_date is None:
        gaps.append("无法从交易日历或本地真实行情解析 runtime_trade_date。")
    return TradingSessionResolution(
        calendar_date=today,
        current_exchange_trade_date=current_trade_date,
        latest_completed_trade_date=latest_completed,
        runtime_trade_date=runtime_trade_date,
        display_trade_date=runtime_trade_date,
        session_mode=session_mode,
        view_mode=view_mode,
        analysis_authority=analysis_authority,
        decision_authority=decision_authority,
        trade_authority="none",
        realtime_decision_available=realtime_decision_available,
        resolution_source=source,
        data_gaps=tuple(gaps),
    )


def _calendar_dates(values: Iterable[object]) -> tuple[date, ...]:
    result: set[date] = set()
    for value in values:
        text = str(value).strip().replace("-", "")
        if len(text) != 8 or not text.isdigit():
            continue
        try:
            result.add(datetime.strptime(text, "%Y%m%d").date())
        except ValueError:
            continue
    return tuple(sorted(result))


def _probe_latest_trade_date(today: date, *, client: object | None) -> date | None:
    """Probe a real benchmark K-line date; never infer from weekdays."""

    if client is not None:
        try:
            query = getattr(client, "query_daily_kline")
            raw = query(
                ["000300.SH"],
                int((today - timedelta(days=14)).strftime("%Y%m%d")),
                int(today.strftime("%Y%m%d")),
            )
            frame = raw.get("000300.SH") if isinstance(raw, dict) else None
            values = (
                frame.get("kline_time", ())
                if frame is not None and hasattr(frame, "get") else ()
            )
            dates = _calendar_dates(values)
            if dates:
                return dates[-1]
        except Exception:
            pass
    from stock_assist.data_sources.eastmoney_klines import fetch_klines

    candles = fetch_klines("1.000300", "1d", limit=10, timeout=3)
    eligible = [item.time.date() for item in candles if item.time.date() <= today]
    return max(eligible, default=None)
