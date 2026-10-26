from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from stock_assist.after_close_workbench_html import render_start_workspace
from stock_assist.paths import PROJECT_ROOT
from stock_assist.portfolio import Portfolio
from stock_assist.portfolio_import_server import _empty_workspace_page, serve_portfolio_import


class MacStartupTests(unittest.TestCase):
    def test_first_run_has_four_routes_and_no_action_authority(self) -> None:
        with patch("stock_assist.portfolio_import_server.load_portfolio", return_value=Portfolio(
            cash=None, holdings=[], source=Path("missing.json"), missing=True,
        )):
            html = _empty_workspace_page("synthetic-session-token")
        for route in ("today", "portfolio", "lookup", "review"):
            self.assertIn(f'data-route-panel="{route}"', html)
        self.assertEqual(html.count('data-route-panel="'), 4)
        self.assertEqual(html.count("synthetic-session-token"), 1)
        self.assertIn('href="/portfolio-import"', html)
        self.assertIn("当前尚无可用分析", html)
        self.assertNotIn('data-plan-response="', html)
        self.assertNotIn('.venv\\Scripts', html)

    def test_saved_portfolio_can_generate_workspace_without_sample_values(self) -> None:
        html = render_start_workspace(portfolio_saved=True)
        self.assertIn("持仓已保存 · 等待分析", html)
        self.assertIn('data-start-refresh type="button"', html)
        self.assertNotIn('data-plan-response="', html)
        self.assertIn("等待真实数据", html)

    def test_health_identifies_checkout_without_credentials_and_writes_require_token(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        opener = build_opener(ProxyHandler({}))
        token = "synthetic-health-token"
        with patch("stock_assist.portfolio_import_server.secrets.token_urlsafe", return_value=token):
            thread = threading.Thread(target=serve_portfolio_import, kwargs={
                "port": port, "open_browser": False, "refresh_coordinator": MagicMock(),
            }, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{port}"
            try:
                for attempt in range(50):
                    try:
                        with opener.open(url + "/api/health", timeout=1) as response:
                            state = json.load(response)
                        break
                    except OSError:
                        if attempt == 49:
                            raise
                        time.sleep(.02)
                self.assertEqual(state, {
                    "application": "InsightRadar", "status": "ready",
                    "workspace_id": hashlib.sha256(str(PROJECT_ROOT.resolve()).encode()).hexdigest(),
                })
                with self.assertRaises(HTTPError) as rejected:
                    opener.open(Request(url + "/api/shutdown", data=b"{}", method="POST"), timeout=1)
                self.assertEqual(rejected.exception.code, 403)
            finally:
                with opener.open(Request(url + "/api/shutdown", data=b"{}", method="POST", headers={
                    "X-InsightRadar-Token": token,
                }), timeout=1):
                    pass
                thread.join(timeout=2)
            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
