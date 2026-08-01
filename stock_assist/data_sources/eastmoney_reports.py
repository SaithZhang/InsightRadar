"""Eastmoney research-report metadata reader."""

from __future__ import annotations

import json
import re
import contextlib
import io
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from stock_assist.intraday.network import (
    build_urllib_opener,
    provider_policy,
    sanitized_error_type,
)


REPORT_ENDPOINT = "https://reportapi.eastmoney.com/report/list"
REPORT_HOME = "https://data.eastmoney.com/report/"


class EastmoneyReportError(RuntimeError):
    """Raised when Eastmoney report metadata cannot be fetched."""


@dataclass(frozen=True)
class ResearchReport:
    title: str
    category: str
    publish_date: str
    org: str
    researcher: str
    rating: str
    stock_code: str = ""
    stock_name: str = ""
    industry: str = ""
    pages: int | None = None
    info_code: str = ""
    url: str = REPORT_HOME
    pdf_url: str = ""
    source: str = "eastmoney_public"


def fetch_reports(
    q_type: int,
    *,
    begin: date,
    end: date,
    page_size: int = 20,
    page_no: int = 1,
) -> list[ResearchReport]:
    """Fetch one page of Eastmoney research report metadata.

    q_type follows Eastmoney's report center convention:
    0 stock reports, 1 industry reports, 2 strategy/macro reports.
    """

    params = {
        "_": "1783520000000",
        "beginTime": begin.isoformat(),
        "cb": "datatable123",
        "endTime": end.isoformat(),
        "fields": "",
        "industry": "*",
        "industryCode": "*",
        "orgCode": "",
        "pageNo": str(page_no),
        "pageSize": str(page_size),
        "qType": str(q_type),
        "rating": "*",
        "ratingChange": "*",
    }
    url = f"{REPORT_ENDPOINT}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        opener = build_urllib_opener(provider_policy("eastmoney"))
        with opener.open(request, timeout=15) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise EastmoneyReportError(
            f"Eastmoney report query failed: {sanitized_error_type(exc)}"
        ) from exc

    payload = _parse_jsonp(text)
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        return []
    return [_parse_report(row, q_type) for row in rows if isinstance(row, dict)]


def fetch_recent_report_groups(
    *,
    lookback_days: int = 7,
    page_size: int = 20,
    today: date | None = None,
) -> tuple[dict[str, list[ResearchReport]], list[str]]:
    """Fetch stock, industry, and strategy/macro report groups."""

    end = today or date.today()
    begin = end - timedelta(days=max(1, lookback_days))
    groups: dict[str, list[ResearchReport]] = {}
    gaps: list[str] = []
    for q_type, label in [(0, "个股研报"), (1, "行业研报"), (2, "策略/宏观")]:
        try:
            groups[label] = fetch_reports(q_type, begin=begin, end=end, page_size=page_size)
        except EastmoneyReportError as exc:
            groups[label] = []
            gaps.append(f"{label}: {exc}")
    return groups, gaps


def fetch_report_cli_groups(
    *,
    stock_codes: list[str] | tuple[str, ...] = (),
    industry_codes: list[str] | tuple[str, ...] = (),
    include_types: list[str] | tuple[str, ...] = ("strategy", "macro", "morning"),
    lookback_days: int = 90,
    page_size: int = 10,
    today: date | None = None,
) -> tuple[dict[str, list[ResearchReport]], list[str]]:
    """Fetch reports through report-cli's Eastmoney client."""

    try:
        from eastmoney.report_client import EastMoneyReportClient, ReportType
    except ImportError as exc:
        return {}, [f"report-cli provider unavailable: {exc}"]

    client = EastMoneyReportClient()
    end = today or date.today()
    begin = end - timedelta(days=max(1, lookback_days))
    begin_text = begin.isoformat()
    end_text = end.isoformat()
    groups: dict[str, list[ResearchReport]] = {}
    gaps: list[str] = []
    type_map = {
        "strategy": ("策略报告", ReportType.STRATEGY),
        "macro": ("宏观研究", ReportType.MACRO),
        "morning": ("券商晨报", ReportType.MORNING),
    }

    stock_reports: list[ResearchReport] = []
    for code in _unique_codes(stock_codes):
        try:
            rows = _report_cli_fetch(
                client,
                ReportType.STOCK,
                stock_code=code,
                page_size=page_size,
                begin_time=begin_text,
                end_time=end_text,
            )
            stock_reports.extend(_from_report_cli_row(row, "个股研报", client) for row in rows)
        except Exception as exc:
            gaps.append(f"report-cli stock {code}: {exc}")
    if stock_reports:
        groups["个股研报(report-cli)"] = _dedupe_reports(stock_reports)

    industry_reports: list[ResearchReport] = []
    for industry_code in industry_codes:
        try:
            rows = _report_cli_fetch(
                client,
                ReportType.INDUSTRY,
                industry_code=str(industry_code),
                page_size=page_size,
                begin_time=begin_text,
                end_time=end_text,
            )
            industry_reports.extend(_from_report_cli_row(row, "行业研报", client) for row in rows)
        except Exception as exc:
            gaps.append(f"report-cli industry {industry_code}: {exc}")
    if industry_reports:
        groups["行业研报(report-cli)"] = _dedupe_reports(industry_reports)

    for name in include_types:
        if name not in type_map:
            continue
        label, report_type = type_map[name]
        try:
            rows = _report_cli_fetch(
                client,
                report_type,
                page_size=page_size,
                begin_time=begin_text,
                end_time=end_text,
            )
            if rows:
                groups[f"{label}(report-cli)"] = _dedupe_reports(
                    [_from_report_cli_row(row, label, client) for row in rows]
                )
        except Exception as exc:
            gaps.append(f"report-cli {name}: {exc}")
    return groups, gaps


def _parse_jsonp(text: str) -> dict[str, Any]:
    match = re.search(r"^[^(]*\((.*)\)\s*$", text.strip(), flags=re.S)
    raw = match.group(1) if match else text
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EastmoneyReportError("Eastmoney returned non-JSON report payload") from exc
    if not isinstance(payload, dict):
        raise EastmoneyReportError("Eastmoney returned unexpected report payload")
    return payload


def _parse_report(row: dict[str, Any], q_type: int) -> ResearchReport:
    stock_code = str(row.get("stockCode") or "")
    stock_name = str(row.get("stockName") or "")
    market = str(row.get("market") or "")
    return ResearchReport(
        title=str(row.get("title") or ""),
        category={0: "个股研报", 1: "行业研报", 2: "策略/宏观"}.get(q_type, "研报"),
        publish_date=str(row.get("publishDate") or "")[:10],
        org=str(row.get("orgSName") or row.get("orgName") or ""),
        researcher=str(row.get("researcher") or ""),
        rating=str(row.get("sRatingName") or row.get("emRatingName") or ""),
        stock_code=stock_code,
        stock_name=stock_name,
        industry=str(row.get("industryName") or row.get("indvInduName") or ""),
        pages=_optional_int(row.get("attachPages")),
        info_code=str(row.get("infoCode") or ""),
        url=_report_url(stock_code, market, q_type),
        pdf_url=_pdf_url(str(row.get("infoCode") or "")),
    )


def _report_url(stock_code: str, market: str, q_type: int) -> str:
    if stock_code:
        prefix = "SH" if market == "SHANGHAI" or stock_code.startswith(("6", "9")) else "SZ"
        return f"https://emweb.eastmoney.com/PC_HSF10/ResearchReport/Index?code={prefix}{stock_code}&type=web"
    if q_type == 1:
        return "https://data.eastmoney.com/report/industry.jshtml"
    if q_type == 2:
        return "https://data.eastmoney.com/report/strategyreport.jshtml"
    return REPORT_HOME


def _pdf_url(info_code: str) -> str:
    if not info_code:
        return ""
    return f"https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"


def _report_cli_fetch(
    client: Any,
    report_type: str,
    *,
    stock_code: str | None = None,
    industry_code: str | None = None,
    page_size: int,
    begin_time: str,
    end_time: str,
) -> list[dict[str, Any]]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        data = client.fetch_reports(
            report_type=report_type,
            stock_code=stock_code,
            industry_code=industry_code,
            page_size=page_size,
            begin_time=begin_time,
            end_time=end_time,
        )
        rows = client.parse_reports(data, report_type=report_type)
    return rows


def _from_report_cli_row(row: dict[str, Any], category: str, client: Any) -> ResearchReport:
    info_code = str(row.get("info_code") or "")
    pdf_url = ""
    if row.get("url"):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            pdf_url = client.get_pdf_url(str(row.get("url")), info_code) or ""
    return ResearchReport(
        title=str(row.get("title") or ""),
        category=category,
        publish_date=str(row.get("publish_date") or "")[:10],
        org=str(row.get("org_name") or ""),
        researcher=str(row.get("researcher") or ""),
        rating=str(row.get("rating_name") or ""),
        stock_code=str(row.get("stock_code") or ""),
        stock_name=str(row.get("stock_name") or ""),
        industry=str(row.get("industry_name") or ""),
        pages=_optional_int(row.get("attach_pages")),
        info_code=info_code,
        url=str(row.get("url") or REPORT_HOME),
        pdf_url=pdf_url or _pdf_url(info_code),
        source="report-cli",
    )


def _unique_codes(codes: list[str] | tuple[str, ...]) -> list[str]:
    cleaned: list[str] = []
    for code in codes:
        value = str(code).strip()
        if not value:
            continue
        value = value.split(".")[0]
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


def _dedupe_reports(reports: list[ResearchReport]) -> list[ResearchReport]:
    seen: set[str] = set()
    result: list[ResearchReport] = []
    for report in reports:
        key = report.info_code or f"{report.title}|{report.org}|{report.publish_date}"
        if key in seen:
            continue
        seen.add(key)
        result.append(report)
    return result


def _optional_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
