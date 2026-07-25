"""Read-only NGA forum access with a local, non-repository cookie store."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Iterable
from urllib.parse import urljoin

import requests


NGA_BASE_URL = "https://bbs.nga.cn/"
DEFAULT_BOARD_FID = 706


class NGAError(RuntimeError):
    """Base error for NGA collection."""


class NGAAuthError(NGAError):
    """Raised when the local cookie is missing or rejected."""


@dataclass(frozen=True)
class NGATopic:
    thread_id: str
    title: str
    url: str
    replies: int
    row_text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class NGAReply:
    pid: str
    floor: int
    author: str
    author_id: str
    posted_at: str
    score: int
    content: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class NGADailyTopic:
    thread_id: str
    title: str
    url: str
    author: str
    author_id: str
    posted_at: str
    last_posted_at: str
    replies: int
    recommend: int
    latest_replies: tuple[NGAReply, ...]
    high_score_replies: tuple[NGAReply, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["latest_replies"] = [item.to_dict() for item in self.latest_replies]
        payload["high_score_replies"] = [item.to_dict() for item in self.high_score_replies]
        return payload


def default_cookie_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"
    return root / "InsightRadar" / "secrets" / "nga_cookie.txt"


def save_cookie(cookie: str, path: Path | None = None) -> Path:
    cleaned = cookie.strip()
    if not cleaned or "=" not in cleaned:
        raise ValueError("Cookie 内容无效：应包含至少一个 name=value 项。")
    if "\n" in cleaned or "\r" in cleaned:
        raise ValueError("Cookie 必须是单行文本。")
    target = path or default_cookie_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(cleaned, encoding="utf-8")
    try:
        target.chmod(stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass
    return target


def load_cookie(path: Path | None = None) -> str:
    environment_cookie = os.environ.get("NGA_COOKIE", "").strip()
    if environment_cookie:
        return environment_cookie
    target = path or default_cookie_path()
    if not target.exists():
        raise NGAAuthError(
            "未找到本机 NGA Cookie。请先运行 `insight-radar nga-auth set`，Cookie 不会写入仓库。"
        )
    cookie = target.read_text(encoding="utf-8").strip()
    if not cookie:
        raise NGAAuthError("本机 NGA Cookie 文件为空，请重新运行 `insight-radar nga-auth set`。")
    return cookie


def clear_cookie(path: Path | None = None) -> bool:
    target = path or default_cookie_path()
    if not target.exists():
        return False
    target.unlink()
    return True


def fetch_board_topics(
    fid: int = DEFAULT_BOARD_FID,
    *,
    cookie: str | None = None,
    timeout: float = 20.0,
    session: requests.Session | None = None,
) -> list[NGATopic]:
    client = session or requests.Session()
    url = urljoin(NGA_BASE_URL, f"thread.php?fid={int(fid)}")
    response = client.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": cookie or load_cookie(),
            "Referer": NGA_BASE_URL,
        },
        timeout=timeout,
    )
    if response.status_code in {401, 403}:
        raise NGAAuthError(
            f"NGA 返回 HTTP {response.status_code}；Cookie 可能已失效，或当前请求触发了访问校验。"
        )
    response.raise_for_status()
    html = _decode_html(response.content, response.headers.get("content-type", ""))
    topics = parse_board_topics(html)
    if not topics:
        raise NGAError("NGA 页面可访问，但未解析到主题；页面结构可能变化或会话需要重新验证。")
    return topics


def fetch_daily_topics(
    fid: int = DEFAULT_BOARD_FID,
    *,
    target_date: str,
    detail_limit: int = 24,
    listing_pages: int = 1,
    window_start: str | None = None,
    window_end: str | None = None,
    request_delay_seconds: float = 0.0,
    detail_retries: int = 2,
    priority_author_ids: set[str] | None = None,
    timeout: float = 20.0,
    cookie: str | None = None,
    session: requests.Session | None = None,
) -> list[NGADailyTopic]:
    client = session or requests.Session()
    secret = cookie or load_cookie()
    start_at = window_start or f"{target_date} 00:00:00"
    end_at = window_end or f"{target_date} 23:59:59"
    raw_topics_by_id: dict[str, dict[str, object]] = {}
    for page in range(1, max(1, listing_pages) + 1):
        listing = _get_json(
            client,
            f"thread.php?fid={int(fid)}&page={page}&__output=11",
            cookie=secret,
            timeout=timeout,
            referer=NGA_BASE_URL,
        )
        raw_listing_topics = listing.get("data", {}).get("__T") or {}
        if isinstance(raw_listing_topics, dict):
            page_topics = list(raw_listing_topics.values())
        elif isinstance(raw_listing_topics, list):
            page_topics = raw_listing_topics
        else:
            raise NGAError("NGA 主题列表 JSON 结构异常。")
        if not page_topics:
            break
        for item in page_topics:
            if isinstance(item, dict) and item.get("tid"):
                raw_topics_by_id[str(item["tid"])] = item
    raw_topics = list(raw_topics_by_id.values())
    candidates = [
        item
        for item in raw_topics
        if _in_window(_timestamp_text(item.get("postdate")), start_at, end_at)
        or _in_window(_timestamp_text(item.get("lastpost")), start_at, end_at)
        or (
            str(item.get("authorid", "")) in (priority_author_ids or set())
            and _timestamp_text(item.get("lastpost")).startswith(target_date)
        )
    ]
    candidates.sort(
        key=lambda item: (
            str(item.get("authorid", "")) in (priority_author_ids or set()),
            _in_window(_timestamp_text(item.get("postdate")), start_at, end_at),
            int(item.get("recommend") or 0),
            int(item.get("replies") or 0),
            _timestamp_text(item.get("lastpost")),
        ),
        reverse=True,
    )
    result: list[NGADailyTopic] = []
    for item in candidates[: max(1, detail_limit)]:
        tid = str(item.get("tid", ""))
        if not tid:
            continue
        replies: dict[str, NGAReply] = {}
        for detail_page in ("1", "e"):
            for attempt in range(max(1, detail_retries)):
                try:
                    detail = _get_json(
                        client,
                        f"read.php?tid={tid}&page={detail_page}&__output=11",
                        cookie=secret,
                        timeout=timeout,
                        referer=f"{NGA_BASE_URL}thread.php?fid={int(fid)}",
                    )
                    detail_data = detail.get("data", {})
                    extracted = _extract_replies(detail_data, start_at, end_at)
                    raw_reply_rows = detail_data.get("__R") if isinstance(detail_data, dict) else None
                    has_reply_rows = bool(raw_reply_rows)
                except NGAError:
                    extracted = {}
                    has_reply_rows = False
                if has_reply_rows or int(item.get("replies") or 0) == 0:
                    replies.update(extracted)
                    break
                if attempt + 1 < max(1, detail_retries):
                    time.sleep(max(0.1, request_delay_seconds * 2))
            if request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
            if detail_page == "1" and replies:
                break
        latest = tuple(sorted(replies.values(), key=lambda row: (row.posted_at, row.floor), reverse=True)[:8])
        high = tuple(sorted(replies.values(), key=lambda row: (row.score, row.posted_at), reverse=True)[:5])
        result.append(
            NGADailyTopic(
                thread_id=tid,
                title=_clean_post_text(str(item.get("subject", "")), limit=240),
                url=urljoin(NGA_BASE_URL, f"read.php?tid={tid}"),
                author=str(item.get("author", "")),
                author_id=str(item.get("authorid", "")),
                posted_at=_timestamp_text(item.get("postdate")),
                last_posted_at=_timestamp_text(item.get("lastpost")),
                replies=int(item.get("replies") or 0),
                recommend=int(item.get("recommend") or 0),
                latest_replies=latest,
                high_score_replies=high,
            )
        )
    return result


def fetch_author_thread_replies(
    thread_id: str,
    author_id: str,
    *,
    window_start: str,
    window_end: str,
    max_pages: int = 8,
    request_delay_seconds: float = 0.0,
    timeout: float = 20.0,
    cookie: str | None = None,
    session: requests.Session | None = None,
) -> tuple[NGAReply, ...]:
    """Fetch one author's posts inside a thread and an exact time window.

    NGA's ``authorid`` thread filter paginates only the selected author's posts.
    Walking backwards from the author's last page therefore recovers long-thread
    activity without scanning thousands of unrelated replies. The HTML response
    is used because NGA can truncate JSON output for content-heavy author pages.
    """

    client = session or requests.Session()
    secret = cookie or load_cookie()
    tid = str(thread_id).strip()
    uid = str(author_id).strip()
    if not tid or not uid:
        return ()

    collected: dict[str, NGAReply] = {}
    page: int | str = "e"
    visited_pages: set[int] = set()
    for _ in range(max(1, max_pages)):
        html = _get_html(
            client,
            f"read.php?tid={tid}&page={page}&authorid={uid}",
            cookie=secret,
            timeout=timeout,
            referer=urljoin(NGA_BASE_URL, f"read.php?tid={tid}"),
        )
        current_page_match = re.search(r"__CURRENT_PAGE\s*=\s*(\d+)", html)
        current_page = _positive_int(current_page_match.group(1) if current_page_match else None, default=1)
        if current_page in visited_pages:
            break
        visited_pages.add(current_page)

        page_replies = _parse_author_thread_replies(html, uid)
        bounds = _reply_bounds(page_replies)
        if bounds is None:
            break
        first_posted_at, last_posted_at = bounds
        if last_posted_at < window_start:
            break

        for reply in page_replies:
            if reply.author_id == uid and _in_window(reply.posted_at, window_start, window_end):
                pid = reply.pid
                collected[pid] = reply

        # Pages are chronological within the author-only result. Once the
        # oldest row on this page reaches the window start, earlier pages cannot
        # contain additional in-window statements.
        if first_posted_at <= window_start or current_page <= 1:
            break
        page = current_page - 1
        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)

    return tuple(sorted(collected.values(), key=lambda item: (item.posted_at, item.floor)))


def _get_json(
    session: requests.Session,
    relative_url: str,
    *,
    cookie: str,
    timeout: float,
    referer: str,
) -> dict[str, object]:
    response = session.get(
        urljoin(NGA_BASE_URL, relative_url),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": cookie,
            "Referer": referer,
        },
        timeout=timeout,
    )
    if response.status_code in {401, 403}:
        raise NGAAuthError(f"NGA 返回 HTTP {response.status_code}；Cookie 可能已失效。")
    response.raise_for_status()
    try:
        payload = response.json()
    except (requests.exceptions.JSONDecodeError, json.JSONDecodeError, ValueError):
        repaired = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r"\\\\", response.text)
        try:
            payload = json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise NGAError(f"NGA JSON 无法解析，响应可能被截断：{relative_url}") from exc
    if not isinstance(payload, dict):
        raise NGAError("NGA JSON 返回结构异常。")
    if payload.get("error"):
        raise NGAError(f"NGA JSON 返回错误：{relative_url}")
    return payload


def _get_html(
    session: requests.Session,
    relative_url: str,
    *,
    cookie: str,
    timeout: float,
    referer: str,
) -> str:
    response = session.get(
        urljoin(NGA_BASE_URL, relative_url),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": cookie,
            "Referer": referer,
        },
        timeout=timeout,
    )
    if response.status_code in {401, 403}:
        raise NGAAuthError(f"NGA 返回 HTTP {response.status_code}，Cookie 可能已经失效。")
    response.raise_for_status()
    return _decode_html(response.content, response.headers.get("content-type", ""))


def _extract_replies(data: dict[str, object], window_start: str, window_end: str) -> dict[str, NGAReply]:
    users = data.get("__U") or {}
    user_map = users if isinstance(users, dict) else {}
    rows = data.get("__R") or {}
    raw_rows = list(rows.values()) if isinstance(rows, dict) else list(rows) if isinstance(rows, list) else []
    merged: list[dict[str, object]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        merged.append(row)
        hot = row.get("hotreply")
        if isinstance(hot, list):
            merged.extend(item for item in hot if isinstance(item, dict))
    result: dict[str, NGAReply] = {}
    for row in merged:
        posted_at = _timestamp_text(row.get("postdate"))
        if not _in_window(posted_at, window_start, window_end):
            continue
        pid = str(row.get("pid") or f"floor-{row.get('lou', 0)}")
        author_id = str(row.get("authorid", ""))
        user = user_map.get(author_id)
        if user is None and author_id.isdigit():
            user = user_map.get(int(author_id))
        author = str(user.get("username", "")) if isinstance(user, dict) else author_id
        result[pid] = NGAReply(
            pid=pid,
            floor=int(row.get("lou") or 0),
            author=author,
            author_id=author_id,
            posted_at=posted_at,
            score=int(row.get("score") or 0),
            content=_clean_post_text(str(row.get("content", "")), limit=1200),
        )
    return result


def _reply_page_bounds(data: dict[str, object]) -> tuple[str, str] | None:
    rows = data.get("__R") or {}
    raw_rows = list(rows.values()) if isinstance(rows, dict) else list(rows) if isinstance(rows, list) else []
    timestamps = [
        _timestamp_text(row.get("postdate"))
        for row in raw_rows
        if isinstance(row, dict) and _timestamp_text(row.get("postdate"))
    ]
    if not timestamps:
        return None
    return min(timestamps), max(timestamps)


def _reply_bounds(replies: tuple[NGAReply, ...]) -> tuple[str, str] | None:
    timestamps = [reply.posted_at for reply in replies if reply.posted_at]
    if not timestamps:
        return None
    return min(timestamps), max(timestamps)


def _parse_author_thread_replies(html: str, author_id: str) -> tuple[NGAReply, ...]:
    parser = _AuthorReplyHTMLParser(author_id)
    parser.feed(html)
    parser.close()
    return parser.replies


def _positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _clean_post_text(value: str, *, limit: int) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"\[(?:img|url|attach)[^\]]*\].*?\[/(?:img|url|attach)\]", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[/?(?:b|i|u|color|size|quote|collapse|table|tr|td)[^\]]*\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\[pid=[^\]]+\]Reply\[/pid\]\s*Post by [^(]+\([^)]*\)\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _timestamp_text(value: object) -> str:
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            return datetime.fromtimestamp(float(value)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, OverflowError, ValueError):
            return str(value)
    return str(value or "")


def _in_window(value: str, start_at: str, end_at: str) -> bool:
    return bool(value) and start_at <= value <= end_at


def parse_board_topics(html: str) -> list[NGATopic]:
    parser = _TopicTableParser()
    parser.feed(html)
    parser.close()
    return parser.topics


def _decode_html(content: bytes, content_type: str) -> str:
    candidates: list[str] = []
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    if match:
        candidates.append(match.group(1))
    head = content[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset=[\"']?([\w-]+)", head, re.IGNORECASE)
    if match:
        candidates.append(match.group(1))
    candidates.extend(["gb18030", "utf-8"])
    for encoding in _unique(candidates):
        try:
            return content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.lower()
        if normalized not in seen:
            seen.add(normalized)
            result.append(item)
    return result


@dataclass
class _Anchor:
    href: str
    text_parts: list[str]

    @property
    def text(self) -> str:
        return _clean_text(" ".join(self.text_parts))


class _AuthorReplyHTMLParser(HTMLParser):
    def __init__(self, expected_author_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.expected_author_id = expected_author_id
        self._current_floor: int | None = None
        self._pid_by_floor: dict[int, str] = {}
        self._author_by_floor: dict[int, str] = {}
        self._date_parts: dict[int, list[str]] = {}
        self._content_parts: dict[int, list[str]] = {}
        self._date_floor: int | None = None
        self._content_floor: int | None = None
        self._content_depth = 0

    @property
    def replies(self) -> tuple[NGAReply, ...]:
        result: list[NGAReply] = []
        for floor, parts in self._content_parts.items():
            author_id = self._author_by_floor.get(floor, self.expected_author_id)
            if author_id != self.expected_author_id:
                continue
            posted_at = _clean_text(" ".join(self._date_parts.get(floor, [])))
            if len(posted_at) == 16:
                posted_at += ":00"
            pid = self._pid_by_floor.get(floor, f"floor-{floor}")
            content = _clean_post_text("".join(parts), limit=1200)
            result.append(
                NGAReply(
                    pid=pid,
                    floor=floor,
                    author=author_id,
                    author_id=author_id,
                    posted_at=posted_at,
                    score=0,
                    content=content,
                )
            )
        return tuple(sorted(result, key=lambda item: (item.posted_at, item.floor)))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id") or ""
        container_match = re.fullmatch(r"postcontainer(\d+)", element_id)
        if container_match:
            self._current_floor = int(container_match.group(1))
        pid_match = re.fullmatch(r"pid(\d+)Anchor", element_id)
        if pid_match and self._current_floor is not None:
            self._pid_by_floor[self._current_floor] = pid_match.group(1)
        author_match = re.fullmatch(r"postauthor(\d+)", element_id)
        if author_match:
            uid_match = re.search(r"(?:^|[?&])uid=(\d+)", attributes.get("href") or "")
            if uid_match:
                self._author_by_floor[int(author_match.group(1))] = uid_match.group(1)
        date_match = re.fullmatch(r"postdate(\d+)", element_id)
        if date_match:
            self._date_floor = int(date_match.group(1))
            self._date_parts.setdefault(self._date_floor, [])
        content_match = re.fullmatch(r"postcontent(\d+)", element_id)
        if content_match:
            self._content_floor = int(content_match.group(1))
            self._content_depth = 1
            self._content_parts.setdefault(self._content_floor, [])
        elif self._content_floor is not None:
            self._content_depth += 1
        if tag.lower() == "br" and self._content_floor is not None:
            self._content_parts[self._content_floor].append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._date_floor is not None and tag.lower() == "span":
            self._date_floor = None
        if self._content_floor is not None:
            self._content_depth -= 1
            if self._content_depth <= 0:
                self._content_floor = None
                self._content_depth = 0
        if tag.lower() == "td":
            self._current_floor = None

    def handle_data(self, data: str) -> None:
        if self._date_floor is not None:
            self._date_parts[self._date_floor].append(data)
        if self._content_floor is not None:
            self._content_parts[self._content_floor].append(data)


class _TopicTableParser(HTMLParser):
    _THREAD_RE = re.compile(r"(?:^|/)read\.php\?tid=(\d+)(?:&|$)", re.IGNORECASE)

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.topics: list[NGATopic] = []
        self._seen: set[str] = set()
        self._row_depth = 0
        self._row_text: list[str] = []
        self._anchors: list[_Anchor] = []
        self._current_anchor: _Anchor | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name == "tr":
            if self._row_depth == 0:
                self._row_text = []
                self._anchors = []
            self._row_depth += 1
        if name == "a" and self._row_depth:
            href = dict(attrs).get("href") or ""
            self._current_anchor = _Anchor(href=href, text_parts=[])

    def handle_data(self, data: str) -> None:
        if not self._row_depth:
            return
        self._row_text.append(data)
        if self._current_anchor is not None:
            self._current_anchor.text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name == "a" and self._current_anchor is not None:
            self._anchors.append(self._current_anchor)
            self._current_anchor = None
        if name == "tr" and self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0:
                self._finish_row()

    def _finish_row(self) -> None:
        row_text = _clean_text(" ".join(self._row_text))
        candidates: list[tuple[str, _Anchor]] = []
        reply_counts: dict[str, list[int]] = {}
        for anchor in self._anchors:
            match = self._THREAD_RE.search(anchor.href)
            if not match:
                continue
            thread_id = match.group(1)
            has_page = re.search(r"(?:[?&])page=", anchor.href, re.IGNORECASE) is not None
            if anchor.text.isdigit() and not has_page:
                reply_counts.setdefault(thread_id, []).append(int(anchor.text))
            if has_page or anchor.text.isdigit() or anchor.text in {"刚才", "NGA股票版"}:
                continue
            if len(anchor.text) >= 2:
                candidates.append((thread_id, anchor))
        for thread_id, anchor in candidates:
            if thread_id in self._seen:
                continue
            self._seen.add(thread_id)
            self.topics.append(
                NGATopic(
                    thread_id=thread_id,
                    title=anchor.text,
                    url=urljoin(NGA_BASE_URL, anchor.href),
                    replies=max(reply_counts.get(thread_id, [0])),
                    row_text=row_text,
                )
            )


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
