from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import unittest

from stock_assist.score_state import evaluate_score_state
from stock_assist.unified_decision import _apply_market_level_authority, _market_level_state


CONFIG = json.loads((Path(__file__).parents[1] / "configs" / "decision_rules.json").read_text(encoding="utf-8"))


def observation(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "market_date": "2026-07-20",
        "market_level_state": "rebound_confirmed",
        "latest": 3830,
        "breadth_state": "up",
        "turnover_state": "not_weak",
        "is_close": False,
        "data_complete": True,
        "data_gaps": [],
        "risk_level": "green",
        "risk_veto": False,
        "hard_risk_event": False,
        "evidence_source": {"market_levels": "test", "breadth_turnover": "test"},
        "evidence_as_of": "2026-07-20 11:30",
    }
    base.update(overrides)
    return base


class ScoreStateTests(unittest.TestCase):
    def test_confirmation_creates_intraday_candidate_without_overwriting_formal(self) -> None:
        contract, _ = evaluate_score_state(observation(), {}, CONFIG)
        self.assertEqual(contract["bear_bull_score"], 2.0)
        self.assertEqual(contract["candidate_score"], 3.0)
        self.assertEqual(contract["candidate_delta"], 1.0)
        self.assertEqual(contract["score_delta"], 0.0)
        self.assertEqual(contract["finalization_status"], "candidate")
        self.assertIn("ML_CONFIRM_BREADTH_UP", contract["triggered_rule_ids"])

    def test_strong_breakout_only_finalizes_at_close_and_moves_at_most_one(self) -> None:
        contract, state = evaluate_score_state(
            observation(
                market_level_state="strong_breakout_confirmed",
                turnover_state="up",
                is_close=True,
                evidence_as_of="2026-07-20 15:00",
            ),
            {"formal_score": 2.0, "previous_formal_score": 2.0},
            CONFIG,
            now=datetime(2026, 7, 20, 15, 5),
        )
        self.assertEqual(contract["previous_score"], 2.0)
        self.assertEqual(contract["bear_bull_score"], 3.0)
        self.assertEqual(contract["score_delta"], 1.0)
        self.assertEqual(contract["finalization_status"], "finalized")
        self.assertEqual(state["formal_score"], 3.0)

    def test_support_failure_and_breadth_down_force_candidate_downgrade(self) -> None:
        contract, _ = evaluate_score_state(
            observation(market_level_state="support_failed", breadth_state="down", turnover_state="weak"),
            {"formal_score": 3.0, "previous_formal_score": 2.0},
            CONFIG,
        )
        self.assertEqual(contract["candidate_score"], 2.0)
        self.assertEqual(contract["candidate_delta"], -1.0)
        self.assertTrue(contract["downgrade_forced"])
        self.assertEqual(contract["negative_points"][0]["rule_id"], "ML_SUPPORT_FAIL_BREADTH_DOWN")

    def test_conflicting_price_breadth_turnover_changes_zero(self) -> None:
        contract, _ = evaluate_score_state(
            observation(breadth_state="down", turnover_state="up"),
            {"formal_score": 2.0},
            CONFIG,
        )
        self.assertEqual(contract["candidate_delta"], 0.0)
        self.assertEqual(contract["score_ledger"][0]["rule_id"], "SIGNAL_CONFLICT")
        self.assertIn("相互矛盾", contract["score_ledger"][0]["explanation"])

    def test_stale_or_missing_blocks_upgrade_without_substituting_zero(self) -> None:
        contract, _ = evaluate_score_state(
            observation(data_complete=False, data_gaps=["breadth stale"]),
            {"formal_score": 2.0},
            CONFIG,
        )
        self.assertEqual(contract["candidate_score"], 2.0)
        self.assertTrue(contract["upgrade_blocked"])
        self.assertIn("DATA_STALE_OR_MISSING", contract["blocked_rule_ids"])
        self.assertIn("ML_CONFIRM_BREADTH_UP", contract["blocked_rule_ids"])

    def test_same_rule_same_market_day_is_deduplicated(self) -> None:
        prior = {
            "formal_score": 3.0,
            "previous_formal_score": 2.0,
            "formal_market_date": "2026-07-20",
            "finalized_at": "2026-07-20T15:05:00",
            "finalized_rule_ids_by_date": {"2026-07-20": ["ML_STRONG_BREAKOUT_CONFIRMED"]},
        }
        contract, _ = evaluate_score_state(
            observation(market_level_state="strong_breakout_confirmed", turnover_state="up", is_close=True),
            prior,
            CONFIG,
        )
        self.assertEqual(contract["bear_bull_score"], 3.0)
        self.assertEqual(contract["candidate_delta"], 0.0)
        self.assertIn("ML_STRONG_BREAKOUT_CONFIRMED", contract["blocked_rule_ids"])
        self.assertEqual(contract["score_ledger"][0]["status"], "deduplicated")

    def test_risk_veto_allows_candidate_score_but_blocks_budget_upgrade(self) -> None:
        contract, _ = evaluate_score_state(
            observation(risk_level="red", risk_veto=True),
            {"formal_score": 2.0},
            CONFIG,
        )
        self.assertEqual(contract["candidate_score"], 3.0)
        self.assertFalse(contract["upgrade_blocked"])
        self.assertTrue(contract["risk_budget_upgrade_blocked"])
        self.assertIn("RISK_VETO", contract["blocked_rule_ids"])

    def test_zone_hysteresis_prevents_boundary_chatter_and_two_bar_gate_prevents_false_failure(self) -> None:
        levels = {
            "source_status": "current",
            "latest": 3740.0,
            "support_zone": {"lower": 3742.0, "upper": 3770.0},
            "confirmation_zone": {"lower": 3790.0, "upper": 3826.0},
            "strong_resistance_zone": {"lower": 3863.0, "upper": 3913.0},
            "daily_repair_zone": {"lower": 3944.0, "upper": 3980.0},
            "completed_below_support_bars": 1,
        }
        risk = {
            "metrics": {"all_a": {"day_return": -0.02, "ma20_gap": -0.05, "amount_percentile_60d": 0.3}}
        }
        self.assertEqual(_market_level_state(levels, risk, CONFIG), "support_testing")
        levels["latest"] = 3735.0
        self.assertEqual(_market_level_state(levels, risk, CONFIG), "below_support")
        levels["completed_below_support_bars"] = 2
        self.assertEqual(_market_level_state(levels, risk, CONFIG), "support_failed")

    def test_market_level_states_have_real_stance_and_budget_authority(self) -> None:
        stance, failed = _apply_market_level_authority(
            "条件进攻", "support_failed", {"level": "green"}, {"risk_budget_upgrade_blocked": False}
        )
        self.assertEqual(stance, "收缩风险")
        self.assertEqual(failed["risk_budget_effect"], "保持或下调")
        self.assertTrue(failed["invalidation_plan"])

        stance, stale = _apply_market_level_authority(
            "条件进攻", "stale", {"level": "green"}, {"risk_budget_upgrade_blocked": True}
        )
        self.assertEqual(stance, "等待确认")
        self.assertEqual(stale["risk_budget_effect"], "禁止上调")

        stance, held = _apply_market_level_authority(
            "防守观察", "support_held", {"level": "red"}, {"risk_budget_upgrade_blocked": True}
        )
        self.assertEqual(stance, "防守观察")
        self.assertIn("不称反转", held["stance_effect"])

        stance, breakout = _apply_market_level_authority(
            "条件进攻", "strong_breakout_confirmed", {"level": "green"}, {"risk_budget_upgrade_blocked": False}
        )
        self.assertTrue(breakout["risk_budget_upgrade_eligible"])


if __name__ == "__main__":
    unittest.main()
