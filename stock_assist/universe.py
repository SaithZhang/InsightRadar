"""Point-in-time universe contracts for leakage-aware A-share research."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.paths import PROJECT_ROOT


MEMBERSHIP_COLUMNS = (
    "universe_id",
    "index_code",
    "code",
    "in_date",
    "out_date",
    "index_name",
    "source",
    "retrieved_at",
)


@dataclass(frozen=True)
class UniverseSpec:
    universe_id: str
    mode: str
    codes_union: tuple[str, ...]
    membership: pd.DataFrame
    manifest_hash: str
    membership_path: Path | None = None

    @property
    def is_point_in_time(self) -> bool:
        return self.mode == "point_in_time"


def resolve_universe(config: Any) -> UniverseSpec:
    """Resolve either a legacy static list or a versioned membership interval file."""

    mode = str(getattr(config, "universe_mode", "static_codes"))
    universe_id = str(getattr(config, "universe_id", "custom_pilot_v1"))
    if mode == "static_codes":
        codes = tuple(sorted({str(code) for code in getattr(config, "codes", ())}))
        if not codes:
            raise ValueError("Static universe requires at least one configured code.")
        manifest_hash = _hash_payload({"mode": mode, "universe_id": universe_id, "codes": codes})
        return UniverseSpec(universe_id, mode, codes, pd.DataFrame(columns=MEMBERSHIP_COLUMNS), manifest_hash)
    if mode != "point_in_time":
        raise ValueError(f"Unsupported universe_mode: {mode}")

    raw_path = getattr(config, "membership_path", None)
    if not raw_path:
        raise ValueError("Point-in-time universe requires membership_path.")
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    membership = load_membership(path, universe_id)
    codes = tuple(sorted(set(membership["code"].astype(str))))
    canonical = membership.loc[:, MEMBERSHIP_COLUMNS].copy()
    canonical["in_date"] = canonical["in_date"].dt.strftime("%Y-%m-%d")
    canonical["out_date"] = canonical["out_date"].dt.strftime("%Y-%m-%d").fillna("")
    manifest_hash = hashlib.sha256(
        canonical.sort_values(["code", "in_date", "out_date"]).to_csv(index=False).encode("utf-8")
    ).hexdigest()
    return UniverseSpec(universe_id, mode, codes, membership, manifest_hash, path)


def load_membership(path: Path, universe_id: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Universe membership file not found: {path}")
    frame = pd.read_csv(path, dtype=str)
    required = {"code", "in_date", "out_date"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Universe membership is missing columns: " + ", ".join(missing))
    result = frame.copy()
    if "universe_id" not in result:
        result["universe_id"] = universe_id
    result["universe_id"] = result["universe_id"].fillna(universe_id).astype(str)
    if set(result["universe_id"].dropna().unique()) != {universe_id}:
        raise ValueError(f"Membership file contains rows outside universe_id={universe_id}.")
    for column, default in {
        "index_code": "",
        "index_name": "",
        "source": "unknown",
        "retrieved_at": "",
    }.items():
        if column not in result:
            result[column] = default
        result[column] = result[column].fillna(default).astype(str)
    result["code"] = result["code"].astype(str)
    result["in_date"] = pd.to_datetime(result["in_date"], errors="coerce")
    result["out_date"] = pd.to_datetime(result["out_date"], errors="coerce")
    if result["in_date"].isna().any():
        raise ValueError("Universe membership contains invalid in_date values.")
    invalid = result["out_date"].notna() & (result["out_date"] <= result["in_date"])
    if invalid.any():
        raise ValueError("Universe membership contains out_date not later than in_date.")
    return (
        result.loc[:, MEMBERSHIP_COLUMNS]
        .sort_values(["code", "in_date", "out_date"])
        .drop_duplicates(["universe_id", "code", "in_date", "out_date"])
        .reset_index(drop=True)
    )


def apply_universe(panel: pd.DataFrame, universe: UniverseSpec) -> pd.DataFrame:
    """Attach lineage and filter rows by intervals after factors have been calculated."""

    result = panel.copy()
    if not universe.is_point_in_time:
        result["universe_id"] = universe.universe_id
        result["universe_manifest_hash"] = universe.manifest_hash
        return result

    membership = universe.membership.loc[:, ["code", "in_date", "out_date"]].copy()
    merged = result.merge(membership, on="code", how="inner", validate="many_to_many")
    active = (merged["date"] >= merged["in_date"]) & (
        merged["out_date"].isna() | (merged["date"] < merged["out_date"])
    )
    merged = merged.loc[active].copy()
    if merged.duplicated(["date", "code"]).any():
        raise ValueError("Overlapping membership intervals created duplicate date/code rows.")
    merged["universe_id"] = universe.universe_id
    merged["universe_manifest_hash"] = universe.manifest_hash
    return merged.sort_values(["date", "code"]).reset_index(drop=True)


def normalize_index_constituent(raw: Any, index_code: str, retrieved_at: str) -> pd.DataFrame:
    frame = raw.get(index_code) if isinstance(raw, dict) else raw
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError(f"AmazingData returned no index constituent rows for {index_code}.")
    renamed = frame.rename(
        columns={
            "INDEX_CODE": "index_code",
            "CON_CODE": "code",
            "INDATE": "in_date",
            "OUTDATE": "out_date",
            "INDEX_NAME": "index_name",
        }
    ).copy()
    missing = sorted({"index_code", "code", "in_date", "out_date", "index_name"} - set(renamed.columns))
    if missing:
        raise ValueError("AmazingData constituent response is missing columns: " + ", ".join(missing))
    renamed["universe_id"] = f"{index_code.lower().replace('.', '_')}_pit_v1"
    renamed["source"] = "amazingdata.get_index_constituent"
    renamed["retrieved_at"] = retrieved_at
    normalized = renamed.loc[:, MEMBERSHIP_COLUMNS].copy()
    normalized["in_date"] = pd.to_datetime(normalized["in_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    normalized["out_date"] = pd.to_datetime(normalized["out_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return normalized.sort_values(["code", "in_date", "out_date"]).reset_index(drop=True)


def sync_index_membership(index_code: str, output_path: Path) -> dict[str, Any]:
    """Fetch and atomically persist index membership intervals from AmazingData."""

    retrieved_at = pd.Timestamp.now(tz="Asia/Shanghai").isoformat()
    client = AmazingDataClient()
    try:
        raw = client.get_index_constituent([index_code])
    finally:
        client.logout()
    normalized = normalize_index_constituent(raw, index_code, retrieved_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    normalized.to_csv(temporary, index=False, encoding="utf-8")
    temporary.replace(output_path)
    universe_id = str(normalized.iloc[0]["universe_id"])
    membership = load_membership(output_path, universe_id)
    canonical = membership.loc[:, MEMBERSHIP_COLUMNS].copy()
    canonical["in_date"] = canonical["in_date"].dt.strftime("%Y-%m-%d")
    canonical["out_date"] = canonical["out_date"].dt.strftime("%Y-%m-%d").fillna("")
    manifest_hash = hashlib.sha256(canonical.to_csv(index=False).encode("utf-8")).hexdigest()
    return {
        "index_code": index_code,
        "universe_id": universe_id,
        "membership_path": str(output_path),
        "manifest_hash": manifest_hash,
        "interval_rows": int(len(normalized)),
        "unique_codes": int(normalized["code"].nunique()),
        "earliest_in_date": str(normalized["in_date"].min()),
        "open_intervals": int(normalized["out_date"].isna().sum()),
        "retrieved_at": retrieved_at,
        "source": "AmazingData.get_index_constituent",
        "data_gaps": [
            "指数权重/自由流通比例接口本次未纳入：近期空结果会触发SDK内部TRADE_DATE错误。",
            "成分数据可能被供应商事后修订；manifest_hash用于锁定本次研究版本。",
        ],
    }


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
