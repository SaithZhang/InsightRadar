"""Durable, single-flight refresh jobs for the loopback InsightRadar service."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Iterable, Iterator, Mapping
from uuid import uuid4

from stock_assist.paths import DATA_DIR, REPORT_DIR
from stock_assist.portfolio import (
    DEFAULT_PORTFOLIO_PATH,
    Portfolio,
    load_portfolio,
    portfolio_version,
)
from stock_assist.portfolio_import import (
    REQUIRED_RERUN_WORKFLOWS,
    _default_runner,
)

DEFAULT_STATE_DB = DATA_DIR / "insightradar_state.sqlite3"
ACTIVE_STATUSES = ("pending", "running")
WINDOWS_PROCESS_INIT_FAILURE_CODES = frozenset({0xC0000142, -1073741502})
ArtifactState = Mapping[str, int]
ArtifactValidation = tuple[bool, str, Path | None]
ArtifactValidator = Callable[[str, ArtifactState, str], ArtifactValidation]


class RefreshCoordinator:
    """Own serial Core refresh execution and expose a small durable interface."""

    def __init__(
        self,
        *,
        db_path: Path = DEFAULT_STATE_DB,
        report_dir: Path = REPORT_DIR,
        portfolio_path: Path = DEFAULT_PORTFOLIO_PATH,
        runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
        artifact_validator: ArtifactValidator | None = None,
        thread_factory: Callable[..., Thread] = Thread,
    ) -> None:
        self.db_path = db_path
        self.report_dir = report_dir
        self.portfolio_path = portfolio_path
        self.runner = runner or _default_runner
        self.artifact_validator = artifact_validator or self._validate_step_artifacts
        self.thread_factory = thread_factory
        self._lock = Lock()
        self._initialize()

    def start(
        self,
        *,
        mode: str = "stale",
        data_health: Iterable[Mapping[str, object]] = (),
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        if mode not in {"stale", "full"}:
            raise ValueError("refresh mode must be stale or full")
        workflows = select_refresh_workflows(mode, data_health)
        key = idempotency_key or f"{mode}:{','.join(workflows)}"
        current_portfolio = (
            load_portfolio(self.portfolio_path)
            if self.portfolio_path.exists()
            else Portfolio(
                cash=None,
                holdings=[],
                source=self.portfolio_path,
                missing=True,
            )
        )
        expected_portfolio_version = portfolio_version(current_portfolio)
        with self._lock:
            active = self.active()
            if active is not None:
                return active
            existing = self._by_idempotency_key(key)
            if existing is not None:
                return existing
            run_id = uuid4().hex
            now = _now()
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO refresh_runs (
                        run_id, idempotency_key, mode, status, requested_at,
                        total_steps, completed_steps, portfolio_version
                    ) VALUES (?, ?, ?, 'pending', ?, ?, 0, ?)
                    """,
                    (
                        run_id,
                        key,
                        mode,
                        now,
                        len(workflows),
                        expected_portfolio_version,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO refresh_steps (
                        run_id, step_order, workflow, status
                    ) VALUES (?, ?, ?, 'pending')
                    """,
                    [
                        (run_id, index, workflow)
                        for index, workflow in enumerate(workflows)
                    ],
                )
            worker = self.thread_factory(
                target=self._run,
                args=(run_id, workflows, expected_portfolio_version),
                daemon=True,
                name=f"insightradar-refresh-{run_id[:8]}",
            )
            worker.start()
            return self.get(run_id) or {"run_id": run_id, "status": "pending"}

    def get(self, run_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM refresh_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            steps = connection.execute(
                """
                SELECT step_order, workflow, status, started_at, finished_at,
                       returncode, stdout, stderr
                FROM refresh_steps
                WHERE run_id = ?
                ORDER BY step_order
                """,
                (run_id,),
            ).fetchall()
        result = dict(row)
        result["steps"] = [dict(item) for item in steps]
        result["progress"] = (
            float(result["completed_steps"]) / float(result["total_steps"])
            if result["total_steps"]
            else 1.0
        )
        return result

    def active(self) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id FROM refresh_runs
                WHERE status IN ('pending', 'running')
                ORDER BY requested_at DESC
                LIMIT 1
                """
            ).fetchone()
        return self.get(str(row["run_id"])) if row is not None else None

    def latest(self) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id FROM refresh_runs
                ORDER BY requested_at DESC
                LIMIT 1
                """
            ).fetchone()
        return self.get(str(row["run_id"])) if row is not None else None

    def record_user_response(self, record: Mapping[str, object]) -> None:
        response_id = str(record.get("response_id") or "")
        if not response_id:
            return
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO user_responses (
                    response_id, plan_id, plan_version, response,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    response_id,
                    str(record.get("plan_id") or ""),
                    str(record.get("plan_version") or ""),
                    str(record.get("response") or ""),
                    json.dumps(dict(record), ensure_ascii=False, sort_keys=True),
                    str(record.get("created_at") or _now()),
                ),
            )

    def _run(
        self,
        run_id: str,
        workflows: tuple[str, ...],
        expected_portfolio_version: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE refresh_runs
                SET status = 'running', started_at = ?
                WHERE run_id = ?
                """,
                (_now(), run_id),
            )
        after_close_report: Path | None = None
        for index, workflow in enumerate(workflows):
            started = _now()
            artifact_state = self._artifact_state(workflow)
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE refresh_runs SET current_step = ? WHERE run_id = ?
                    """,
                    (workflow, run_id),
                )
                connection.execute(
                    """
                    UPDATE refresh_steps
                    SET status = 'running', started_at = ?
                    WHERE run_id = ? AND step_order = ?
                    """,
                    (started, run_id, index),
                )
            command = [sys.executable, "-m", "stock_assist.cli", workflow]
            try:
                completed = self.runner(command)
                if _is_windows_process_init_failure(completed):
                    completed = self.runner(command)
            except Exception as exc:
                self._fail_step(
                    run_id,
                    index,
                    workflow,
                    returncode=None,
                    stdout="",
                    stderr=f"{type(exc).__name__}: {exc}",
                )
                return
            stdout = completed.stdout.strip()[-4000:]
            stderr = completed.stderr.strip()[-4000:]
            if _is_windows_process_init_failure(completed):
                stderr = _windows_process_init_failure_message(workflow)
            if completed.returncode != 0:
                self._fail_step(
                    run_id,
                    index,
                    workflow,
                    returncode=completed.returncode,
                    stdout=stdout,
                    stderr=stderr,
                )
                return
            valid, artifact_error, artifact = self.artifact_validator(
                workflow,
                artifact_state,
                expected_portfolio_version,
            )
            if not valid:
                self._fail_step(
                    run_id,
                    index,
                    workflow,
                    returncode=completed.returncode,
                    stdout=stdout,
                    stderr=artifact_error,
                )
                return
            if workflow == "portfolio-beta":
                refreshed_portfolio = (
                    load_portfolio(self.portfolio_path)
                    if self.portfolio_path.exists()
                    else Portfolio(
                        cash=None,
                        holdings=[],
                        source=self.portfolio_path,
                        missing=True,
                    )
                )
                expected_portfolio_version = portfolio_version(
                    refreshed_portfolio
                )
                with self._connect() as connection:
                    connection.execute(
                        """
                        UPDATE refresh_runs SET portfolio_version = ?
                        WHERE run_id = ?
                        """,
                        (expected_portfolio_version, run_id),
                    )
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE refresh_steps
                    SET status = 'completed', finished_at = ?, returncode = ?,
                        stdout = ?, stderr = ?
                    WHERE run_id = ? AND step_order = ?
                    """,
                    (_now(), completed.returncode, stdout, stderr, run_id, index),
                )
                connection.execute(
                    """
                    UPDATE refresh_runs
                    SET completed_steps = ?, current_step = ?
                    WHERE run_id = ?
                    """,
                    (index + 1, workflow, run_id),
                )
            self._record_source_snapshot(run_id, workflow, artifact)
            if workflow == "after-close":
                after_close_report = artifact

        latest_report = (
            after_close_report.with_suffix(".html")
            if after_close_report is not None
            and after_close_report.with_suffix(".html").exists()
            else None
        )
        self._mirror_latest_workspace(run_id, after_close_report)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE refresh_runs
                SET status = 'completed', finished_at = ?, current_step = NULL,
                    latest_report = ?
                WHERE run_id = ?
                """,
                (
                    _now(),
                    str(latest_report) if latest_report is not None else None,
                    run_id,
                ),
            )

    def _fail_step(
        self,
        run_id: str,
        index: int,
        workflow: str,
        *,
        returncode: int | None,
        stdout: str,
        stderr: str,
    ) -> None:
        error = stderr or stdout or f"{workflow} failed"
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE refresh_steps
                SET status = 'failed', finished_at = ?, returncode = ?,
                    stdout = ?, stderr = ?
                WHERE run_id = ? AND step_order = ?
                """,
                (now, returncode, stdout, stderr, run_id, index),
            )
            connection.execute(
                """
                UPDATE refresh_runs
                SET status = 'failed', finished_at = ?, current_step = ?,
                    failed_step = ?, error = ?
                WHERE run_id = ?
                """,
                (now, workflow, workflow, error[-2000:], run_id),
            )

    def _record_source_snapshot(
        self,
        run_id: str,
        workflow: str,
        report: Path | None,
    ) -> None:
        payload: dict[str, object] = {}
        if report is not None:
            try:
                raw = json.loads(report.read_text(encoding="utf-8"))
                payload = raw if isinstance(raw, dict) else {}
            except (OSError, json.JSONDecodeError):
                payload = {}
        as_of = (
            payload.get("as_of")
            or payload.get("generated_at")
            or payload.get("effective_market_date")
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_snapshots (
                    source_id, status, as_of, report_path, updated_at, run_id
                ) VALUES (?, 'ready', ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    status = excluded.status,
                    as_of = excluded.as_of,
                    report_path = excluded.report_path,
                    updated_at = excluded.updated_at,
                    run_id = excluded.run_id
                """,
                (
                    workflow.replace("-", "_"),
                    str(as_of) if as_of is not None else None,
                    str(report) if report is not None else None,
                    _now(),
                    run_id,
                ),
            )

    def _mirror_latest_workspace(
        self,
        run_id: str,
        report: Path | None,
    ) -> None:
        if report is None:
            return
        try:
            raw = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        workspace = raw.get("decision_workspace") if isinstance(raw, dict) else None
        if not isinstance(workspace, Mapping):
            return
        generated_at = str(workspace.get("source_generated_at") or workspace.get("generated_at") or "")
        evidence = workspace.get("decision_evidence")
        evidence_rows = evidence.get("items") if isinstance(evidence, Mapping) else []
        plans = workspace.get("active_plans")
        with self._connect() as connection:
            for item in evidence_rows if isinstance(evidence_rows, list) else []:
                if not isinstance(item, Mapping) or not item.get("evidence_id"):
                    continue
                connection.execute(
                    """
                    INSERT OR REPLACE INTO evidence_items (
                        evidence_id, workspace_generated_at, payload_json,
                        source_time, freshness, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(item.get("evidence_id")),
                        generated_at,
                        json.dumps(dict(item), ensure_ascii=False, sort_keys=True),
                        str(item.get("source_time") or "") or None,
                        str(item.get("freshness") or "unknown"),
                        run_id,
                    ),
                )
            for item in plans if isinstance(plans, list) else []:
                if (
                    not isinstance(item, Mapping)
                    or not item.get("plan_id")
                    or not item.get("plan_version")
                ):
                    continue
                connection.execute(
                    """
                    INSERT OR REPLACE INTO plan_versions (
                        plan_id, plan_version, payload_json, created_at, run_id
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(item.get("plan_id")),
                        str(item.get("plan_version")),
                        json.dumps(dict(item), ensure_ascii=False, sort_keys=True),
                        str(item.get("created_at") or generated_at),
                        run_id,
                    ),
                )

    def _latest_report(self, workflow: str, suffix: str) -> Path | None:
        paths = sorted(
            self.report_dir.glob(f"*-{workflow}{suffix}"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return paths[0].resolve() if paths else None

    def _artifact_state(self, workflow: str) -> dict[str, int]:
        return {
            str(path.resolve()): path.stat().st_mtime_ns
            for path in self.report_dir.glob(f"*-{workflow}.*")
            if path.is_file()
        }

    def _validate_step_artifacts(
        self,
        workflow: str,
        before: ArtifactState,
        expected_portfolio_version: str,
    ) -> ArtifactValidation:
        json_report = self._new_artifact(workflow, ".json", before)
        if json_report is None:
            return (
                False,
                f"{workflow} 返回成功但未生成本次刷新对应的新 JSON 产物。",
                None,
            )
        try:
            raw = json.loads(json_report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return (
                False,
                f"{workflow} 新 JSON 无法解析：{type(exc).__name__}",
                None,
            )
        if not isinstance(raw, dict):
            return False, f"{workflow} 新 JSON 顶层不是对象。", None
        if workflow != "after-close":
            return True, "", json_report

        stem = json_report.with_suffix("")
        for suffix in (".md", ".html"):
            companion = stem.with_suffix(suffix)
            previous_mtime = before.get(str(companion.resolve()))
            if (
                not companion.exists()
                or (
                    previous_mtime is not None
                    and companion.stat().st_mtime_ns <= previous_mtime
                )
            ):
                return (
                    False,
                    "after-close 未生成与新 JSON 同 stem 的 JSON/Markdown/HTML 三件套。",
                    None,
                )
        workspace = raw.get("decision_workspace")
        actual_version = (
            str(workspace.get("portfolio_version") or "")
            if isinstance(workspace, Mapping)
            else ""
        )
        if actual_version != expected_portfolio_version:
            return (
                False,
                "after-close 产物未绑定本次保存的 portfolio_version；上一版报告仍保留。",
                None,
            )
        return True, "", json_report

    def _new_artifact(
        self,
        workflow: str,
        suffix: str,
        before: ArtifactState,
    ) -> Path | None:
        candidates = sorted(
            self.report_dir.glob(f"*-{workflow}{suffix}"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for path in candidates:
            resolved = path.resolve()
            previous_mtime = before.get(str(resolved))
            if previous_mtime is None or path.stat().st_mtime_ns > previous_mtime:
                return resolved
        return None

    def _by_idempotency_key(self, key: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id FROM refresh_runs
                WHERE idempotency_key = ?
                ORDER BY requested_at DESC
                LIMIT 1
                """,
                (key,),
            ).fetchone()
        return self.get(str(row["run_id"])) if row is not None else None

    def _initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS refresh_runs (
                    run_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    current_step TEXT,
                    failed_step TEXT,
                    error TEXT,
                    latest_report TEXT,
                    total_steps INTEGER NOT NULL,
                    completed_steps INTEGER NOT NULL,
                    portfolio_version TEXT
                );
                CREATE TABLE IF NOT EXISTS refresh_steps (
                    run_id TEXT NOT NULL,
                    step_order INTEGER NOT NULL,
                    workflow TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    returncode INTEGER,
                    stdout TEXT,
                    stderr TEXT,
                    PRIMARY KEY (run_id, step_order)
                );
                CREATE TABLE IF NOT EXISTS source_snapshots (
                    source_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    as_of TEXT,
                    report_path TEXT,
                    updated_at TEXT NOT NULL,
                    run_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_items (
                    evidence_id TEXT NOT NULL,
                    workspace_generated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_time TEXT,
                    freshness TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    PRIMARY KEY (evidence_id, workspace_generated_at)
                );
                CREATE TABLE IF NOT EXISTS plan_versions (
                    plan_id TEXT NOT NULL,
                    plan_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    PRIMARY KEY (plan_id, plan_version)
                );
                CREATE TABLE IF NOT EXISTS user_responses (
                    response_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    plan_version TEXT NOT NULL,
                    response TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(refresh_runs)")
            }
            if "portfolio_version" not in columns:
                connection.execute(
                    "ALTER TABLE refresh_runs ADD COLUMN portfolio_version TEXT"
                )
            connection.execute(
                """
                UPDATE refresh_runs
                SET status = 'interrupted', finished_at = ?,
                    error = '本地服务在刷新完成前退出；请重新发起刷新。'
                WHERE status IN ('pending', 'running')
                """,
                (_now(),),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def select_refresh_workflows(
    mode: str,
    data_health: Iterable[Mapping[str, object]],
) -> tuple[str, ...]:
    if mode == "full":
        return tuple(REQUIRED_RERUN_WORKFLOWS)
    stale_sources = {
        str(item.get("source_name") or item.get("id") or "").replace("_", "-")
        for item in data_health
        if str(item.get("status") or "missing")
        in {"stale", "missing", "blocked", "failed", "pending", "unknown"}
    }
    selected = [
        workflow
        for workflow in REQUIRED_RERUN_WORKFLOWS
        if workflow in stale_sources
    ]
    if "risk-watch" in selected and "portfolio-beta" not in selected:
        selected.insert(0, "portfolio-beta")
    if "after-close" not in selected:
        selected.append("after-close")
    return tuple(selected)


def _is_windows_process_init_failure(
    completed: subprocess.CompletedProcess[str],
) -> bool:
    return (
        completed.returncode in WINDOWS_PROCESS_INIT_FAILURE_CODES
        and not (completed.stdout or "").strip()
        and not (completed.stderr or "").strip()
    )


def _windows_process_init_failure_message(workflow: str) -> str:
    return (
        f"{workflow} 的 Windows 子进程初始化失败（0xC0000142），"
        "不是数据校验失败。系统已自动重试一次但仍未恢复；"
        "请关闭并重新启动 InsightRadar 本地应用，再点击“全量刷新”。"
        "持仓已经保存，上一版报告仍保留。"
    )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
