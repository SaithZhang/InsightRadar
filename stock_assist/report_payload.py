"""Shared InsightRadar report payload helpers."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from stock_assist.branding import PRODUCT_NAME


SCHEMA_VERSION = "insight-payload/v1"


def create_report_payload(
    *,
    kind: str,
    workflow: str,
    title: str,
    generated_at: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Create the common cross-client payload envelope."""

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "workflow": workflow,
        "product": PRODUCT_NAME,
        "title": title,
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
    }
    payload.update(fields)
    return payload


def first_markdown_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def markdown_sections(content: str) -> list[dict[str, Any]]:
    """Parse top-level Markdown sections into client-readable blocks."""

    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    used_ids: set[str] = set()

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current = {
                "id": _unique_id(_slug(line[3:].strip()), used_ids, len(sections) + 1),
                "title": line[3:].strip(),
                "level": 2,
                "body": [],
                "items": [],
            }
            sections.append(current)
            continue
        if current is None or not line.strip() or line.startswith("# "):
            continue
        current["body"].append(line)
        if line.lstrip().startswith("- "):
            current["items"].append(line.lstrip()[2:].strip())

    return sections


def section_items(
    sections: list[dict[str, Any]],
    title_fragments: tuple[str, ...],
    *,
    fallback_first: bool = False,
) -> list[str]:
    for section in sections:
        title = str(section.get("title", ""))
        if any(fragment in title for fragment in title_fragments):
            items = section.get("items", [])
            return [str(item) for item in items] if isinstance(items, list) else []
    if fallback_first and sections:
        items = sections[0].get("items", [])
        return [str(item) for item in items] if isinstance(items, list) else []
    return []


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def _unique_id(base: str, used: set[str], index: int) -> str:
    candidate = base if base != "section" else f"section-{index}"
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate
