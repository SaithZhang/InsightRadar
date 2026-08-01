"""Local JSONL archive for minute bars and point-in-time quotes."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable

from stock_assist.intraday.contracts import MinuteBar, PointQuote, contract_dict
from stock_assist.paths import DATA_DIR


DEFAULT_INTRADAY_ROOT = DATA_DIR / "intraday"


class MinuteArchive:
    """Persist provider observations by trade date and symbol.

    The interface is intentionally small: write immutable provider rows, then
    read one day with an optional point-in-time cutoff.  Rules never call a
    market provider directly.
    """

    def __init__(self, root: Path = DEFAULT_INTRADAY_ROOT) -> None:
        self.root = root

    def write_bars(self, bars: Iterable[MinuteBar]) -> list[Path]:
        groups: dict[tuple[date, str, str], list[MinuteBar]] = defaultdict(list)
        for bar in bars:
            groups[(bar.timestamp.date(), _slug(bar.source), bar.symbol)].append(bar)
        paths: list[Path] = []
        for (trade_date, provider, symbol), rows in sorted(groups.items()):
            path = self._bar_path(trade_date, provider, symbol)
            content = "".join(
                json.dumps(contract_dict(item), ensure_ascii=False, sort_keys=True) + "\n"
                for item in sorted(rows, key=lambda item: item.timestamp)
            )
            _atomic_write(path, content)
            paths.append(path)
        return paths

    def write_quotes(self, quotes: Iterable[PointQuote]) -> list[Path]:
        groups: dict[tuple[date, str], list[PointQuote]] = defaultdict(list)
        for quote in quotes:
            groups[(quote.timestamp.date(), _slug(quote.source))].append(quote)
        paths: list[Path] = []
        for (trade_date, provider), rows in sorted(groups.items()):
            path = self.root / "quotes" / trade_date.isoformat() / f"{provider}.jsonl"
            content = "".join(
                json.dumps(contract_dict(item), ensure_ascii=False, sort_keys=True) + "\n"
                for item in sorted(rows, key=lambda item: (item.timestamp, item.symbol))
            )
            _atomic_write(path, content)
            paths.append(path)
        return paths

    def read_bars(
        self,
        trade_date: date,
        *,
        symbols: Iterable[str] | None = None,
        through: datetime | None = None,
    ) -> dict[str, list[MinuteBar]]:
        wanted = {str(item).upper() for item in symbols} if symbols is not None else None
        result: dict[str, list[MinuteBar]] = defaultdict(list)
        day_root = self.root / "minute" / trade_date.isoformat()
        if not day_root.exists():
            return {}
        for path in sorted(day_root.glob("*/*.jsonl")):
            symbol = path.stem.upper()
            if wanted is not None and symbol not in wanted:
                continue
            for item in _jsonl_rows(path):
                bar = _bar_from_dict(item)
                if through is None or bar.timestamp <= through:
                    result[symbol].append(bar)
        return {
            symbol: sorted(rows, key=lambda item: item.timestamp)
            for symbol, rows in result.items()
        }

    def read_quotes(
        self,
        trade_date: date,
        *,
        through: datetime | None = None,
    ) -> list[PointQuote]:
        rows: list[PointQuote] = []
        day_root = self.root / "quotes" / trade_date.isoformat()
        if not day_root.exists():
            return rows
        for path in sorted(day_root.glob("*.jsonl")):
            for item in _jsonl_rows(path):
                quote = _quote_from_dict(item)
                if through is None or quote.timestamp <= through:
                    rows.append(quote)
        return sorted(rows, key=lambda item: (item.timestamp, item.symbol))

    def available_dates(self) -> tuple[date, ...]:
        root = self.root / "minute"
        if not root.exists():
            return ()
        result: list[date] = []
        for item in root.iterdir():
            try:
                result.append(date.fromisoformat(item.name))
            except ValueError:
                continue
        return tuple(sorted(result))

    def _bar_path(self, trade_date: date, provider: str, symbol: str) -> Path:
        return self.root / "minute" / trade_date.isoformat() / provider / f"{symbol.upper()}.jsonl"


def _bar_from_dict(item: dict[str, object]) -> MinuteBar:
    timestamp = datetime.fromisoformat(str(item["timestamp"]))
    return MinuteBar(
        symbol=str(item["symbol"]).upper(),
        timestamp=timestamp,
        open=float(item["open"]),
        high=float(item["high"]),
        low=float(item["low"]),
        close=float(item["close"]),
        volume=float(item["volume"]),
        amount=float(item["amount"]),
        source_time=datetime.fromisoformat(str(item.get("source_time") or timestamp.isoformat())),
        fetched_at=datetime.fromisoformat(str(item["fetched_at"])),
        source=str(item["source"]),
    )


def _quote_from_dict(item: dict[str, object]) -> PointQuote:
    timestamp = datetime.fromisoformat(str(item["timestamp"]))
    return PointQuote(
        symbol=str(item["symbol"]).upper(),
        timestamp=timestamp,
        price=float(item["price"]),
        pre_close=_optional_float(item.get("pre_close")),
        open=_optional_float(item.get("open")),
        high=_optional_float(item.get("high")),
        low=_optional_float(item.get("low")),
        volume=_optional_float(item.get("volume")),
        amount=_optional_float(item.get("amount")),
        source_time=datetime.fromisoformat(str(item.get("source_time") or timestamp.isoformat())),
        fetched_at=datetime.fromisoformat(str(item["fetched_at"])),
        source=str(item["source"]),
        phase=str(item.get("phase") or ""),
    )


def _jsonl_rows(path: Path) -> Iterable[dict[str, object]]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            yield item


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def _slug(value: str) -> str:
    clean = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in clean.split("-") if part) or "unknown"


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
