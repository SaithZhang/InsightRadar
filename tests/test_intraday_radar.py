from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from stock_assist.intraday.archive import MinuteArchive
from stock_assist.intraday.backtest import compare_strategies
from stock_assist.intraday.contracts import (
    HoldingSnapshot,
    IntradaySnapshot,
    MinuteBar,
    PointQuote,
    ThemeSnapshot,
    contract_dict,
)
from stock_assist.intraday.polling import (
    _alert_transitions,
    _live_case,
    _runtime_envelope,
    load_reentry_states,
    next_checkpoint_time,
    poll_intraday_once,
)
from stock_assist.intraday.execution import (
    append_execution,
    append_reentry_confirmation,
    load_executions,
    load_reentry_confirmations,
)
from stock_assist.intraday.rules import (
    AccountRiskEngine,
    CatalystFailureEngine,
    IntradayDecisionEngine,
    OpportunityRadarEngine,
    ReentryGuardEngine,
    ReentryPositionState,
)
from stock_assist.intraday.snapshots import IntradaySnapshotBuilder
from stock_assist.intraday.universe import load_intraday_universe
from stock_assist.portfolio_import_server import _latest_workspace, _normalize_intraday_overlay


class IntradayRadarTests(unittest.TestCase):
    def test_bounded_universe_contains_required_themes(self) -> None:
        universe = load_intraday_universe()
        themes = universe["themes"]
        self.assertGreaterEqual(len(themes), 20)
        self.assertLessEqual(len(themes), 30)
        self.assertTrue(all(2 <= len(item["representative_symbols"]) <= 5 for item in themes))

    def test_archive_cutoff_never_reads_future_minute(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = MinuteArchive(Path(temporary))
            start = datetime(2026, 7, 31, 9, 30)
            archive.write_bars(
                [self._bar(start), self._bar(start + timedelta(minutes=1), close=9.8)]
            )
            rows = archive.read_bars(
                date(2026, 7, 31),
                through=start,
            )
        self.assertEqual([item.timestamp for item in rows["588200.SH"]], [start])

    def test_archive_correction_never_overwrites_first_observation_bytes_or_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = MinuteArchive(Path(temporary))
            source_time = datetime(2026, 7, 31, 9, 25)
            first_path = archive.write_bars(
                [self._bar(source_time, close=10.0, fetched_at=source_time + timedelta(seconds=5))]
            )[0]
            first_bytes = first_path.read_bytes()
            first_mtime = first_path.stat().st_mtime_ns

            corrected_path = archive.write_bars(
                [self._bar(source_time, close=9.8, fetched_at=source_time + timedelta(minutes=35))]
            )[0]

            self.assertNotEqual(first_path, corrected_path)
            self.assertEqual(first_path.read_bytes(), first_bytes)
            self.assertEqual(first_path.stat().st_mtime_ns, first_mtime)
            self.assertTrue(corrected_path.is_file())
            observations = archive.read_bar_observations(date(2026, 7, 31), symbols=["588200.SH"])
            self.assertEqual([item.close for item in observations["588200.SH"]], [10.0, 9.8])
            self.assertTrue(all(item.observation_id for item in observations["588200.SH"]))
            self.assertTrue(all(item.trade_date == "2026-07-31" for item in observations["588200.SH"]))
            self.assertTrue(all(item.provider == "fixture" for item in observations["588200.SH"]))
            early_view = archive.read_bars(
                date(2026, 7, 31),
                symbols=["588200.SH"],
                through=source_time,
                observed_through=source_time + timedelta(minutes=10),
            )
            corrected_view = archive.read_bars(
                date(2026, 7, 31),
                symbols=["588200.SH"],
                through=source_time,
                observed_through=source_time + timedelta(minutes=40),
            )
            self.assertEqual(early_view["588200.SH"][0].close, 10.0)
            self.assertEqual(corrected_view["588200.SH"][0].close, 9.8)

    def test_future_account_peak_cannot_change_archived_0925_snapshot_hash(self) -> None:
        source_time = datetime(2026, 7, 31, 9, 25)
        quote = PointQuote(
            symbol="588200.SH", timestamp=source_time, price=11.0,
            pre_close=10.0, open=11.0, high=11.0, low=11.0,
            volume=100.0, amount=1100.0, source_time=source_time,
            fetched_at=source_time, source="fixture",
        )
        portfolio = SimpleNamespace(
            cash=0.0,
            holdings=[
                SimpleNamespace(
                    code="588200.SH", name="fixture", shares=1000.0, available=1000.0,
                )
            ],
        )
        bars = {date(2026, 7, 31): {"588200.SH": [self._bar(source_time, close=11.0, fetched_at=source_time)]}}
        themes = [
            {
                "theme_id": "ai_hardware_semiconductor",
                "representative_etf": "588200.SH",
                "representative_symbols": [],
            }
        ]

        def snapshot_hash(previous: dict[str, object] | None) -> str:
            case = _live_case(portfolio, themes, [quote], previous=previous)
            snapshot = IntradaySnapshotBuilder(
                case=case, themes=themes, bars_by_date=bars, quotes=[quote],
            ).build(source_time)
            alert = AccountRiskEngine(["ai_hardware_semiconductor"]).evaluate(snapshot).alerts[0]
            raw = json.dumps(
                {"snapshot": contract_dict(snapshot), "alert": contract_dict(alert)},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            return hashlib.sha256(raw).hexdigest()

        original = snapshot_hash(None)
        after_ten_oclock_peak = snapshot_hash(
            {
                "trade_date": "2026-07-31",
                "latest_snapshot": {
                    "timestamp": "2026-07-31T10:00:00",
                    "account_peak_daily_pnl": 50000.0,
                },
            }
        )
        self.assertEqual(original, after_ten_oclock_peak)

    def test_checkpoint_clock_advances_in_declared_order(self) -> None:
        before_open = datetime(2026, 8, 3, 8, 30)
        self.assertEqual(
            next_checkpoint_time(before_open),
            datetime(2026, 8, 3, 9, 25),
        )
        self.assertEqual(
            next_checkpoint_time(datetime(2026, 8, 3, 9, 25), {"09:25"}),
            datetime(2026, 8, 3, 9, 35),
        )
        self.assertEqual(
            next_checkpoint_time(
                datetime(2026, 8, 3, 10, 0),
                {"09:25", "09:35", "10:00"},
            ),
            None,
        )

    def test_runtime_contract_separates_trade_date_data_freshness_and_authority(self) -> None:
        timestamp = datetime(2026, 8, 3, 9, 25)
        payload = _runtime_envelope(
            timestamp,
            status="shadow",
            data_status="available",
            freshness_status="fresh",
            source_time=timestamp,
            previous=None,
            extra={"latest_snapshot": None, "timeline": [], "active_alerts": []},
        )
        self.assertEqual(payload["trade_date"], "2026-08-03")
        self.assertEqual(payload["data_status"], "available")
        self.assertEqual(payload["freshness_status"], "fresh")
        self.assertEqual(payload["decision_authority"], "shadow_only")
        self.assertEqual(payload["source_time"], "2026-08-03T09:25:00")
        self.assertEqual(payload["fetch_time"], "2026-08-03T09:25:00")
        self.assertEqual(payload["next_check_time"], "2026-08-03T09:35:00")

    def test_live_poll_payload_uses_runtime_v2_and_shadow_sanitization(self) -> None:
        timestamp = datetime(2026, 8, 3, 9, 25)
        bar = self._bar(timestamp, close=11.0, fetched_at=timestamp)
        quote = PointQuote(
            symbol="588200.SH", timestamp=timestamp, price=11.0,
            pre_close=10.0, open=11.0, high=11.0, low=11.0,
            volume=100.0, amount=1100.0, source_time=timestamp,
            fetched_at=timestamp, source="fixture",
        )
        portfolio = SimpleNamespace(
            cash=0.0,
            holdings=[SimpleNamespace(
                code="588200.SH", name="fixture", shares=1000.0, available=1000.0,
            )],
        )
        universe = {
            "benchmark": "588200.SH",
            "themes": [{
                "theme_id": "ai_hardware_semiconductor",
                "representative_etf": "588200.SH",
                "representative_symbols": [],
            }],
        }

        class FakeClient:
            def logout(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as temporary:
            archive = MinuteArchive(Path(temporary))
            with (
                patch("stock_assist.intraday.polling.load_intraday_universe", return_value=universe),
                patch("stock_assist.intraday.polling.load_portfolio", return_value=portfolio),
                patch("stock_assist.intraday.polling.MinuteArchive", return_value=archive),
                patch("stock_assist.intraday.polling.AmazingDataClient", FakeClient),
                patch("stock_assist.intraday.polling.fetch_amazingdata_minute_bars", return_value=[bar]),
                patch("stock_assist.intraday.polling.fetch_amazingdata_latest_quotes", return_value=[quote]),
                patch("stock_assist.intraday.polling.load_intraday_runtime", return_value=None),
                patch("stock_assist.intraday.polling.load_reentry_states", return_value=()),
            ):
                payload = poll_intraday_once(as_of=timestamp, allow_fallback=False)
        self.assertEqual(payload["schema_version"], "intraday-runtime/v2")
        self.assertEqual(payload["status"], "shadow")
        self.assertEqual(payload["data_status"], "available")
        self.assertEqual(payload["freshness_status"], "fresh")
        self.assertEqual(payload["decision_authority"], "shadow_only")
        serialized = json.dumps(payload["timeline"], ensure_ascii=False)
        self.assertNotIn("减仓", serialized)
        self.assertNotIn("min_reduction_pct", serialized)

    def test_cross_trade_date_ready_runtime_is_expired_before_workspace_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            payload = {
                "decision_workspace": {
                    "effective_market_date": "2026-08-01",
                    "source_generated_at": "2026-08-01T08:30:00",
                }
            }
            (report_dir / "20260801-083000-after-close.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            old_runtime = {
                "schema_version": "intraday-runtime/v1",
                "trade_date": "2026-07-31",
                "status": "ready",
                "data_status": "available",
                "freshness_status": "fresh",
                "decision_authority": "ready",
                "source_time": "2026-07-31T10:00:00",
                "fetch_time": "2026-07-31T10:00:05",
                "latest_snapshot": {"timestamp": "2026-07-31T10:00:00"},
                "timeline": [
                    {
                        "type": "account_risk", "target_type": "account",
                        "target_id": "portfolio", "title": "立即减仓 40%–60%",
                        "conclusion": "建议减仓 40%–60%",
                        "evidence": ["兑现 40%–60% 仓位"],
                        "action_state": "human_confirmation_required",
                        "suggested_risk_change": {
                            "min_reduction_pct": 40, "max_reduction_pct": 60,
                        },
                    }
                ],
            }
            with (
                patch("stock_assist.portfolio_import_server.REPORT_DIR", report_dir),
                patch("stock_assist.portfolio_import_server.load_runtime_state", return_value=None),
                patch("stock_assist.portfolio_import_server.load_intraday_runtime", return_value=old_runtime),
            ):
                workspace = _latest_workspace()
        self.assertIsNotNone(workspace)
        runtime = workspace["intraday_radar"]
        self.assertEqual(runtime["freshness_status"], "expired")
        self.assertEqual(runtime["decision_authority"], "none")
        self.assertNotEqual(runtime["status"], "ready")
        self.assertIn("intraday_history", workspace)
        self.assertNotIn("减仓", json.dumps(runtime["timeline"], ensure_ascii=False))
        self.assertNotIn("兑现", json.dumps(runtime["timeline"], ensure_ascii=False))
        self.assertNotIn("min_reduction_pct", runtime["timeline"][0]["suggested_risk_change"])

    def test_same_trade_date_runtime_outside_freshness_window_is_historical_only(self) -> None:
        runtime, historical = _normalize_intraday_overlay(
            {
                "trade_date": "2026-08-03", "status": "shadow",
                "data_status": "available", "freshness_status": "fresh",
                "decision_authority": "shadow_only",
                "source_time": "2026-08-03T09:35:00",
            },
            expected_trade_date="2026-08-03",
            now=datetime(2026, 8, 3, 9, 40),
        )
        self.assertTrue(historical)
        self.assertEqual(runtime["freshness_status"], "expired")
        self.assertEqual(runtime["decision_authority"], "none")

    def test_future_same_day_runtime_cannot_overlay_current_workspace(self) -> None:
        runtime, historical = _normalize_intraday_overlay(
            {
                "trade_date": "2026-08-03", "status": "ready",
                "data_status": "available", "freshness_status": "fresh",
                "decision_authority": "ready",
                "source_time": "2026-08-03T10:00:00",
            },
            expected_trade_date="2026-08-03",
            now=datetime(2026, 8, 3, 9, 35),
        )
        self.assertTrue(historical)
        self.assertEqual(runtime["status"], "expired")
        self.assertEqual(runtime["decision_authority"], "none")

    def test_account_risk_matches_ir001_acceptance_range(self) -> None:
        snapshot = self._snapshot(
            datetime(2026, 7, 31, 9, 24),
            exposure=70.0,
            daily_pnl=33000,
            theme=self._theme(gap=9.94),
        )
        result = AccountRiskEngine(["ai_hardware_semiconductor"]).evaluate(snapshot)
        self.assertEqual(result.alerts[0].severity, "red")
        self.assertEqual(result.alerts[0].suggested_risk_change["min_reduction_pct"], 40)
        self.assertEqual(result.alerts[0].suggested_risk_change["max_reduction_pct"], 60)
        self.assertIn("禁止新增科技风险", result.alerts[0].conclusion)

    def test_alert_state_machine_emits_resolved_event_when_condition_clears(self) -> None:
        timestamp = datetime(2026, 7, 31, 9, 25)
        active_snapshot = self._snapshot(
            timestamp,
            exposure=70.0,
            daily_pnl=33000.0,
            theme=self._theme(gap=9.94),
        )
        active_alerts = AccountRiskEngine(["ai_hardware_semiconductor"]).evaluate(active_snapshot).alerts
        first, active = _alert_transitions(active_snapshot, active_alerts, {})
        self.assertEqual(first[0]["event_state"], "activated")

        cleared_snapshot = self._snapshot(
            timestamp + timedelta(minutes=10),
            exposure=20.0,
            daily_pnl=5000.0,
            theme=self._theme(gap=1.0),
        )
        resolved, remaining = _alert_transitions(cleared_snapshot, (), active)
        self.assertEqual(resolved[0]["event_state"], "resolved")
        self.assertEqual(resolved[0]["action_state"], "observation_only")
        self.assertEqual(remaining, {})

    def test_ir002_shadow_only_cannot_emit_position_action_copy_or_range(self) -> None:
        snapshot = self._snapshot(
            datetime(2026, 7, 31, 9, 25),
            exposure=70.0,
            daily_pnl=33000.0,
            theme=self._theme(gap=9.94),
        )
        engine = IntradayDecisionEngine(
            technology_theme_ids=["ai_hardware_semiconductor"],
            catalyst_theme_ids=["ai_hardware_semiconductor"],
            decision_authority="shadow_only",
        )
        result = engine.evaluate(snapshot)
        alert = next(item for item in result.alerts if item.type == "account_risk")
        self.assertEqual(alert.action_state, "observation_only")
        self.assertNotIn("减仓", alert.conclusion)
        self.assertNotIn("兑现", alert.conclusion)
        self.assertNotIn("min_reduction_pct", alert.suggested_risk_change)
        self.assertNotIn("max_reduction_pct", alert.suggested_risk_change)
        serialized = json.dumps(contract_dict(alert), ensure_ascii=False)
        self.assertNotIn("减仓", serialized)
        self.assertNotIn("兑现", serialized)
        self.assertNotIn("40%", serialized)
        self.assertNotIn("60%", serialized)

    def test_catalyst_failure_escalates_yellow_orange_red(self) -> None:
        engine = CatalystFailureEngine(["ai_hardware_semiconductor"])
        base = datetime(2026, 7, 31, 9, 30)
        yellow = self._snapshot(
            base,
            theme=self._theme(from_open=-0.7, vwap=-0.5, breadth_vwap=0.75),
        )
        rebound = self._snapshot(
            base + timedelta(minutes=10),
            theme=self._theme(from_open=0.8, vwap=0.4, breadth_vwap=0.75),
        )
        orange = self._snapshot(
            base + timedelta(minutes=20),
            theme=self._theme(from_open=-0.8, vwap=-0.7, breadth_vwap=0.5),
        )
        red = self._snapshot(
            base + timedelta(minutes=30),
            theme=self._theme(from_open=-1.8, vwap=-1.0, breadth_vwap=0.25),
        )
        self.assertEqual(engine.evaluate(yellow, []).alerts[0].severity, "yellow")
        self.assertEqual(engine.evaluate(orange, [yellow, rebound]).alerts[0].severity, "orange")
        self.assertEqual(engine.evaluate(red, [yellow, rebound, orange]).alerts[0].severity, "red")

    def test_opportunity_requires_vwap_breadth_volume_and_leader(self) -> None:
        engine = OpportunityRadarEngine(["ai_software_apps"])
        weak = self._theme(
            theme_id="ai_software_apps",
            from_open=1.8,
            vwap=-0.1,
            breadth_open=0.75,
            breadth_vwap=0.5,
            volume_ratio=1.5,
            leader=True,
            relative_strength=1.4,
        )
        confirmed = self._theme(
            theme_id="ai_software_apps",
            from_open=1.8,
            vwap=0.6,
            breadth_open=0.75,
            breadth_vwap=0.75,
            volume_ratio=1.5,
            leader=True,
            relative_strength=1.4,
        )
        first = engine.evaluate(self._snapshot(datetime(2026, 7, 31, 9, 35), theme=weak), [])
        second = engine.evaluate(self._snapshot(datetime(2026, 7, 31, 9, 40), theme=confirmed), [])
        self.assertNotEqual(first.opportunity_states["ai_software_apps"], "确认")
        self.assertEqual(second.opportunity_states["ai_software_apps"], "确认")
        self.assertFalse(second.alerts[0].suggested_risk_change["new_risk_authorized"])

        invalidated = self._theme(
            theme_id="ai_software_apps",
            from_open=-0.5,
            vwap=-0.5,
            breadth_open=0.25,
            breadth_vwap=0.25,
            volume_ratio=1.0,
            leader=False,
            relative_strength=-0.5,
        )
        third = engine.evaluate(
            self._snapshot(datetime(2026, 7, 31, 9, 45), theme=invalidated),
            [],
        )
        self.assertEqual(third.opportunity_states["ai_software_apps"], "失效")
        self.assertEqual(third.alerts[0].event_state, "invalidation")

    def test_reentry_guard_blocks_price_only_and_account_floor(self) -> None:
        engine = ReentryGuardEngine()
        timepoint = datetime(2026, 7, 31, 11, 0)
        price_only = self._snapshot(
            timepoint,
            daily_pnl=20000,
            theme=self._theme(
                from_open=-3.2,
                vwap=-1.0,
                breadth_vwap=0.25,
                no_new_low=False,
                higher_low=False,
            ),
        )
        state = ReentryPositionState("ai_hardware_semiconductor", "09:25", 0.5, 1.18, account_profit_floor=16470)
        alert = engine.evaluate(price_only, [state]).alerts[0]
        self.assertEqual(alert.action_state, "reentry_blocked")
        repaired_but_floor_broken = self._snapshot(
            timepoint + timedelta(minutes=10),
            daily_pnl=15000,
            theme=self._theme(
                from_open=-3.1,
                vwap=0.5,
                breadth_vwap=0.75,
                no_new_low=True,
                higher_low=True,
                reclaimed_vwap=True,
            ),
        )
        alert = engine.evaluate(repaired_but_floor_broken, [state]).alerts[0]
        self.assertEqual(alert.action_state, "reentry_blocked")
        self.assertTrue(any("保护线" in item for item in alert.evidence))
        second_lock = ReentryPositionState(
            "ai_hardware_semiconductor", "09:25", 0.5, 1.18,
            reentry_count=1, post_reentry_low_broken=True, account_profit_floor=10000,
        )
        alert = engine.evaluate(repaired_but_floor_broken, [second_lock]).alerts[0]
        self.assertEqual(alert.action_state, "reentry_blocked")
        self.assertTrue(any("第二次接回" in item for item in alert.evidence))

    def test_confirmed_sale_blocks_price_only_reentry_immediately_without_waiting_for_three_pct_drop(self) -> None:
        engine = ReentryGuardEngine()
        timestamp = datetime(2026, 7, 31, 9, 36)
        returned_to_sale_price = self._snapshot(
            timestamp,
            daily_pnl=30000.0,
            theme=self._theme(
                from_open=-0.1,
                vwap=-0.1,
                breadth_vwap=0.5,
                no_new_low=False,
                higher_low=False,
            ),
        )
        state = ReentryPositionState(
            "ai_hardware_semiconductor",
            "2026-07-31T09:25:00",
            0.5,
            1.18,
        )
        alerts = engine.evaluate(returned_to_sale_price, [state]).alerts
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].action_state, "reentry_blocked")
        evidence = " ".join(alerts[0].evidence)
        self.assertIn("09:25", evidence)
        self.assertIn("1.18", evidence)

    def test_reentry_requires_five_minutes_structure_and_locks_second_attempt_after_new_low(self) -> None:
        engine = ReentryGuardEngine()
        timestamp = datetime(2026, 7, 31, 10, 10)
        sale = ReentryPositionState(
            "ai_hardware_semiconductor", "2026-07-31T09:25:00", 0.5, 1.18,
        )
        too_early = self._snapshot(
            timestamp,
            theme=self._theme(
                from_open=-1.0, vwap=0.2, breadth_vwap=0.75,
                no_new_low=True, higher_low=True, reclaimed_vwap=True,
                minutes_without_new_low=4, price=1.16,
            ),
        )
        self.assertEqual(engine.evaluate(too_early, [sale]).alerts[0].action_state, "reentry_blocked")
        repaired = self._snapshot(
            timestamp + timedelta(minutes=2),
            theme=self._theme(
                from_open=-0.5, vwap=0.3, breadth_vwap=0.75,
                no_new_low=True, higher_low=True, reclaimed_vwap=True,
                minutes_without_new_low=6, price=1.17,
            ),
        )
        self.assertEqual(engine.evaluate(repaired, [sale]).alerts[0].action_state, "human_review_only")

        failed_first_reentry = ReentryPositionState(
            "ai_hardware_semiconductor", "2026-07-31T09:25:00", 0.5, 1.18,
            reentry_count=1, first_reentry_price=1.17,
        )
        new_low = self._snapshot(
            timestamp + timedelta(minutes=5),
            theme=self._theme(
                from_open=-1.5, vwap=0.3, breadth_vwap=0.75,
                no_new_low=False, higher_low=True, reclaimed_vwap=True,
                minutes_without_new_low=6, price=1.15,
            ),
        )
        locked = engine.evaluate(new_low, [failed_first_reentry]).alerts[0]
        self.assertEqual(locked.action_state, "reentry_blocked")
        self.assertTrue(any("第二次接回锁死" in item for item in locked.evidence))

    def test_execution_ledger_fields_feed_reentry_state_without_zero_inference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "execution_ledger.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "symbol": "588200.SH",
                        "target_id": "ai_hardware_semiconductor",
                        "side": "sell",
                        "quantity": 500.0,
                        "available_quantity": 1000.0,
                        "sold_at": "2026-07-31T09:25:00",
                        "sale_price": 1.18,
                        "source": "user_confirmed_broker_execution",
                        "user_confirmed": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            states = load_reentry_states(path)
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].sold_at, "2026-07-31T09:25:00")
        self.assertEqual(states[0].sale_price, 1.18)
        self.assertEqual(states[0].quantity, 500.0)
        self.assertEqual(states[0].available_quantity, 1000.0)

    def test_execution_ledger_is_append_only_idempotent_and_buy_needs_real_fill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "execution_ledger.jsonl"
            sale = {
                "symbol": "588200.SH", "target_id": "ai_hardware_semiconductor",
                "side": "sell", "quantity": 500.0, "available_quantity": 1000.0,
                "sold_at": "2026-07-31T09:25:00", "sale_price": 1.18,
                "source": "user_confirmed_broker_execution", "user_confirmed": True,
            }
            first = append_execution(
                sale, path=path, confirmed_at=datetime(2026, 7, 31, 9, 26)
            )
            second = append_execution(
                sale, path=path, confirmed_at=datetime(2026, 7, 31, 9, 27)
            )
            self.assertEqual(first.execution_id, second.execution_id)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)
            self.assertEqual(len(load_executions(path)), 1)
            with self.assertRaisesRegex(ValueError, "executed_at and execution_price"):
                append_execution(
                    {**sale, "side": "buy", "quantity": 100.0},
                    path=path,
                    confirmed_at=datetime(2026, 7, 31, 10, 5),
                )
            with self.assertRaisesRegex(ValueError, "cannot exceed"):
                append_execution(
                    {**sale, "quantity": 1001.0},
                    path=path,
                    confirmed_at=datetime(2026, 7, 31, 10, 5),
                )

    def test_second_reentry_unlock_is_a_post_failure_confirmation_not_a_fake_buy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            execution_path = Path(temporary) / "execution_ledger.jsonl"
            confirmation_path = Path(temporary) / "reentry_confirmation_ledger.jsonl"
            sale_payload = {
                "symbol": "588200.SH", "target_id": "ai_hardware_semiconductor",
                "side": "sell", "quantity": 500.0, "available_quantity": 1000.0,
                "sold_at": "2026-07-31T09:25:00", "sale_price": 1.18,
                "source": "user_confirmed_broker_execution", "user_confirmed": True,
            }
            append_execution(
                sale_payload,
                path=execution_path,
                confirmed_at=datetime(2026, 7, 31, 9, 26),
            )
            first_buy = append_execution(
                {
                    **sale_payload,
                    "side": "buy", "quantity": 100.0,
                    "executed_at": "2026-07-31T10:00:00", "execution_price": 1.17,
                },
                path=execution_path,
                confirmed_at=datetime(2026, 7, 31, 10, 1),
            )
            locked = load_reentry_states(
                execution_path,
                confirmation_path=confirmation_path,
            )[0]
            self.assertFalse(locked.second_reentry_confirmed)
            confirmation = append_reentry_confirmation(
                {
                    "symbol": "588200.SH",
                    "target_id": "ai_hardware_semiconductor",
                    "sold_at": "2026-07-31T09:25:00",
                    "failed_reentry_execution_id": first_buy.execution_id,
                    "new_low_observed_at": "2026-07-31T10:08:00",
                    "source": "user_confirmed_reentry_override",
                    "user_confirmed": True,
                },
                execution_path=execution_path,
                path=confirmation_path,
                confirmed_at=datetime(2026, 7, 31, 10, 10),
            )
            unlocked = load_reentry_states(
                execution_path,
                confirmation_path=confirmation_path,
            )[0]
            self.assertTrue(unlocked.second_reentry_confirmed)
            self.assertEqual(len(load_executions(execution_path)), 2)
            self.assertEqual(len(load_reentry_confirmations(confirmation_path)), 1)
            self.assertEqual(confirmation.failed_reentry_execution_id, first_buy.execution_id)

    def test_backtest_outputs_all_required_strategies_and_unknown_actual(self) -> None:
        snapshots = [
            self._portfolio_snapshot(datetime(2026, 7, 31, 9, 24), 11.0, 7.0, 0.0),
            self._portfolio_snapshot(datetime(2026, 7, 31, 9, 25), 11.0, 7.0, 0.0),
            self._portfolio_snapshot(datetime(2026, 7, 31, 10, 0), 10.5, 7.0, -0.5),
            self._portfolio_snapshot(datetime(2026, 7, 31, 14, 0), 9.5, 7.0, -3.5),
            self._portfolio_snapshot(datetime(2026, 7, 31, 15, 0), 9.0, 7.0, -4.0),
        ]
        result = compare_strategies(
            snapshots,
            technology_theme_ids=["ai_hardware_semiconductor"],
        )
        self.assertEqual(len(result["strategies"]), 9)
        self.assertEqual(result["actual_comparison"]["status"], "unknown")
        self.assertTrue(all(item["improvement_vs_actual"] is None for item in result["strategies"]))
        unconditional = next(item for item in result["strategies"] if item["strategy_id"] == "drop_3_unconditional_reentry")
        self.assertEqual(unconditional["trade_count"], 2)
        self.assertEqual(unconditional["reentry_success_rate_pct"], 0.0)

    def _bar(
        self,
        timestamp: datetime,
        *,
        close: float = 10.0,
        fetched_at: datetime | None = None,
    ) -> MinuteBar:
        return MinuteBar(
            symbol="588200.SH", timestamp=timestamp, open=10, high=10.2, low=9.8,
            close=close, volume=100, amount=close * 100, source_time=timestamp,
            fetched_at=fetched_at or timestamp + timedelta(minutes=5), source="fixture",
        )

    def _theme(
        self,
        *,
        theme_id: str = "ai_hardware_semiconductor",
        gap: float = 9.94,
        from_open: float = -0.5,
        vwap: float = -0.5,
        breadth_open: float = 0.75,
        breadth_vwap: float = 0.75,
        volume_ratio: float = 1.5,
        leader: bool = True,
        relative_strength: float = 1.2,
        no_new_low: bool | None = None,
        higher_low: bool | None = None,
        reclaimed_vwap: bool | None = None,
        minutes_without_new_low: int | None = None,
        price: float | None = None,
    ) -> ThemeSnapshot:
        return ThemeSnapshot(
            theme_id=theme_id, representative_etf="588200.SH",
            representative_symbols=("300308.SZ", "002463.SZ"), gap_pct=gap,
            return_pct=gap + from_open, return_from_open=from_open,
            vwap_distance=vwap, volume_ratio_same_time=volume_ratio,
            breadth_above_open=breadth_open, breadth_above_vwap=breadth_vwap,
            breadth_new_high=0.5, leader_confirmation=leader,
            external_mapping_return=2.0, relative_strength=relative_strength,
            state="fixture", no_new_low=no_new_low, higher_low=higher_low,
            reclaimed_vwap=reclaimed_vwap, reclaimed_rebound_high=False,
            minutes_without_new_low=minutes_without_new_low,
            price=price,
        )

    def _snapshot(
        self,
        timestamp: datetime,
        *,
        exposure: float = 70.0,
        daily_pnl: float = 33000,
        theme: ThemeSnapshot,
    ) -> IntradaySnapshot:
        return IntradaySnapshot(
            timestamp=timestamp, portfolio_value=500000, account_daily_pnl=daily_pnl,
            account_peak_daily_pnl=33000, pnl_giveback_ratio=max(0, (33000 - daily_pnl) / 33000),
            exposure_by_theme={theme.theme_id: exposure}, quote_freshness=(),
            theme_snapshots=(theme,), holding_snapshots=(), source_times=(timestamp,),
        )

    def _portfolio_snapshot(
        self,
        timestamp: datetime,
        technology_price: float,
        power_price: float,
        from_open: float,
    ) -> IntradaySnapshot:
        technology = HoldingSnapshot(
            symbol="588200.SH", name="科技ETF", shares=1000, available=1000,
            primary_theme_id="ai_hardware_semiconductor", price=technology_price,
            pre_close=10, open=11, market_value=technology_price * 1000,
            day_pnl=(technology_price - 10) * 1000,
            return_pct=(technology_price / 10 - 1) * 100, return_from_open=from_open,
            vwap_distance=-0.5, session_low=technology_price, no_new_low=False,
            higher_low=False, reclaimed_vwap=False, reclaimed_rebound_high=False,
            source_times=(timestamp,),
        )
        power = HoldingSnapshot(
            symbol="600011.SH", name="电力", shares=1000, available=1000,
            primary_theme_id="power", price=power_price, pre_close=7, open=7,
            market_value=power_price * 1000, day_pnl=0, return_pct=0,
            return_from_open=0, vwap_distance=0, session_low=7, no_new_low=True,
            higher_low=True, reclaimed_vwap=True, reclaimed_rebound_high=False,
            source_times=(timestamp,),
        )
        total = technology.market_value + power.market_value + 2000
        return IntradaySnapshot(
            timestamp=timestamp, portfolio_value=total,
            account_daily_pnl=technology.day_pnl,
            account_peak_daily_pnl=1000, pnl_giveback_ratio=0,
            exposure_by_theme={"ai_hardware_semiconductor": technology.market_value / total * 100},
            quote_freshness=(), theme_snapshots=(self._theme(from_open=from_open),),
            holding_snapshots=(technology, power), source_times=(timestamp,),
        )


if __name__ == "__main__":
    unittest.main()
