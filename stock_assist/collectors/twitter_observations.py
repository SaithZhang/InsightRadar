"""Convert raw Twitter/X captures into influencer observation records."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from stock_assist.collectors.twitter_cli import TWITTER_RAW_DIR
from stock_assist.paths import ensure_runtime_dirs
from stock_assist.workflows.influencer_skills import DEFAULT_OBSERVATIONS_PATH


HANDLE_ALIASES = {
    "aleabitoreddit": "X 白毛女 / Serenity",
}

KEYWORD_RULES = [
    {
        "needles": ["dram", "samsung"],
        "symbols": ["005930.KS"],
        "industries": ["半导体存储", "AI算力"],
        "themes": ["DRAM", "存储周期", "三星财报"],
    },
    {
        "needles": ["cpo"],
        "symbols": [],
        "industries": ["AI算力", "CPO", "光通信"],
        "themes": ["主题性抛售", "CPO延误", "机构反向交易"],
    },
    {
        "needles": ["compute"],
        "symbols": [],
        "industries": ["AI算力"],
        "themes": ["AI算力"],
    },
    {
        "needles": ["short", "wiped out", "betting against"],
        "symbols": [],
        "industries": ["宏观风险偏好"],
        "themes": ["short squeeze", "风险偏好"],
    },
    {
        "needles": ["glass", "tgv", "lide", "substrate"],
        "symbols": ["603773.SH", "000725.SZ", "301338.SZ"],
        "industries": ["玻璃基板", "先进封装", "AI算力"],
        "themes": ["TGV", "LIDE", "glass core substrate"],
    },
]


def sync_observations_from_twitter_raw(
    raw_path: Path | None = None,
    observations_path: Path = DEFAULT_OBSERVATIONS_PATH,
) -> Path:
    """Rebuild first-party observations derived from twitter-cli raw captures."""

    ensure_runtime_dirs()
    observations_path.parent.mkdir(exist_ok=True)
    existing_items = _load_existing_items(observations_path)
    payloads = _load_raw_payloads(raw_path)
    generated: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for tweet in payload.get("data", []):
            item = _tweet_to_observation(tweet)
            generated[item["id"]] = item

    manual_items = [item for item in existing_items if not str(item.get("id", "")).startswith("x-")]
    merged_items = [*manual_items, *generated.values()]
    with observations_path.open("w", encoding="utf-8", newline="\n") as file:
        for item in merged_items:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")
    return observations_path


def _load_raw_payloads(raw_path: Path | None) -> list[dict[str, Any]]:
    if raw_path is not None:
        paths = [raw_path]
    else:
        paths = sorted(TWITTER_RAW_DIR.glob("*.json")) if TWITTER_RAW_DIR.exists() else []
    payloads = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("ok") and isinstance(payload.get("data"), list):
            payloads.append(payload)
    return payloads


def _load_existing_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            items.append(item)
    return items


def _tweet_to_observation(tweet: dict[str, Any]) -> dict[str, Any]:
    author = tweet.get("author", {}) or {}
    handle = str(author.get("screenName", "")).lstrip("@")
    text = html.unescape(str(tweet.get("text", ""))).strip()
    symbols = _extract_symbols(text)
    industries, themes, mapped_symbols = _keyword_maps(text)
    symbols = _dedupe([*symbols, *mapped_symbols])
    tweet_id = str(tweet.get("id", ""))
    source_url = f"https://x.com/{handle}/status/{tweet_id}" if handle and tweet_id else ""
    metrics = tweet.get("metrics", {}) or {}
    return {
        "id": f"x-{tweet_id}",
        "source_post_id": tweet_id,
        "date": _tweet_date(tweet),
        "author": HANDLE_ALIASES.get(handle, f"X @{handle}" if handle else "X"),
        "source": "X",
        "source_url": source_url,
        "source_type": "first_party",
        "summary": _summarize_text(text),
        "symbols": symbols,
        "industries": industries,
        "themes": themes,
        "direction": _direction(text),
        "confidence": _confidence(metrics),
        "impact_horizon": "short",
        "status": "watching",
        "verification": _verification_items(symbols, industries, themes),
        "metrics": metrics,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }


def _tweet_date(tweet: dict[str, Any]) -> str:
    value = str(tweet.get("createdAtISO") or "")
    if value:
        return value[:10]
    local_value = str(tweet.get("createdAtLocal") or "")
    if local_value:
        return local_value[:10]
    return datetime.now().strftime("%Y-%m-%d")


def _summarize_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:260] + ("..." if len(compact) > 260 else "")


def _extract_symbols(text: str) -> list[str]:
    symbols = [
        match.rstrip(".,;:!?)]}").upper()
        for match in re.findall(r"\$([A-Za-z][A-Za-z0-9._-]*)", text)
    ]
    return _dedupe(symbols)


def _keyword_maps(text: str) -> tuple[list[str], list[str], list[str]]:
    lowered = text.lower()
    industries: list[str] = []
    themes: list[str] = []
    symbols: list[str] = []
    for rule in KEYWORD_RULES:
        if any(needle in lowered for needle in rule["needles"]):
            industries.extend(rule["industries"])
            themes.extend(rule["themes"])
            symbols.extend(rule["symbols"])
    return _dedupe(industries), _dedupe(themes), _dedupe(symbols)


def _direction(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["dumbest", "high confidence", "hiking", "most profitable"]):
        return "bullish"
    if any(term in lowered for term in ["selloff", "sells off"]) and "$" not in text:
        return "mixed"
    if "short" in lowered:
        return "mixed"
    return "neutral"


def _confidence(metrics: dict[str, Any]) -> str:
    views = _safe_int(metrics.get("views"))
    likes = _safe_int(metrics.get("likes"))
    if views >= 100_000 or likes >= 1_000:
        return "medium"
    return "low"


def _verification_items(symbols: list[str], industries: list[str], themes: list[str]) -> list[str]:
    checks = ["复核 X 原帖上下文和是否有后续修正"]
    if symbols:
        checks.append("映射到相关 A 股前先验证价格是否已充分反应")
    if industries or themes:
        checks.append("补产业链数据、公告和业绩验证")
    return checks


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
