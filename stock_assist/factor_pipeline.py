"""Low-cost daily training pipeline for the personal A-share factor model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd

from stock_assist.factor_lab import (
    FACTOR_COLUMNS,
    FactorLabConfig,
    build_factor_panel,
    fit_ridge,
    load_price_history,
)
from stock_assist.paths import PROJECT_ROOT
from stock_assist.universe import resolve_universe


OBSERVATION_COLUMNS = (
    "universe_id",
    "universe_manifest_hash",
    "date",
    "code",
    "close",
    *FACTOR_COLUMNS,
    "label",
    "label_train",
)
MODEL_FEATURES = tuple(name for name in FACTOR_COLUMNS if name != "amihud_20")


@dataclass(frozen=True)
class PromotionGates:
    min_validation_dates: int = 20
    min_rank_ic: float = 0.02
    min_positive_ic_rate: float = 0.52
    min_net_top_bottom: float = 0.0
    min_quintile_monotonicity: float = 0.50
    max_condition_number: float = 50.0
    max_vif: float = 10.0


@dataclass(frozen=True)
class FactorPipelineConfig:
    factor_config_path: Path
    data_dir: Path
    validation_dates: int = 60
    gates: PromotionGates = PromotionGates()

    @classmethod
    def load(cls, path: Path) -> "FactorPipelineConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        factor_path = _project_path(raw.get("factor_config", "configs/factor_lab.json"))
        data_dir = _project_path(raw.get("data_dir", "data/factor_pipeline"))
        gate_raw = raw.get("promotion_gates", {})
        return cls(
            factor_config_path=factor_path,
            data_dir=data_dir,
            validation_dates=int(raw.get("validation_dates", 60)),
            gates=PromotionGates(
                min_validation_dates=int(gate_raw.get("min_validation_dates", 20)),
                min_rank_ic=float(gate_raw.get("min_rank_ic", 0.02)),
                min_positive_ic_rate=float(gate_raw.get("min_positive_ic_rate", 0.52)),
                min_net_top_bottom=float(gate_raw.get("min_net_top_bottom", 0.0)),
                min_quintile_monotonicity=float(gate_raw.get("min_quintile_monotonicity", 0.50)),
                max_condition_number=float(gate_raw.get("max_condition_number", 50.0)),
                max_vif=float(gate_raw.get("max_vif", 10.0)),
            ),
        )


def run_factor_pipeline(config_path: Path, panel_override: pd.DataFrame | None = None) -> dict[str, Any]:
    """Ingest observations, mature labels, train a challenger, and conditionally promote it."""

    started = time.perf_counter()
    pipeline = FactorPipelineConfig.load(config_path)
    factor_config = FactorLabConfig.load(pipeline.factor_config_path)
    universe = resolve_universe(factor_config)
    pipeline.data_dir.mkdir(parents=True, exist_ok=True)
    model_dir = pipeline.data_dir / "models"
    model_dir.mkdir(exist_ok=True)

    data_gaps: list[str] = []
    if panel_override is None:
        prices, data_gaps = load_price_history(factor_config, universe)
        panel = build_factor_panel(prices, factor_config.benchmark, factor_config.horizon_days, universe)
        source = str(prices.attrs.get("source", "unknown"))
    else:
        panel = panel_override.copy()
        panel["universe_id"] = universe.universe_id
        panel["universe_manifest_hash"] = universe.manifest_hash
        source = "test_override"

    incoming = _observation_frame(panel)
    observation_path = pipeline.data_dir / "observations.csv"
    previous = _read_observations(observation_path, universe.universe_id, universe.manifest_hash)
    observations, ingest = merge_observations(previous, incoming)
    _write_observations(observation_path, observations)

    candidate = train_challenger(observations, factor_config, pipeline)
    data_hash = _training_hash(observations)
    model_spec = {
        "model_type": "ridge_v1",
        "feature_names": list(MODEL_FEATURES),
        "ridge_alpha": factor_config.ridge_alpha,
        "horizon_days": factor_config.horizon_days,
        "universe_id": universe.universe_id,
        "universe_manifest_hash": universe.manifest_hash,
    }
    model_hash = hashlib.sha256((data_hash + json.dumps(model_spec, sort_keys=True)).encode("utf-8")).hexdigest()
    as_of = str(observations["date"].max().date())
    version = f"{as_of.replace('-', '')}-{model_hash[:10]}"
    candidate.update(
        {
            "schema_version": "factor-model/v2",
            "version": version,
            "model_type": "ridge_v1",
            "as_of": as_of,
            "data_hash": data_hash,
            "feature_names": list(MODEL_FEATURES),
            "excluded_features": {"amihud_20": "collinear_with_liquidity_in_mvp"},
            "horizon_days": factor_config.horizon_days,
            "universe_name": factor_config.universe_name,
            "universe_type": factor_config.universe_type,
            "universe_id": universe.universe_id,
            "universe_mode": universe.mode,
            "universe_manifest_hash": universe.manifest_hash,
        }
    )

    candidate_path = model_dir / f"{version}.json"
    _write_json(candidate_path, candidate)
    champion_path = pipeline.data_dir / "champion.json"
    champion_before = _read_json(champion_path)
    promotion = decide_promotion(candidate, champion_before)
    if promotion["promoted"]:
        _write_json(champion_path, candidate)
    champion_after = candidate if promotion["promoted"] else champion_before
    registry_path = pipeline.data_dir / "registry.jsonl"
    _append_registry_once(registry_path, candidate, promotion)

    result = {
        "as_of": as_of,
        "source": source,
        "universe_id": universe.universe_id,
        "universe_mode": universe.mode,
        "universe_manifest_hash": universe.manifest_hash,
        "model_type": "ridge_v1",
        "candidate_version": version,
        "candidate_path": str(candidate_path),
        "champion_version": champion_after.get("version") if champion_after else None,
        "promotion": promotion,
        "ingest": ingest,
        "observation_rows": int(len(observations)),
        "mature_rows": int(observations["label_train"].notna().sum()),
        "pending_rows": int(observations["label_train"].isna().sum()),
        "candidate": candidate,
        "ranking_mode": "champion" if champion_after else "diagnostic_candidate",
        "latest_ranking": score_latest(observations, champion_after or candidate, factor_config.top_n),
        "data_gaps": [
            *data_gaps,
            *(["当前股票池为显式个人研究池，尚无历史时点成分，存在生存者偏差。"] if not universe.is_point_in_time else []),
            "尚未加入行业/市值中性化、ST/新股/涨跌停成交约束和真实冲击成本。",
        ],
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "estimated_training_cost_cny": 0.0,
    }
    return result


def merge_observations(previous: pd.DataFrame, incoming: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Upsert point-in-time rows while preserving already matured labels."""

    old = _ensure_lineage(previous.copy())
    new = _ensure_lineage(incoming.copy())
    key_columns = ["universe_id", "date", "code"]
    old_keys = set(map(tuple, old[key_columns].itertuples(index=False, name=None))) if not old.empty else set()
    old_labels = (
        old.set_index(key_columns)["label_train"].to_dict() if not old.empty else {}
    )
    if old.empty:
        merged = new
    else:
        old_indexed = old.set_index(key_columns)
        new_indexed = new.set_index(key_columns)
        merged = new_indexed.combine_first(old_indexed).reset_index()
    merged = merged.loc[:, OBSERVATION_COLUMNS].sort_values(["universe_id", "date", "code"]).drop_duplicates(key_columns)
    new_keys = set(map(tuple, new[key_columns].itertuples(index=False, name=None)))
    matured = 0
    for row in merged.itertuples():
        key = (row.universe_id, row.date, row.code)
        if key in old_labels and pd.isna(old_labels[key]) and pd.notna(row.label_train):
            matured += 1
    return merged.reset_index(drop=True), {
        "new_rows": len(new_keys - old_keys),
        "matured_labels": matured,
        "updated_rows": len(new_keys & old_keys),
    }


def train_challenger(
    observations: pd.DataFrame,
    factor_config: FactorLabConfig,
    pipeline: FactorPipelineConfig,
) -> dict[str, Any]:
    labeled = observations.dropna(subset=[*MODEL_FEATURES, "label", "label_train"]).copy()
    dates = list(pd.Index(labeled["date"].drop_duplicates()).sort_values())
    embargo = factor_config.horizon_days
    validation_count = min(pipeline.validation_dates, max(0, len(dates) - factor_config.min_train_days - embargo))
    if validation_count < pipeline.gates.min_validation_dates:
        return _empty_candidate("insufficient_validation_dates", len(dates), validation_count)
    validation_dates = dates[-validation_count:]
    train_dates = dates[: -(validation_count + embargo)]
    train = labeled[labeled["date"].isin(train_dates)]
    validation = labeled[labeled["date"].isin(validation_dates)]
    if train["date"].nunique() < factor_config.min_train_days:
        return _empty_candidate("insufficient_training_dates", len(dates), validation_count)

    validation_weights, validation_intercept, condition, vif = fit_ridge(train, factor_config.ridge_alpha, MODEL_FEATURES)
    metrics = evaluate_model(validation, validation_weights, validation_intercept, factor_config)
    metrics["condition_number"] = _finite(condition)
    metrics["factor_vif"] = {name: _finite(value) for name, value in vif.items()}
    gates = evaluate_gates(metrics, pipeline.gates)

    final_dates = dates[-factor_config.train_window_days :]
    final_train = labeled[labeled["date"].isin(final_dates)]
    weights, intercept, final_condition, final_vif = fit_ridge(final_train, factor_config.ridge_alpha, MODEL_FEATURES)
    return {
        "training_status": "trained",
        "validation_status": "passed" if all(gates.values()) else "failed",
        "training_dates": int(final_train["date"].nunique()),
        "training_rows": int(len(final_train)),
        "validation_dates": validation_count,
        "validation_start": str(pd.Timestamp(validation_dates[0]).date()),
        "validation_end": str(pd.Timestamp(validation_dates[-1]).date()),
        "ridge_alpha": factor_config.ridge_alpha,
        "intercept": float(intercept),
        "weights": {name: float(value) for name, value in zip(MODEL_FEATURES, weights)},
        "condition_number": _finite(final_condition),
        "factor_vif": {name: _finite(value) for name, value in final_vif.items()},
        "validation_metrics": metrics,
        "gate_results": gates,
        "promotion_score": _promotion_score(metrics),
    }


def evaluate_model(
    validation: pd.DataFrame,
    weights: np.ndarray,
    intercept: float,
    config: FactorLabConfig,
) -> dict[str, Any]:
    rows: list[dict[str, float]] = []
    previous: set[str] = set()
    for _, group in validation.groupby("date", sort=True):
        current = group.dropna(subset=[*MODEL_FEATURES, "label"]).copy()
        if len(current) < max(5, config.top_n):
            continue
        current["score"] = current.loc[:, MODEL_FEATURES].to_numpy(float) @ weights + intercept
        current = current.sort_values("score", ascending=False)
        selected = set(current.head(config.top_n)["code"].astype(str))
        turnover = 1.0 if not previous else 1.0 - len(selected & previous) / config.top_n
        previous = selected
        buckets = [current.iloc[pos] for pos in np.array_split(np.arange(len(current)), 5)]
        bucket_returns = [float(bucket["label"].mean()) for bucket in buckets]
        rows.append(
            {
                "rank_ic": float(current["score"].corr(current["label"], method="spearman")),
                "top_bottom": bucket_returns[0] - bucket_returns[-1],
                "net_top_bottom": bucket_returns[0] - bucket_returns[-1] - turnover * config.transaction_cost_bps / 10000,
                "turnover": turnover,
                **{f"q{index + 1}": value for index, value in enumerate(bucket_returns)},
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"period_count": 0}
    quintiles = [float(frame[f"q{i}"].mean()) for i in range(1, 6)]
    monotonicity = float(pd.Series([5, 4, 3, 2, 1]).corr(pd.Series(quintiles), method="spearman"))
    return {
        "period_count": int(len(frame)),
        "rank_ic_mean": float(frame["rank_ic"].mean()),
        "rank_ic_positive_rate": float((frame["rank_ic"] > 0).mean()),
        "top_bottom_mean": float(frame["top_bottom"].mean()),
        "net_top_bottom_mean": float(frame["net_top_bottom"].mean()),
        "average_turnover": float(frame["turnover"].mean()),
        "quintile_average_returns": quintiles,
        "quintile_monotonicity": monotonicity,
    }


def evaluate_gates(metrics: dict[str, Any], gates: PromotionGates) -> dict[str, bool]:
    vif_values = [value for value in metrics.get("factor_vif", {}).values() if value is not None]
    max_vif = max(vif_values, default=float("inf"))
    return {
        "enough_validation_dates": int(metrics.get("period_count", 0)) >= gates.min_validation_dates,
        "rank_ic": float(metrics.get("rank_ic_mean", -999)) >= gates.min_rank_ic,
        "positive_ic_rate": float(metrics.get("rank_ic_positive_rate", -999)) >= gates.min_positive_ic_rate,
        "net_top_bottom": float(metrics.get("net_top_bottom_mean", -999)) > gates.min_net_top_bottom,
        "quintile_monotonicity": float(metrics.get("quintile_monotonicity", -999)) >= gates.min_quintile_monotonicity,
        "condition_number": metrics.get("condition_number") is not None
        and float(metrics["condition_number"]) < gates.max_condition_number,
        "vif": max_vif < gates.max_vif,
    }


def decide_promotion(candidate: dict[str, Any], champion: dict[str, Any] | None) -> dict[str, Any]:
    if candidate.get("validation_status") != "passed":
        return {"promoted": False, "reason": "candidate_failed_hard_gates"}
    if not champion:
        return {"promoted": True, "reason": "first_candidate_to_pass_hard_gates"}
    candidate_score = float(candidate.get("promotion_score", -999))
    champion_score = float(champion.get("promotion_score", -999))
    if candidate_score > champion_score:
        return {"promoted": True, "reason": "candidate_score_improved", "previous_score": champion_score}
    return {"promoted": False, "reason": "champion_retained", "champion_score": champion_score}


def score_latest(observations: pd.DataFrame, model: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
    weights_map = model.get("weights", {})
    if not weights_map or model.get("intercept") is None:
        return []
    latest_date = observations["date"].max()
    feature_names = tuple(str(name) for name in model.get("feature_names", MODEL_FEATURES))
    latest = observations[observations["date"] == latest_date].dropna(subset=list(feature_names)).copy()
    weights = np.array([weights_map[name] for name in feature_names], dtype=float)
    latest["score"] = latest.loc[:, feature_names].to_numpy(float) @ weights + float(model["intercept"])
    latest = latest.sort_values("score", ascending=False).head(max(10, top_n))
    return [
        {"rank": index + 1, "code": str(row.code), "score": float(row.score), "close": float(row.close)}
        for index, row in enumerate(latest.itertuples())
    ]


def _observation_frame(panel: pd.DataFrame) -> pd.DataFrame:
    result = _ensure_lineage(panel.copy()).loc[:, OBSERVATION_COLUMNS]
    result["date"] = pd.to_datetime(result["date"])
    return result.dropna(subset=[*FACTOR_COLUMNS]).sort_values(["date", "code"])


def _read_observations(path: Path, universe_id: str, manifest_hash: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=OBSERVATION_COLUMNS)
    frame = pd.read_csv(path, parse_dates=["date"])
    if "universe_id" not in frame:
        frame["universe_id"] = universe_id
    if "universe_manifest_hash" not in frame:
        frame["universe_manifest_hash"] = manifest_hash
    return frame.loc[:, OBSERVATION_COLUMNS]


def _write_observations(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(".tmp")
    frame.to_csv(temporary, index=False, date_format="%Y-%m-%d")
    temporary.replace(path)


def _empty_candidate(reason: str, training_dates: int, validation_dates: int) -> dict[str, Any]:
    return {
        "training_status": "not_trained",
        "validation_status": "insufficient_sample",
        "reason": reason,
        "training_dates": training_dates,
        "validation_dates": validation_dates,
        "weights": {},
        "intercept": None,
        "validation_metrics": {"period_count": validation_dates},
        "gate_results": {},
        "promotion_score": -999.0,
    }


def _promotion_score(metrics: dict[str, Any]) -> float:
    return float(metrics.get("rank_ic_mean", -999)) + 0.10 * float(metrics.get("net_top_bottom_mean", 0)) + 0.01 * float(
        metrics.get("quintile_monotonicity", 0)
    )


def _training_hash(frame: pd.DataFrame) -> str:
    mature = frame.dropna(subset=["label_train"]).loc[:, OBSERVATION_COLUMNS]
    content = mature.to_csv(index=False, date_format="%Y-%m-%d", float_format="%.10g")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _ensure_lineage(frame: pd.DataFrame) -> pd.DataFrame:
    if "universe_id" not in frame:
        frame["universe_id"] = "legacy_static"
    frame["universe_id"] = frame["universe_id"].fillna("legacy_static").astype(str)
    if "universe_manifest_hash" not in frame:
        frame["universe_manifest_hash"] = ""
    frame["universe_manifest_hash"] = frame["universe_manifest_hash"].fillna("").astype(str)
    return frame


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _append_registry_once(path: Path, candidate: dict[str, Any], promotion: dict[str, Any]) -> None:
    existing_versions: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing_versions.add(str(json.loads(line).get("version")))
    if candidate["version"] in existing_versions:
        return
    record = {
        "version": candidate["version"],
        "as_of": candidate["as_of"],
        "model_type": candidate["model_type"],
        "validation_status": candidate["validation_status"],
        "promotion": promotion,
        "validation_metrics": candidate.get("validation_metrics", {}),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def _finite(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path
