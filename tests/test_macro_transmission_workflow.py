from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stock_assist.data_sources.global_markets import MarketDailyBar
from stock_assist.risk_watch import (
    DailyPoint,
    DailySeries,
    PortfolioRiskProfile,
)
from stock_assist.workflows.risk_watch import (
    _load_macro_shadow,
    _parse_macro_events,
    build_risk_watch_bundle,
)


def stable_risk_series() -> dict[str, DailySeries]:
    start = date(2026, 1, 1)
    points = tuple(
        DailyPoint(start + timedelta(days=index), 100.0 + index * 0.05)
        for index in range(220)
    )
    return {
        key: DailySeries(
            key,
            key,
            f"https://example.test/{key}",
            points,
        )
        for key in (
            "all_a",
            "shanghai",
            "chinext",
            "star50",
            "csi1000",
            "sp500",
            "qqq",
            "sox",
            "kospi",
            "nikkei",
        )
    }


def shadow_state(status: str = "confirmed") -> dict[str, object]:
    return {
        "status": status,
        "triggered_rule_ids": ["oil_rates_tech_triple_confirmation"],
        "blocked_rule_ids": [],
        "evidence": ["verified fixture"],
        "counter_evidence": [],
        "gaps": [],
        "next_review_condition": "next completed close",
    }


def confirmed_shadow() -> dict[str, object]:
    state = shadow_state()
    return {
        "as_of": "2026-07-20",
        "energy_supply_shock": state,
        "duration_pressure": state,
        "korea_import_stress": state,
        "metrics": {
            "brent_5d_return": 0.1,
            "us10y_5d_change_pct_points": 0.2,
            "qqq_sp500_5d_relative": -0.05,
            "sox_sp500_5d_relative": -0.06,
            "kospi_sp500_5d_relative": -0.05,
        },
        "sources": [
            {
                "key": "brent",
                "url": "https://example.test/brent",
                "as_of": "2026-07-19",
                "fetched_at": "2026-07-20T07:30:00+00:00",
                "timezone": "Asia/Shanghai",
            }
        ],
        "calibration_status": "insufficient_events",
        "independent_event_count": 9,
        "calibration": {
            "calibration_status": "insufficient_events",
            "independent_event_count": 9,
            "in_sample_event_count": 8,
            "out_of_sample_event_count": 1,
            "outcomes": [],
            "threshold_sensitivity": [],
            "authority": "diagnostic_only",
        },
        "authority": "diagnostic_only",
        "data_gaps": [],
    }


def unavailable_shadow() -> dict[str, object]:
    unavailable = shadow_state("unavailable")
    unavailable["gaps"] = ["macro source unavailable"]
    return {
        "as_of": "2026-07-20",
        "energy_supply_shock": unavailable,
        "duration_pressure": unavailable,
        "korea_import_stress": unavailable,
        "metrics": {},
        "sources": [],
        "calibration_status": "unavailable",
        "independent_event_count": 0,
        "authority": "diagnostic_only",
        "data_gaps": ["macro source unavailable"],
    }


class MacroTransmissionWorkflowTests(unittest.TestCase):
    def _config_path(self, directory: str) -> Path:
        path = Path(directory) / "risk-watch.json"
        path.write_text("{}", encoding="utf-8")
        return path

    @patch(
        "stock_assist.workflows.risk_watch.fetch_a_share_crowding",
        side_effect=RuntimeError("fixture unavailable"),
    )
    @patch(
        "stock_assist.workflows.risk_watch._load_macro_shadow",
        return_value=confirmed_shadow(),
    )
    @patch(
        "stock_assist.workflows.risk_watch._fetch_series",
        return_value=(stable_risk_series(), []),
    )
    @patch(
        "stock_assist.workflows.risk_watch._load_profile",
        return_value=(PortfolioRiskProfile(), []),
    )
    def test_shadow_is_rendered_without_mutating_risk_state(
        self,
        load_profile: object,
        fetch_series: object,
        load_macro_shadow: object,
        fetch_crowding: object,
    ) -> None:
        with TemporaryDirectory() as directory:
            payload, markdown, html = build_risk_watch_bundle(
                self._config_path(directory),
                as_of="2026-07-20",
                replay_start="2026-07-01",
            )
        self.assertEqual(
            "diagnostic_only",
            payload["macro_transmission"]["authority"],
        )
        self.assertEqual(
            payload["latest"]["level"],
            payload["replay"]["rows"][-1]["level"],
        )
        self.assertIn("能源—科技宏观传导（影子）", markdown)
        self.assertIn("https://example.test/brent", markdown)
        self.assertIn('id="macro-transmission-shadow"', html)
        self.assertNotIn(
            "macro_transmission",
            {
                signal["family"]
                for signal in payload["latest"]["signals"]
            },
        )

    @patch(
        "stock_assist.workflows.risk_watch.fetch_a_share_crowding",
        side_effect=RuntimeError("fixture unavailable"),
    )
    @patch(
        "stock_assist.workflows.risk_watch._load_macro_shadow",
        side_effect=[unavailable_shadow(), confirmed_shadow()],
    )
    @patch(
        "stock_assist.workflows.risk_watch._fetch_series",
        return_value=(stable_risk_series(), []),
    )
    @patch(
        "stock_assist.workflows.risk_watch._load_profile",
        return_value=(PortfolioRiskProfile(), []),
    )
    def test_shadow_never_changes_actions_alerts_or_budget(
        self,
        load_profile: object,
        fetch_series: object,
        load_macro_shadow: object,
        fetch_crowding: object,
    ) -> None:
        with TemporaryDirectory() as directory:
            config_path = self._config_path(directory)
            unavailable, _, _ = build_risk_watch_bundle(
                config_path,
                as_of="2026-07-20",
                replay_start="2026-07-01",
            )
            confirmed, _, _ = build_risk_watch_bundle(
                config_path,
                as_of="2026-07-20",
                replay_start="2026-07-01",
            )
        self.assertEqual(unavailable["latest"], confirmed["latest"])
        self.assertEqual(unavailable["actions"], confirmed["actions"])
        self.assertEqual(unavailable["alerts"], confirmed["alerts"])
        self.assertEqual(
            unavailable["event_alerts"],
            confirmed["event_alerts"],
        )

    @patch(
        "stock_assist.workflows.risk_watch.fetch_yahoo_history",
        side_effect=TimeoutError("provider timeout"),
    )
    def test_provider_failure_returns_explicit_gap(self, fetch_history: object) -> None:
        result = _load_macro_shadow(date(2026, 7, 20))
        self.assertEqual("diagnostic_only", result["authority"])
        self.assertEqual("unavailable", result["calibration_status"])
        self.assertTrue(
            any("provider timeout" in gap for gap in result["data_gaps"])
        )

    @patch("stock_assist.workflows.risk_watch.fetch_yahoo_history")
    def test_macro_shadow_exposes_only_last_30_completed_closes(
        self,
        fetch_history: object,
    ) -> None:
        start = date(2026, 5, 1)
        bars = [
            MarketDailyBar(start + timedelta(days=index), 100.0 + index)
            for index in range(90)
        ]
        fetch_history.return_value = bars

        result = _load_macro_shadow(date(2026, 7, 20))

        brent = result["series_30d"]["brent"]
        self.assertEqual(len(brent["points"]), 30)
        self.assertEqual(brent["points"][-1]["date"], "2026-07-20")
        self.assertEqual(brent["points"][-1]["close"], 180.0)
        self.assertEqual(brent["as_of"], "2026-07-20")
        self.assertTrue(brent["source"].startswith("https://"))

    @patch(
        "stock_assist.workflows.risk_watch.fetch_yahoo_history",
        side_effect=TimeoutError("provider timeout"),
    )
    def test_macro_shadow_failure_keeps_empty_series_contract(
        self,
        fetch_history: object,
    ) -> None:
        result = _load_macro_shadow(date(2026, 7, 20))

        self.assertEqual(result["series_30d"], {})
        self.assertEqual(result["authority"], "diagnostic_only")
        self.assertTrue(
            any("provider timeout" in gap for gap in result["data_gaps"])
        )

    def test_malformed_event_is_rejected_without_aborting_other_events(self) -> None:
        events, gaps = _parse_macro_events(
            [
                {
                    "event_id": "bad",
                    "event_type": "supply_disruption",
                    "published_at": "2026-07-01T00:00:00+00:00",
                    "confirmed_at": "not-a-time",
                    "active_from": "2026-07-01",
                    "verification_status": "official",
                    "source_url": "http://not-secure.test/event",
                },
                {
                    "event_id": "good",
                    "event_type": "supply_disruption",
                    "published_at": "2026-07-01T00:00:00+00:00",
                    "confirmed_at": "2026-07-01T01:00:00+00:00",
                    "active_from": "2026-07-01",
                    "active_until": None,
                    "verification_status": "official",
                    "source_url": "https://example.test/event",
                },
            ]
        )
        self.assertEqual(["good"], [event.event_id for event in events])
        self.assertTrue(any("bad" in gap for gap in gaps))


if __name__ == "__main__":
    unittest.main()
