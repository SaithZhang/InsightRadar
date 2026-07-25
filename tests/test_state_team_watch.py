from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from stock_assist.state_team_watch import build_state_team_etf_proxy
from stock_assist.workflows.market_pulse import _fetch_state_team_etf_proxy


def _frame(rows: list[tuple[int, float]]) -> pd.DataFrame:
    return pd.DataFrame([{"CHANGE_DATE": day, "TOTAL_SHARE": total} for day, total in rows])


class StateTeamWatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "disclosure_as_of": "2025-12-31",
            "baseline_dates": {
                "pre_buildup": "2023-03-31",
                "pre_first_announcement": "2023-08-01",
                "pre_rescue_acceleration": "2023-10-20",
            },
            "direct_holding_gap": "直接持股待半年报核验。",
            "items": [
                {
                    "code": "510300.SH",
                    "label": "样本ETF",
                    "disclosed_state_shares": 1_000_000_000,
                    "source_label": "年报",
                    "source_url": "https://example.com/report.pdf",
                }
            ],
        }

    def test_builds_hard_lower_bound_and_baseline_changes(self) -> None:
        history = {
            "510300.SH": _frame(
                [
                    (20230331, 20_000),
                    (20230801, 30_000),
                    (20231020, 40_000),
                    (20260717, 10_000),
                ]
            )
        }

        result = build_state_team_etf_proxy(history, self.config, as_of=date(2026, 7, 19))
        row = result["rows"][0]
        summary = result["summary"]

        self.assertEqual(row["current_total_shares"], 100_000_000)
        self.assertEqual(row["minimum_exited_shares"], 900_000_000)
        self.assertEqual(row["minimum_exit_ratio"], 0.9)
        self.assertEqual(row["baselines"]["pre_buildup"]["current_change_pct"], -50.0)
        self.assertEqual(summary["state"], "ETF份额近清仓式退出")
        self.assertIn("不等于二级市场净卖出金额", result["methodology"][1])

    def test_as_of_excludes_future_observations(self) -> None:
        history = {
            "510300.SH": _frame(
                [
                    (20230331, 20_000),
                    (20260717, 10_000),
                    (20260720, 99_000),
                ]
            )
        }

        result = build_state_team_etf_proxy(history, self.config, as_of=date(2026, 7, 19))

        self.assertEqual(result["rows"][0]["current_date"], "2026-07-17")
        self.assertEqual(result["rows"][0]["current_total_shares"], 100_000_000)

    def test_recent_changes_monitor_contraction_without_claiming_current_seller(self) -> None:
        history = {
            "510300.SH": _frame(
                [
                    (20260601 + index, 30_000 - index * 1_000)
                    for index in range(21)
                ]
            )
        }

        result = build_state_team_etf_proxy(history, self.config, as_of=date(2026, 7, 19))
        row_changes = result["rows"][0]["recent_changes"]
        summary = result["summary"]

        self.assertEqual(row_changes["five_observations"]["change_pct"], -33.33)
        self.assertEqual(row_changes["twenty_observations"]["change_pct"], -66.67)
        self.assertEqual(summary["change_signal"], "ETF总份额继续收缩")
        self.assertEqual(
            summary["recent_changes"]["twenty_observations"]["lower_bound_tightening_shares"],
            200_000_000,
        )
        self.assertIn("不能证明当期卖方就是国家队", result["methodology"][3])

    def test_missing_history_remains_an_explicit_gap(self) -> None:
        result = build_state_team_etf_proxy({}, self.config, as_of=date(2026, 7, 19))

        self.assertEqual(result["rows"], [])
        self.assertTrue(any("510300.SH" in gap for gap in result["data_gaps"]))
        self.assertTrue(any("直接持股" in gap for gap in result["data_gaps"]))

    def test_change_signal_separates_short_replenishment_from_medium_contraction(self) -> None:
        totals = [30_000 - index * 1_000 for index in range(16)] + [10_000, 11_000, 12_000, 13_000, 14_000, 15_000]
        history = {
            "510300.SH": _frame(
                [(20260601 + index, total) for index, total in enumerate(totals)]
            )
        }

        result = build_state_team_etf_proxy(history, self.config, as_of=date(2026, 7, 19))

        self.assertEqual(result["summary"]["recent_changes"]["five_observations"]["change_pct"], 50.0)
        self.assertEqual(result["summary"]["recent_changes"]["twenty_observations"]["change_pct"], -48.28)
        self.assertEqual(result["summary"]["change_signal"], "短期回补、近20次仍净收缩")

    def test_workflow_fetches_all_codes_once_and_logs_out(self) -> None:
        class FakeClient:
            instances: list["FakeClient"] = []

            def __init__(self) -> None:
                self.codes: list[str] = []
                self.logged_out = False
                self.__class__.instances.append(self)

            def get_fund_share(self, codes: list[str]) -> dict[str, pd.DataFrame]:
                self.codes = codes
                return {"510300.SH": _frame([(20260717, 10_000)])}

            def logout(self) -> None:
                self.logged_out = True

        proxy, gaps = _fetch_state_team_etf_proxy(
            {"state_team_etf_proxy": self.config},
            client_cls=FakeClient,
        )

        self.assertEqual(FakeClient.instances[0].codes, ["510300.SH"])
        self.assertTrue(FakeClient.instances[0].logged_out)
        self.assertEqual(proxy["summary"]["minimum_exit_ratio"], 0.9)
        self.assertTrue(any("直接持股" in gap for gap in gaps))


if __name__ == "__main__":
    unittest.main()
