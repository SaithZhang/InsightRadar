"""Bounded, public-safe Harness trace recording and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Callable, Mapping, TextIO

from stock_assist.harness_eval.models import (
    FailureClass,
    MAX_TRACE_EVENTS,
    PrivacyClass,
    TRACE_SCHEMA_VERSION,
)
from stock_assist.harness_eval.validation import (
    has_valid_unicode,
    identifier_error,
    json_tree_error,
    public_material_error,
    read_bounded_bytes,
    reference_error,
)


ALLOWED_EVENT_TYPES = frozenset(
    {
        "run_started",
        "context_loaded",
        "memory_retrieved",
        "tool_requested",
        "tool_completed",
        "checkpoint_saved",
        "checkpoint_restored",
        "verification_result",
        "policy_blocked",
        "human_correction",
        "failure_classified",
        "run_completed",
    }
)
TRACE_FIELDS = (
    "schema_version",
    "run_id",
    "sequence",
    "event_type",
    "occurred_at",
    "privacy_class",
    "payload",
)
VALID_TOOL_IDS = frozenset({"read_project_files", "write_runtime_artifacts"})
MAX_FILE_BYTES = 128 * 1024
MAX_LINE_BYTES = 8 * 1024
MAX_EVENTS = MAX_TRACE_EVENTS
MAX_PAYLOAD_DEPTH = 4
MAX_CONTAINER_ITEMS = 32
MAX_STRING_LENGTH = 256
MAX_NUMERIC_MAGNITUDE = 1_000_000
RUN_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
WINDOWS_ABSOLUTE = re.compile(r"(?i)[a-z]:[\\/]")


@dataclass(frozen=True)
class TraceEvent:
    schema_version: str
    run_id: str
    sequence: int
    event_type: str
    occurred_at: str
    privacy_class: str
    payload: Mapping[str, object]


def _has_valid_unicode(value: str) -> bool:
    return has_valid_unicode(value)


def _validate_json_tree(value: object, location: str) -> str | None:
    """Validate JSON scalars and bounds iteratively before any recursive work."""
    return json_tree_error(
        value,
        location,
        max_depth=MAX_PAYLOAD_DEPTH,
        max_items=MAX_CONTAINER_ITEMS,
        max_containers=MAX_CONTAINER_ITEMS,
        max_string_length=MAX_STRING_LENGTH,
        max_numeric_magnitude=MAX_NUMERIC_MAGNITUDE,
    )


def _defense_error(value: object, location: str = "payload") -> str | None:
    """Defense in depth for material that must never appear in any payload."""
    del location
    return public_material_error(value)


def _identifier_error(value: object, name: str) -> str | None:
    return identifier_error(value, name)


def _reference_error(value: object, name: str) -> str | None:
    return reference_error(value, name)


def _exact_fields(payload: dict[str, object], fields: frozenset[str]) -> str | None:
    missing = sorted(fields - payload.keys())
    unknown = sorted(payload.keys() - fields)
    if missing:
        return "missing payload field"
    if unknown:
        return "unknown payload field"
    return None


def _reference_list_error(value: object, name: str) -> str | None:
    if not isinstance(value, list) or len(value) > 16:
        return f"{name} must be a bounded reference list"
    for item in value:
        error = _reference_error(item, name)
        if error:
            return error
    return None


def _identifier_list_error(value: object, name: str) -> str | None:
    if not isinstance(value, list) or len(value) > 16:
        return f"{name} must be a bounded identifier list"
    for item in value:
        error = _identifier_error(item, name)
        if error:
            return error
    return None


def _enum_error(value: object, name: str, values: frozenset[str]) -> str | None:
    if not isinstance(value, str) or value not in values:
        return f"{name} has an invalid value"
    return None


def _payload_schema_error(event_type: str, payload: dict[str, object]) -> str | None:
    schemas: dict[str, frozenset[str]] = {
        "run_started": frozenset({"task_id"}),
        "context_loaded": frozenset({"starting_state_refs", "context_refs", "memory_refs"}),
        "memory_retrieved": frozenset({"memory_ref", "status"}),
        "tool_requested": frozenset({"tool_id", "status"}),
        "tool_completed": frozenset({"tool_id", "status", "result_code"}),
        "checkpoint_saved": frozenset({"checkpoint_ref"}),
        "checkpoint_restored": frozenset({"verified_steps"}),
        "verification_result": frozenset({"check", "status"}),
        "policy_blocked": frozenset({"policy_id", "status"}),
        "human_correction": frozenset({"correction_ref", "category"}),
        "failure_classified": frozenset({"failure_class"}),
        "run_completed": frozenset({"status"}),
    }
    fields_error = _exact_fields(payload, schemas[event_type])
    if fields_error:
        return fields_error
    if event_type == "run_started":
        return _identifier_error(payload["task_id"], "task_id")
    if event_type == "context_loaded":
        return (
            _reference_list_error(payload["starting_state_refs"], "starting_state_refs")
            or _reference_list_error(payload["context_refs"], "context_refs")
            or _reference_list_error(payload["memory_refs"], "memory_refs")
        )
    if event_type == "memory_retrieved":
        return _reference_error(payload["memory_ref"], "memory_ref") or _enum_error(payload["status"], "status", frozenset({"found", "missing", "stale"}))
    if event_type in {"tool_requested", "tool_completed"}:
        tool = payload["tool_id"]
        if not isinstance(tool, str) or tool not in VALID_TOOL_IDS:
            return "tool_id has an invalid value"
        if event_type == "tool_requested":
            return _enum_error(payload["status"], "status", frozenset({"requested"}))
        return _enum_error(payload["status"], "status", frozenset({"completed", "failed", "blocked"})) or _enum_error(
            payload["result_code"], "result_code", frozenset({"ok", "no_output", "timeout", "malformed", "denied"})
        )
    if event_type == "checkpoint_saved":
        return _reference_error(payload["checkpoint_ref"], "checkpoint_ref")
    if event_type == "checkpoint_restored":
        return _identifier_list_error(payload["verified_steps"], "verified_steps")
    if event_type == "verification_result":
        return _identifier_error(payload["check"], "check") or _enum_error(payload["status"], "status", frozenset({"pass", "fail", "blocked"}))
    if event_type == "policy_blocked":
        return _identifier_error(payload["policy_id"], "policy_id") or _enum_error(payload["status"], "status", frozenset({"blocked"}))
    if event_type == "human_correction":
        return _reference_error(payload["correction_ref"], "correction_ref") or _enum_error(
            payload["category"], "category", frozenset({"scope", "privacy", "format", "evidence"})
        )
    if event_type == "failure_classified":
        return _enum_error(payload["failure_class"], "failure_class", frozenset(item.value for item in FailureClass))
    return _enum_error(payload["status"], "status", frozenset({"pass", "fail", "blocked"}))


def _payload_error(event_type: str, payload: object) -> str | None:
    if not isinstance(payload, dict):
        return "payload must be an object"
    bounds_error = _validate_json_tree(payload, "payload")
    if bounds_error:
        return bounds_error
    defense_error = _defense_error(payload)
    if defense_error:
        return defense_error
    return _payload_schema_error(event_type, payload)


def _reject_nonstandard_json(value: str) -> None:
    raise ValueError("non-standard JSON value")


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not _has_valid_unicode(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(timezone.utc)


def _run_id_error(run_id: object) -> str | None:
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        return "run_id must be a bounded opaque identifier"
    if _defense_error(run_id, "run_id"):
        return "run_id contains forbidden material"
    return None


def _validate_lifecycle(event_type: str, state: str) -> tuple[str, str | None]:
    if state == "new":
        if event_type != "run_started":
            return state, "first event must be run_started"
        return "active", None
    if state == "completed":
        return state, "event after run_completed"
    if event_type == "run_started":
        return state, "run_started may occur only once"
    if event_type == "run_completed":
        return "completed", None
    return state, None


def _resolve_trace_path(runtime_artifact_root: Path, relative_trace_path: Path) -> tuple[Path, Path]:
    root = Path(runtime_artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve(strict=True)
    raw_path = str(relative_trace_path)
    target = Path(relative_trace_path)
    if (
        not raw_path
        or target.is_absolute()
        or raw_path.startswith(("\\\\", "//", "\\\\?\\", "\\\\.\\"))
        or WINDOWS_ABSOLUTE.search(raw_path)
        or any(part in {"", ".", ".."} for part in target.parts)
    ):
        raise ValueError("relative trace path is required")
    resolved_target = (resolved_root / target).resolve(strict=False)
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("relative trace path escapes runtime artifact root") from exc
    return resolved_root, resolved_target


class TraceWriter:
    """Create exactly one bounded JSONL trace beneath an explicit runtime root."""

    def __init__(
        self,
        runtime_artifact_root: Path,
        relative_trace_path: Path,
        run_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        run_error = _run_id_error(run_id)
        if run_error:
            raise ValueError(run_error)
        self.runtime_artifact_root, self.path = _resolve_trace_path(runtime_artifact_root, relative_trace_path)
        if os.path.lexists(self.path):
            raise ValueError("trace target already exists")
        self.run_id = run_id
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sequence = 0
        self._state = "new"
        self._last_timestamp: datetime | None = None
        self._handle: TextIO | None = None
        self._identity: tuple[int, int] | None = None
        self._closed = False

    def __enter__(self) -> "TraceWriter":
        if self._closed:
            raise ValueError("trace writer is closed")
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        if self._handle is not None:
            self._handle.flush()
            self._handle.close()
        self._closed = True

    def _verify_target_identity(self) -> None:
        if self._handle is None or self._identity is None:
            return
        try:
            descriptor = os.fstat(self._handle.fileno())
            path_status = os.lstat(self.path)
        except (OSError, ValueError) as exc:
            raise ValueError("trace target identity changed") from exc
        if (
            not stat.S_ISREG(descriptor.st_mode)
            or descriptor.st_nlink != 1
            or (descriptor.st_dev, descriptor.st_ino) != self._identity
            or not stat.S_ISREG(path_status.st_mode)
            or path_status.st_nlink != 1
            or (path_status.st_dev, path_status.st_ino) != self._identity
        ):
            raise ValueError("trace target identity changed")

    def _create_target(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = self.path.parent.resolve(strict=True)
        try:
            resolved_parent.relative_to(self.runtime_artifact_root)
        except ValueError as exc:
            raise ValueError("relative trace path escapes runtime artifact root") from exc
        try:
            handle = self.path.open("x", encoding="utf-8", newline="\n")
        except FileExistsError as exc:
            raise ValueError("trace target already exists") from exc
        try:
            descriptor = os.fstat(handle.fileno())
            path_status = os.lstat(self.path)
            if (
                not stat.S_ISREG(descriptor.st_mode)
                or descriptor.st_nlink != 1
                or not stat.S_ISREG(path_status.st_mode)
                or path_status.st_nlink != 1
                or (descriptor.st_dev, descriptor.st_ino) != (path_status.st_dev, path_status.st_ino)
            ):
                raise ValueError("trace target identity changed")
        except Exception:
            handle.close()
            raise
        self._handle = handle
        self._identity = (descriptor.st_dev, descriptor.st_ino)

    def append(
        self,
        event_type: str,
        payload: dict[str, object],
        privacy_class: PrivacyClass,
    ) -> TraceEvent:
        if self._closed:
            raise ValueError("trace writer is closed")
        if self.sequence >= MAX_EVENTS:
            raise ValueError("trace exceeds maximum event count")
        if not isinstance(privacy_class, PrivacyClass):
            raise ValueError("privacy_class must be a PrivacyClass")
        if privacy_class is not PrivacyClass.PUBLIC:
            raise ValueError("v1 traces require public privacy class")
        if event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"unsupported trace event_type {event_type}")
        payload_error = _payload_error(event_type, payload)
        if payload_error:
            raise ValueError(payload_error)
        occurred = self.clock()
        if occurred.tzinfo is None or occurred.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        occurred = occurred.astimezone(timezone.utc)
        if self._last_timestamp is not None and occurred < self._last_timestamp:
            raise ValueError("timestamps must be non-decreasing")
        next_state, lifecycle_error = _validate_lifecycle(event_type, self._state)
        if lifecycle_error:
            raise ValueError(lifecycle_error)
        payload_copy = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        row = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "run_id": self.run_id,
            "sequence": self.sequence + 1,
            "event_type": event_type,
            "occurred_at": occurred.isoformat(),
            "privacy_class": privacy_class.value,
            "payload": payload_copy,
        }
        serialized = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(serialized.encode("utf-8")) > MAX_LINE_BYTES:
            raise ValueError("trace line exceeds maximum size")
        if self._handle is None:
            self._create_target()
        self._verify_target_identity()
        if self._handle is None:
            raise AssertionError("trace target handle is missing")
        self._handle.write(serialized + "\n")
        self._handle.flush()
        self.sequence = row["sequence"]
        self._state = next_state
        self._last_timestamp = occurred
        frozen_payload = _freeze(payload_copy)
        if not isinstance(frozen_payload, Mapping):
            raise AssertionError("validated trace payload must be a mapping")
        return TraceEvent(
            schema_version=TRACE_SCHEMA_VERSION,
            run_id=self.run_id,
            sequence=self.sequence,
            event_type=event_type,
            occurred_at=row["occurred_at"],
            privacy_class=privacy_class.value,
            payload=frozen_payload,
        )


def validate_public_trace(path: Path, *, require_completed: bool = True) -> list[str]:
    """Return stable fail-closed errors for an untrusted public UTF-8 JSONL trace."""

    try:
        raw = read_bounded_bytes(path, MAX_FILE_BYTES, "trace")
    except ValueError as exc:
        return [str(exc).replace("maximum size", "maximum file size")]
    if not raw:
        return ["trace is empty"]
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return ["trace invalid utf-8"]
    if not text.endswith("\n"):
        return ["trace must end with a newline"]
    lines = text[:-1].split("\n")
    if not lines or lines == [""]:
        return ["trace is empty"]
    if len(lines) > MAX_EVENTS:
        return ["trace exceeds maximum event count"]

    errors: list[str] = []
    expected_run_id: str | None = None
    previous_timestamp: datetime | None = None
    lifecycle = "new"
    completed_count = 0
    for line_number, line in enumerate(lines, start=1):
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            errors.append(f"line {line_number}: trace line exceeds maximum size")
            continue
        try:
            row = json.loads(line, parse_constant=_reject_nonstandard_json, object_pairs_hook=_reject_duplicate_json_keys)
        except json.JSONDecodeError:
            errors.append(f"line {line_number}: invalid JSON")
            continue
        except ValueError as exc:
            if str(exc) == "duplicate JSON key":
                errors.append(f"line {line_number}: duplicate JSON key")
            elif str(exc) == "non-standard JSON value":
                errors.append(f"line {line_number}: non-standard JSON value")
            else:
                errors.append(f"line {line_number}: invalid JSON")
            continue
        except RecursionError:
            errors.append(f"line {line_number}: invalid JSON")
            continue
        if not isinstance(row, dict):
            errors.append(f"line {line_number}: trace event must be an object")
            continue
        envelope = dict(row)
        envelope["payload"] = None
        tree_error = _validate_json_tree(envelope, "trace event")
        if tree_error:
            errors.append(f"line {line_number}: {tree_error}")
            continue
        for field in TRACE_FIELDS:
            if field not in row:
                errors.append(f"line {line_number}: missing required trace field {field}")
        for field in row:
            if field not in TRACE_FIELDS:
                errors.append(f"line {line_number}: unknown trace field")
        if row.get("schema_version") != TRACE_SCHEMA_VERSION:
            errors.append(f"line {line_number}: unsupported trace schema_version")
        sequence = row.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0 or sequence > MAX_EVENTS:
            errors.append(f"line {line_number}: sequence must be a positive integer")
        if sequence != line_number:
            errors.append(f"line {line_number}: non-monotonic sequence")
        run_error = _run_id_error(row.get("run_id"))
        if run_error:
            errors.append(f"line {line_number}: {run_error}")
        elif expected_run_id is None:
            expected_run_id = row["run_id"]
        elif row["run_id"] != expected_run_id:
            errors.append(f"line {line_number}: inconsistent run_id")
        event_type = row.get("event_type")
        if event_type not in ALLOWED_EVENT_TYPES:
            errors.append(f"line {line_number}: unsupported trace event_type")
        timestamp = _parse_timestamp(row.get("occurred_at"))
        if timestamp is None:
            errors.append(f"line {line_number}: occurred_at must be an ISO-8601 UTC timestamp")
        elif previous_timestamp is not None and timestamp < previous_timestamp:
            errors.append(f"line {line_number}: timestamps must be non-decreasing")
        elif timestamp is not None:
            previous_timestamp = timestamp
        privacy = row.get("privacy_class")
        if privacy == PrivacyClass.SANITIZED.value:
            errors.append(f"line {line_number}: v1 traces require public privacy class")
        elif privacy != PrivacyClass.PUBLIC.value:
            errors.append(f"line {line_number}: privacy class is not public-exportable")
        if isinstance(event_type, str) and event_type in ALLOWED_EVENT_TYPES:
            next_lifecycle, lifecycle_error = _validate_lifecycle(event_type, lifecycle)
            if lifecycle_error:
                errors.append(f"line {line_number}: {lifecycle_error}")
            else:
                lifecycle = next_lifecycle
                if event_type == "run_completed":
                    completed_count += 1
        payload_error = _payload_error(event_type, row.get("payload")) if isinstance(event_type, str) and event_type in ALLOWED_EVENT_TYPES else "payload must be an object"
        if payload_error:
            errors.append(f"line {line_number}: invalid payload: {payload_error}")
    if lifecycle == "new":
        errors.append("trace must start with one run_started event")
    if require_completed and (completed_count != 1 or lifecycle != "completed"):
        errors.append("trace must end with one run_completed event")
    return errors
