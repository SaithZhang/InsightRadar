from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from stock_assist.intraday.archive import MinuteArchive
from stock_assist.intraday.backtest import compare_strategies
from stock_assist.intraday.contracts import (
    HoldingSnapshot,
    IntradaySnapshot,
    MinuteBar,
    ThemeSnapshot,
)
from stock_assist.intraday.rules import (
    AccountRiskEngine,
    CatalystFailureEngine,
    OpportunityRadarEngine,
    ReentryGuardEngine,
    ReentryPositionState,
)
from stock_assist.intraday.universe import load_intraday_universe


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

    def _bar(self, timestamp: datetime, *, close: float = 10.0) -> MinuteBar:
        return MinuteBar(
            symbol="588200.SH", timestamp=timestamp, open=10, high=10.2, low=9.8,
            close=close, volume=100, amount=close * 100, source_time=timestamp,
            fetched_at=timestamp + timedelta(minutes=5), source="fixture",
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
