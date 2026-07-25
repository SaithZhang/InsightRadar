"""CNInfo announcement lookup for fresh filings before vendor data catches up."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import requests


CNINFO_SEARCH_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STOCK_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"
CNINFO_PDF_BASE = "https://static.cninfo.com.cn/"

HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.cninfo.com.cn",
    "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
}

CATEGORY_MAP = {
    "profit_notice": "category_yjygjxz_szsh",
    "semi_annual": "category_bndbg_szsh",
    "annual": "category_ndbg_szsh",
}


@dataclass(frozen=True)
class CninfoAnnouncement:
    code: str
    name: str
    title: str
    announcement_id: str
    date: str
    category: str
    pdf_url: str
    detail_url: str


def search_profit_notices(
    code: str,
    date_from: date | None = None,
    date_to: date | None = None,
    page_size: int = 30,
) -> list[CninfoAnnouncement]:
    """Search recent CNInfo performance forecast announcements for one A-share."""

    clean_code = code.split(".")[0]
    date_to = date_to or (date.today() + timedelta(days=1))
    date_from = date_from or (date_to - timedelta(days=14))
    payload = {
        "pageNum": "1",
        "pageSize": str(page_size),
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": _stock_param(clean_code),
        "searchkey": "",
        "secid": "",
        "category": CATEGORY_MAP["profit_notice"],
        "trade": "",
        "seDate": f"{date_from:%Y-%m-%d}~{date_to:%Y-%m-%d}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    response = requests.post(CNINFO_SEARCH_URL, data=payload, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    return [_parse_announcement(item) for item in data.get("announcements") or []]


def latest_profit_notice(code: str, days: int = 14) -> CninfoAnnouncement | None:
    notices = search_profit_notices(code, date_from=date.today() - timedelta(days=days))
    return notices[0] if notices else None


def _stock_param(code: str) -> str:
    response = requests.get(
        CNINFO_STOCK_URL,
        headers={"User-Agent": HEADERS["User-Agent"], "Referer": "https://www.cninfo.com.cn/"},
        timeout=30,
    )
    response.raise_for_status()
    for item in response.json().get("stockList", []):
        if str(item.get("code", "")).strip() == code:
            org_id = item.get("orgId", "")
            return f"{code},{org_id}" if org_id else code
    return code


def _parse_announcement(item: dict[str, Any]) -> CninfoAnnouncement:
    title = re.sub(r"</?em>", "", str(item.get("announcementTitle", ""))).strip()
    name = re.sub(r"</?em>", "", str(item.get("secName", ""))).strip()
    timestamp = item.get("announcementTime") or 0
    announcement_date = ""
    if timestamp:
        announcement_date = datetime.fromtimestamp(int(timestamp) / 1000).strftime("%Y-%m-%d")
    adjunct_url = str(item.get("adjunctUrl", ""))
    announcement_id = str(item.get("announcementId", ""))
    return CninfoAnnouncement(
        code=str(item.get("secCode", "")).strip(),
        name=name,
        title=title,
        announcement_id=announcement_id,
        date=announcement_date,
        category="业绩预告",
        pdf_url=f"{CNINFO_PDF_BASE}{adjunct_url}" if adjunct_url else "",
        detail_url=(
            f"https://www.cninfo.com.cn/new/disclosure/detail?announcementId={announcement_id}"
            if announcement_id
            else ""
        ),
    )
