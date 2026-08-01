"""Validation and loading for the bounded intraday theme universe."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from stock_assist.paths import CONFIG_DIR


DEFAULT_UNIVERSE_PATH = CONFIG_DIR / "intraday_universe.json"
REQUIRED_THEME_IDS = {
    "ai_hardware_semiconductor",
    "communication_cpo",
    "pcb",
    "ai_software_apps",
    "robot",
    "innovation_drug",
    "nonferrous",
    "power",
    "dividend",
    "bank",
    "brokerage",
    "defense",
    "consumer",
}


def load_intraday_universe(path: Path | None = None) -> dict[str, object]:
    actual = path or DEFAULT_UNIVERSE_PATH
    payload = json.loads(actual.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("intraday universe must be a JSON object")
    themes = payload.get("themes")
    if not isinstance(themes, list) or not 20 <= len(themes) <= 30:
        raise ValueError("intraday universe must contain 20-30 themes")
    ids: set[str] = set()
    for item in themes:
        if not isinstance(item, Mapping):
            raise ValueError("each intraday theme must be an object")
        theme_id = str(item.get("theme_id") or "")
        if not theme_id or theme_id in ids:
            raise ValueError(f"invalid or duplicate theme_id: {theme_id or 'missing'}")
        ids.add(theme_id)
        if not str(item.get("representative_etf") or ""):
            raise ValueError(f"{theme_id} is missing representative_etf")
        symbols = item.get("representative_symbols")
        if not isinstance(symbols, list) or not 2 <= len(symbols) <= 5:
            raise ValueError(f"{theme_id} must contain 2-5 representative symbols")
    missing = sorted(REQUIRED_THEME_IDS - ids)
    if missing:
        raise ValueError("intraday universe is missing required themes: " + ", ".join(missing))
    return payload


def universe_symbols(payload: Mapping[str, object]) -> tuple[str, ...]:
    symbols: list[str] = [str(payload.get("benchmark") or "000300.SH")]
    themes = payload.get("themes")
    for item in themes if isinstance(themes, list) else []:
        if not isinstance(item, Mapping):
            continue
        symbols.append(str(item.get("representative_etf") or ""))
        raw = item.get("representative_symbols")
        if isinstance(raw, list):
            symbols.extend(str(symbol) for symbol in raw if str(symbol))
    return tuple(dict.fromkeys(symbol.upper() for symbol in symbols if symbol))
