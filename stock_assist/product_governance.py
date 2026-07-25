"""Bounded product-experiment governance for InsightRadar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any

from stock_assist.paths import CONFIG_DIR, PROJECT_ROOT


DEFAULT_GOVERNANCE_PATH = CONFIG_DIR / "product_governance.json"
DEFAULT_FEATURE_PATH = PROJECT_ROOT / "feature_list.json"
VALID_LOOP_STAGES = {"observe", "explain", "decide", "verify", "governance"}
REQUIRED_EXPERIMENT_FIELDS = (
    "feature_id",
    "problem",
    "loop_stage",
    "baseline",
    "outcome_metric",
    "smallest_experiment",
    "safety_boundaries",
    "kill_criterion",
    "review_date",
)
REQUIRED_TEXT_FIELDS = tuple(
    field for field in REQUIRED_EXPERIMENT_FIELDS if field != "safety_boundaries"
)


@dataclass(frozen=True)
class Experiment:
    feature_id: str
    problem: str
    loop_stage: str
    baseline: str
    outcome_metric: str
    smallest_experiment: str
    safety_boundaries: tuple[str, ...]
    kill_criterion: str
    review_date: date


@dataclass(frozen=True)
class GovernanceSnapshot:
    max_active_experiments: int
    max_queued_experiments: int
    active_experiments: tuple[Experiment, ...]
    queued_experiments: tuple[Experiment, ...]

    @property
    def remaining_queue_slots(self) -> int:
        return max(0, self.max_queued_experiments - len(self.queued_experiments))


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _feature_statuses(path: Path) -> dict[str, str]:
    payload = _read_object(path)
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{path} must contain a features list")
    return {
        str(item["id"]): str(item.get("status", "unknown"))
        for item in features
        if isinstance(item, dict) and item.get("id")
    }


def _parse_experiment(raw: object, location: str) -> Experiment:
    if not isinstance(raw, dict):
        raise ValueError(f"{location} must be an object")
    missing = [field for field in REQUIRED_EXPERIMENT_FIELDS if not raw.get(field)]
    if missing:
        raise ValueError(f"{location} missing required fields: {', '.join(missing)}")
    invalid_text = [
        field
        for field in REQUIRED_TEXT_FIELDS
        if not isinstance(raw[field], str) or not raw[field].strip()
    ]
    if invalid_text:
        raise ValueError(
            f"{location} fields must be non-empty strings: {', '.join(invalid_text)}"
        )
    loop_stage = str(raw["loop_stage"])
    if loop_stage not in VALID_LOOP_STAGES:
        raise ValueError(f"{location} has invalid loop_stage {loop_stage}")
    boundaries = raw["safety_boundaries"]
    if not isinstance(boundaries, list) or not boundaries or not all(
        isinstance(item, str) and item.strip() for item in boundaries
    ):
        raise ValueError(f"{location} safety_boundaries must be a non-empty string list")
    review_date_text = raw["review_date"]
    if len(review_date_text) != 10 or review_date_text[4] != "-" or review_date_text[7] != "-":
        raise ValueError(f"{location} review_date must use YYYY-MM-DD")
    try:
        review_date = date.fromisoformat(review_date_text)
    except ValueError as exc:
        raise ValueError(f"{location} review_date must use YYYY-MM-DD") from exc
    return Experiment(
        feature_id=str(raw["feature_id"]),
        problem=str(raw["problem"]),
        loop_stage=loop_stage,
        baseline=str(raw["baseline"]),
        outcome_metric=str(raw["outcome_metric"]),
        smallest_experiment=str(raw["smallest_experiment"]),
        safety_boundaries=tuple(str(item) for item in boundaries),
        kill_criterion=str(raw["kill_criterion"]),
        review_date=review_date,
    )


def load_governance_snapshot(
    config_path: Path = DEFAULT_GOVERNANCE_PATH,
    feature_path: Path = DEFAULT_FEATURE_PATH,
) -> GovernanceSnapshot:
    payload = _read_object(config_path)
    if payload.get("schema_version") != "insightradar-product-governance/v1":
        raise ValueError("unsupported product governance schema_version")
    limits = payload.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("product governance limits must be an object")
    max_active = limits.get("max_active_experiments")
    max_queued = limits.get("max_queued_experiments")
    if type(max_active) is not int or type(max_queued) is not int:
        raise ValueError("product governance limits must use integers")
    if max_active != 1:
        raise ValueError("max_active_experiments must equal 1")
    if max_queued != 2:
        raise ValueError("max_queued_experiments must equal 2")
    active_raw = payload.get("active_experiments", [])
    queued_raw = payload.get("queued_experiments", [])
    if not isinstance(active_raw, list) or not isinstance(queued_raw, list):
        raise ValueError("experiment collections must be lists")
    if len(active_raw) > max_active:
        raise ValueError("active experiment limit exceeded")
    if len(queued_raw) > max_queued:
        raise ValueError("queued experiment limit exceeded")
    active = tuple(
        _parse_experiment(item, f"active_experiments[{index}]")
        for index, item in enumerate(active_raw)
    )
    queued = tuple(
        _parse_experiment(item, f"queued_experiments[{index}]")
        for index, item in enumerate(queued_raw)
    )
    statuses = _feature_statuses(feature_path)
    seen: set[str] = set()
    for experiment in (*active, *queued):
        if experiment.feature_id in seen:
            raise ValueError(f"duplicate governed feature {experiment.feature_id}")
        seen.add(experiment.feature_id)
        if experiment.feature_id not in statuses:
            raise ValueError(f"unknown feature {experiment.feature_id}")
        if statuses[experiment.feature_id] == "pass":
            raise ValueError(
                f"completed feature {experiment.feature_id} cannot remain governed"
            )
    return GovernanceSnapshot(max_active, max_queued, active, queued)


def governance_markdown_lines(snapshot: GovernanceSnapshot) -> list[str]:
    lines = [
        f"活跃实验 {len(snapshot.active_experiments)}/{snapshot.max_active_experiments}",
        f"排队实验 {len(snapshot.queued_experiments)}/{snapshot.max_queued_experiments}",
        "实验状态只能由负责人或主 Agent 在明确批准后修改；evolve 只提供候选。",
    ]
    for experiment in snapshot.active_experiments:
        lines.append(
            f"{experiment.feature_id} 进行中：{experiment.problem}；复核日 "
            f"{experiment.review_date.isoformat()}；终止条件：{experiment.kill_criterion}"
        )
    for experiment in snapshot.queued_experiments:
        lines.append(
            f"{experiment.feature_id} 待负责人启动：{experiment.smallest_experiment}；复核日 "
            f"{experiment.review_date.isoformat()}；终止条件：{experiment.kill_criterion}"
        )
    return lines
