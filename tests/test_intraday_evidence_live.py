"""Opt-in live smoke; default unittest discovery never depends on market networks."""

from __future__ import annotations

import os
import time
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from stock_assist.intraday.evidence import default_service


@unittest.skipUnless(
    os.environ.get("INSIGHTRADAR_LIVE_INTRADAY") == "1",
    "set INSIGHTRADAR_LIVE_INTRADAY=1 for the optional public-provider smoke",
)
class LiveIntradayEvidenceSmoke(unittest.TestCase):
    def test_one_bounded_benchmark_request(self) -> None:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        started = time.monotonic()
        result = default_service().get_intraday("000688.SH", now.date())
        elapsed = time.monotonic() - started
        self.assertIn(result.status, {"ok", "degraded", "stale", "blocked", "no_data"})
        self.assertLess(elapsed, 10.0)
        self.assertEqual(result.trade_authority, "none")


if __name__ == "__main__":
    unittest.main()
