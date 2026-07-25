"""Minimal read-only Iwencai adapter for the equal-weight A-share index.

The API key is read only from ``IWENCAI_API_KEY``.  The adapter intentionally
returns a narrow daily-series contract so the risk engine does not depend on
free-form response wording outside the requested bracketed fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
import os
import secrets
import urllib.request


IWENCAI_API_URL = "https://openapi.iwencai.com/v1/query2data"


@dataclass(frozen=True)
class IwencaiDailyBar:
    day: date
    close: float
    change_pct: float | None = None
    amount: float | None = None


@dataclass(frozen=True)
class IwencaiCrowdingSnapshot:
    day: date
    total_amount: float
    top1_amount_share: float
    top10_amount_share: float
    top20_amount_share: float
    top50_amount_share: float
    top50_hhi_partial: float
    top1_turnover_free_float: float | None
    top1_code: str
    top1_name: str
    universe_count: int


def fetch_a_share_anchor_records(
    anchor: date,
    end: date,
    *,
    page_size: int = 500,
    max_pages: int = 20,
    timeout: int = 60,
) -> tuple[list[dict[str, object]], str, str]:
    """Fetch a complete A-share anchor-date cross-section serially.

    The interval-return field is explicitly requested as forward adjusted.
    Pagination coverage is checked before rows are returned so downstream
    aggregation cannot mistake the first page for the whole market.
    """

    page_size = max(50, min(500, int(page_size)))
    max_pages = max(1, min(30, int(max_pages)))
    anchor_text = f"{anchor.year}年{anchor.month}月{anchor.day}日"
    end_text = f"{end.year}年{end.month}月{end.day}日"
    query = (
        f"A股{anchor_text}至{end_text}前复权区间涨跌幅，"
        f"{anchor_text}收盘价，{end_text}收盘价，所属申万一级行业，"
        f"{end_text}自由流通市值，上市日期"
    )
    rows: list[dict[str, object]] = []
    expected = 0
    for page in range(1, max_pages + 1):
        payload = _query_iwencai(query, limit=page_size, timeout=timeout, page=page)
        page_rows = payload.get("datas") if isinstance(payload, dict) else None
        if not isinstance(page_rows, list) or not page_rows:
            raise RuntimeError(f"Iwencai anchor cross-section page {page} returned no rows")
        rows.extend(item for item in page_rows if isinstance(item, dict))
        expected = _nonnegative_int(payload.get("code_count"))
        if expected and len(rows) >= expected:
            break
        if len(page_rows) < page_size:
            break
    by_code = {
        str(item.get("股票代码") or "").strip(): item
        for item in rows
        if str(item.get("股票代码") or "").strip()
    }
    if expected and len(by_code) < expected:
        raise RuntimeError(
            f"Iwencai anchor cross-section pagination incomplete: {len(by_code)}/{expected} unique rows"
        )
    anchor_stamp = anchor.strftime("%Y%m%d")
    end_stamp = end.strftime("%Y%m%d")
    normalized: list[dict[str, object]] = []
    for item in by_code.values():
        normalized.append(
            {
                "code": str(item.get("股票代码") or ""),
                "name": str(item.get("股票简称") or ""),
                "listing_date": item.get("上市日期"),
                "return_rate": _interval_return(item, anchor_stamp, end_stamp),
                "anchor_close": _positive_float(item.get(f"收盘价[{anchor_stamp}]")),
                "current_close": _positive_float(item.get(f"收盘价[{end_stamp}]")),
                "industry": item.get("所属申万一级行业"),
                "current_free_float_cap": _positive_float(item.get(f"自由流通市值[{end_stamp}]")),
            }
        )
    return normalized, "同花顺问财 A股前复权锚点横截面", query


def fetch_ths_all_a(
    start: date,
    end: date,
    *,
    timeout: int = 30,
) -> tuple[list[IwencaiDailyBar], str]:
    """Fetch 同花顺全A(沪深京) daily closes, returns and turnover."""

    api_key = os.environ.get("IWENCAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("IWENCAI_API_KEY is not configured")
    query = (
        f"同花顺全A(沪深京){start.isoformat()}至{end.isoformat()}"
        "每日收盘价、涨跌幅、成交额"
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Claw-Call-Type": "normal",
        "X-Claw-Skill-Id": "hithink-market-query",
        "X-Claw-Skill-Version": "1.0.0",
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": secrets.token_hex(32),
    }
    body = json.dumps(
        {"query": query, "page": "1", "limit": "1", "is_cache": "1", "expand_index": "true"}
    ).encode("utf-8")
    request = urllib.request.Request(IWENCAI_API_URL, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    records = payload.get("datas") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        raise RuntimeError("Iwencai returned no 同花顺全A daily series")
    record = records[0]
    if str(record.get("指数代码", "")) != "883957.TI":
        raise RuntimeError("Iwencai response did not resolve to 883957.TI")
    closes = _dated_values(record, "收盘价")
    changes = dict(_dated_values(record, "涨跌幅"))
    amounts = dict(_dated_values(record, "成交额"))
    bars = [
        IwencaiDailyBar(
            day=day,
            close=value,
            change_pct=changes.get(day),
            amount=amounts.get(day),
        )
        for day, value in closes
        if value > 0
    ]
    if len(bars) < 20:
        raise RuntimeError(f"Iwencai returned only {len(bars)} usable 同花顺全A bars")
    return bars, "同花顺问财 883957.TI"


def fetch_a_share_crowding(
    day: date,
    *,
    timeout: int = 30,
) -> tuple[IwencaiCrowdingSnapshot, str]:
    """Fetch an as-of A-share turnover concentration snapshot.

    The snapshot is diagnostic until enough daily observations exist to form
    a stable historical percentile.
    """

    stamp = day.strftime("%Y%m%d")
    day_text = f"{day.year}年{day.month}月{day.day}日"
    top_payload = _query_iwencai(
        f"{day_text}A股成交额前50股票，成交额和自由流通市值",
        limit=50,
        timeout=timeout,
    )
    total_payload = _query_iwencai(
        f"{day_text}A股总成交额",
        limit=10,
        timeout=timeout,
    )
    top_records = top_payload.get("datas") if isinstance(top_payload, dict) else None
    total_records = total_payload.get("datas") if isinstance(total_payload, dict) else None
    if not isinstance(top_records, list) or len(top_records) < 20:
        raise RuntimeError("Iwencai returned fewer than 20 ranked A-share turnover rows")
    if not isinstance(total_records, list) or not total_records or not isinstance(total_records[0], dict):
        raise RuntimeError("Iwencai returned no total A-share turnover row")
    ranked = [item for item in top_records if isinstance(item, dict)]
    amount_key = f"成交额[{stamp}]"
    free_float_key = f"自由流通市值[{stamp}]"
    amounts = [_positive_float(item.get(amount_key)) for item in ranked]
    if any(value is None for value in amounts[:20]):
        raise RuntimeError(f"Iwencai turnover ranking is missing {amount_key}")
    usable_amounts = [float(value) for value in amounts if value is not None and value > 0]
    total_amount = _positive_float(total_records[0].get(amount_key))
    if total_amount is None:
        raise RuntimeError(f"Iwencai total turnover is missing {amount_key}")
    shares = [value / total_amount for value in usable_amounts]
    first = ranked[0]
    top1_free_float = _positive_float(first.get(free_float_key))
    try:
        universe_count = int(top_payload.get("code_count", 0))
    except (TypeError, ValueError):
        universe_count = 0
    return (
        IwencaiCrowdingSnapshot(
            day=day,
            total_amount=total_amount,
            top1_amount_share=shares[0],
            top10_amount_share=sum(shares[:10]),
            top20_amount_share=sum(shares[:20]),
            top50_amount_share=sum(shares[:50]),
            top50_hhi_partial=sum(value * value for value in shares[:50]),
            top1_turnover_free_float=(usable_amounts[0] / top1_free_float if top1_free_float else None),
            top1_code=str(first.get("股票代码", "")),
            top1_name=str(first.get("股票简称", "")),
            universe_count=universe_count,
        ),
        "同花顺问财 A股成交额排名/全A总成交额",
    )


def _query_iwencai(
    query: str,
    *,
    limit: int,
    timeout: int,
    page: int = 1,
    call_type: str = "normal",
) -> dict[str, object]:
    api_key = os.environ.get("IWENCAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("IWENCAI_API_KEY is not configured")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Claw-Call-Type": call_type,
        "X-Claw-Skill-Id": "hithink-market-query",
        "X-Claw-Skill-Version": "1.0.0",
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": secrets.token_hex(32),
    }
    body = json.dumps(
        {"query": query, "page": str(page), "limit": str(limit), "is_cache": "1", "expand_index": "true"},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(IWENCAI_API_URL, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("Iwencai returned a non-object response")
    return payload


def _dated_values(record: dict[str, object], prefix: str) -> list[tuple[date, float]]:
    values: list[tuple[date, float]] = []
    marker = f"{prefix}["
    for key, raw in record.items():
        if not key.startswith(marker) or not key.endswith("]"):
            continue
        stamp = key[len(marker) : -1]
        try:
            day = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
            value = float(raw)
        except (TypeError, ValueError):
            continue
        values.append((day, value))
    return sorted(values)


def _positive_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _interval_return(item: dict[str, object], anchor_stamp: str, end_stamp: str) -> float | None:
    expected = f"涨跌幅[{anchor_stamp}-{end_stamp}]"
    raw = item.get(expected)
    if raw is None:
        raw = next(
            (
                value
                for key, value in item.items()
                if key.startswith("涨跌幅[") and anchor_stamp in key and end_stamp in key
            ),
            None,
        )
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        return None
    return parsed / 100.0 if math.isfinite(parsed) else None


def _nonnegative_int(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)
