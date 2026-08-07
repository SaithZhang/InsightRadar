"""Provider adapters for the read-only intraday evidence layer.

This is the only module allowed to know Eastmoney ``f51...`` positions or the
Tencent whitespace row format.  Adapters return ``ProviderResult`` containing
one provider-owned normalized tape; callers never merge rows across sources.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from stock_assist.data_sources.contracts import ProviderResult, ProviderStatus
from stock_assist.intraday.evidence_contracts import (
    InstrumentRef,
    IntradayTape,
    TapeMinute,
)
from stock_assist.intraday.network import (
    build_requests_session,
    provider_policy,
    sanitized_error_type,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
EASTMONEY_TRENDS_HOSTS = (
    "https://push2delay.eastmoney.com/api/qt/stock/trends2/get",
    "https://push2.eastmoney.com/api/qt/stock/trends2/get",
    "https://push2his.eastmoney.com/api/qt/stock/trends2/get",
)
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
TENCENT_DAY_URL = "https://web.ifzq.gtimg.cn/appstock/app/day/query"


@dataclass(frozen=True)
class IntradayFetch:
    instrument: InstrumentRef
    trade_date: date


class IntradayProvider(Protocol):
    provider_id: str

    def fetch(self, request: IntradayFetch) -> ProviderResult[IntradayTape]: ...

    def fetch_recent(
        self,
        instrument: InstrumentRef,
        *,
        through_date: date,
    ) -> ProviderResult[tuple[IntradayTape, ...]]: ...


class EastmoneyIntradayProvider:
    provider_id = "eastmoney"

    def __init__(
        self,
        *,
        session: object | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = provider_policy("eastmoney_push2")
        self._session: Any = session or build_requests_session(self._policy)
        self._now_fn = now_fn or (lambda: datetime.now(SHANGHAI))

    def fetch(self, request: IntradayFetch) -> ProviderResult[IntradayTape]:
        recent = self.fetch_recent(request.instrument, through_date=request.trade_date)
        tapes = recent.data if recent.status in {"ok", "partial"} else ()
        tape = next((item for item in tapes if item.trade_date == request.trade_date), None)
        if tape is None:
            status: ProviderStatus = (
                "invalid" if recent.status in {"invalid", "quarantined"} else "empty"
            )
            return ProviderResult(
                provider=recent.provider,
                schema_version="intraday-tape/v1",
                source_time=recent.source_time,
                fetched_at=recent.fetched_at,
                trade_date=request.trade_date,
                status=status,
                gaps=recent.gaps + ("requested_trade_date_unavailable",),
                errors=recent.errors,
                price_basis="unadjusted",
                data=_empty_tape(request.instrument, request.trade_date),
            )
        return ProviderResult(
            provider=recent.provider,
            schema_version="intraday-tape/v1",
            source_time=tape.minutes[-1].timestamp,
            fetched_at=recent.fetched_at,
            trade_date=tape.trade_date,
            status=recent.status,
            gaps=recent.gaps,
            errors=recent.errors,
            price_basis="unadjusted",
            data=tape,
        )

    def fetch_recent(
        self,
        instrument: InstrumentRef,
        *,
        through_date: date,
    ) -> ProviderResult[tuple[IntradayTape, ...]]:
        fetched_at = _aware(self._now_fn())
        params = {
            "secid": instrument.eastmoney_secid,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "ndays": "5",
            "iscr": "0",
            "iscca": "0",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 InsightRadar/0.1",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://quote.eastmoney.com/",
        }
        errors: list[str] = []
        for endpoint in EASTMONEY_TRENDS_HOSTS:
            try:
                response = self._session.get(  # type: ignore[attr-defined]
                    endpoint,
                    params=params,
                    headers=headers,
                    timeout=self._policy.timeout_seconds,
                )
                if int(getattr(response, "status_code", 200)) == 429:
                    errors.append("rate_limited")
                    continue
                response.raise_for_status()
                payload = _response_json(response)
                parsed = parse_eastmoney_trends(
                    payload,
                    instrument=instrument,
                    fetched_at=fetched_at,
                    through_date=through_date,
                )
                if parsed.data:
                    return parsed
                errors.extend(parsed.errors or ("empty_response",))
            except Exception as exc:  # noqa: BLE001 - fail closed at provider boundary
                errors.append(sanitized_error_type(exc))
        return ProviderResult(
            provider=self.provider_id,
            schema_version="intraday-tapes/v1",
            source_time=None,
            fetched_at=fetched_at,
            trade_date=through_date,
            status="invalid" if errors else "empty",
            gaps=("eastmoney_trends_unavailable",),
            errors=tuple(dict.fromkeys(errors)),
            price_basis="unadjusted",
            data=(),
        )


class TencentIntradayProvider:
    provider_id = "tencent"

    def __init__(
        self,
        *,
        session: object | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = provider_policy("tencent")
        self._session: Any = session or build_requests_session(self._policy)
        self._now_fn = now_fn or (lambda: datetime.now(SHANGHAI))

    def fetch(self, request: IntradayFetch) -> ProviderResult[IntradayTape]:
        fetched_at = _aware(self._now_fn())
        headers = {
            "User-Agent": "Mozilla/5.0 InsightRadar/0.1",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://gu.qq.com/",
        }
        try:
            response = self._session.get(  # type: ignore[attr-defined]
                TENCENT_MINUTE_URL,
                params={"code": request.instrument.tencent_symbol},
                headers=headers,
                timeout=self._policy.timeout_seconds,
            )
            if int(getattr(response, "status_code", 200)) == 429:
                raise RuntimeError("rate_limited")
            response.raise_for_status()
            return parse_tencent_minute(
                _response_json(response),
                instrument=request.instrument,
                requested_date=request.trade_date,
                fetched_at=fetched_at,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed at provider boundary
            return ProviderResult(
                provider=self.provider_id,
                schema_version="intraday-tape/v1",
                source_time=None,
                fetched_at=fetched_at,
                trade_date=request.trade_date,
                status="invalid",
                gaps=("tencent_minute_unavailable",),
                errors=(sanitized_error_type(exc),),
                price_basis="unadjusted",
                data=_empty_tape(request.instrument, request.trade_date),
            )

    def fetch_recent(
        self,
        instrument: InstrumentRef,
        *,
        through_date: date,
    ) -> ProviderResult[tuple[IntradayTape, ...]]:
        fetched_at = _aware(self._now_fn())
        headers = {
            "User-Agent": "Mozilla/5.0 InsightRadar/0.1",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://gu.qq.com/",
        }
        try:
            response = self._session.get(  # type: ignore[attr-defined]
                TENCENT_DAY_URL,
                params={"code": instrument.tencent_symbol},
                headers=headers,
                timeout=self._policy.timeout_seconds,
            )
            if int(getattr(response, "status_code", 200)) == 429:
                raise RuntimeError("rate_limited")
            response.raise_for_status()
            return parse_tencent_days(
                _response_json(response),
                instrument=instrument,
                fetched_at=fetched_at,
                through_date=through_date,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed at provider boundary
            return ProviderResult(
                provider=self.provider_id,
                schema_version="intraday-tapes/v1",
                source_time=None,
                fetched_at=fetched_at,
                trade_date=through_date,
                status="invalid",
                gaps=("tencent_day_unavailable",),
                errors=(sanitized_error_type(exc),),
                price_basis="unadjusted",
                data=(),
            )


def parse_eastmoney_trends(
    payload: object,
    *,
    instrument: InstrumentRef,
    fetched_at: datetime,
    through_date: date,
) -> ProviderResult[tuple[IntradayTape, ...]]:
    """Normalize Eastmoney trends2 rows; raw f-field positions end here."""

    fetched_at = _aware(fetched_at)
    root: dict[str, object] = payload if isinstance(payload, dict) else {}
    raw_data = root.get("data")
    data: dict[str, object] = raw_data if isinstance(raw_data, dict) else {}
    rows = data.get("trends")
    name = _text(data.get("name"))
    pre_close = _number(data.get("preClose"))
    if not isinstance(rows, list):
        return ProviderResult(
            provider="eastmoney",
            schema_version="intraday-tapes/v1",
            source_time=None,
            fetched_at=fetched_at,
            trade_date=through_date,
            status="empty",
            gaps=("missing_trends_rows",),
            errors=(),
            price_basis="unadjusted",
            data=(),
        )
    grouped: dict[date, list[TapeMinute]] = {}
    gaps: list[str] = []
    seen: dict[datetime, TapeMinute] = {}
    missing_amount_by_day: dict[date, int] = {}
    latest_payload_date: date | None = None
    invalid_rows = 0
    for raw in rows:
        parts = str(raw).split(",")
        stamp = _parse_stamp(parts[0]) if parts else None
        if stamp is not None and (
            latest_payload_date is None or stamp.date() > latest_payload_date
        ):
            latest_payload_date = stamp.date()
        if stamp is not None and stamp.date() > through_date:
            continue
        if stamp is not None and (
            len(parts) <= 6 or _nonnegative(parts[6]) is None
        ):
            day = stamp.date()
            missing_amount_by_day[day] = missing_amount_by_day.get(day, 0) + 1
        if len(parts) < 8:
            invalid_rows += 1
            continue
        price = _number(parts[2])
        if stamp is None or price is None or price <= 0:
            invalid_rows += 1
            continue
        minute = TapeMinute(
            timestamp=stamp,
            price=price,
            avg_price=_positive(parts[7]),
            high=_positive(parts[3]),
            low=_positive(parts[4]),
            volume=_nonnegative(parts[5]),
            amount=_nonnegative(parts[6]),
        )
        previous = seen.get(stamp)
        if previous is not None and previous != minute:
            return ProviderResult(
                provider="eastmoney",
                schema_version="intraday-tapes/v1",
                source_time=stamp,
                fetched_at=fetched_at,
                trade_date=stamp.date(),
                status="quarantined",
                gaps=("conflicting_duplicate_minute",),
                errors=(),
                price_basis="unadjusted",
                data=(),
            )
        seen[stamp] = minute
    for minute in sorted(seen.values(), key=lambda item: item.timestamp):
        grouped.setdefault(minute.timestamp.date(), []).append(minute)
    if invalid_rows:
        gaps.append(f"invalid_rows:{invalid_rows}")
    gaps.extend(
        f"missing_minute_amount:{day.isoformat()}:{count}"
        for day, count in sorted(missing_amount_by_day.items())
    )
    tapes = tuple(
        IntradayTape(
            instrument=instrument,
            name=name or instrument.display_name,
            trade_date=day,
            pre_close=(
                pre_close
                if latest_payload_date is not None
                and latest_payload_date <= through_date
                and day == latest_payload_date
                else None
            ),
            minutes=tuple(day_rows),
            amount_kind=(
                "incomplete" if missing_amount_by_day.get(day, 0) else "incremental"
            ),
            volume_unit="lot",
        )
        for day, day_rows in sorted(grouped.items())
        if day_rows
    )
    source_time = max((item.minutes[-1].timestamp for item in tapes), default=None)
    if source_time is not None and source_time > fetched_at:
        return ProviderResult(
            provider="eastmoney",
            schema_version="intraday-tapes/v1",
            source_time=source_time,
            fetched_at=fetched_at,
            trade_date=through_date,
            status="invalid",
            gaps=("source_time_after_fetched_at",),
            errors=(),
            price_basis="unadjusted",
            data=(),
        )
    return ProviderResult(
        provider="eastmoney",
        schema_version="intraday-tapes/v1",
        source_time=source_time,
        fetched_at=fetched_at,
        trade_date=max((item.trade_date for item in tapes), default=through_date),
        status="partial" if gaps else "ok" if tapes else "empty",
        gaps=tuple(gaps),
        errors=(),
        price_basis="unadjusted",
        data=tapes,
    )


def parse_tencent_minute(
    payload: object,
    *,
    instrument: InstrumentRef,
    requested_date: date,
    fetched_at: datetime,
) -> ProviderResult[IntradayTape]:
    fetched_at = _aware(fetched_at)
    node = _tencent_symbol_node(payload, instrument.tencent_symbol)
    raw_minute_data = node.get("data")
    minute_data: dict[str, object] = (
        raw_minute_data if isinstance(raw_minute_data, dict) else {}
    )
    raw_date = str(minute_data.get("date") or "")
    parsed_date = _compact_date(raw_date)
    if parsed_date != requested_date:
        return ProviderResult(
            provider="tencent",
            schema_version="intraday-tape/v1",
            source_time=None,
            fetched_at=fetched_at,
            trade_date=requested_date,
            status="empty",
            gaps=("requested_trade_date_unavailable",),
            errors=(),
            price_basis="unadjusted",
            data=_empty_tape(instrument, requested_date),
        )
    qt = node.get("qt") if isinstance(node.get("qt"), dict) else {}
    quote = qt.get(instrument.tencent_symbol) if isinstance(qt, dict) else None
    name = _text(quote[1]) if isinstance(quote, list) and len(quote) > 1 else None
    pre_close = _positive(quote[4]) if isinstance(quote, list) and len(quote) > 4 else None
    result = _parse_tencent_rows(
        minute_data.get("data"),
        instrument=instrument,
        trade_date=requested_date,
        name=name,
        pre_close=pre_close,
        fetched_at=fetched_at,
    )
    return result


def parse_tencent_days(
    payload: object,
    *,
    instrument: InstrumentRef,
    fetched_at: datetime,
    through_date: date,
) -> ProviderResult[tuple[IntradayTape, ...]]:
    fetched_at = _aware(fetched_at)
    node = _tencent_symbol_node(payload, instrument.tencent_symbol)
    raw_days = node.get("data")
    if not isinstance(raw_days, list):
        return ProviderResult(
            provider="tencent",
            schema_version="intraday-tapes/v1",
            source_time=None,
            fetched_at=fetched_at,
            trade_date=through_date,
            status="empty",
            gaps=("missing_day_rows",),
            errors=(),
            price_basis="unadjusted",
            data=(),
        )
    tapes: list[IntradayTape] = []
    gaps: list[str] = []
    for day_node in raw_days:
        if not isinstance(day_node, dict):
            gaps.append("invalid_day_node")
            continue
        day = _compact_date(str(day_node.get("date") or ""))
        if day is None or day > through_date:
            continue
        parsed = _parse_tencent_rows(
            day_node.get("data"),
            instrument=instrument,
            trade_date=day,
            name=instrument.display_name,
            pre_close=None,
            fetched_at=fetched_at,
        )
        if parsed.status in {"ok", "partial"} and parsed.data.minutes:
            tapes.append(parsed.data)
            gaps.extend(parsed.gaps)
        elif parsed.status in {"invalid", "quarantined"}:
            return ProviderResult(
                provider="tencent",
                schema_version="intraday-tapes/v1",
                source_time=parsed.source_time,
                fetched_at=fetched_at,
                trade_date=day,
                status=parsed.status,
                gaps=parsed.gaps,
                errors=parsed.errors,
                price_basis="unadjusted",
                data=(),
            )
    tapes.sort(key=lambda item: item.trade_date)
    return ProviderResult(
        provider="tencent",
        schema_version="intraday-tapes/v1",
        source_time=max((item.minutes[-1].timestamp for item in tapes), default=None),
        fetched_at=fetched_at,
        trade_date=tapes[-1].trade_date if tapes else through_date,
        status="partial" if gaps else "ok" if tapes else "empty",
        gaps=tuple(dict.fromkeys(gaps)),
        errors=(),
        price_basis="unadjusted",
        data=tuple(tapes),
    )


def _parse_tencent_rows(
    rows: object,
    *,
    instrument: InstrumentRef,
    trade_date: date,
    name: str | None,
    pre_close: float | None,
    fetched_at: datetime,
) -> ProviderResult[IntradayTape]:
    if not isinstance(rows, list):
        return ProviderResult(
            provider="tencent",
            schema_version="intraday-tape/v1",
            source_time=None,
            fetched_at=fetched_at,
            trade_date=trade_date,
            status="empty",
            gaps=("missing_minute_rows",),
            errors=(),
            price_basis="unadjusted",
            data=_empty_tape(instrument, trade_date),
        )
    parsed_raw: list[tuple[datetime, float, float, float]] = []
    invalid_rows = 0
    missing_amount_rows = 0
    previous_volume = 0.0
    previous_amount = 0.0
    previous_stamp: datetime | None = None
    seen_stamps: set[datetime] = set()
    reversals = 0
    future_minute_count = 0
    for raw in rows:
        parts = re.split(r"\s+", str(raw).strip())
        if not parts or not re.fullmatch(r"\d{4}", parts[0]):
            invalid_rows += 1
            continue
        stamp = _minute_stamp(trade_date, parts[0])
        if stamp is None:
            invalid_rows += 1
            continue
        if stamp > fetched_at:
            future_minute_count += 1
            continue
        if stamp in seen_stamps:
            return ProviderResult(
                provider="tencent",
                schema_version="intraday-tape/v1",
                source_time=stamp,
                fetched_at=fetched_at,
                trade_date=trade_date,
                status="quarantined",
                gaps=("duplicate_minute_timestamp",),
                errors=(),
                price_basis="unadjusted",
                data=_empty_tape(instrument, trade_date),
            )
        if previous_stamp is not None and stamp < previous_stamp:
            return ProviderResult(
                provider="tencent",
                schema_version="intraday-tape/v1",
                source_time=stamp,
                fetched_at=fetched_at,
                trade_date=trade_date,
                status="quarantined",
                gaps=("out_of_order_minute_timestamp",),
                errors=(),
                price_basis="unadjusted",
                data=_empty_tape(instrument, trade_date),
            )
        seen_stamps.add(stamp)
        previous_stamp = stamp
        if len(parts) < 4:
            missing_amount_rows += 1
            invalid_rows += 1
            continue
        price = _positive(parts[1])
        cumulative_volume = _nonnegative(parts[2])
        cumulative_amount = _nonnegative(parts[3])
        if cumulative_amount is None:
            missing_amount_rows += 1
        if price is None or cumulative_volume is None or cumulative_amount is None:
            invalid_rows += 1
            continue
        if cumulative_volume < previous_volume or cumulative_amount + 0.01 < previous_amount:
            reversals += 1
            continue
        parsed_raw.append((stamp, price, cumulative_volume, cumulative_amount))
        previous_volume = cumulative_volume
        previous_amount = cumulative_amount
    if reversals:
        return ProviderResult(
            provider="tencent",
            schema_version="intraday-tape/v1",
            source_time=parsed_raw[-1][0] if parsed_raw else None,
            fetched_at=fetched_at,
            trade_date=trade_date,
            status="quarantined",
            gaps=(f"cumulative_counter_reversal:{reversals}",),
            errors=(),
            price_basis="unadjusted",
            data=_empty_tape(instrument, trade_date),
        )
    volume_multiplier, volume_unit = _infer_volume_multiplier(parsed_raw)
    minutes: list[TapeMinute] = []
    previous_volume = 0.0
    previous_amount = 0.0
    for stamp, price, cumulative_volume, cumulative_amount in parsed_raw:
        volume = cumulative_volume - previous_volume
        amount = cumulative_amount - previous_amount
        adjusted_cumulative_volume = cumulative_volume * volume_multiplier
        avg_price = (
            cumulative_amount / adjusted_cumulative_volume
            if adjusted_cumulative_volume > 0 else None
        )
        minutes.append(
            TapeMinute(
                timestamp=stamp,
                price=price,
                avg_price=avg_price,
                high=None,
                low=None,
                volume=volume * volume_multiplier,
                amount=amount,
                cumulative_volume=adjusted_cumulative_volume,
                cumulative_amount=cumulative_amount,
            )
        )
        previous_volume = cumulative_volume
        previous_amount = cumulative_amount
    gaps = []
    if invalid_rows:
        gaps.append(f"invalid_rows:{invalid_rows}")
    if missing_amount_rows:
        gaps.append(f"missing_minute_amount:{missing_amount_rows}")
    if parsed_raw and volume_multiplier != 1.0:
        gaps.append("volume_unit_inferred_from_price_consistency")
    if future_minute_count:
        gaps.append(f"future_minute_dropped:{future_minute_count}")
    tape = IntradayTape(
        instrument=instrument,
        name=name or instrument.display_name,
        trade_date=trade_date,
        pre_close=pre_close,
        minutes=tuple(minutes),
        amount_kind="incomplete" if missing_amount_rows else "incremental",
        volume_unit=volume_unit,
    )
    source_time = minutes[-1].timestamp if minutes else None
    return ProviderResult(
        provider="tencent",
        schema_version="intraday-tape/v1",
        source_time=source_time,
        fetched_at=fetched_at,
        trade_date=trade_date,
        status="partial" if minutes and gaps else "ok" if minutes else "empty",
        gaps=tuple(gaps),
        errors=(),
        price_basis="unadjusted",
        data=tape,
    )


def _infer_volume_multiplier(
    rows: list[tuple[datetime, float, float, float]],
) -> tuple[float, Literal["share", "unknown"]]:
    usable = next(
        ((price, volume, amount) for _, price, volume, amount in reversed(rows) if volume > 0 and amount > 0),
        None,
    )
    if usable is None:
        return 1.0, "unknown"
    price, volume, amount = usable
    candidates: tuple[tuple[float, Literal["share"]], ...] = (
        (1.0, "share"),
        (100.0, "share"),
    )
    multiplier, unit = min(
        candidates,
        key=lambda item: abs((amount / (volume * item[0])) / price - 1.0),
    )
    implied = amount / (volume * multiplier)
    if abs(implied / price - 1.0) > 0.5:
        return 1.0, "unknown"
    return multiplier, unit


def _tencent_symbol_node(payload: object, symbol: str) -> dict[str, object]:
    root: dict[str, object] = payload if isinstance(payload, dict) else {}
    raw_data = root.get("data")
    data: dict[str, object] = raw_data if isinstance(raw_data, dict) else {}
    node = data.get(symbol)
    return node if isinstance(node, dict) else {}


def _response_json(response: object) -> object:
    try:
        return response.json()  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        text = str(getattr(response, "text", "")).strip()
        if text.startswith("{"):
            return json.loads(text)
        match = re.search(r"^[^(]*\((.*)\)\s*;?\s*$", text, re.DOTALL)
        if not match:
            raise ValueError("invalid_provider_json")
        return json.loads(match.group(1))


def _empty_tape(instrument: InstrumentRef, trade_date: date) -> IntradayTape:
    return IntradayTape(
        instrument=instrument,
        name=instrument.display_name,
        trade_date=trade_date,
        pre_close=None,
        minutes=(),
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=SHANGHAI) if value.tzinfo is None else value.astimezone(SHANGHAI)


def _parse_stamp(value: object) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M").replace(tzinfo=SHANGHAI)
    except ValueError:
        return None


def _minute_stamp(day: date, hhmm: str) -> datetime | None:
    try:
        parsed = datetime.combine(
            day,
            datetime.min.time(),
            tzinfo=SHANGHAI,
        ).replace(hour=int(hhmm[:2]), minute=int(hhmm[2:4]))
    except (ValueError, TypeError):
        return None
    return parsed


def _compact_date(value: str) -> date | None:
    try:
        return date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:8]}")
    except ValueError:
        return None


def _number(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _positive(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _nonnegative(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
