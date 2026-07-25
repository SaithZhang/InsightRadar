"""Deterministic, no-model smoke workflow for Harness contracts and recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Callable

from stock_assist.agent_contracts import validate_agent_contracts
from stock_assist.harness_eval.checkpoint import Checkpoint, goal_digest, load_checkpoint, save_checkpoint
from stock_assist.harness_eval.manifest import load_task_manifest
from stock_assist.harness_eval.models import (
    AcceptanceCheck,
    CHECKPOINT_SCHEMA_VERSION,
    PrivacyClass,
    TaskBudget,
)
from stock_assist.harness_eval.trace import MAX_FILE_BYTES, TraceWriter, validate_public_trace
from stock_assist.harness_eval.validation import read_bounded_bytes
from stock_assist.paths import CONFIG_DIR, DATA_DIR, PROJECT_ROOT
from stock_assist.product_governance import load_governance_snapshot


DEFAULT_MANIFEST_PATH = CONFIG_DIR / "harness_eval" / "smoke_task.json"
DEFAULT_OUTPUT_DIR = DATA_DIR / "harness_eval" / "runs"
DEFAULT_ROSTER_PATH = CONFIG_DIR / "agents.json"
DEFAULT_AGENT_DIR = PROJECT_ROOT / ".codex" / "agents"
RUN_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
REQUIRED_SAFE_TOOLS = frozenset({"read_project_files", "write_runtime_artifacts"})
OPERATOR_CLEANUP_ERROR = "staging directory ownership changed; operator cleanup required"


@dataclass(frozen=True)
class SmokeResult:
    run_id: str
    trace_path: Path
    checkpoint_path: Path
    summary_path: Path
    markdown: str


@dataclass(frozen=True)
class _OwnedStagingDirectory:
    output_root: Path
    final_run_dir: Path
    temporary_run_dir: Path
    device: int
    inode: int


@dataclass
class _BudgetCounter:
    budget: TaskBudget
    started_at: datetime
    steps: int = 0
    tool_calls: int = 0

    def step(self, current_time: datetime) -> None:
        self.steps += 1
        if self.steps > self.budget.max_steps:
            raise ValueError("smoke step budget exceeded")
        self.check_elapsed(current_time)

    def tool_call(self, current_time: datetime) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.budget.max_tool_calls:
            raise ValueError("smoke tool-call budget exceeded")
        self.check_elapsed(current_time)

    def check_elapsed(self, current_time: datetime) -> None:
        elapsed = (current_time - self.started_at).total_seconds()
        if elapsed < 0 or elapsed > self.budget.max_elapsed_seconds:
            raise ValueError("smoke elapsed-time budget exceeded")


def _sha256(path: Path) -> str:
    return hashlib.sha256(read_bounded_bytes(path, MAX_FILE_BYTES, "trace")).hexdigest()


def _write_text_atomically(path: Path, content: str) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except OSError as exc:
        raise ValueError("smoke summary cannot be saved") from exc
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def _require_exact_safe_tools(allowed_tools: tuple[str, ...]) -> None:
    if len(allowed_tools) != len(REQUIRED_SAFE_TOOLS) or frozenset(allowed_tools) != REQUIRED_SAFE_TOOLS:
        raise ValueError("smoke manifest must grant the exact safe tool set")


def _new_owned_run_directory(output_dir: Path, run_id: str) -> _OwnedStagingDirectory:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a bounded opaque identifier")
    output_root = Path(output_dir).resolve()
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError("runtime output directory cannot be created") from exc
    if not output_root.is_dir():
        raise ValueError("runtime output directory is not a directory")
    final_run_dir = output_root / run_id
    try:
        final_run_dir.relative_to(output_root)
    except ValueError as exc:
        raise ValueError("runtime artifacts must stay under runtime output") from exc
    if os.path.lexists(final_run_dir):
        raise ValueError("smoke run directory already exists")
    try:
        temporary_run_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=output_root))
    except OSError as exc:
        raise ValueError("runtime output directory cannot be created") from exc
    try:
        status = os.lstat(temporary_run_dir)
    except OSError as exc:
        raise ValueError(OPERATOR_CLEANUP_ERROR) from exc
    if not stat.S_ISDIR(status.st_mode) or stat.S_ISLNK(status.st_mode):
        raise ValueError(OPERATOR_CLEANUP_ERROR)
    return _OwnedStagingDirectory(
        output_root=output_root,
        final_run_dir=final_run_dir,
        temporary_run_dir=temporary_run_dir,
        device=status.st_dev,
        inode=status.st_ino,
    )


def _require_owned_staging_directory(staging: _OwnedStagingDirectory) -> None:
    try:
        if staging.temporary_run_dir.parent.resolve() != staging.output_root.resolve():
            raise ValueError(OPERATOR_CLEANUP_ERROR)
        status = os.lstat(staging.temporary_run_dir)
    except OSError as exc:
        raise ValueError(OPERATOR_CLEANUP_ERROR) from exc
    if (
        not stat.S_ISDIR(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or (status.st_dev, status.st_ino) != (staging.device, staging.inode)
    ):
        raise ValueError(OPERATOR_CLEANUP_ERROR)


def _cleanup_owned_run_directory(staging: _OwnedStagingDirectory) -> None:
    """Best-effort cleanup limited to the unique staging directory created above."""

    try:
        _require_owned_staging_directory(staging)
        shutil.rmtree(staging.temporary_run_dir)
    except OSError as exc:
        raise ValueError(OPERATOR_CLEANUP_ERROR) from exc


def _publish_run_directory(staging: _OwnedStagingDirectory) -> None:
    _require_owned_staging_directory(staging)
    try:
        staging.temporary_run_dir.replace(staging.final_run_dir)
    except OSError as exc:
        raise ValueError("smoke run cannot be published") from exc


def _utc_now(clock: Callable[[], datetime]) -> datetime:
    current = clock()
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("smoke clock must return a timezone-aware datetime")
    return current.astimezone(timezone.utc)


def _validate_governance_sources() -> None:
    try:
        load_governance_snapshot()
    except Exception as exc:
        raise ValueError("Harness governance validation failed") from exc
    if validate_agent_contracts(DEFAULT_AGENT_DIR, DEFAULT_ROSTER_PATH):
        raise ValueError("Harness agent-contract validation failed")


def _is_regular_artifact(path: Path) -> bool:
    try:
        status = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(status.st_mode) and not stat.S_ISLNK(status.st_mode)


def _require_exact_artifacts(run_dir: Path, expected_artifacts: tuple[str, ...]) -> None:
    try:
        entries = list(run_dir.iterdir())
        actual = {
            item.name
            for item in entries
            if _is_regular_artifact(item)
        }
    except OSError as exc:
        raise ValueError("smoke artifact set cannot be inspected") from exc
    if len(entries) != len(actual) or actual != set(expected_artifacts):
        raise ValueError("smoke artifact set mismatch")


def _evaluate_acceptance(run_dir: Path, checks: tuple[AcceptanceCheck, ...]) -> None:
    for check in checks:
        path = run_dir / check.target
        if check.kind == "file_exists":
            actual = _is_regular_artifact(path)
            if check.expected not in {"true", "false"} or actual != (check.expected == "true"):
                raise ValueError("smoke acceptance check failed")
            continue
        if check.kind == "text_contains":
            if not _is_regular_artifact(path):
                raise ValueError("smoke acceptance check failed")
            try:
                content = read_bounded_bytes(path, 64 * 1024, "smoke acceptance target").decode(
                    "utf-8", errors="strict"
                )
            except (UnicodeDecodeError, ValueError) as exc:
                raise ValueError("smoke acceptance check failed") from exc
            if check.expected not in content:
                raise ValueError("smoke acceptance check failed")
            continue
        raise ValueError("smoke acceptance check failed")


def run_contract_smoke(
    manifest_path: Path | None = None,
    output_dir: Path | None = None,
    run_id: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> SmokeResult:
    """Produce one self-contained public trace, checkpoint, and summary with no model call."""

    now = clock or (lambda: datetime.now(timezone.utc))
    manifest = load_task_manifest(manifest_path or DEFAULT_MANIFEST_PATH)
    if manifest.privacy_class is not PrivacyClass.PUBLIC:
        raise ValueError("smoke manifest must be public")
    _require_exact_safe_tools(manifest.allowed_tools)
    _validate_governance_sources()
    started_at = _utc_now(now)
    counters = _BudgetCounter(manifest.budget, started_at)
    counters.step(_utc_now(now))
    actual_run_id = run_id or started_at.strftime("smoke-%Y%m%dt%H%M%Sz")
    staging = _new_owned_run_directory(output_dir or DEFAULT_OUTPUT_DIR, actual_run_id)
    published = False
    try:
        trace_path = staging.temporary_run_dir / "trace.jsonl"
        checkpoint_path = staging.temporary_run_dir / "checkpoint.json"
        summary_path = staging.temporary_run_dir / "harness-smoke.md"

        with TraceWriter(staging.temporary_run_dir, Path("trace.jsonl"), actual_run_id, clock=now) as writer:
            writer.append("run_started", {"task_id": manifest.task_id}, PrivacyClass.PUBLIC)
            counters.tool_call(_utc_now(now))
            writer.append(
                "tool_requested",
                {"tool_id": "read_project_files", "status": "requested"},
                PrivacyClass.PUBLIC,
            )
            counters.step(_utc_now(now))
            writer.append(
                "context_loaded",
                {
                    "starting_state_refs": list(manifest.starting_state.references),
                    "context_refs": list(manifest.context_refs),
                    "memory_refs": list(manifest.memory_refs),
                },
                PrivacyClass.PUBLIC,
            )
            writer.append(
                "tool_completed",
                {"tool_id": "read_project_files", "status": "completed", "result_code": "ok"},
                PrivacyClass.PUBLIC,
            )
            counters.step(_utc_now(now))
            counters.tool_call(_utc_now(now))
            writer.append(
                "tool_requested",
                {"tool_id": "write_runtime_artifacts", "status": "requested"},
                PrivacyClass.PUBLIC,
            )
            initial_checkpoint = Checkpoint(
                schema_version=CHECKPOINT_SCHEMA_VERSION,
                run_id=actual_run_id,
                task_id=manifest.task_id,
                goal_hash=goal_digest(manifest.goal),
                sequence=writer.sequence,
                verified_steps=("manifest_loaded", "starting_state_recorded", "context_refs_recorded"),
                pending_steps=("public_trace_verified",),
                artifact_hashes={},
                created_at=_utc_now(now).isoformat(),
            )
            save_checkpoint(initial_checkpoint, checkpoint_path)
            writer.append("checkpoint_saved", {"checkpoint_ref": checkpoint_path.name}, PrivacyClass.PUBLIC)
            restored = load_checkpoint(checkpoint_path, manifest.task_id, manifest.goal)
            writer.append(
                "checkpoint_restored",
                {"verified_steps": list(restored.verified_steps)},
                PrivacyClass.PUBLIC,
            )
            writer.append(
                "verification_result",
                {"check": "checkpoint_goal_continuity", "status": "pass"},
                PrivacyClass.PUBLIC,
            )
            counters.step(_utc_now(now))
            markdown = "\n".join(
                (
                    "# Agent Harness Contract Smoke",
                    "",
                    f"- Run ID\uff1a{actual_run_id}",
                    f"- Task\uff1a{manifest.task_id}",
                    f"- Privacy\uff1a{manifest.privacy_class.value}",
                    "- \u6a21\u578b\u8c03\u7528\uff1anone",
                    "- \u4ea4\u6613\u6743\u9650\uff1anone",
                    "- Checkpoint \u76ee\u6807\u8fde\u7eed\u6027\uff1aPASS",
                    "- \u516c\u5f00 Trace \u6821\u9a8c\uff1aPASS",
                    f"- Steps\uff1a8/{manifest.budget.max_steps}",
                    f"- Tool calls\uff1a{counters.tool_calls}/{manifest.budget.max_tool_calls}",
                    "- Trace\uff1atrace.jsonl",
                    "- Checkpoint\uff1acheckpoint.json",
                )
            )
            _write_text_atomically(summary_path, markdown + "\n")
            _require_owned_staging_directory(staging)
            counters.step(_utc_now(now))
            _require_exact_artifacts(staging.temporary_run_dir, manifest.expected_artifacts)
            counters.step(_utc_now(now))
            _evaluate_acceptance(staging.temporary_run_dir, manifest.acceptance_checks)
            writer.append(
                "tool_completed",
                {"tool_id": "write_runtime_artifacts", "status": "completed", "result_code": "ok"},
                PrivacyClass.PUBLIC,
            )
            writer.append(
                "verification_result",
                {"check": "manifest_artifact_contract", "status": "pass"},
                PrivacyClass.PUBLIC,
            )
            writer.append(
                "verification_result",
                {"check": "manifest_acceptance", "status": "pass"},
                PrivacyClass.PUBLIC,
            )
            counters.step(_utc_now(now))
            writer.append(
                "verification_result",
                {"check": "public_trace_prefix", "status": "pass"},
                PrivacyClass.PUBLIC,
            )
            counters.step(_utc_now(now))
            public_errors = validate_public_trace(trace_path, require_completed=False)
            if public_errors:
                raise ValueError("public trace validation failed: " + "; ".join(public_errors))
            counters.check_elapsed(_utc_now(now))
            writer.append("run_completed", {"status": "pass"}, PrivacyClass.PUBLIC)

        public_errors = validate_public_trace(trace_path)
        if public_errors:
            raise ValueError("public trace validation failed: " + "; ".join(public_errors))
        final_checkpoint = Checkpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=actual_run_id,
            task_id=manifest.task_id,
            goal_hash=goal_digest(manifest.goal),
            sequence=writer.sequence,
            verified_steps=(
                "manifest_loaded",
                "starting_state_recorded",
                "context_refs_recorded",
                "checkpoint_goal_continuity",
                "manifest_artifact_contract",
                "manifest_acceptance",
                "public_trace_verified",
            ),
            pending_steps=(),
            artifact_hashes={"trace.jsonl": _sha256(trace_path)},
            created_at=_utc_now(now).isoformat(),
        )
        save_checkpoint(final_checkpoint, checkpoint_path)
        restored_final = load_checkpoint(checkpoint_path, manifest.task_id, manifest.goal)
        if restored_final.artifact_hashes != {"trace.jsonl": _sha256(trace_path)}:
            raise ValueError("final checkpoint trace hash mismatch")
        if summary_path.read_text(encoding="utf-8") != markdown + "\n":
            raise ValueError("smoke summary persistence mismatch")
        _require_owned_staging_directory(staging)
        _require_exact_artifacts(staging.temporary_run_dir, manifest.expected_artifacts)
        _evaluate_acceptance(staging.temporary_run_dir, manifest.acceptance_checks)
        counters.check_elapsed(_utc_now(now))
        _publish_run_directory(staging)
        published = True
        return SmokeResult(
            actual_run_id,
            staging.final_run_dir / "trace.jsonl",
            staging.final_run_dir / "checkpoint.json",
            staging.final_run_dir / "harness-smoke.md",
            markdown,
        )
    finally:
        if not published:
            _cleanup_owned_run_directory(staging)
