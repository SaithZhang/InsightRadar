from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stock_assist.portfolio_import_server import (
    _latest_workspace_html,
    _page,
    serve_portfolio_import,
)
from stock_assist.reports import portfolio_import_html_parts


ROOT = Path(__file__).resolve().parents[1]


class OneClickLauncherTests(unittest.TestCase):
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
        self.assertIn('id="beta-selectors"', html)
        self.assertIn('class="output"', html)
        self.assertIn("renderPreview", html)
        self.assertIn("pollRefresh", html)
        self.assertIn("后台刷新已取得任务号", html)
        self.assertNotIn("正在原子保存并串行刷新，请勿关闭本页", html)
        self.assertNotIn("JSON.stringify(last,null,2)", html)
        self.assertIn("high_beta", html)
        self.assertIn("normal", html)
        self.assertIn('href="/#portfolio"', html)

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
