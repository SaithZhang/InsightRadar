"""Versioned Agent Harness evaluation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


TASK_SCHEMA_VERSION = "insightradar-harness-task/v1"
TRACE_SCHEMA_VERSION = "insightradar-harness-trace/v1"
CHECKPOINT_SCHEMA_VERSION = "insightradar-harness-checkpoint/v1"
MAX_TRACE_EVENTS = 64


class PrivacyClass(str, Enum):
    PUBLIC = "public"
    SANITIZED = "sanitized"
    PRIVATE = "private"
    SECRET = "secret"


class FailureClass(str, Enum):
    CONTEXT_MISSING = "context_missing"
    CONTEXT_MISROUTED = "context_misrouted"
    STALE_MEMORY = "stale_memory"
    CONFLICTING_MEMORY = "conflicting_memory"
    INCORRECT_MEMORY_RECALL = "incorrect_memory_recall"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_PERMISSION_DENIED = "tool_permission_denied"
    TOOL_MALFORMED_RESULT = "tool_malformed_result"
    UNEXPECTED_SIDE_EFFECT = "unexpected_side_effect"
    SCOPE_DRIFT = "scope_drift"
    ARTIFACT_MISMATCH = "artifact_mismatch"
    FALSE_COMPLETION = "false_completion"
    AGENT_CONFLICT = "agent_conflict"
    DUPLICATE_AGENT_WORK = "duplicate_agent_work"
    CHECKPOINT_MISSING = "checkpoint_missing"
    CHECKPOINT_CORRUPT = "checkpoint_corrupt"
    GOAL_DRIFT = "goal_drift"
    UNSUPPORTED_INVESTMENT_ACTION = "unsupported_investment_action"
    PRIVACY_LEAK = "privacy_leak"


@dataclass(frozen=True)
class TaskBudget:
    max_steps: int
    max_tool_calls: int
    max_elapsed_seconds: int


@dataclass(frozen=True)
class AcceptanceCheck:
    id: str
    kind: str
    target: str
    expected: str


@dataclass(frozen=True)
class StartingState:
    references: tuple[str, ...]


@dataclass(frozen=True)
class TaskManifest:
    schema_version: str
    task_id: str
    title: str
    goal: str
    starting_state: StartingState
    context_refs: tuple[str, ...]
    memory_refs: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    budget: TaskBudget
    expected_artifacts: tuple[str, ...]
    acceptance_checks: tuple[AcceptanceCheck, ...]
    privacy_class: PrivacyClass
