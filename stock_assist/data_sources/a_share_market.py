"""Public A-share intraday market data helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request

from stock_assist.data_sources.iwencai_market import _query_iwencai
from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.intraday.network import (
    build_urllib_opener,
    provider_policy,
    sanitized_error_type,
)


EASTMONEY_TRENDS_URL = "https://push2.eastmoney.com/api/qt/stock/trends2/get"
EASTMONEY_UT = "fb5fd1943c7b386f172d6893dbfba10b"


@dataclass(frozen=True)
class IntradaySnapshot:
    secid: str
    code: str
    name: str
    label: str
    category: str
    price: float | None
    pre_close: float | None
    change_pct: float | None
    high: float | None
    low: float | None
    amount: float | None
    update_time: str
    source: str = "Eastmoney trends2"
    error: str = ""


@dataclass(frozen=True)
class FuturesBasisObservation:
    family: str
    contract: str
    underlying_code: str
    underlying_label: str
    current_time: str
    previous_time: str
    future_price: float | None
    spot_price: float | None
    future_change: float | None
    spot_change: float | None
    basis: float | None
    previous_basis: float | None
    basis_change: float | None
    basis_pct: float | None
    as_of_date: str = ""
    volume: float | None = None
    open_interest: float | None = None
    open_interest_change: float | None = None
    quote_kind: str = "intraday"
    source: str = "Galaxy AmazingData query_snapshot"
    error: str = ""


DEFAULT_FUTURES_BASIS_WATCH = [
    {"family": "IF", "underlying_code": "000300.SH", "underlying_label": "沪深300", "contracts": 2},
    {"family": "IH", "underlying_code": "000016.SH", "underlying_label": "上证50", "contracts": 2},
    {"family": "IC", "underlying_code": "000905.SH", "underlying_label": "中证500", "contracts": 2},
    {"family": "IM", "underlying_code": "000852.SH", "underlying_label": "中证1000", "contracts": 2},
]

IWENCAI_FUTURES_SOURCE = "同花顺问财 OpenAPI close snapshot"


def fetch_iwencai_futures_basis(
    families: list[dict[str, object]] | None = None,
    *,
    now: datetime | None = None,
    timeout: int = 30,
    max_age_days: int = 4,
    require_same_day: bool = False,
) -> tuple[list[FuturesBasisObservation], list[str]]:
    """Fetch the latest completed-session IF/IH/IC/IM basis from Iwencai.

    The provider is queried in two serial steps: first resolve one shared spot
    close date, then request every CFFEX contract for that exact date.  Expired
    zero-open-interest rows are excluded and the nearest configured contracts
    are selected dynamically, so contract months are never hard-coded.
    """

    watch = families or DEFAULT_FUTURES_BASIS_WATCH
    current = now or datetime.now()
    timeout = max(3, min(60, int(timeout)))
    max_age_days = max(0, min(10, int(max_age_days)))
    expected_spots = {
        str(item.get("underlying_code") or "").strip(): str(
            item.get("underlying_label") or item.get("underlying_code") or ""
        ).strip()
        for item in watch
        if str(item.get("underlying_code") or "").strip()
    }
    if not expected_spots:
        return [], ["同花顺问财股指期货配置缺少现货指数。"]

    spot_query = f"{' '.join(expected_spots.values())} 最近一个交易日收盘价"
    spot_records = _iwencai_records(spot_query, limit=20, timeout=timeout)
    spot_rows, as_of = _iwencai_spot_closes(spot_records, expected_spots)
    age_days = (current.date() - as_of).days
    if age_days < 0:
        raise RuntimeError(f"Iwencai spot date is in the future: {as_of.isoformat()}")
    if require_same_day and as_of != current.date():
        raise RuntimeError(
            f"Iwencai latest completed close is {as_of.isoformat()}, not current live session {current.date().isoformat()}"
        )
    if age_days > max_age_days:
        raise RuntimeError(
            f"Iwencai futures basis is stale: {as_of.isoformat()} ({age_days} calendar days old)"
        )

    day_text = f"{as_of.year}年{as_of.month}月{as_of.day}日"
    families_text = " ".join(
        sorted({str(item.get("family") or "").upper() for item in watch if item.get("family")})
    )
    futures_query = (
        f"{day_text} 中金所{families_text}股指期货全部合约，"
        "收盘价、成交量、持仓量、日增仓"
    )
    futures_records = _iwencai_records(futures_query, limit=50, timeout=timeout)
    by_family = _iwencai_futures_rows(futures_records, as_of)

    observations: list[FuturesBasisObservation] = []
    gaps: list[str] = []
    for item in watch:
        family = str(item.get("family") or "").upper()
        underlying_code = str(item.get("underlying_code") or "").strip()
        underlying_label = str(item.get("underlying_label") or underlying_code).strip()
        contract_limit = _positive_int(item.get("contracts"), default=2)
        spot_price = spot_rows.get(underlying_code)
        if spot_price is None:
            gaps.append(f"同花顺问财/{underlying_label} 缺少 {as_of.isoformat()} 收盘价。")
            continue
        contracts = by_family.get(family, [])[:contract_limit]
        if not contracts:
            gaps.append(f"同花顺问财/{family} 未找到正持仓有效合约。")
            continue
        if len(contracts) < contract_limit:
            gaps.append(f"同花顺问财/{family} 仅返回 {len(contracts)}/{contract_limit} 个有效合约。")
        for row in contracts:
            future_price = float(row["price"])
            basis = future_price - spot_price
            observations.append(
                FuturesBasisObservation(
                    family=family,
                    contract=str(row["contract"]),
                    underlying_code=underlying_code,
                    underlying_label=underlying_label,
                    current_time=f"{as_of.isoformat()} 15:00",
                    previous_time="",
                    future_price=future_price,
                    spot_price=spot_price,
                    future_change=None,
                    spot_change=None,
                    basis=basis,
                    previous_basis=None,
                    basis_change=None,
                    basis_pct=(basis / spot_price * 100 if spot_price else None),
                    as_of_date=as_of.isoformat(),
                    volume=_to_float(row.get("volume")),
                    open_interest=_to_float(row.get("open_interest")),
                    open_interest_change=_to_float(row.get("open_interest_change")),
                    quote_kind="completed_close",
                    source=IWENCAI_FUTURES_SOURCE,
                )
            )
    return observations, gaps


def fetch_amazingdata_snapshots(
    client: AmazingDataClient,
    items: list[dict[str, object]],
) -> list[IntradaySnapshot]:
    codes = [_item_code(item) for item in items]
    valid_codes = [code for code in codes if code]
    if not valid_codes:
        return []
    today = client.calendar[-1]
    raw = client.query_snapshot(valid_codes, begin_date=today, end_date=today)
    frames = _snapshot_frames(raw, today)
    results: list[IntradaySnapshot] = []
    for item, code in zip(items, codes):
        label = str(item.get("label") or code)
        category = str(item.get("category") or "watch")
        if not code:
            results.append(_empty_snapshot(str(item.get("secid") or ""), label, category, "missing AmazingData code"))
            continue
        frame = frames.get(code)
        if frame is None or getattr(frame, "empty", True):
            results.append(_empty_snapshot(str(item.get("secid") or code), label, category, "AmazingData snapshot empty"))
            continue
        row = frame.tail(1).iloc[0]
        price = _to_float(_row_value(row, ["last", "close", "price"]))
        pre_close = _to_float(_row_value(row, ["pre_close", "preclose", "prev_close"]))
        change_pct = (price / pre_close - 1) * 100 if price and pre_close else None
        results.append(
            IntradaySnapshot(
                secid=str(item.get("secid") or code),
                code=code,
                name=str(_row_value(row, ["name", "symbol"]) or label),
                label=label,
                category=category,
                price=price,
                pre_close=pre_close,
                change_pct=change_pct,
                high=_to_float(_row_value(row, ["high"])),
                low=_to_float(_row_value(row, ["low"])),
                amount=_to_float(_row_value(row, ["amount"])),
                update_time=str(_row_value(row, ["trade_time", "datetime", "time"]) or ""),
                source="Galaxy AmazingData query_snapshot",
            )
        )
    return results


def fetch_amazingdata_futures_basis(
    client: AmazingDataClient,
    families: list[dict[str, object]] | None = None,
    lookback_minutes: int = 4,
) -> tuple[list[FuturesBasisObservation], list[str]]:
    """Fetch CFFEX index-futures basis observations one code at a time."""

    watch = families or DEFAULT_FUTURES_BASIS_WATCH
    try:
        available_codes = client.get_future_code_list("ZJ_FUTURE")
    except Exception as exc:
        return [], [f"股指期货合约列表不可用：{exc}"]

    today = client.calendar[-1]
    observations: list[FuturesBasisObservation] = []
    gaps: list[str] = []
    spot_frames: dict[str, Any] = {}

    for family in watch:
        prefix = str(family.get("family") or "").upper()
        underlying_code = str(family.get("underlying_code") or "")
        underlying_label = str(family.get("underlying_label") or underlying_code)
        limit = _positive_int(family.get("contracts"), default=2)
        if not prefix or not underlying_code:
            gaps.append(f"股指期货配置缺少 family 或 underlying_code：{family}")
            continue

        contracts = _select_future_contracts(available_codes, prefix, limit)
        if not contracts:
            gaps.append(f"{prefix} 未找到可用中金所合约")
            continue

        spot_frame = spot_frames.get(underlying_code)
        if spot_frame is None:
            spot_frame, spot_error = _snapshot_frame_for_code(client, underlying_code, today)
            spot_frames[underlying_code] = spot_frame
            if spot_error:
                gaps.append(f"{underlying_label} 现货指数快照不可用：{spot_error}")

        for contract in contracts:
            future_frame, future_error = _snapshot_frame_for_code(client, contract, today)
            if future_error or spot_frame is None:
                observations.append(
                    _empty_basis(
                        family=prefix,
                        contract=contract,
                        underlying_code=underlying_code,
                        underlying_label=underlying_label,
                        error=future_error or "spot snapshot unavailable",
                    )
                )
                continue
            observations.append(
                _basis_from_frames(
                    family=prefix,
                    contract=contract,
                    underlying_code=underlying_code,
                    underlying_label=underlying_label,
                    future_frame=future_frame,
                    spot_frame=spot_frame,
                    lookback_minutes=lookback_minutes,
                )
            )

    return observations, gaps


def _iwencai_records(query: str, *, limit: int, timeout: int) -> list[dict[str, object]]:
    """Return provider rows with one bounded relaxed retry for an empty result."""

    payload = _query_iwencai(query, limit=limit, timeout=timeout)
    records = payload.get("datas") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        payload = _query_iwencai(
            query.replace("全部合约", "合约"),
            limit=limit,
            timeout=timeout,
            call_type="retry",
        )
        records = payload.get("datas") if isinstance(payload, dict) else None
    rows = [item for item in (records or []) if isinstance(item, dict)]
    if not rows:
        raise RuntimeError(f"Iwencai returned no rows for query: {query}")
    return rows


def _iwencai_spot_closes(
    records: list[dict[str, object]],
    expected: dict[str, str],
) -> tuple[dict[str, float], date]:
    closes: dict[str, float] = {}
    dates: set[date] = set()
    for record in records:
        code = str(record.get("指数代码") or "").strip()
        if code not in expected:
            continue
        dated = _dated_numeric_field(record, "收盘价")
        if dated is None or dated[1] <= 0:
            continue
        as_of, close = dated
        dates.add(as_of)
        closes[code] = close
    missing = sorted(set(expected) - set(closes))
    if missing:
        raise RuntimeError(f"Iwencai spot response missing indexes: {', '.join(missing)}")
    if len(dates) != 1:
        rendered = ", ".join(sorted(item.isoformat() for item in dates)) or "none"
        raise RuntimeError(f"Iwencai spot response dates are not aligned: {rendered}")
    return closes, next(iter(dates))


def _iwencai_futures_rows(
    records: list[dict[str, object]],
    as_of: date,
) -> dict[str, list[dict[str, object]]]:
    stamp = as_of.strftime("%Y%m%d")
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        contract = str(record.get("合约代码") or "").strip().upper()
        match = re.fullmatch(r"(IF|IH|IC|IM)(\d{4})\.CFE", contract)
        if match is None:
            continue
        family, month = match.groups()
        price = _to_float(record.get(f"收盘价[{stamp}]"))
        open_interest = _to_float(record.get(f"持仓量[{stamp}]"))
        if price is None or price <= 0 or open_interest is None or open_interest <= 0:
            continue
        grouped.setdefault(family, []).append(
            {
                "contract": contract,
                "month": int(month),
                "price": price,
                "volume": _to_float(record.get(f"成交量[{stamp}]")),
                "open_interest": open_interest,
                "open_interest_change": _to_float(record.get(f"日增仓[{stamp}]")),
            }
        )
    for rows in grouped.values():
        rows.sort(key=lambda item: (int(item["month"]), str(item["contract"])))
    return grouped


def _dated_numeric_field(record: dict[str, object], prefix: str) -> tuple[date, float] | None:
    matches: list[tuple[date, float]] = []
    pattern = re.compile(rf"^{re.escape(prefix)}\[(\d{{8}})\]$")
    for key, raw in record.items():
        match = pattern.match(str(key))
        if match is None:
            continue
        stamp = match.group(1)
        value = _to_float(raw)
        if value is None:
            continue
        try:
            day = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        except ValueError:
            continue
        matches.append((day, value))
    return max(matches, key=lambda item: item[0]) if matches else None


def fetch_intraday_snapshot(secid: str, label: str, category: str, timeout: int = 10) -> IntradaySnapshot:
    """Fetch one index/ETF intraday snapshot from Eastmoney trends2."""

    params = {
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "ut": EASTMONEY_UT,
        "ndays": "1",
        "iscr": "1",
        "secid": secid,
    }
    url = f"{EASTMONEY_TRENDS_URL}?{urlencode(params)}"
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        opener = build_urllib_opener(provider_policy("eastmoney_push2"))
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return _empty_snapshot(
            secid, label, category,
            f"request failed: {sanitized_error_type(exc)}",
        )

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return _empty_snapshot(secid, label, category, f"empty response rc={payload.get('rc') if isinstance(payload, dict) else 'NA'}")

    trends = data.get("trends") or []
    if not trends:
        return _empty_snapshot(secid, label, category, "no intraday trend rows")

    latest = str(trends[-1]).split(",")
    if len(latest) < 8:
        return _empty_snapshot(secid, label, category, "malformed latest trend row")

    price = _to_float(latest[2])
    pre_close = _to_float(data.get("preClose"))
    change_pct = (price / pre_close - 1) * 100 if price and pre_close else None
    return IntradaySnapshot(
        secid=secid,
        code=str(data.get("code") or secid.split(".")[-1]),
        name=str(data.get("name") or label),
        label=label,
        category=category,
        price=price,
        pre_close=pre_close,
        change_pct=change_pct,
        high=_to_float(latest[3]),
        low=_to_float(latest[4]),
        amount=_to_float(latest[6]),
        update_time=str(latest[0]),
    )


def _snapshot_frame_for_code(client: AmazingDataClient, code: str, today: int) -> tuple[Any | None, str]:
    try:
        raw = client.query_snapshot([code], begin_date=today, end_date=today)
    except Exception as exc:
        return None, str(exc)
    frames = _snapshot_frames(raw, today)
    frame = frames.get(code)
    if frame is None or getattr(frame, "empty", True):
        return None, "empty snapshot"
    return frame, ""


def _basis_from_frames(
    family: str,
    contract: str,
    underlying_code: str,
    underlying_label: str,
    future_frame: Any,
    spot_frame: Any,
    lookback_minutes: int,
) -> FuturesBasisObservation:
    future_latest_time = _latest_time(future_frame)
    spot_latest_time = _latest_time(spot_frame)
    if future_latest_time is None or spot_latest_time is None:
        return _empty_basis(family, contract, underlying_code, underlying_label, "missing trade_time")

    current_cutoff = min(future_latest_time, spot_latest_time)
    previous_cutoff = current_cutoff - timedelta(minutes=lookback_minutes)
    future_now = _row_at_or_before(future_frame, current_cutoff)
    spot_now = _row_at_or_before(spot_frame, current_cutoff)
    future_prev = _row_at_or_before(future_frame, previous_cutoff)
    spot_prev = _row_at_or_before(spot_frame, previous_cutoff)
    if future_now is None or spot_now is None:
        return _empty_basis(family, contract, underlying_code, underlying_label, "missing current aligned rows")

    future_price = _to_float(_row_value(future_now, ["last", "close", "price"]))
    spot_price = _to_float(_row_value(spot_now, ["last", "close", "price"]))
    future_prev_price = _to_float(_row_value(future_prev, ["last", "close", "price"])) if future_prev is not None else None
    spot_prev_price = _to_float(_row_value(spot_prev, ["last", "close", "price"])) if spot_prev is not None else None
    basis = future_price - spot_price if future_price is not None and spot_price is not None else None
    previous_basis = (
        future_prev_price - spot_prev_price
        if future_prev_price is not None and spot_prev_price is not None
        else None
    )
    basis_change = basis - previous_basis if basis is not None and previous_basis is not None else None
    basis_pct = basis / spot_price * 100 if basis is not None and spot_price else None
    return FuturesBasisObservation(
        family=family,
        contract=contract,
        underlying_code=underlying_code,
        underlying_label=underlying_label,
        current_time=current_cutoff.strftime("%H:%M"),
        previous_time=previous_cutoff.strftime("%H:%M"),
        future_price=future_price,
        spot_price=spot_price,
        future_change=_diff(future_price, future_prev_price),
        spot_change=_diff(spot_price, spot_prev_price),
        basis=basis,
        previous_basis=previous_basis,
        basis_change=basis_change,
        basis_pct=basis_pct,
    )


def _empty_basis(
    family: str,
    contract: str,
    underlying_code: str,
    underlying_label: str,
    error: str,
) -> FuturesBasisObservation:
    return FuturesBasisObservation(
        family=family,
        contract=contract,
        underlying_code=underlying_code,
        underlying_label=underlying_label,
        current_time="",
        previous_time="",
        future_price=None,
        spot_price=None,
        future_change=None,
        spot_change=None,
        basis=None,
        previous_basis=None,
        basis_change=None,
        basis_pct=None,
        error=error,
    )


def _select_future_contracts(codes: list[str], prefix: str, limit: int) -> list[str]:
    family_codes = [code for code in codes if str(code).startswith(prefix)]
    return sorted(family_codes, key=_future_sort_key)[:limit]


def _future_sort_key(code: str) -> tuple[int, int, str]:
    match = re.match(r"^[A-Z]+(\d{2})(\d{2})", str(code))
    if not match:
        return (9999, 99, str(code))
    year = 2000 + int(match.group(1))
    month = int(match.group(2))
    return (year, month, str(code))


def _latest_time(frame: Any) -> datetime | None:
    row = frame.tail(1).iloc[0]
    return _parse_time(_row_value(row, ["trade_time", "datetime", "time"]))


def _row_at_or_before(frame: Any, cutoff: datetime) -> Any | None:
    best_row = None
    best_time = None
    for _, row in frame.iterrows():
        row_time = _parse_time(_row_value(row, ["trade_time", "datetime", "time"]))
        if row_time is None or row_time > cutoff:
            continue
        if best_time is None or row_time >= best_time:
            best_row = row
            best_time = row_time
    return best_row


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _diff(value: float | None, previous: float | None) -> float | None:
    if value is None or previous is None:
        return None
    return value - previous


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _item_code(item: dict[str, object]) -> str:
    code = str(item.get("code") or "").strip()
    if code:
        return code
    secid = str(item.get("secid") or "").strip()
    if "." not in secid:
        return secid
    market, raw_code = secid.split(".", 1)
    suffix = "SH" if market == "1" else "SZ"
    return f"{raw_code}.{suffix}"


def _snapshot_frames(raw: Any, today: int) -> dict[str, Any]:
    if isinstance(raw, dict) and today in raw and isinstance(raw[today], dict):
        return raw[today]
    if isinstance(raw, dict):
        return raw
    return {}


def _row_value(row: Any, names: list[str]) -> Any:
    lowered = {str(key).lower(): key for key in getattr(row, "index", [])}
    for name in names:
        key = lowered.get(name.lower())
        if key is not None:
            return row.get(key)
    return None


def _empty_snapshot(secid: str, label: str, category: str, error: str) -> IntradaySnapshot:
    return IntradaySnapshot(
        secid=secid,
        code=secid.split(".")[-1],
        name=label,
        label=label,
        category=category,
        price=None,
        pre_close=None,
        change_pct=None,
        high=None,
        low=None,
        amount=None,
        update_time="",
        error=error,
    )


def _to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
