from __future__ import annotations

from datetime import date, datetime, timedelta
from http.client import RemoteDisconnected
import inspect
import json
import os
from pathlib import Path
import re
import socket
from subprocess import TimeoutExpired
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen

from stock_assist.after_close_workbench_html import (
    _intraday_portfolio_panel,
    _intraday_today_panel,
    _script,
)
from stock_assist.intraday.archive import MinuteArchive
from stock_assist.intraday.contracts import IntradaySnapshot, MinuteBar, ThemeSnapshot
from stock_assist.intraday.execution import (
    append_execution,
    append_reentry_confirmation,
    append_reentry_failure,
    load_reentry_failures,
)
from stock_assist.intraday.network import (
    build_requests_session,
    build_urllib_opener,
    declared_provider_routes,
    provider_policy,
    sanitize_diagnostic_text,
)
from stock_assist.intraday.providers import (
    EndpointCircuitBreaker,
    fetch_eastmoney_minute_bars,
)
from stock_assist.intraday.polling import (
    _acquire_scheduler_lock,
    _completed_checkpoints,
    _exhausted_checkpoints,
    _release_scheduler_lock,
    _run_bounded_refresh,
    _runtime_envelope,
    load_reentry_states,
    persist_execution_guard,
    poll_intraday_once,
    run_intraday_service,
)
from stock_assist.intraday.rules import AccountRiskEngine, OpportunityRadarEngine
from stock_assist.intraday.session import (
    latest_completed_trade_date,
    resolve_trading_session,
)
from stock_assist.portfolio_import_server import (
    _intraday_workspace_views,
    _normalize_intraday_overlay,
)
from stock_assist.portfolio_import_server import serve_portfolio_import


ROOT = Path(__file__).resolve().parents[1]


class IntradayReliabilityTests(unittest.TestCase):
    def test_eastmoney_urllib_client_is_direct_even_with_http_proxy(self) -> None:
        with patch.dict(
            os.environ,
            {"HTTP_PROXY": "http://user:secret@proxy.invalid:8080"},
            clear=False,
        ):
            opener = build_urllib_opener(provider_policy("eastmoney"))
        self.assertEqual(opener.insightradar_proxy_policy, "direct")

    def test_domestic_requests_session_does_not_inherit_system_proxy(self) -> None:
        session = build_requests_session(provider_policy("cninfo"))
        self.assertFalse(session.trust_env)

    def test_foreign_requests_session_keeps_system_proxy(self) -> None:
        session = build_requests_session(provider_policy("yahoo"))
        self.assertTrue(session.trust_env)

    def test_amazingdata_declares_raw_tcp_direct_route(self) -> None:
        policy = provider_policy("galaxy_amazingdata")
        self.assertEqual(policy.network_region, "domestic")
        self.assertEqual(policy.proxy_policy, "direct")
        self.assertEqual(policy.transport, "raw_tcp")

    def test_proxy_addresses_and_credentials_are_redacted(self) -> None:
        value = (
            "HTTPS_PROXY=http://alice:secret@10.0.0.8:7890 "
            "failed via http://alice:secret@10.0.0.8:7890"
        )
        sanitized = sanitize_diagnostic_text(value)
        self.assertNotIn("alice", sanitized)
        self.assertNotIn("secret", sanitized)
        self.assertNotIn("10.0.0.8", sanitized)
        self.assertNotIn("7890", sanitized)
        self.assertIn("[redacted_proxy]", sanitized)
        bare = sanitize_diagnostic_text(
            "ProxyError(host='10.0.0.8', port=7890, "
            "user='alice', password='secret', endpoint=proxy.invalid:7890)"
        )
        for value in ("10.0.0.8", "7890", "alice", "secret", "proxy.invalid"):
            self.assertNotIn(value, bare)
        unlabeled = sanitize_diagnostic_text(
            "proxy alice:secret@10.0.0.8:7890; user alice password secret"
        )
        for value in ("10.0.0.8", "7890", "alice", "secret"):
            self.assertNotIn(value, unlabeled)
        nested_labels = sanitize_diagnostic_text(
            "proxy username alice password secret host 10.0.0.8 port 7890"
        )
        for value in ("10.0.0.8", "7890", "alice", "secret"):
            self.assertNotIn(value, nested_labels)
        mapping_repr = sanitize_diagnostic_text(
            "ProxyError({'host': '10.0.0.8', 'port': 7890, "
            "'user': 'alice', 'password': 'secret'}) "
            '\"username\": \"alice\", \"password\": \"secret\"'
        )
        for value in ("10.0.0.8", "7890", "alice", "secret"):
            self.assertNotIn(value, mapping_repr)

    def test_eastmoney_circuit_opens_after_three_equal_connection_errors(self) -> None:
        calls: list[str] = []

        def fail(secid: str, interval: str, **_kwargs):
            calls.append(secid)
            raise RemoteDisconnected("remote end closed connection")

        symbols = [f"6000{index:02d}.SH" for index in range(92)]
        bars, failures, diagnostics = fetch_eastmoney_minute_bars(
            symbols,
            start=date(2026, 7, 31),
            end=date(2026, 7, 31),
            candle_fetcher=fail,
            circuit_breaker=EndpointCircuitBreaker(failure_threshold=3),
            include_diagnostics=True,
        )
        self.assertEqual(bars, [])
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(failures), 92)
        self.assertTrue(
            all(
                value == "provider_unavailable_due_to_circuit_breaker"
                for value in list(failures.values())[3:]
            )
        )
        self.assertEqual(diagnostics["circuit_state"], "open")
        self.assertEqual(diagnostics["attempt_count"], 3)

    def test_eastmoney_refresh_stops_at_total_deadline(self) -> None:
        ticks = iter([0.0, 0.0, 0.7, 1.4, 2.1, 2.1])
        calls: list[str] = []

        def slow_empty(secid: str, interval: str, **_kwargs):
            calls.append(secid)
            return []

        _bars, failures, diagnostics = fetch_eastmoney_minute_bars(
            ["600000.SH", "600001.SH", "600002.SH", "600003.SH"],
            start=date(2026, 7, 31),
            end=date(2026, 7, 31),
            candle_fetcher=slow_empty,
            include_diagnostics=True,
            total_timeout_seconds=1.0,
            monotonic_fn=lambda: next(ticks),
        )
        self.assertLess(len(calls), 4)
        self.assertEqual(diagnostics["status"], "partial")
        self.assertIn("refresh_total_timeout", set(failures.values()))
        process = Mock(pid=987654, returncode=-15)
        process.wait.side_effect = [
            TimeoutExpired(cmd="intraday-poll", timeout=0.01),
            -15,
        ]
        with (
            patch(
                "stock_assist.intraday.polling.subprocess.Popen",
                return_value=process,
            ),
            patch(
                "stock_assist.intraday.polling.load_intraday_runtime",
                return_value={"latest_snapshot": None, "data_gaps": []},
            ),
            patch("stock_assist.intraday.polling._atomic_json") as write_runtime,
        ):
            hard_timeout = _run_bounded_refresh(
                allow_fallback=True,
                timeout_seconds=0.01,
            )
        process.terminate.assert_called_once()
        write_runtime.assert_called_once()
        self.assertEqual(hard_timeout["refresh_process_status"], "refresh_total_timeout")
        self.assertEqual(hard_timeout["trade_authority"], "none")

    def test_saturday_resolves_latest_real_exchange_trade_date(self) -> None:
        class FakeClient:
            calendar = [20260729, 20260730, 20260731, 20260803]

        with tempfile.TemporaryDirectory() as temporary:
            resolution = resolve_trading_session(
                datetime(2026, 8, 1, 9, 10),
                client=FakeClient(),
                archive=MinuteArchive(Path(temporary)),
            )
        self.assertEqual(resolution.calendar_date, date(2026, 8, 1))
        self.assertIsNone(resolution.current_exchange_trade_date)
        self.assertEqual(resolution.latest_completed_trade_date, date(2026, 7, 31))
        self.assertEqual(resolution.runtime_trade_date, date(2026, 7, 31))
        self.assertEqual(resolution.session_mode, "non_trading_day")
        self.assertEqual(resolution.trade_authority, "none")

    def test_monday_premarket_uses_friday_from_explicit_exchange_calendar(self) -> None:
        result = latest_completed_trade_date(
            datetime(2026, 8, 10, 8, 30),
            [20260807, 20260810],
        )

        self.assertEqual(result, date(2026, 8, 7))

    def test_non_trading_day_runtime_is_historical_not_fake_live(self) -> None:
        class FakeClient:
            calendar = [20260731, 20260803]

        with tempfile.TemporaryDirectory() as temporary:
            resolution = resolve_trading_session(
                datetime(2026, 8, 1, 12, 0),
                client=FakeClient(),
                archive=MinuteArchive(Path(temporary)),
            )
        payload = resolution.as_dict()
        self.assertEqual(payload["display_trade_date"], "2026-07-31")
        self.assertEqual(payload["view_mode"], "historical_review")
        self.assertEqual(payload["analysis_authority"], "historical_shadow")
        self.assertEqual(payload["trade_authority"], "none")
        self.assertFalse(payload["realtime_decision_available"])
        with tempfile.TemporaryDirectory() as temporary:
            probed = resolve_trading_session(
                datetime(2026, 8, 1, 12, 0),
                client=None,
                archive=MinuteArchive(Path(temporary)),
                trade_date_probe=lambda _today: date(2026, 7, 31),
            )
        self.assertEqual(probed.runtime_trade_date, date(2026, 7, 31))
        self.assertEqual(
            probed.resolution_source,
            "bounded completed A-share K-line date probe",
        )

    def test_launcher_starts_workspace_before_background_refresh(self) -> None:
        launcher = (ROOT / "scripts" / "insightradar-launcher.ps1").read_text(
            encoding="utf-8"
        )
        intraday = launcher.split("function Start-IntradayRadar", 1)[1].split(
            "function Show-Menu", 1
        )[0]
        self.assertIn("portfolio-import", intraday)
        self.assertIn("--intraday", intraday)
        self.assertNotIn("intraday-poll --iterations 1", intraday)
        self.assertLess(intraday.index("portfolio-import"), intraday.index("background"))
        service_source = inspect.getsource(run_intraday_service)
        self.assertLess(
            service_source.index("_acquire_scheduler_lock"),
            service_source.index("_run_bounded_refresh"),
        )

    def test_page_observes_background_progress_every_second(self) -> None:
        workspace = {
            "intraday_radar": {
                "status": "running",
                "session_mode": "non_trading_day",
                "runtime_trade_date": "2026-07-31",
                "view_mode": "historical_review",
                "refresh_progress": {
                    "phase": "fetching_primary",
                    "provider": "galaxy_amazingdata",
                    "route_display": "国内直连",
                    "processed_symbols": 24,
                    "total_symbols": 92,
                },
                "network_routes": declared_provider_routes(),
            }
        }
        html = _intraday_today_panel(workspace)
        script = _script()
        self.assertIn('id="intradayProgressPhase"', html)
        self.assertIn('id="intradayCounts"', html)
        self.assertIn('/api/intraday/runtime', script)
        self.assertIn('window.setInterval(pollIntradayRuntime, 1000)', script)
        self.assertIn("yahoo", html)
        self.assertIn("国外系统代理", html)
        self.assertIn("localhost", html)
        self.assertIn("本地服务", html)
        self.assertIn("TUN", html)

    def test_saturday_poll_never_queries_saturday_minute_bars(self) -> None:
        timestamp = datetime(2026, 8, 1, 9, 25)
        requested: list[tuple[date, date]] = []
        bar = self._bar(datetime(2026, 7, 31, 9, 25))

        class FakeClient:
            calendar = [20260731, 20260803]

            def logout(self) -> None:
                return None

        def fetch_primary(
            _client,
            _symbols,
            *,
            start,
            end,
            fetched_at,
            timeout_seconds,
        ):
            requested.append((start, end))
            self.assertGreater(timeout_seconds, 0)
            self.assertLessEqual(timeout_seconds, 12)
            return [bar]

        universe = {
            "benchmark": "588200.SH",
            "themes": [{
                "theme_id": "ai_hardware_semiconductor",
                "representative_etf": "588200.SH",
                "representative_symbols": [],
            }],
        }
        portfolio = SimpleNamespace(cash=0.0, holdings=[])
        with tempfile.TemporaryDirectory() as temporary:
            archive = MinuteArchive(Path(temporary))
            with (
                patch("stock_assist.intraday.polling.load_intraday_universe", return_value=universe),
                patch("stock_assist.intraday.polling.load_portfolio", return_value=portfolio),
                patch("stock_assist.intraday.polling.MinuteArchive", return_value=archive),
                patch("stock_assist.intraday.polling.AmazingDataClient", FakeClient),
                patch("stock_assist.intraday.polling.fetch_amazingdata_minute_bars", side_effect=fetch_primary),
                patch("stock_assist.intraday.polling.fetch_amazingdata_latest_quotes") as quotes,
                patch("stock_assist.intraday.polling.load_intraday_runtime", return_value=None),
                patch("stock_assist.intraday.polling.load_reentry_states", return_value=()),
                patch("stock_assist.intraday.polling.detect_reentry_failures", return_value=()),
            ):
                payload = poll_intraday_once(as_of=timestamp, allow_fallback=False)
        self.assertEqual(requested, [(date(2026, 7, 31), date(2026, 7, 31))])
        quotes.assert_not_called()
        self.assertEqual(payload["trade_date"], "2026-07-31")
        self.assertEqual(payload["data_status"], "historical_available")
        self.assertEqual(payload["trade_authority"], "none")

    def test_old_after_close_date_does_not_rewrite_current_runtime_authority(self) -> None:
        runtime = {
            "trade_date": "2026-08-03",
            "calendar_date": "2026-08-03",
            "session_mode": "live",
            "view_mode": "current_session",
            "status": "blocked",
            "data_status": "failed",
            "freshness_status": "missing",
            "analysis_authority": "none",
            "decision_authority": "blocked",
            "trade_authority": "none",
            "source_time": None,
        }
        normalized, _historical = _normalize_intraday_overlay(
            runtime,
            expected_trade_date="2026-07-31",
            now=datetime(2026, 8, 3, 9, 30),
        )
        self.assertEqual(normalized["decision_authority"], "blocked")
        self.assertEqual(normalized["status"], "blocked")

    def test_runtime_api_and_workspace_views_share_key_state(self) -> None:
        runtime = {
            "schema_version": "intraday-runtime/v2",
            "calendar_date": "2026-08-01",
            "current_exchange_trade_date": None,
            "latest_completed_trade_date": "2026-07-31",
            "runtime_trade_date": "2026-07-31",
            "display_trade_date": "2026-07-31",
            "trade_date": "2026-07-31",
            "session_mode": "non_trading_day",
            "view_mode": "historical_review",
            "status": "historical_review",
            "data_status": "historical_available",
            "freshness_status": "historical",
            "analysis_authority": "historical_shadow",
            "decision_authority": "historical_shadow_only",
            "trade_authority": "none",
            "realtime_decision_available": False,
            "source_time": "2026-07-31T15:00:00",
        }
        views = _intraday_workspace_views(runtime, now=datetime(2026, 8, 1, 10, 0))
        selected = views["selected_session"]
        latest = views["latest_completed_session"]
        self.assertEqual(selected, latest)
        for field in (
            "runtime_trade_date", "session_mode", "data_status",
            "analysis_authority", "decision_authority", "trade_authority",
        ):
            self.assertEqual(selected[field], runtime[field])

    def test_ledger_form_remains_visible_without_intraday_snapshot(self) -> None:
        html = _intraday_portfolio_panel(
            {
                "intraday_radar": {
                    "latest_snapshot": None,
                    "freshness_status": "missing",
                    "decision_authority": "blocked",
                },
                "portfolio_positions": [
                    {"symbol": "588200.SH", "name": "科技ETF"}
                ],
            }
        )
        self.assertIn('id="executionForm"', html)
        self.assertIn("588200.SH", html)
        self.assertIn('id="executionReference"', html)

    def test_confirmed_sell_persists_guard_immediately_with_missing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution_path = root / "execution.jsonl"
            runtime_path = root / "runtime.json"
            confirmation_path = root / "confirm.jsonl"
            failure_path = root / "failure.jsonl"
            runtime_path.write_text(
                json.dumps({"schema_version": "intraday-runtime/v2", "latest_snapshot": None}),
                encoding="utf-8",
            )
            append_execution(
                self._sale(),
                path=execution_path,
                confirmed_at=datetime(2026, 7, 31, 9, 26),
            )
            append_execution(
                {
                    **self._sale(quantity=200),
                    "sold_at": "2026-07-31T09:27:00",
                },
                path=execution_path,
                confirmed_at=datetime(2026, 7, 31, 9, 28),
            )
            guard = persist_execution_guard(
                runtime_path=runtime_path,
                execution_path=execution_path,
                confirmation_path=confirmation_path,
                failure_path=failure_path,
            )
            persisted = json.loads(runtime_path.read_text(encoding="utf-8"))
        self.assertEqual(guard["status"], "active")
        self.assertEqual(guard["structure_data_status"], "missing")
        self.assertEqual(guard["default_reentry_policy"], "structure_confirmation_required")
        self.assertEqual(len(persisted["reentry_guard_states"]), 2)
        self.assertEqual(
            len({item["sale_execution_id"] for item in persisted["reentry_guard_states"]}),
            2,
        )

    def test_orphan_buy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "execution.jsonl"
            with self.assertRaisesRegex(ValueError, "reference_execution_id"):
                append_execution(self._buy(reference=None), path=path)

    def test_buy_must_reference_matching_sell(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "execution.jsonl"
            sale = append_execution(self._sale(), path=path)
            with self.assertRaisesRegex(ValueError, "match sell"):
                append_execution(
                    self._buy(reference=sale.execution_id, symbol="300308.SZ"),
                    path=path,
                )

    def test_cumulative_reentry_cannot_exceed_remaining_sell_quantity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "execution.jsonl"
            sale = append_execution(self._sale(quantity=100), path=path)
            append_execution(self._buy(reference=sale.execution_id, quantity=60), path=path)
            with self.assertRaisesRegex(ValueError, "remaining sell quantity"):
                append_execution(self._buy(reference=sale.execution_id, quantity=50), path=path)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "execution.jsonl"
            sale = append_execution(self._sale(quantity=100), path=path)
            barrier = threading.Barrier(3)
            outcomes: list[str] = []

            def submit(quantity: float) -> None:
                barrier.wait()
                try:
                    append_execution(
                        self._buy(reference=sale.execution_id, quantity=quantity),
                        path=path,
                    )
                    outcomes.append("accepted")
                except ValueError:
                    outcomes.append("rejected")

            workers = [
                threading.Thread(target=submit, args=(60,)),
                threading.Thread(target=submit, args=(50,)),
            ]
            for worker in workers:
                worker.start()
            barrier.wait()
            for worker in workers:
                worker.join(timeout=3)
            self.assertEqual(sorted(outcomes), ["accepted", "rejected"])

    def test_reentry_failure_is_append_only_and_later_rebound_does_not_unlock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution_path = root / "execution.jsonl"
            failure_path = root / "failure.jsonl"
            confirmation_path = root / "confirm.jsonl"
            sale = append_execution(self._sale(), path=execution_path)
            buy = append_execution(self._buy(reference=sale.execution_id), path=execution_path)
            failure = append_reentry_failure(
                self._failure(buy.execution_id, sale.execution_id),
                execution_path=execution_path,
                path=failure_path,
            )
            states = load_reentry_states(
                execution_path,
                confirmation_path=confirmation_path,
                failure_path=failure_path,
            )
            failure_count = len(load_reentry_failures(failure_path))
        self.assertEqual(failure_count, 1)
        self.assertTrue(states[0].post_reentry_low_broken)
        self.assertFalse(states[0].second_reentry_confirmed)
        self.assertTrue(failure.market_observation_id)

    def test_reentry_override_must_reference_real_failure_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution_path = root / "execution.jsonl"
            failure_path = root / "failure.jsonl"
            confirmation_path = root / "confirm.jsonl"
            sale = append_execution(self._sale(), path=execution_path)
            buy = append_execution(self._buy(reference=sale.execution_id), path=execution_path)
            with self.assertRaisesRegex(ValueError, "real re-entry failure"):
                append_reentry_confirmation(
                    {
                        "symbol": sale.symbol,
                        "target_id": sale.target_id,
                        "sold_at": sale.sold_at,
                        "failure_observation_id": "missing",
                        "source": "user_confirmed_reentry_override",
                        "user_confirmed": True,
                    },
                    execution_path=execution_path,
                    failure_path=failure_path,
                    path=confirmation_path,
                )
            failure = append_reentry_failure(
                self._failure(buy.execution_id, sale.execution_id),
                execution_path=execution_path,
                path=failure_path,
            )
            confirmation = append_reentry_confirmation(
                {
                    "symbol": sale.symbol,
                    "target_id": sale.target_id,
                    "sold_at": sale.sold_at,
                    "failure_observation_id": failure.failure_id,
                    "source": "user_confirmed_reentry_override",
                    "user_confirmed": True,
                },
                execution_path=execution_path,
                failure_path=failure_path,
                path=confirmation_path,
                confirmed_at=datetime(2026, 7, 31, 10, 10),
            )
        self.assertEqual(confirmation.failure_observation_id, failure.failure_id)

    def test_empty_timeline_renders_no_state_events_not_enum_examples(self) -> None:
        html = _intraday_today_panel(
            {"intraday_radar": {"latest_snapshot": None, "timeline": []}}
        )
        self.assertIn("暂无状态事件", html)
        self.assertNotIn("activated / escalated / resolved / invalidation", html)

    def test_fresh_representatives_cannot_mask_stale_etf(self) -> None:
        theme = self._theme(component_freshness={
            "etf": "stale", "representatives": "fresh", "benchmark": "fresh"
        })
        snapshot = self._snapshot(theme)
        result = OpportunityRadarEngine([theme.theme_id]).evaluate(snapshot, [])
        self.assertEqual(result.opportunity_states[theme.theme_id], "观察")

    def test_unknown_technology_exposure_returns_insufficient_data_not_zero(self) -> None:
        theme = self._theme()
        snapshot = IntradaySnapshot(
            timestamp=datetime(2026, 7, 31, 9, 25),
            portfolio_value=None,
            account_daily_pnl=None,
            account_peak_daily_pnl=None,
            pnl_giveback_ratio=None,
            exposure_by_theme={theme.theme_id: None},
            quote_freshness=(),
            theme_snapshots=(theme,),
            holding_snapshots=(),
            source_times=(),
        )
        result = AccountRiskEngine([theme.theme_id]).evaluate(snapshot)
        self.assertEqual(result.state_updates["account_risk"], "insufficient_data")
        self.assertEqual(result.alerts, ())

    def test_failed_checkpoint_is_not_completed_and_retry_is_bounded(self) -> None:
        runtime = {
            "trade_date": "2026-08-03",
            "checkpoint_runs": [
                {"trade_date": "2026-08-03", "checkpoint": "09:25", "status": "failed"},
                {"trade_date": "2026-08-03", "checkpoint": "09:25", "status": "failed"},
            ],
        }
        self.assertNotIn("09:25", _completed_checkpoints(runtime, "2026-08-03"))
        self.assertIn("09:25", _exhausted_checkpoints(runtime, "2026-08-03"))
        failed = _runtime_envelope(
            datetime(2026, 8, 3, 9, 25, 30),
            status="failed",
            data_status="failed",
            freshness_status="missing",
            source_time=None,
            previous=None,
            extra={"latest_snapshot": None, "timeline": [], "active_alerts": []},
        )
        self.assertEqual(failed["checkpoint_runs"][0]["status"], "failed")
        self.assertNotIn("09:25", _completed_checkpoints(failed, "2026-08-03"))
        exhausted = _runtime_envelope(
            datetime(2026, 8, 3, 9, 25, 45),
            status="failed",
            data_status="failed",
            freshness_status="missing",
            source_time=None,
            previous=failed,
            extra={"latest_snapshot": None, "timeline": [], "active_alerts": []},
        )
        self.assertEqual(len(exhausted["checkpoint_runs"]), 2)
        self.assertIn("09:25", _exhausted_checkpoints(exhausted, "2026-08-03"))
        self.assertEqual(exhausted["next_check_time"], "2026-08-03T09:35:00")
        after_restart = _runtime_envelope(
            datetime(2026, 8, 3, 9, 26),
            status="failed",
            data_status="failed",
            freshness_status="missing",
            source_time=None,
            previous=exhausted,
            extra={"latest_snapshot": None, "timeline": [], "active_alerts": []},
        )
        self.assertEqual(len(after_restart["checkpoint_runs"]), 2)
        self.assertEqual(after_restart["next_check_time"], "2026-08-03T09:35:00")
        with tempfile.TemporaryDirectory() as temporary:
            lock_path = Path(temporary) / "scheduler.lock"
            lock_path.write_text("pid=999999 started_at=2026-08-03T09:00:00\n", encoding="utf-8")
            with (
                patch("stock_assist.intraday.polling.SCHEDULER_LOCK_PATH", lock_path),
                patch("stock_assist.intraday.polling._process_is_alive", return_value=False),
            ):
                descriptor = _acquire_scheduler_lock(datetime(2026, 8, 3, 9, 24))
                self.assertIsNotNone(descriptor)
                _release_scheduler_lock(descriptor)
            self.assertFalse(lock_path.exists())

    def test_raw_provider_exception_is_not_rendered_on_normal_page(self) -> None:
        secret_error = "RemoteDisconnected http://alice:secret@10.0.0.8:7890"
        html = _intraday_today_panel(
            {
                "intraday_radar": {
                    "latest_snapshot": None,
                    "data_gaps": [sanitize_diagnostic_text(secret_error)],
                    "provider_status": {
                        "diagnostics": [{"sanitized_error_type": "RemoteDisconnected"}]
                    },
                }
            }
        )
        self.assertNotIn("alice", html)
        self.assertNotIn("secret", html)
        self.assertNotIn("10.0.0.8", html)

    def test_four_first_level_routes_remain_unchanged(self) -> None:
        script = _script()
        self.assertIn('new Set(["today", "portfolio", "lookup", "review"])', script)
        self.assertNotIn('"fifth"', script)

    def test_declared_provider_routes_cover_domestic_foreign_and_local(self) -> None:
        expected = {
            "galaxy_amazingdata": "direct",
            "eastmoney": "direct",
            "tencent": "direct",
            "cninfo": "direct",
            "iwencai": "direct",
            "yahoo": "system_proxy",
            "localhost": "local_only",
            "futu_opend": "local_only",
        }
        self.assertEqual(
            {provider: provider_policy(provider).proxy_policy for provider in expected},
            expected,
        )
        routes = {item["provider_id"]: item for item in declared_provider_routes()}
        self.assertEqual(routes["yahoo"]["display_route"], "国外系统代理")
        self.assertEqual(routes["localhost"]["display_route"], "本地服务")
        self.assertFalse(routes["eastmoney_push2his"]["os_tun_bypass_guaranteed"])

    def test_workspace_starts_under_five_seconds_while_network_worker_is_blocked(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        release = threading.Event()

        def blocked_refresh(**_kwargs: object) -> dict[str, object]:
            release.wait(timeout=3)
            return {}

        with (
            patch(
                "stock_assist.portfolio_import_server.run_intraday_service",
                side_effect=blocked_refresh,
            ),
            patch(
                "stock_assist.portfolio_import_server._latest_workspace_html",
                side_effect=lambda token, **_kwargs: (
                    '<html><head><meta name="insightradar-session-token" '
                    f'content="{token}"></head><body>ready</body></html>'
                ),
            ),
        ):
            server_thread = threading.Thread(
                target=serve_portfolio_import,
                kwargs={
                    "port": port,
                    "open_browser": False,
                    "intraday_mode": True,
                },
                daemon=True,
            )
            started = time.perf_counter()
            server_thread.start()
            page = ""
            for _ in range(50):
                try:
                    with urlopen(f"http://127.0.0.1:{port}/", timeout=0.2) as response:
                        page = response.read().decode("utf-8")
                    break
                except OSError:
                    time.sleep(0.02)
            elapsed = time.perf_counter() - started
            token_match = re.search(
                r'name="insightradar-session-token" content="([^"]+)"', page
            )
            self.assertIsNotNone(token_match)
            request = Request(
                f"http://127.0.0.1:{port}/api/shutdown",
                data=b"{}",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-InsightRadar-Token": token_match.group(1),
                },
            )
            with urlopen(request, timeout=1):
                pass
            release.set()
            server_thread.join(timeout=2)
        self.assertLess(elapsed, 5.0)

    def test_intraday_raw_runtime_endpoint_is_explicit(self) -> None:
        source = (ROOT / "stock_assist" / "portfolio_import_server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('self.path == "/api/intraday/runtime"', source)
        self.assertIn('"current_session"', source)
        self.assertIn('"latest_completed_session"', source)

    def _sale(self, *, quantity: float = 500.0) -> dict[str, object]:
        return {
            "symbol": "588200.SH",
            "target_id": "ai_hardware_semiconductor",
            "side": "sell",
            "quantity": quantity,
            "available_quantity": 1000.0,
            "sold_at": "2026-07-31T09:25:00",
            "sale_price": 1.18,
            "source": "user_confirmed_broker_execution",
            "user_confirmed": True,
        }

    def _buy(
        self,
        *,
        reference: str | None,
        quantity: float = 100.0,
        symbol: str = "588200.SH",
    ) -> dict[str, object]:
        return {
            **self._sale(),
            "symbol": symbol,
            "side": "buy",
            "quantity": quantity,
            "reference_execution_id": reference,
            "executed_at": "2026-07-31T10:00:00",
            "execution_price": 1.17,
        }

    def _failure(self, buy_id: str, sell_id: str) -> dict[str, object]:
        return {
            "referenced_buy_execution_id": buy_id,
            "referenced_sell_execution_id": sell_id,
            "source_time": "2026-07-31T10:08:00",
            "fetched_at": "2026-07-31T10:08:02",
            "price": 1.16,
            "first_reentry_price": 1.17,
            "market_observation_id": "observation-001",
            "rule_version": "intraday-rules/ir-001-v1",
        }

    def _bar(self, timestamp: datetime) -> MinuteBar:
        return MinuteBar(
            symbol="588200.SH",
            timestamp=timestamp,
            open=1.1,
            high=1.2,
            low=1.09,
            close=1.18,
            volume=100,
            amount=118,
            source_time=timestamp,
            fetched_at=timestamp + timedelta(seconds=2),
            source="fixture",
            observation_id="bar-observation",
        )

    def _theme(self, **overrides: object) -> ThemeSnapshot:
        values: dict[str, object] = {
            "theme_id": "ai_hardware_semiconductor",
            "representative_etf": "588200.SH",
            "representative_symbols": ("300308.SZ",),
            "gap_pct": 2.0,
            "return_pct": 3.0,
            "return_from_open": 2.0,
            "vwap_distance": 0.8,
            "volume_ratio_same_time": 1.5,
            "breadth_above_open": 1.0,
            "breadth_above_vwap": 1.0,
            "breadth_new_high": 1.0,
            "leader_confirmation": True,
            "external_mapping_return": None,
            "relative_strength": 1.5,
            "state": "above_vwap",
        }
        values.update(overrides)
        return ThemeSnapshot(**values)

    def _snapshot(self, theme: ThemeSnapshot) -> IntradaySnapshot:
        timestamp = datetime(2026, 7, 31, 9, 35)
        return IntradaySnapshot(
            timestamp=timestamp,
            portfolio_value=500000.0,
            account_daily_pnl=10000.0,
            account_peak_daily_pnl=10000.0,
            pnl_giveback_ratio=0.0,
            exposure_by_theme={theme.theme_id: 50.0},
            quote_freshness=(),
            theme_snapshots=(theme,),
            holding_snapshots=(),
            source_times=(timestamp,),
        )


if __name__ == "__main__":
    unittest.main()
