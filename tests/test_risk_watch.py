from __future__ import annotations

from datetime import date, timedelta
import unittest

from stock_assist.data_sources.iwencai_market import _dated_values, fetch_a_share_crowding
from stock_assist.risk_watch import DailyPoint, DailySeries, PortfolioRiskProfile, replay_risk, score_risk


class RiskWatchTests(unittest.TestCase):
    def test_score_ignores_future_points(self) -> None:
        start = date(2026, 1, 1)
        points = [DailyPoint(start + timedelta(days=index), 100 + index * 0.2) for index in range(100)]
        points.extend(DailyPoint(start + timedelta(days=100 + index), 60 - index) for index in range(5))
        full = DailySeries("all_a", "全A", "test", tuple(points))
        truncated = DailySeries("all_a", "全A", "test", tuple(points[:100]))
        as_of = points[99].day
        profile = PortfolioRiskProfile(total_exposure_pct=20, holding_weights_pct=(20,), high_beta_exposure_pct=20)
        full_score = score_risk({"all_a": full}, profile, as_of)
        truncated_score = score_risk({"all_a": truncated}, profile, as_of)
        self.assertEqual(truncated_score.score, full_score.score)
        self.assertEqual(truncated_score.metrics, full_score.metrics)

    def test_single_data_family_cannot_confirm_red(self) -> None:
        start = date(2026, 1, 1)
        points = tuple(
            DailyPoint(start + timedelta(days=index), 200 - index * 1.4)
            for index in range(100)
        )
        result = score_risk(
            {"all_a": DailySeries("all_a", "全A", "test", points)},
            PortfolioRiskProfile(),
            points[-1].day,
        )
        self.assertEqual("yellow", result.level)

    def test_replay_requires_confirmation_for_orange_or_red(self) -> None:
        start = date(2026, 1, 1)
        keys = ("all_a", "shanghai", "chinext", "star50", "csi1000", "qqq", "sox", "kospi", "nikkei")
        series = {}
        for offset, key in enumerate(keys):
            points = tuple(
                DailyPoint(start + timedelta(days=index), 200 + offset - max(0, index - 65) * 2.5)
                for index in range(100)
            )
            series[key] = DailySeries(key, key, "test", points)
        replay = replay_risk(
            series,
            PortfolioRiskProfile(
                total_exposure_pct=87,
                holding_weights_pct=(25, 22, 18),
                high_beta_exposure_pct=75,
                fomo_flag=True,
                long_horizon_pricing_flag=True,
                retail_euphoria_flag=True,
            ),
            start=start + timedelta(days=60),
            end=start + timedelta(days=99),
        )
        first_high_raw = next(item for item in replay if item.raw_level in {"orange", "red"})
        self.assertLessEqual(
            {"green": 0, "yellow": 1, "orange": 2, "red": 3}[first_high_raw.level],
            {"green": 0, "yellow": 1, "orange": 2, "red": 3}[first_high_raw.raw_level],
        )
        self.assertTrue(any(item.level in {"orange", "red"} for item in replay))
        red_index = next(index for index, item in enumerate(replay) if item.budget_level == "red")
        later_non_green = next(
            (item for item in replay[red_index + 1 :] if item.level != "red" and item.level != "green"),
            None,
        )
        if later_non_green is not None:
            self.assertEqual("red", later_non_green.budget_level)

    def test_iwencai_bracket_fields_parse_by_date(self) -> None:
        record = {
            "收盘价[20260717]": 1712.337,
            "收盘价[20260716]": 1794.131,
            "最新价": "1712.337",
        }
        self.assertEqual(
            [(date(2026, 7, 16), 1794.131), (date(2026, 7, 17), 1712.337)],
            _dated_values(record, "收盘价"),
        )

    def test_iwencai_crowding_snapshot_uses_ranked_turnover_share(self) -> None:
        from unittest.mock import patch

        stamp = "20260717"
        ranked = [
            {
                "股票代码": f"{index:06d}.SZ",
                "股票简称": f"样本{index}",
                f"成交额[{stamp}]": 100 - index,
                f"自由流通市值[{stamp}]": 1000,
            }
            for index in range(50)
        ]
        responses = [
            {"code_count": 50, "datas": ranked},
            {"datas": [{f"成交额[{stamp}]": 10000}]},
        ]
        with patch(
            "stock_assist.data_sources.iwencai_market._query_iwencai",
            side_effect=responses,
        ):
            snapshot, _ = fetch_a_share_crowding(date(2026, 7, 17))
        self.assertAlmostEqual(0.01, snapshot.top1_amount_share)
        self.assertAlmostEqual(sum(range(51, 101)) / 10000, snapshot.top50_amount_share)
        self.assertAlmostEqual(0.1, snapshot.top1_turnover_free_float)

    def test_korea_circuit_breaker_signal_stays_latched_for_ten_sessions(self) -> None:
        start = date(2026, 1, 1)
        closes = [100 + index * 0.1 for index in range(70)]
        closes.append(closes[-1] * 0.90)
        closes.extend(closes[-1] * (1 + index * 0.002) for index in range(1, 12))
        points = tuple(DailyPoint(start + timedelta(days=index), close) for index, close in enumerate(closes))
        series = {"kospi": DailySeries("kospi", "KOSPI", "test", points)}
        latched = score_risk(series, PortfolioRiskProfile(), points[75].day)
        expired = score_risk(series, PortfolioRiskProfile(), points[-1].day)
        self.assertIn("korea_circuit_breaker_window", {signal.key for signal in latched.signals})
        self.assertNotIn("korea_circuit_breaker_window", {signal.key for signal in expired.signals})

    def test_us_index_shock_opens_generic_event_window(self) -> None:
        start = date(2026, 1, 1)
        closes = [100 + index * 0.1 for index in range(70)]
        closes.append(closes[-1] * 0.95)
        closes.extend(closes[-1] * 1.002 for _ in range(5))
        points = tuple(DailyPoint(start + timedelta(days=index), close) for index, close in enumerate(closes))
        result = score_risk(
            {"qqq": DailySeries("qqq", "QQQ", "test", points)},
            PortfolioRiskProfile(),
            points[-1].day,
        )
        self.assertIn("qqq_shock_window", {signal.key for signal in result.signals})

    def test_second_korea_circuit_breaker_escalates_within_twenty_sessions(self) -> None:
        start = date(2026, 1, 1)
        closes = [100 + index * 0.1 for index in range(70)]
        closes.append(closes[-1] * 0.90)
        closes.extend(closes[-1] * 1.01 for _ in range(10))
        closes.append(closes[-1] * 0.90)
        points = tuple(DailyPoint(start + timedelta(days=index), close) for index, close in enumerate(closes))
        result = score_risk(
            {"kospi": DailySeries("kospi", "KOSPI", "test", points)},
            PortfolioRiskProfile(),
            points[-1].day,
        )
        self.assertIn("korea_second_circuit_breaker", {signal.key for signal in result.signals})


if __name__ == "__main__":
    unittest.main()
