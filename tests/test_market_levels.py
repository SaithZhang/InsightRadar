from __future__ import annotations

from datetime import datetime, timedelta
import math
import unittest
from types import SimpleNamespace

from stock_assist.data_sources.eastmoney_klines import Candle, resample_minutes
from stock_assist.market_levels import (
    LevelZone,
    TimeframeAnalysis,
    _evidence_family,
    _intraday_confluence,
    analyze_timeframe,
    synthesize_market_view,
)


class MarketLevelsTests(unittest.TestCase):
    def test_resample_minutes_preserves_ohlcv(self) -> None:
        start = datetime(2026, 7, 14, 9, 30)
        rows = [
            Candle(start + timedelta(minutes=i), 100 + i, 101 + i, 102 + i, 99 + i, 10 + i, 1000 + i)
            for i in range(6)
        ]
        result = resample_minutes(rows, 3)
        self.assertEqual(2, len(result))
        self.assertEqual(100, result[0].open)
        self.assertEqual(103, result[0].close)
        self.assertEqual(104, result[0].high)
        self.assertEqual(99, result[0].low)
        self.assertEqual(33, result[0].volume)

    def test_analysis_emits_conditional_response(self) -> None:
        start = datetime(2026, 1, 1)
        rows = []
        for index in range(180):
            base = 3800 + math.sin(index / 5) * 35 + index * 0.45
            rows.append(Candle(start + timedelta(days=index), base - 5, base, base + 12, base - 12, 1000, 0))
        analysis = analyze_timeframe("day", rows)
        self.assertEqual("日线", analysis.label)
        self.assertTrue(analysis.response)
        self.assertTrue(any("若" in item for item in analysis.response))
        for zone in [*analysis.support_zones, *analysis.resistance_zones]:
            families = {_evidence_family(item) for item in zone.evidence}
            self.assertGreaterEqual(len(families), 2)

    def test_synthesis_never_returns_deterministic_order(self) -> None:
        start = datetime(2026, 1, 1)
        rows = []
        for index in range(180):
            base = 4000 + math.sin(index / 4) * 45 - index * 0.3
            rows.append(Candle(start + timedelta(hours=index), base + 3, base, base + 10, base - 10, 1000, 0))
        analysis = analyze_timeframe("60m", rows)
        result = synthesize_market_view([analysis])
        text = " ".join(str(item) for item in result.get("conditions", []))
        self.assertNotIn("一定", text)
        self.assertNotIn("必然", text)

    def test_intraday_confluence_uses_three_timeframe_intersection(self) -> None:
        zones = {
            "60m": LevelZone(3865, 3889, 3877, ("BOLL下轨", "近20根低点"), 2),
            "15m": LevelZone(3867, 3881, 3874, ("BOLL下轨", "分型低点"), 2),
            "3m": LevelZone(3865, 3884, 3874.5, ("MA10", "中枢边界"), 2),
        }
        items = [SimpleNamespace(timeframe=key, label=key, support_zones=(zone,)) for key, zone in zones.items()]
        result = _intraday_confluence(items, zones["60m"])
        self.assertEqual(3867, result["lower"])
        self.assertEqual(3881, result["upper"])
        self.assertEqual(3874, result["midpoint"])

    def test_synthesis_ignores_timeframes_without_support_zones(self) -> None:
        zone = LevelZone(3800, 3850, 3825, ("分型低点", "MA20"), 2)

        def item(timeframe: str, zones: tuple[LevelZone, ...]) -> TimeframeAnalysis:
            return TimeframeAnalysis(
                timeframe=timeframe,
                label=timeframe,
                as_of="2026-07-17",
                bars=120,
                latest=3900,
                latest_bar_low=3880,
                latest_bar_high=3920,
                change_pct=-1.0,
                phase="弱势",
                macd_state="零轴下",
                divergence="未识别到明确背驰",
                stroke_direction="向下",
                center=None,
                support_zones=zones,
                resistance_zones=(),
                response=(),
                data_note="",
            )

        result = synthesize_market_view([item("day", ()), item("60m", ()), item("week", (zone,))])

        self.assertEqual(result["primary_zone"]["midpoint"], 3825)


if __name__ == "__main__":
    unittest.main()
