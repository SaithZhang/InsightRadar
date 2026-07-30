from __future__ import annotations

import sqlite3
import subprocess
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest

from stock_assist.refresh_jobs import (
    RefreshCoordinator,
    select_refresh_workflows,
)


def _accept_artifacts(
    workflow: str,
    before: object,
    portfolio_version: str,
) -> tuple[bool, str, Path | None]:
    return True, "", None


class RefreshJobTests(unittest.TestCase):
    def _wait_terminal(
        self,
        coordinator: RefreshCoordinator,
        run_id: str,
    ) -> dict[str, object]:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            snapshot = coordinator.get(run_id)
            assert snapshot is not None
            if snapshot["status"] not in {"pending", "running"}:
                return snapshot
            time.sleep(0.01)
        self.fail("refresh job did not reach a terminal state")

    def test_full_refresh_is_serial_includes_ai_capex_and_persists_steps(self) -> None:
        calls: list[str] = []

        def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(command[-1])
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{command[-1]} ok",
                stderr="",
            )

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            coordinator = RefreshCoordinator(
                db_path=root / "state.sqlite3",
                report_dir=root / "reports",
                runner=runner,
                artifact_validator=_accept_artifacts,
            )
            started = coordinator.start(
                mode="full",
                idempotency_key="full:test-1",
            )
            completed = self._wait_terminal(
                coordinator,
                str(started["run_id"]),
            )

        self.assertEqual(
            calls,
            [
                "market-levels",
                "risk-watch",
                "market-pulse",
                "style-rotation",
                "ai-capex-watch",
                "after-close",
            ],
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["completed_steps"], 6)
        self.assertEqual(
            [step["status"] for step in completed["steps"]],
            ["completed"] * 6,
        )

    def test_duplicate_click_reuses_active_job(self) -> None:
        entered = Event()
        release = Event()

        def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            entered.set()
            release.wait(timeout=2)
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        with TemporaryDirectory() as temporary:
            coordinator = RefreshCoordinator(
                db_path=Path(temporary) / "state.sqlite3",
                report_dir=Path(temporary) / "reports",
                runner=runner,
                artifact_validator=_accept_artifacts,
            )
            started_at = time.monotonic()
            first = coordinator.start(
                mode="full",
                idempotency_key="click:one",
            )
            start_elapsed = time.monotonic() - started_at
            self.assertTrue(entered.wait(timeout=1))
            duplicate = coordinator.start(
                mode="full",
                idempotency_key="click:two",
            )
            release.set()
            self._wait_terminal(coordinator, str(first["run_id"]))

        self.assertEqual(first["run_id"], duplicate["run_id"])
        self.assertLess(start_elapsed, 1.0)

    def test_failure_names_exact_workflow_and_stops_remaining_steps(self) -> None:
        def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            workflow = command[-1]
            return subprocess.CompletedProcess(
                command,
                2 if workflow == "ai-capex-watch" else 0,
                stdout="",
                stderr="provider unavailable" if workflow == "ai-capex-watch" else "",
            )

        with TemporaryDirectory() as temporary:
            coordinator = RefreshCoordinator(
                db_path=Path(temporary) / "state.sqlite3",
                report_dir=Path(temporary) / "reports",
                runner=runner,
                artifact_validator=_accept_artifacts,
            )
            started = coordinator.start(
                mode="full",
                idempotency_key="failure:test",
            )
            failed = self._wait_terminal(
                coordinator,
                str(started["run_id"]),
            )

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["failed_step"], "ai-capex-watch")
        self.assertIn("provider unavailable", failed["error"])
        self.assertEqual(failed["steps"][-1]["workflow"], "after-close")
        self.assertEqual(failed["steps"][-1]["status"], "pending")

    def test_stale_mode_runs_only_unhealthy_sources_then_after_close(self) -> None:
        selected = select_refresh_workflows(
            "stale",
            [
                {"source_name": "risk_watch", "status": "ready"},
                {"source_name": "market_pulse", "status": "failed"},
                {"source_name": "ai_capex_watch", "status": "stale"},
            ],
        )

        self.assertEqual(
            selected,
            ("market-pulse", "ai-capex-watch", "after-close"),
        )

    def test_service_restart_marks_abandoned_job_interrupted(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.sqlite3"
            coordinator = RefreshCoordinator(db_path=path)
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """
                    INSERT INTO refresh_runs (
                        run_id, idempotency_key, mode, status, requested_at,
                        total_steps, completed_steps
                    ) VALUES ('abandoned', 'abandoned', 'full', 'running',
                              '2026-07-30T20:00:00', 6, 2)
                    """
                )
                connection.commit()
            finally:
                connection.close()

            restarted = RefreshCoordinator(db_path=path)
            snapshot = restarted.get("abandoned")

        assert snapshot is not None
        self.assertEqual(snapshot["status"], "interrupted")
        self.assertIn("重新发起刷新", snapshot["error"])

    def test_sqlite_mirrors_evidence_plans_sources_and_user_responses(self) -> None:
        def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = root / "reports"
            reports.mkdir()
            (reports / "20260730-210000-after-close.json").write_text(
                json.dumps(
                    {
                        "decision_workspace": {
                            "source_generated_at": "2026-07-30T21:00:00",
                            "decision_evidence": {
                                "items": [
                                    {
                                        "evidence_id": "market:risk",
                                        "source_time": "2026-07-30",
                                        "freshness": "ready",
                                    }
                                ]
                            },
                            "active_plans": [
                                {
                                    "plan_id": "holding:900001.SH",
                                    "plan_version": "v-123",
                                    "created_at": "2026-07-30T21:00:00",
                                }
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            db_path = root / "state.sqlite3"
            coordinator = RefreshCoordinator(
                db_path=db_path,
                report_dir=reports,
                runner=runner,
                artifact_validator=lambda workflow, before, version: (
                    True,
                    "",
                    (
                        reports / "20260730-210000-after-close.json"
                        if workflow == "after-close"
                        else None
                    ),
                ),
            )
            started = coordinator.start(
                mode="full",
                idempotency_key="mirror:test",
            )
            self._wait_terminal(coordinator, str(started["run_id"]))
            coordinator.record_user_response(
                {
                    "response_id": "response-1",
                    "plan_id": "holding:900001.SH",
                    "plan_version": "v-123",
                    "response": "accepted",
                    "created_at": "2026-07-30T21:01:00",
                }
            )
            connection = sqlite3.connect(db_path)
            try:
                counts = {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in (
                        "refresh_runs",
                        "refresh_steps",
                        "source_snapshots",
                        "evidence_items",
                        "plan_versions",
                        "user_responses",
                    )
                }
            finally:
                connection.close()

        self.assertEqual(counts["refresh_runs"], 1)
        self.assertEqual(counts["refresh_steps"], 6)
        self.assertEqual(counts["source_snapshots"], 6)
        self.assertEqual(counts["evidence_items"], 1)
        self.assertEqual(counts["plan_versions"], 1)
        self.assertEqual(counts["user_responses"], 1)

    def test_zero_exit_without_a_new_json_artifact_fails_closed(self) -> None:
        def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            coordinator = RefreshCoordinator(
                db_path=root / "state.sqlite3",
                report_dir=root / "reports",
                portfolio_path=root / "portfolio.json",
                runner=runner,
            )
            started = coordinator.start(
                mode="stale",
                idempotency_key="artifact:missing",
            )
            failed = self._wait_terminal(
                coordinator,
                str(started["run_id"]),
            )

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["failed_step"], "after-close")
        self.assertIn("未生成本次刷新对应的新 JSON", failed["error"])

    def test_after_close_requires_complete_triplet_and_matching_portfolio(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = root / "reports"
            reports.mkdir()
            portfolio_path = root / "portfolio.json"
            portfolio_path.write_text(
                json.dumps(
                    {
                        "schema_version": "insightradar-portfolio/v2",
                        "as_of": "2026-07-30",
                        "cash": None,
                        "holdings": [],
                        "risk_reconciliation": {"status": "ready"},
                    }
                ),
                encoding="utf-8",
            )

            def incomplete_runner(
                command: list[str],
            ) -> subprocess.CompletedProcess[str]:
                (reports / "20260730-220000-after-close.json").write_text(
                    json.dumps(
                        {
                            "decision_workspace": {
                                "portfolio_version": "wrong-version",
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

            incomplete = RefreshCoordinator(
                db_path=root / "incomplete.sqlite3",
                report_dir=reports,
                portfolio_path=portfolio_path,
                runner=incomplete_runner,
            )
            started = incomplete.start(
                mode="stale",
                idempotency_key="artifact:incomplete",
            )
            failed = self._wait_terminal(incomplete, str(started["run_id"]))

        self.assertEqual(failed["status"], "failed")
        self.assertIn("JSON/Markdown/HTML 三件套", failed["error"])

    def test_after_close_rejects_a_new_triplet_for_another_portfolio(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = root / "reports"
            reports.mkdir()
            portfolio_path = root / "portfolio.json"
            portfolio_path.write_text(
                json.dumps(
                    {
                        "schema_version": "insightradar-portfolio/v2",
                        "as_of": "2026-07-30",
                        "cash": None,
                        "holdings": [],
                        "risk_reconciliation": {"status": "ready"},
                    }
                ),
                encoding="utf-8",
            )

            def wrong_version_runner(
                command: list[str],
            ) -> subprocess.CompletedProcess[str]:
                stem = reports / "20260730-220100-after-close"
                stem.with_suffix(".json").write_text(
                    json.dumps(
                        {
                            "decision_workspace": {
                                "portfolio_version": "portfolio-other",
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                stem.with_suffix(".md").write_text("# report\n", encoding="utf-8")
                stem.with_suffix(".html").write_text("<p>report</p>", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

            coordinator = RefreshCoordinator(
                db_path=root / "wrong.sqlite3",
                report_dir=reports,
                portfolio_path=portfolio_path,
                runner=wrong_version_runner,
            )
            started = coordinator.start(
                mode="stale",
                idempotency_key="artifact:wrong-version",
            )
            failed = self._wait_terminal(
                coordinator,
                str(started["run_id"]),
            )

        self.assertEqual(failed["status"], "failed")
        self.assertIn("portfolio_version", failed["error"])


if __name__ == "__main__":
    unittest.main()
