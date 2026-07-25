from __future__ import annotations

from datetime import date, timedelta
import unittest

from stock_assist.macro_transmission import (
    MacroCalibrationResult,
    MacroTransmissionObservation,
    ShadowState,
    VerifiedMacroEvent,
    calibrate_macro_transmission,
    evaluate_macro_transmission,
    replay_macro_transmission,
)
from stock_assist.risk_watch import DailyPoint, DailySeries


START = date(2026, 1, 1)
BASE_CONFIG = {
    "thresholds": {
        "oil_5d_return": 0.08,
        "yield_5d_change_pct_points": 0.15,
        "qqq_sp500_5d_relative": -0.03,
        "sox_sp500_5d_relative": -0.04,
        "kospi_sp500_5d_relative": -0.04,
        "oil_unwind_5d_return": -0.05,
    },
    "yield_divisor": 10.0,
    "event_max_age_days": 20,
    "evaluation_timezone": "Asia/Shanghai",
    "market_calendar_lag_days": {
        "brent": 0,
        "wti": 0,
        "us10y": 0,
        "sp500": 0,
        "qqq": 0,
        "sox": 0,
        "kospi": 0,
    },
}


def make_series(key: str, closes: list[float], *, start: date = START) -> DailySeries:
    return DailySeries(
        key=key,
        name=key,
        source=f"https://example.test/{key}",
        points=tuple(
            DailyPoint(start + timedelta(days=index), close)
            for index, close in enumerate(closes)
        ),
    )


def flat_inputs() -> dict[str, DailySeries]:
    return {
        key: make_series(key, [100.0] * 20)
        for key in ("brent", "wti", "sp500", "qqq", "sox", "kospi")
    } | {"us10y": make_series("us10y", [42.0] * 20)}


def supply_event(
    *,
    event_id: str = "supply-1",
    event_type: str = "supply_disruption",
    verification_status: str = "official",
    confirmed_at: str = "2026-01-18T09:00:00+00:00",
    active_from: date = date(2026, 1, 18),
) -> VerifiedMacroEvent:
    return VerifiedMacroEvent(
        event_id=event_id,
        event_type=event_type,
        published_at="2026-01-18T08:00:00+00:00",
        confirmed_at=confirmed_at,
        active_from=active_from,
        active_until=None,
        verification_status=verification_status,
        source_url=f"https://example.test/official/{event_id}",
    )


def confirmed_inputs() -> dict[str, DailySeries]:
    return {
        "brent": make_series("brent", [100.0] * 14 + [100, 102, 104, 106, 108, 110]),
        "wti": make_series("wti", [100.0] * 14 + [100, 102, 104, 106, 108, 109]),
        "us10y": make_series("us10y", [42.0] * 14 + [42, 42.5, 43, 43.5, 44, 44.5]),
        "sp500": make_series("sp500", [100.0] * 20),
        "qqq": make_series("qqq", [100.0] * 14 + [100, 99, 98, 97, 96, 95]),
        "sox": make_series("sox", [100.0] * 14 + [100, 99, 97, 95, 94, 93]),
        "kospi": make_series("kospi", [100.0] * 14 + [100, 99, 98, 97, 96, 95]),
    }


def confirmed_previous(day: date) -> MacroTransmissionObservation:
    confirmed = ShadowState(
        status="confirmed",
        triggered_rule_ids=("verified_supply_and_oil_shock",),
        blocked_rule_ids=(),
        evidence=("fixture",),
        counter_evidence=(),
        gaps=(),
        next_review_condition="watch for supply normalization",
    )
    observe = ShadowState(
        status="observe",
        triggered_rule_ids=(),
        blocked_rule_ids=(),
        evidence=(),
        counter_evidence=(),
        gaps=(),
        next_review_condition="next completed close",
    )
    return MacroTransmissionObservation(
        as_of=day,
        energy_supply_shock=confirmed,
        duration_pressure=observe,
        korea_import_stress=observe,
        metrics={},
        sources=(),
        calibration_status="not_replayed",
        independent_event_count=0,
    )


def calibration_observation(
    day: date,
    *,
    oil: bool = True,
    rates: bool = True,
    technology: bool = True,
) -> MacroTransmissionObservation:
    observe = ShadowState(
        status="observe",
        triggered_rule_ids=(),
        blocked_rule_ids=(),
        evidence=(),
        counter_evidence=(),
        gaps=(),
        next_review_condition="next completed close",
    )
    return MacroTransmissionObservation(
        as_of=day,
        energy_supply_shock=observe,
        duration_pressure=observe,
        korea_import_stress=observe,
        metrics={
            "brent_5d_return": 0.10 if oil else 0.01,
            "wti_5d_return": 0.09 if oil else 0.01,
            "us10y_5d_change_pct_points": 0.20 if rates else 0.02,
            "qqq_sp500_5d_relative": -0.05 if technology else 0.01,
            "sox_sp500_5d_relative": -0.06 if technology else 0.01,
            "kospi_sp500_5d_relative": -0.05 if technology else 0.01,
        },
        sources=(),
        calibration_status="not_replayed",
        independent_event_count=0,
    )


def calibration_series(
    *,
    start: date = date(2015, 1, 1),
    days: int = 5000,
) -> dict[str, DailySeries]:
    return {
        key: make_series(
            key,
            [100.0 + index * (0.02 + offset * 0.001) for index in range(days)],
            start=start,
        )
        for offset, key in enumerate(
            ("brent", "wti", "us10y", "sp500", "qqq", "sox", "kospi")
        )
    }


class MacroTransmissionTests(unittest.TestCase):
    def test_oil_only_stays_observe_and_cannot_confirm_duration_pressure(self) -> None:
        inputs = flat_inputs()
        inputs["brent"] = make_series(
            "brent", [100.0] * 14 + [100, 102, 104, 106, 108, 110]
        )
        result = evaluate_macro_transmission(
            inputs, date(2026, 1, 20), BASE_CONFIG
        )
        self.assertEqual("observe", result.energy_supply_shock.status)
        self.assertNotEqual("confirmed", result.duration_pressure.status)
        self.assertIn(
            "missing_verified_supply_event",
            result.energy_supply_shock.blocked_rule_ids,
        )
        self.assertEqual("diagnostic_only", result.authority)

    def test_verified_supply_rates_and_relative_weakness_confirm_joint_states(self) -> None:
        result = evaluate_macro_transmission(
            confirmed_inputs(),
            date(2026, 1, 20),
            BASE_CONFIG,
            (supply_event(),),
        )
        self.assertEqual("confirmed", result.energy_supply_shock.status)
        self.assertEqual("confirmed", result.duration_pressure.status)
        self.assertEqual("confirmed", result.korea_import_stress.status)
        self.assertIn(
            "oil_rates_tech_triple_confirmation",
            result.duration_pressure.triggered_rule_ids,
        )

    def test_future_bars_and_later_event_confirmation_are_ignored(self) -> None:
        inputs = flat_inputs()
        shocked = [100.0] * 20 + [120.0]
        inputs["brent"] = make_series("brent", shocked)
        future_event = supply_event(confirmed_at="2026-01-21T01:00:00+00:00")
        result = evaluate_macro_transmission(
            inputs,
            date(2026, 1, 20),
            BASE_CONFIG,
            (future_event,),
        )
        truncated = dict(inputs)
        truncated["brent"] = make_series("brent", shocked[:20])
        expected = evaluate_macro_transmission(
            truncated,
            date(2026, 1, 20),
            BASE_CONFIG,
        )
        self.assertEqual(expected.metrics, result.metrics)
        self.assertNotEqual("confirmed", result.energy_supply_shock.status)

    def test_ceasefire_requires_oil_unwind_and_previous_confirmation(self) -> None:
        inputs = flat_inputs()
        inputs["brent"] = make_series(
            "brent", [110.0] * 14 + [110, 108, 106, 104, 102, 100]
        )
        inputs["wti"] = make_series(
            "wti", [110.0] * 14 + [110, 108, 106, 104, 102, 100]
        )
        ceasefire = supply_event(
            event_id="ceasefire-1",
            event_type="ceasefire",
        )
        result = evaluate_macro_transmission(
            inputs,
            date(2026, 1, 20),
            BASE_CONFIG,
            (ceasefire,),
            previous=confirmed_previous(date(2026, 1, 19)),
        )
        self.assertEqual("invalidated", result.energy_supply_shock.status)
        self.assertNotEqual("confirmed", result.duration_pressure.status)
        self.assertIn(
            "technology_repair_requires_relative_price_confirmation",
            result.duration_pressure.blocked_rule_ids,
        )

    def test_missing_sp500_keeps_duration_and_korea_unavailable(self) -> None:
        inputs = confirmed_inputs()
        del inputs["sp500"]
        result = evaluate_macro_transmission(
            inputs,
            date(2026, 1, 20),
            BASE_CONFIG,
            (supply_event(),),
        )
        self.assertEqual("unavailable", result.duration_pressure.status)
        self.assertEqual("unavailable", result.korea_import_stress.status)
        self.assertIn("missing_series:sp500", result.duration_pressure.gaps)

    def test_missing_sox_is_not_misreported_as_missing_sp500(self) -> None:
        inputs = confirmed_inputs()
        del inputs["sox"]
        result = evaluate_macro_transmission(
            inputs,
            date(2026, 1, 20),
            BASE_CONFIG,
            (supply_event(),),
        )
        self.assertEqual("unavailable", result.duration_pressure.status)
        self.assertIn("missing_series:sox", result.duration_pressure.gaps)
        self.assertNotIn("missing_series:sp500", result.duration_pressure.gaps)

    def test_conflicting_primary_event_blocks_confirmation(self) -> None:
        result = evaluate_macro_transmission(
            confirmed_inputs(),
            date(2026, 1, 20),
            BASE_CONFIG,
            (
                supply_event(),
                supply_event(
                    event_id="conflict-1",
                    verification_status="conflicting",
                ),
            ),
        )
        self.assertEqual("observe", result.energy_supply_shock.status)
        self.assertIn(
            "conflicting_primary_evidence",
            result.energy_supply_shock.blocked_rule_ids,
        )

    def test_china_after_close_uses_prior_completed_us_session(self) -> None:
        inputs = flat_inputs()
        inputs["qqq"] = make_series("qqq", [100.0] * 19 + [90.0])
        same_day = evaluate_macro_transmission(
            inputs,
            date(2026, 1, 20),
            BASE_CONFIG,
        )
        lagged_config = {
            **BASE_CONFIG,
            "market_calendar_lag_days": {
                **BASE_CONFIG["market_calendar_lag_days"],
                "qqq": 1,
                "sp500": 1,
            },
        }
        prior_close = evaluate_macro_transmission(
            inputs,
            date(2026, 1, 20),
            lagged_config,
        )
        self.assertLess(same_day.metrics["qqq_sp500_5d_relative"], 0)
        self.assertEqual(0.0, prior_close.metrics["qqq_sp500_5d_relative"])

    def test_consecutive_trigger_days_form_one_independent_episode(self) -> None:
        observations = tuple(
            calibration_observation(date(2026, 1, day))
            for day in (10, 11, 12, 30)
        )
        result = calibrate_macro_transmission(
            observations,
            calibration_series(start=date(2025, 12, 1), days=120),
            {
                **BASE_CONFIG,
                "episode_gap_sessions": 10,
                "minimum_promotion_events": 60,
                "forward_horizons": [5, 20],
            },
        )
        self.assertIsInstance(result, MacroCalibrationResult)
        self.assertEqual(2, result.independent_event_count)
        self.assertEqual("insufficient_events", result.calibration_status)

    def test_sixty_independent_events_still_require_out_of_sample_rows(self) -> None:
        observations = tuple(
            calibration_observation(
                date(2016, 1, 1) + timedelta(days=index * 30)
            )
            for index in range(60)
        )
        result = calibrate_macro_transmission(
            observations,
            calibration_series(),
            {
                **BASE_CONFIG,
                "episode_gap_sessions": 20,
                "minimum_promotion_events": 60,
                "forward_horizons": [5, 20],
                "out_of_sample_start": "2025-01-01",
            },
        )
        self.assertEqual(60, result.independent_event_count)
        self.assertEqual(
            "missing_out_of_sample_events",
            result.calibration_status,
        )

    def test_calibration_reports_three_rule_sets_and_threshold_grid(self) -> None:
        observations = (
            calibration_observation(date(2026, 1, 10), rates=False, technology=False),
            calibration_observation(date(2026, 2, 10), technology=False),
            calibration_observation(date(2026, 3, 10)),
        )
        result = calibrate_macro_transmission(
            observations,
            calibration_series(start=date(2025, 12, 1), days=240),
            {
                **BASE_CONFIG,
                "episode_gap_sessions": 10,
                "minimum_promotion_events": 60,
                "forward_horizons": [5, 20],
                "threshold_sensitivity_multipliers": [0.8, 1.0, 1.2],
            },
        )
        rule_sets = {row["rule_set"] for row in result.outcomes}
        self.assertEqual(
            {"oil_only", "oil_plus_rates", "triple_confirmation"},
            rule_sets,
        )
        self.assertEqual(3, len(result.threshold_sensitivity))
        self.assertNotIn("best_threshold", result.to_dict())

    def test_missing_forward_bars_remain_visible_in_calibration(self) -> None:
        observation = calibration_observation(date(2026, 1, 30))
        result = calibrate_macro_transmission(
            (observation,),
            calibration_series(start=date(2026, 1, 1), days=30),
            {
                **BASE_CONFIG,
                "episode_gap_sessions": 10,
                "minimum_promotion_events": 60,
                "forward_horizons": [20],
            },
        )
        triple_rows = [
            row
            for row in result.outcomes
            if row["rule_set"] == "triple_confirmation"
        ]
        self.assertTrue(triple_rows)
        self.assertTrue(
            any(row["unavailable_outcomes"] > 0 for row in triple_rows)
        )

    def test_replay_uses_only_dates_at_or_before_end(self) -> None:
        inputs = confirmed_inputs()
        replay = replay_macro_transmission(
            inputs,
            START,
            date(2026, 1, 19),
            BASE_CONFIG,
            (supply_event(),),
        )
        self.assertTrue(replay)
        self.assertLessEqual(replay[-1].as_of, date(2026, 1, 19))
        self.assertTrue(all(item.authority == "diagnostic_only" for item in replay))


if __name__ == "__main__":
    unittest.main()
