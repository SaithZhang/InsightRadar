from __future__ import annotations

from datetime import date
import unittest

from stock_assist.ai_capex_watch import score_ai_capex_watch


class AiCapexWatchTests(unittest.TestCase):
    def test_future_and_unverified_evidence_do_not_score(self) -> None:
        config = {
            "companies": [
                {
                    "name": "Future",
                    "observed_at": "2026-08-01",
                    "verification_status": "official",
                    "guidance_direction": "up",
                    "ai_dc_link": "explicit",
                },
                {
                    "name": "Rumor",
                    "observed_at": "2026-07-01",
                    "verification_status": "user_claim",
                    "guidance_direction": "up",
                    "ai_dc_link": "explicit",
                },
            ]
        }
        result = score_ai_capex_watch(config, date(2026, 7, 19))
        capex = result["metrics"][0]
        self.assertIsNone(capex["score"])
        self.assertEqual("insufficient", capex["state"])
        self.assertEqual([], result["companies"])

    def test_sparse_positive_evidence_is_shrunk_toward_neutral(self) -> None:
        config = {
            "companies": [
                {
                    "name": "One",
                    "observed_at": "2026-07-01",
                    "verification_status": "official",
                    "guidance_low_billion_usd": 20,
                    "guidance_high_billion_usd": 20,
                    "prior_guidance_low_billion_usd": 10,
                    "prior_guidance_high_billion_usd": 10,
                    "guidance_direction": "up",
                    "ai_dc_link": "explicit",
                },
                {"name": "Missing"},
            ]
        }
        result = score_ai_capex_watch(config, date(2026, 7, 19))
        capex = result["metrics"][0]
        self.assertGreater(capex["score"], 50)
        self.assertLess(capex["score"], 100)
        self.assertLess(capex["coverage"], 1)

    def test_capex_and_network_strength_do_not_bypass_supplier_validation(self) -> None:
        config = {
            "companies": [
                {
                    "name": "Cloud",
                    "observed_at": "2026-07-01",
                    "verification_status": "official",
                    "guidance_low_billion_usd": 20,
                    "guidance_high_billion_usd": 20,
                    "prior_guidance_low_billion_usd": 10,
                    "prior_guidance_high_billion_usd": 10,
                    "prior_actual_capex_billion_usd": 10,
                    "guidance_direction": "up",
                    "ai_dc_link": "explicit",
                }
            ],
            "optical_evidence": [
                {
                    "observed_at": "2026-07-01",
                    "verification_status": "official",
                    "category": category,
                    "direction": "positive",
                    "strength": 1,
                }
                for category in ("network_revenue", "network_allocation", "module_demand")
            ],
            "supplier_checks": [{"label": "毛利率", "status": "pending"}],
        }
        result = score_ai_capex_watch(config, date(2026, 7, 19))
        self.assertIn("不构成追涨依据", result["conclusion"])
        self.assertTrue(any("不直接发出买卖" in item for item in result["actions"]))

    def test_stale_evidence_is_visible_as_gap(self) -> None:
        config = {
            "max_age_days": 30,
            "companies": [
                {
                    "name": "Old",
                    "observed_at": "2026-01-01",
                    "verification_status": "official",
                    "guidance_direction": "down",
                }
            ],
        }
        result = score_ai_capex_watch(config, date(2026, 7, 19))
        self.assertTrue(any("已过期" in item for item in result["data_gaps"]))


if __name__ == "__main__":
    unittest.main()
