"""Atomic, goal-bound checkpoints for long-running Harness tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from stock_assist.harness_eval.models import CHECKPOINT_SCHEMA_VERSION, MAX_TRACE_EVENTS
from stock_assist.harness_eval.validation import identifier_error, read_bounded_bytes, reference_error


CHECKPOINT_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "task_id",
        "goal_hash",
        "sequence",
        "verified_steps",
        "pending_steps",
        "artifact_hashes",
        "created_at",
    }
)
MAX_CHECKPOINT_BYTES = 32 * 1024
MAX_CHECKPOINT_DEPTH = 4
MAX_CONTAINER_ITEMS = 32
MAX_STEPS = 32
MAX_ARTIFACT_HASHES = 16
MAX_STRING_LENGTH = 256
RUN_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Checkpoint:
    schema_version: str
    run_id: str
    task_id: str
    goal_hash: str
    sequence: int
    verified_steps: tuple[str, ...]
    pending_steps: tuple[str, ...]
    artifact_hashes: dict[str, str]
    created_at: str


def goal_digest(goal: str) -> str:
    """Return the stable SHA-256 identifier for a goal without storing its text."""

    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must be a non-empty string")
    return hashlib.sha256(goal.encode("utf-8")).hexdigest()


def _reject_nonstandard_json(value: str) -> None:
    raise ValueError("non-standard JSON value")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _require_identifier(value: object, field: str, pattern: re.Pattern[str] = IDENTIFIER) -> str:
    if pattern is RUN_ID:
        invalid = not isinstance(value, str) or not RUN_ID.fullmatch(value)
    else:
        invalid = identifier_error(value, field) is not None
    if invalid:
        raise ValueError(f"checkpoint {field} is invalid")
    assert isinstance(value, str)
    return value


def _require_reference(value: object, field: str) -> str:
    if reference_error(value, field):
        raise ValueError(f"checkpoint {field} is invalid")
    assert isinstance(value, str)
    return value


def _require_steps(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_STEPS or not all(isinstance(item, str) for item in value):
        raise ValueError(f"checkpoint {field} must be a string list")
    steps = tuple(_require_identifier(item, field) for item in value)
    if len(steps) != len(set(steps)):
        raise ValueError(f"checkpoint {field} contains duplicates")
    return steps


def _require_artifact_hashes(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > MAX_ARTIFACT_HASHES:
        raise ValueError("checkpoint artifact_hashes must be an object")
    hashes: dict[str, str] = {}
    for reference, digest in value.items():
        checked_reference = _require_reference(reference, "artifact reference")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError("checkpoint artifact hash is invalid")
        hashes[checked_reference] = digest
    return hashes


def _require_timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > MAX_STRING_LENGTH:
        raise ValueError("checkpoint created_at is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("checkpoint created_at is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("checkpoint created_at is invalid")
    return value


def _tree_error(value: object) -> str | None:
    """Bound an untrusted decoded JSON tree without recursive traversal."""

    stack: list[tuple[object, int]] = [(value, 0)]
    containers = 0
    while stack:
        current, depth = stack.pop()
        if depth > MAX_CHECKPOINT_DEPTH:
            return "checkpoint exceeds maximum depth"
        if isinstance(current, dict):
            containers += 1
            if containers > MAX_CONTAINER_ITEMS or len(current) > MAX_CONTAINER_ITEMS:
                return "checkpoint exceeds maximum container size"
            for key, child in current.items():
                if not isinstance(key, str) or len(key) > MAX_STRING_LENGTH:
                    return "checkpoint has invalid key"
                stack.append((child, depth + 1))
            continue
        if isinstance(current, list):
            containers += 1
            if containers > MAX_CONTAINER_ITEMS or len(current) > MAX_CONTAINER_ITEMS:
                return "checkpoint exceeds maximum container size"
            stack.extend((child, depth + 1) for child in current)
            continue
        if isinstance(current, str) and len(current) > MAX_STRING_LENGTH:
            return "checkpoint has oversized string"
    return None


def _validate_checkpoint(checkpoint: Checkpoint) -> Checkpoint:
    if checkpoint.schema_version != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("unsupported checkpoint schema_version")
    _require_identifier(checkpoint.run_id, "run_id", RUN_ID)
    _require_identifier(checkpoint.task_id, "task_id")
    if not isinstance(checkpoint.goal_hash, str) or not SHA256.fullmatch(checkpoint.goal_hash):
        raise ValueError("checkpoint goal_hash is invalid")
    if (
        isinstance(checkpoint.sequence, bool)
        or not isinstance(checkpoint.sequence, int)
        or checkpoint.sequence < 0
        or checkpoint.sequence > MAX_TRACE_EVENTS
    ):
        raise ValueError("checkpoint sequence is invalid")
    _require_steps(list(checkpoint.verified_steps), "verified_steps")
    _require_steps(list(checkpoint.pending_steps), "pending_steps")
    _require_artifact_hashes(checkpoint.artifact_hashes)
    _require_timestamp(checkpoint.created_at)
    return checkpoint


def save_checkpoint(checkpoint: Checkpoint, path: Path) -> None:
    """Atomically replace a validated checkpoint at its caller-owned runtime path."""

    _validate_checkpoint(checkpoint)
    payload = asdict(checkpoint)
    payload["verified_steps"] = list(checkpoint.verified_steps)
    payload["pending_steps"] = list(checkpoint.pending_steps)
    tree_error = _tree_error(payload)
    if tree_error:
        raise ValueError(tree_error)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if len(serialized.encode("utf-8")) > MAX_CHECKPOINT_BYTES:
        raise ValueError("checkpoint exceeds maximum size")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
    except OSError as exc:
        raise ValueError("checkpoint cannot be saved") from exc
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def load_checkpoint(path: Path, expected_task_id: str, expected_goal: str) -> Checkpoint:
    """Load a strict checkpoint only when its task and goal still match."""

    _require_identifier(expected_task_id, "task_id")
    expected_goal_hash = goal_digest(expected_goal)
    raw = read_bounded_bytes(path, MAX_CHECKPOINT_BYTES, "checkpoint")
    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            parse_constant=_reject_nonstandard_json,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except UnicodeDecodeError as exc:
        raise ValueError("checkpoint is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("checkpoint is not valid JSON") from exc
    except RecursionError as exc:
        raise ValueError("checkpoint is not valid JSON") from exc
    except ValueError as exc:
        if str(exc) in {"duplicate JSON key", "non-standard JSON value"}:
            raise
        raise ValueError("checkpoint is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("checkpoint must be an object")
    tree_error = _tree_error(payload)
    if tree_error:
        raise ValueError(tree_error)
    fields = set(payload)
    if fields - CHECKPOINT_FIELDS:
        raise ValueError("checkpoint has unknown field")
    if CHECKPOINT_FIELDS - fields:
        raise ValueError("checkpoint is missing required field")
    checkpoint = Checkpoint(
        schema_version=payload["schema_version"],
        run_id=payload["run_id"],
        task_id=payload["task_id"],
        goal_hash=payload["goal_hash"],
        sequence=payload["sequence"],
        verified_steps=_require_steps(payload["verified_steps"], "verified_steps"),
        pending_steps=_require_steps(payload["pending_steps"], "pending_steps"),
        artifact_hashes=_require_artifact_hashes(payload["artifact_hashes"]),
        created_at=_require_timestamp(payload["created_at"]),
    )
    _validate_checkpoint(checkpoint)
    if checkpoint.task_id != expected_task_id:
        raise ValueError("checkpoint task mismatch")
    if checkpoint.goal_hash != expected_goal_hash:
        raise ValueError("checkpoint goal drift detected")
    return checkpoint
