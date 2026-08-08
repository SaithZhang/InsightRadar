from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from stock_assist.after_close_workbench_html import render_after_close_workbench
from stock_assist.portfolio import Holding, Portfolio, portfolio_version
from stock_assist.portfolio_import_server import (
    _latest_workspace,
    _latest_workspace_html,
    _page,
    _require_current_workspace_authority,
    serve_portfolio_import,
)
from stock_assist.reports import portfolio_import_html_parts

ROOT = Path(__file__).resolve().parents[1]


class OneClickLauncherTests(unittest.TestCase):
    def _workspace(self, version: str) -> dict[str, object]:
        plan = {
            "plan_id": "holding:TEST01.SZ",
            "symbol": "TEST01.SZ",
            "name": "合成标的甲",
            "plan_version": "plan-v1",
            "status": "unchanged",
            "authority_state": "effective",
            "effective_after_user_confirmation": True,
            "user_response_status": "accepted",
            "blocking_reasons": [],
            "risk_constraints": [],
            "change_reasons": [],
        }
        return {
            "portfolio_version": version,
            "effective_market_date": "2026-08-07",
            "generated_at": "2026-08-08T08:00:00",
            "source_generated_at": "2026-08-08T08:00:00",
            "run_stage": "after_close",
            "runtime_status": "reviewed",
            "market_gate": {"status": "ready"},
            "data_health": [],
            "portfolio_summary": {"holding_count": 1},
            "portfolio_positions": [
                {
                    "symbol": "TEST01.SZ",
                    "current_plan_id": plan["plan_id"],
                    "today_status": plan["status"],
                }
            ],
            "plan_changes": [plan],
            "active_plans": [plan],
            "research_tasks": [],
            "user_responses": [],
            "monitor_handoffs": [],
            "outcome_summary": {},
        }

    def test_root_contains_clickable_product_and_task_launchers(self) -> None:
        expected = [
            ROOT / "InsightRadar.cmd",
            ROOT / "生成盘后报告.cmd",
            ROOT / "导入持仓.cmd",
            ROOT / "打开最新报告.cmd",
        ]

        for path in expected:
            self.assertTrue(path.is_file(), path)
            wrapper = path.read_text(encoding="utf-8")
            self.assertIn("insightradar-launcher.ps1", wrapper)
            self.assertIn("if errorlevel 1", wrapper)

    def test_launcher_exposes_generate_import_and_open_actions(self) -> None:
        launcher = (ROOT / "scripts" / "insightradar-launcher.ps1").read_text(encoding="utf-8")
        product_entry = (ROOT / "InsightRadar.cmd").read_text(encoding="utf-8")

        self.assertIn("-m stock_assist.cli after-close", launcher)
        self.assertIn("-m stock_assist.cli portfolio-import --serve", launcher)
        self.assertIn("Start-Process -FilePath $latestReport.FullName", launcher)
        self.assertIn(".venv\\Scripts\\python.exe", launcher)
        self.assertIn("Get-Command python.exe", launcher)
        self.assertIn("did not create a fresh after-close HTML report", launcher)
        self.assertIn("Invoke-WebRequest", launcher)
        self.assertIn("InsightRadar is already running", launcher)
        self.assertIn('"--serve", "--intraday"', launcher)
        self.assertNotIn("intraday-poll --iterations 1", launcher)
        self.assertNotIn("-WindowStyle Hidden", launcher)
        self.assertIn("-Mode Import", product_entry)

    def test_import_page_has_local_preview_and_approved_apply_flow(self) -> None:
        html = _page("test-token")

        self.assertIn('id="file"', html)
        self.assertIn("/api/preview", html)
        self.assertIn("/api/apply", html)
        self.assertIn("/api/refresh/", html)
        self.assertIn("/api/shutdown", html)
        self.assertIn("X-InsightRadar-Token", html)
        self.assertIn("127.0.0.1", html)
        self.assertIn('id="beta-status"', html)
        self.assertIn('class="output"', html)
        self.assertIn("renderPreview", html)
        self.assertIn("pollRefresh", html)
        self.assertIn('id="retry-refresh"', html)
        self.assertIn("重新启动 InsightRadar", html)
        self.assertIn('post("/api/refresh"', html)
        self.assertIn("后台刷新已取得任务号", html)
        self.assertNotIn("正在原子保存并串行刷新，请勿关闭本页", html)
        self.assertNotIn("JSON.stringify(last,null,2)", html)
        self.assertIn("Beta 无需手工导入", html)
        self.assertIn("保存后先自动计算 beta", html)
        self.assertIn('href="/#portfolio"', html)

    def test_workspace_contains_user_confirmed_execution_ledger_flow(self) -> None:
        from stock_assist.after_close_workbench_html import render_after_close_workbench

        payload = {
            "decision_workspace": {
                "effective_market_date": "2026-08-01",
                "runtime_status": "reviewed",
                "market_gate": {}, "data_health": [], "portfolio_summary": {},
                "portfolio_positions": [], "plan_changes": [], "active_plans": [],
                "research_tasks": [], "user_responses": [], "monitor_handoffs": [],
                "outcome_summary": {},
                "intraday_radar": {
                    "status": "shadow", "data_status": "available",
                    "freshness_status": "fresh", "decision_authority": "shadow_only",
                    "source_time": "2026-08-01T09:35:00", "fetch_time": "2026-08-01T09:35:05",
                    "next_check_time": "2026-08-01T10:00:00", "timeline": [],
                    "latest_snapshot": {
                        "timestamp": "2026-08-01T09:35:00",
                        "exposure_by_theme": {}, "quote_freshness": [],
                        "holding_snapshots": [
                            {"symbol": "FIXTURE.SZ", "name": "合成标的", "primary_theme_id": "fixture_theme"}
                        ],
                    },
                },
            }
        }
        html = render_after_close_workbench(payload, "# fixture")
        self.assertIn('id="executionForm"', html)
        self.assertIn('/api/execution', html)
        self.assertIn('id="reentryConfirmationForm"', html)
        self.assertIn('/api/reentry-confirmation', html)
        self.assertIn('user_confirmed', html)
        self.assertIn('shadow_only', html)
        self.assertIn('source_time', html)
        self.assertIn('next_check_time', html)

    def test_static_report_explains_that_the_app_must_be_running(self) -> None:
        _button, modal, script = portfolio_import_html_parts()

        self.assertIn("先双击", modal)
        self.assertIn("InsightRadar.cmd", modal)
        self.assertIn("打开 InsightRadar 导入页", modal)
        self.assertIn("navigator.clipboard.writeText(input.value)", script)

    def test_workspace_injects_token_once_and_keeps_static_guard(self) -> None:
        with TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            payload = {
                "decision_workspace": {
                    "effective_market_date": "2026-07-25",
                    "run_stage": "after_close",
                    "runtime_status": "reviewed",
                    "market_gate": {},
                    "data_health": [],
                    "portfolio_summary": {},
                    "portfolio_positions": [],
                    "plan_changes": [],
                    "active_plans": [],
                    "research_tasks": [],
                    "user_responses": [],
                    "monitor_handoffs": [],
                    "outcome_summary": {},
                }
            }
            (report_dir / "20260725-083000-after-close.json").write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            (report_dir / "20260725-083000-after-close.md").write_text(
                "# fixture",
                encoding="utf-8",
            )
            with patch(
                "stock_assist.portfolio_import_server.REPORT_DIR",
                report_dir,
            ):
                html = _latest_workspace_html("local-test-token")

        self.assertIsNotNone(html)
        self.assertEqual(html.count("local-test-token"), 1)
        self.assertIn('token === "__LOCAL_SESSION_TOKEN__"', html)

    def test_old_workspace_is_superseded_after_saved_portfolio_changes(self) -> None:
        current = Portfolio(
            cash=None,
            holdings=[Holding(code="TEST02.SZ", name="合成标的乙")],
            source=Path("data/portfolio.json"),
            as_of="2026-08-08",
        )
        old_workspace = self._workspace("portfolio-old-version")
        failed_refresh = {
            "status": "failed",
            "failed_step": "after-close",
            "error": "synthetic after-close failure",
        }
        with TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            report = report_dir / "20260808-080000-after-close.json"
            report.write_text(
                json.dumps({"decision_workspace": old_workspace}, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch(
                "stock_assist.portfolio_import_server.REPORT_DIR",
                report_dir,
            ):
                selected = _latest_workspace(
                    current_portfolio=current,
                    refresh_snapshot=failed_refresh,
                )

            self.assertTrue(report.exists())

        self.assertIsNotNone(selected)
        self.assertEqual(selected["workspace_validity"]["status"], "superseded")
        self.assertEqual(selected["runtime_status"], "superseded")
        plan = selected["active_plans"][0]
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["authority_state"], "blocked")
        self.assertFalse(plan["effective_after_user_confirmation"])
        self.assertNotEqual(plan["user_response_status"], "accepted")

    def test_matching_workspace_restores_current_authority_and_keeps_history(self) -> None:
        current = Portfolio(
            cash=None,
            holdings=[Holding(code="TEST02.SZ", name="合成标的乙")],
            source=Path("data/portfolio.json"),
            as_of="2026-08-08",
        )
        current_version = portfolio_version(current)
        with TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            old_report = report_dir / "20260808-080000-after-close.json"
            old_report.write_text(
                json.dumps(
                    {"decision_workspace": self._workspace("portfolio-old-version")},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            new_report = report_dir / "20260808-090000-after-close.json"
            new_report.write_text(
                json.dumps(
                    {"decision_workspace": self._workspace(current_version)},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            old_report.touch()
            time.sleep(0.01)
            new_report.touch()
            with patch(
                "stock_assist.portfolio_import_server.REPORT_DIR",
                report_dir,
            ):
                selected = _latest_workspace(current_portfolio=current)

            self.assertTrue(old_report.exists())

        self.assertIsNotNone(selected)
        self.assertEqual(selected["workspace_validity"]["status"], "current")
        self.assertEqual(selected["active_plans"][0]["authority_state"], "effective")
        self.assertTrue(
            selected["active_plans"][0]["effective_after_user_confirmation"]
        )
        _require_current_workspace_authority(selected, current)

    def test_superseded_workspace_renders_history_only_without_plan_actions(self) -> None:
        workspace = self._workspace("portfolio-old-version")
        workspace["workspace_validity"] = {
            "status": "superseded",
            "reason_code": "PORTFOLIO_VERSION_SUPERSEDED",
            "current_portfolio_version": "portfolio-current-version",
            "workspace_portfolio_version": "portfolio-old-version",
            "current_portfolio_as_of": "2026-08-08",
            "workspace_effective_market_date": "2026-08-07",
            "latest_refresh": {
                "status": "failed",
                "failed_step": "after-close",
                "error": "synthetic after-close failure",
            },
        }

        html = render_after_close_workbench(
            {"decision_workspace": workspace},
            "# synthetic fixture",
        )

        self.assertIn("当前持仓已更新，但决策工作台刷新失败", html)
        self.assertIn("历史快照 · 仅供回看", html)
        self.assertIn("after-close", html)
        self.assertIn('id="refresh-all-data"', html)
        self.assertNotIn('data-plan-response="', html)

    def test_plan_response_endpoint_rejects_superseded_workspace(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        workspace = self._workspace("portfolio-old-version")
        workspace["workspace_validity"] = {
            "status": "superseded",
            "current_decision_authority": "blocked",
        }
        current = Portfolio(
            cash=None,
            holdings=[Holding(code="TEST02.SZ", name="合成标的乙")],
            source=Path("data/portfolio.json"),
            as_of="2026-08-08",
        )
        coordinator = MagicMock()
        append_response = MagicMock(return_value={"response": "accepted"})
        token = "synthetic-local-token"
        with (
            patch(
                "stock_assist.portfolio_import_server.secrets.token_urlsafe",
                return_value=token,
            ),
            patch(
                "stock_assist.portfolio_import_server._latest_workspace_html",
                return_value="<html><body>ready</body></html>",
            ),
            patch(
                "stock_assist.portfolio_import_server._latest_workspace",
                return_value=workspace,
            ),
            patch(
                "stock_assist.portfolio_import_server.load_portfolio",
                return_value=current,
            ),
            patch(
                "stock_assist.portfolio_import_server.append_plan_response",
                append_response,
            ),
        ):
            server_thread = threading.Thread(
                target=serve_portfolio_import,
                kwargs={
                    "port": port,
                    "open_browser": False,
                    "refresh_coordinator": coordinator,
                },
                daemon=True,
            )
            server_thread.start()
            for _ in range(50):
                try:
                    with urlopen(f"http://127.0.0.1:{port}/", timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.02)
            request = Request(
                f"http://127.0.0.1:{port}/api/plan-response",
                data=json.dumps(
                    {
                        "plan_id": "holding:TEST01.SZ",
                        "plan_version": "plan-v1",
                        "response": "accepted",
                    }
                ).encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-InsightRadar-Token": token,
                },
            )
            try:
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(request, timeout=1)
                body = json.loads(rejected.exception.read().decode("utf-8"))
                self.assertIn("当前持仓已更新", body["error"])
            finally:
                shutdown = Request(
                    f"http://127.0.0.1:{port}/api/shutdown",
                    data=b"{}",
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "X-InsightRadar-Token": token,
                    },
                )
                with urlopen(shutdown, timeout=1):
                    pass
                server_thread.join(timeout=2)

        append_response.assert_not_called()
        coordinator.record_user_response.assert_not_called()

    def test_import_service_binds_loopback_opens_browser_and_closes(self) -> None:
        state: dict[str, object] = {}

        class FakeServer:
            def __init__(self, address: tuple[str, int], handler: object) -> None:
                state["address"] = address
                state["handler"] = handler

            def serve_forever(self) -> None:
                state["served"] = True

            def server_close(self) -> None:
                state["closed"] = True

        with (
            patch(
                "stock_assist.portfolio_import_server.ThreadingHTTPServer",
                FakeServer,
            ),
            patch("webbrowser.open") as open_browser,
        ):
            serve_portfolio_import(
                port=8876,
                open_browser=True,
                refresh_coordinator=object(),  # Handler is not exercised here.
            )

        self.assertEqual(state["address"], ("127.0.0.1", 8876))
        self.assertTrue(state["served"])
        self.assertTrue(state["closed"])
        open_browser.assert_called_once_with("http://127.0.0.1:8876/")


if __name__ == "__main__":
    unittest.main()
