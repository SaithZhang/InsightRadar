from __future__ import annotations

from datetime import date, datetime, timezone
from threading import Lock
from time import sleep
import unittest
from unittest.mock import patch

from stock_assist.data_sources.global_markets import (
    MARKET_GROUPS,
    MarketIndexSnapshot,
    _history_bars,
    fetch_global_market_groups,
)


class GlobalMarketHistoryTests(unittest.TestCase):
    def test_snapshot_requests_overlap_instead_of_accumulating_timeouts(self) -> None:
        active = 0
        max_active = 0
        lock = Lock()

        def slow_snapshot(
            symbol: str,
            name: str,
            region: str,
            timeout: float,
        ) -> MarketIndexSnapshot:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            sleep(0.03)
            with lock:
                active -= 1
            return MarketIndexSnapshot(region, symbol, name, 1.0, 0.0)

        with patch(
            "stock_assist.data_sources.global_markets._fetch_yahoo_chart",
            side_effect=slow_snapshot,
        ):
            groups = fetch_global_market_groups(timeout=0.01)

        self.assertEqual(
            sum(len(items) for items in groups.values()),
            sum(len(items) for items in MARKET_GROUPS.values()),
        )
        self.assertGreater(max_active, 1)

    def test_history_date_uses_exchange_timezone_not_host_timezone(self) -> None:
        timestamp = int(
            datetime(2026, 7, 23, 0, 30, tzinfo=timezone.utc).timestamp()
        )
        result = {
            "meta": {
                "exchangeTimezoneName": "America/New_York",
                "gmtoffset": -14400,
            },
            "timestamp": [timestamp],
            "indicators": {"quote": [{"close": [100.0], "volume": [1000]}]},
        }
        bars = _history_bars(result)
        self.assertEqual(date(2026, 7, 22), bars[0].day)

    def test_unknown_timezone_uses_declared_offset(self) -> None:
        timestamp = int(
            datetime(2026, 7, 23, 0, 30, tzinfo=timezone.utc).timestamp()
        )
        result = {
            "meta": {"exchangeTimezoneName": "Unknown/Zone", "gmtoffset": -14400},
            "timestamp": [timestamp],
            "indicators": {"quote": [{"close": [100.0], "volume": [1000]}]},
        }
        bars = _history_bars(result)
        self.assertEqual(date(2026, 7, 22), bars[0].day)

    def test_non_positive_or_missing_closes_are_filtered(self) -> None:
        timestamps = [
            int(datetime(2026, 7, day, tzinfo=timezone.utc).timestamp())
            for day in (20, 21, 22, 23)
        ]
        result = {
            "meta": {"exchangeTimezoneName": "UTC", "gmtoffset": 0},
            "timestamp": timestamps,
            "indicators": {
                "quote": [
                    {
                        "close": [100.0, 0.0, -1.0, None],
                        "volume": [1000, 1000, 1000, 1000],
                    }
                ]
            },
        }
        bars = _history_bars(result)
        self.assertEqual([100.0], [bar.close for bar in bars])


if __name__ == "__main__":
    unittest.main()
