"""Strict bounded loading for versioned Harness task manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_assist.harness_eval.models import (
    AcceptanceCheck,
    PrivacyClass,
    StartingState,
    TASK_SCHEMA_VERSION,
    TaskBudget,
    TaskManifest,
)
from stock_assist.harness_eval.validation import (
    has_trade_authority_lexeme,
    identifier_error,
    json_tree_error,
    public_material_error,
    read_bounded_bytes,
    reference_error,
)


MAX_MANIFEST_BYTES = 64 * 1024
MAX_REFERENCES = 16
MAX_TOOLS = 8
MAX_ACCEPTANCE_CHECKS = 16
MAX_STEPS = 64
MAX_TOOL_CALLS = 64
MAX_ELAPSED_SECONDS = 86_400
REQUIRED_FIELDS = (
    "schema_version",
    "task_id",
    "title",
    "goal",
    "starting_state",
    "context_refs",
    "memory_refs",
    "allowed_tools",
    "budget",
    "expected_artifacts",
    "acceptance_checks",
    "privacy_class",
)
STARTING_STATE_FIELDS = ("references",)
BUDGET_FIELDS = ("max_steps", "max_tool_calls", "max_elapsed_seconds")
ACCEPTANCE_CHECK_FIELDS = ("id", "kind", "target", "expected")
VALID_CHECK_KINDS = frozenset({"file_exists", "text_contains"})
VALID_ALLOWED_TOOLS = frozenset({"read_project_files", "write_runtime_artifacts"})
PUBLIC_PROJECT_REFERENCE_PREFIXES = (
    ".codex/agents/",
    "configs/",
    "docs/",
    "stock_assist/",
    "tests/",
)
PUBLIC_PROJECT_ROOT_FILES = frozenset(
    {
        "AGENTS.md",
        "PROJECT_MEMORY.md",
        "CURRENT_STATE.md",
        "feature_list.json",
        "progress.md",
        "session-handoff.md",
    }
)
APPROVED_PUBLIC_TRADE_ACCEPTANCE = (
    "trade",
    "text_contains",
    "harness-smoke.md",
    "\u4ea4\u6613\u6743\u9650\uff1anone",
)


def _non_empty_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _strict_object(raw: object, required_fields: tuple[str, ...], name: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be an object")
    missing = next((field for field in required_fields if field not in raw), None)
    if missing is not None:
        if name == "manifest":
            raise ValueError(f"missing required field {missing}")
        raise ValueError(f"missing {name} field {missing}")
    if any(field not in required_fields for field in raw):
        raise ValueError(f"unknown {name} field")
    return raw


def _string_tuple(
    raw: dict[str, Any],
    key: str,
    *,
    allow_empty: bool = False,
    limit: int = MAX_REFERENCES,
) -> tuple[str, ...]:
    value = raw.get(key)
    if (
        not isinstance(value, list)
        or len(value) > limit
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ValueError(f"{key} must be a bounded string list")
    if not allow_empty and not value:
        raise ValueError(f"{key} must not be empty")
    result = tuple(item.strip() for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{key} contains duplicates")
    return result


def _reference_tuple(
    raw: dict[str, Any],
    key: str,
    *,
    allow_empty: bool = False,
    public_project: bool = False,
) -> tuple[str, ...]:
    values = _string_tuple(raw, key, allow_empty=allow_empty)
    if any(reference_error(value, key) for value in values):
        raise ValueError(f"{key} must contain bounded relative references")
    if public_project and any(
        value not in PUBLIC_PROJECT_ROOT_FILES
        and not value.startswith(PUBLIC_PROJECT_REFERENCE_PREFIXES)
        for value in values
    ):
        raise ValueError(f"{key} must contain bounded public project references")
    return values


def _allowed_tools(raw: dict[str, Any]) -> tuple[str, ...]:
    tools = _string_tuple(raw, "allowed_tools", limit=MAX_TOOLS)
    if any(tool not in VALID_ALLOWED_TOOLS for tool in tools):
        raise ValueError("unsupported allowed tool")
    return tools


def _has_forbidden_public_free_text(payload: dict[str, Any]) -> bool:
    for field in ("title", "goal"):
        value = payload.get(field)
        if isinstance(value, str) and has_trade_authority_lexeme(value):
            return True
    checks = payload.get("acceptance_checks")
    if not isinstance(checks, list):
        return False
    for check in checks:
        if not isinstance(check, dict):
            continue
        expected = check.get("expected")
        if not isinstance(expected, str) or not has_trade_authority_lexeme(expected):
            continue
        declaration = tuple(
            check.get(field) for field in ("id", "kind", "target", "expected")
        )
        if declaration != APPROVED_PUBLIC_TRADE_ACCEPTANCE:
            return True
    return False


def _positive_bounded_integer(raw: dict[str, Any], key: str, maximum: int) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > maximum:
        raise ValueError(f"budget {key} must be a positive integer within bound")
    return value


def _reject_nonstandard_json(_: str) -> None:
    raise ValueError("non-standard JSON value")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode_manifest(path: Path) -> dict[str, Any]:
    raw = read_bounded_bytes(path, MAX_MANIFEST_BYTES, "task manifest")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("task manifest is not valid UTF-8") from exc
    try:
        payload = json.loads(
            text,
            parse_constant=_reject_nonstandard_json,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("task manifest is not valid JSON") from exc
    except RecursionError as exc:
        raise ValueError("task manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("manifest must be an object")
    bounds_error = json_tree_error(payload, "manifest")
    if bounds_error:
        raise ValueError(bounds_error)
    return payload


def load_task_manifest(path: Path) -> TaskManifest:
    payload = _decode_manifest(Path(path))
    raw_privacy = payload.get("privacy_class")
    try:
        privacy_class = PrivacyClass(raw_privacy)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid privacy_class") from exc
    if privacy_class in {PrivacyClass.PUBLIC, PrivacyClass.SANITIZED}:
        if public_material_error(payload, reject_trade_lexemes=False):
            raise ValueError("manifest contains forbidden public material")
        if _has_forbidden_public_free_text(payload):
            raise ValueError("manifest contains forbidden public material")
    if privacy_class is PrivacyClass.SANITIZED:
        raise ValueError("sanitized manifest requires a verified transformation record")
    if privacy_class is PrivacyClass.SECRET:
        raise ValueError("secret manifests cannot be stored")

    raw = _strict_object(payload, REQUIRED_FIELDS, "manifest")
    if raw["schema_version"] != TASK_SCHEMA_VERSION:
        raise ValueError("unsupported task schema_version")
    task_id = _non_empty_string(raw, "task_id")
    if identifier_error(task_id, "task_id"):
        raise ValueError("task_id must be a bounded ASCII identifier")

    starting_raw = _strict_object(raw["starting_state"], STARTING_STATE_FIELDS, "starting_state")
    public_project_refs = privacy_class in {PrivacyClass.PUBLIC, PrivacyClass.SANITIZED}
    starting_state = StartingState(
        references=_reference_tuple(
            starting_raw,
            "references",
            public_project=public_project_refs,
        )
    )

    budget_raw = _strict_object(raw["budget"], BUDGET_FIELDS, "budget")
    budget = TaskBudget(
        max_steps=_positive_bounded_integer(budget_raw, "max_steps", MAX_STEPS),
        max_tool_calls=_positive_bounded_integer(budget_raw, "max_tool_calls", MAX_TOOL_CALLS),
        max_elapsed_seconds=_positive_bounded_integer(
            budget_raw, "max_elapsed_seconds", MAX_ELAPSED_SECONDS
        ),
    )

    checks_raw = raw["acceptance_checks"]
    if not isinstance(checks_raw, list) or not checks_raw or len(checks_raw) > MAX_ACCEPTANCE_CHECKS:
        raise ValueError("acceptance_checks must be a bounded non-empty list")
    checks: list[AcceptanceCheck] = []
    check_ids: set[str] = set()
    for item in checks_raw:
        check = _strict_object(item, ACCEPTANCE_CHECK_FIELDS, "acceptance_check")
        check_id = _non_empty_string(check, "id")
        if identifier_error(check_id, "acceptance check id") or check_id in check_ids:
            raise ValueError("acceptance check id is invalid or duplicated")
        check_ids.add(check_id)
        kind = _non_empty_string(check, "kind")
        if kind not in VALID_CHECK_KINDS:
            raise ValueError("acceptance check kind is invalid")
        target = _non_empty_string(check, "target")
        if reference_error(target, "acceptance target"):
            raise ValueError("acceptance target must be a bounded relative reference")
        checks.append(
            AcceptanceCheck(
                id=check_id,
                kind=kind,
                target=target,
                expected=_non_empty_string(check, "expected"),
            )
        )

    return TaskManifest(
        schema_version=TASK_SCHEMA_VERSION,
        task_id=task_id,
        title=_non_empty_string(raw, "title"),
        goal=_non_empty_string(raw, "goal"),
        starting_state=starting_state,
        context_refs=_reference_tuple(
            raw,
            "context_refs",
            public_project=public_project_refs,
        ),
        memory_refs=_reference_tuple(
            raw,
            "memory_refs",
            allow_empty=True,
            public_project=public_project_refs,
        ),
        allowed_tools=_allowed_tools(raw),
        budget=budget,
        expected_artifacts=_reference_tuple(raw, "expected_artifacts"),
        acceptance_checks=tuple(checks),
        privacy_class=privacy_class,
    )
