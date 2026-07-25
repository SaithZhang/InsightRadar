from __future__ import annotations

from datetime import datetime
import unittest
from unittest.mock import patch

from stock_assist.data_sources.a_share_market import FuturesBasisObservation, IntradaySnapshot
from stock_assist.workflows.market_pulse import _fetch_futures_basis, _fetch_with_priority


class MarketPulseReliabilityTests(unittest.TestCase):
    @patch("stock_assist.workflows.market_pulse.fetch_intraday_snapshot")
    @patch("stock_assist.workflows.market_pulse.AmazingDataClient")
    def test_weekend_skips_realtime_sdk_and_uses_bounded_public_fallback(self, client_cls, public_fetch) -> None:
        public_fetch.return_value = IntradaySnapshot(
            secid="1.000001",
            code="000001",
            name="上证指数",
            label="上证指数",
            category="broad",
            price=3764.15,
            pre_close=3882.38,
            change_pct=-3.05,
            high=3800,
            low=3740,
            amount=800_000_000_000,
            update_time="2026-07-17 15:00",
        )

        snapshots, gaps = _fetch_with_priority(
            [{"code": "000001.SH", "secid": "1.000001", "label": "上证指数", "category": "broad"}],
            now=datetime(2026, 7, 19, 10, 0),
            public_timeout=3,
        )

        client_cls.assert_not_called()
        public_fetch.assert_called_once_with(
            secid="1.000001",
            label="上证指数",
            category="broad",
            timeout=3,
        )
        self.assertEqual(len(snapshots), 1)
        self.assertTrue(any("不在A股连续交易时段" in item for item in gaps))

    @patch("stock_assist.workflows.market_pulse.fetch_iwencai_futures_basis")
    @patch("stock_assist.workflows.market_pulse.AmazingDataClient")
    def test_weekend_futures_basis_uses_dated_iwencai_close_without_sdk_login(
        self,
        client_cls,
        iwencai_fetch,
    ) -> None:
        iwencai_fetch.return_value = (
            [
                FuturesBasisObservation(
                    family="IF",
                    contract="IF2608.CFE",
                    underlying_code="000300.SH",
                    underlying_label="沪深300",
                    current_time="2026-07-17 15:00",
                    previous_time="",
                    future_price=4505.0,
                    spot_price=4529.0953,
                    future_change=None,
                    spot_change=None,
                    basis=-24.0953,
                    previous_basis=None,
                    basis_change=None,
                    basis_pct=-0.5321,
                    as_of_date="2026-07-17",
                    quote_kind="completed_close",
                    source="同花顺问财 OpenAPI close snapshot",
                )
            ],
            [],
        )

        rows, gaps = _fetch_futures_basis({}, now=datetime(2026, 7, 19, 10, 0))

        client_cls.assert_not_called()
        self.assertEqual(len(rows), 1)
        self.assertEqual(gaps, [])
        iwencai_fetch.assert_called_once()
        self.assertFalse(iwencai_fetch.call_args.kwargs["require_same_day"])

    @patch("stock_assist.workflows.market_pulse.fetch_amazingdata_futures_basis")
    @patch("stock_assist.workflows.market_pulse.fetch_iwencai_futures_basis")
    @patch("stock_assist.workflows.market_pulse.AmazingDataClient")
    def test_live_session_falls_back_to_amazingdata_when_iwencai_is_stale(
        self,
        client_cls,
        iwencai_fetch,
        amazingdata_fetch,
    ) -> None:
        client = client_cls.return_value
        iwencai_fetch.side_effect = RuntimeError("previous close is stale")
        amazingdata_fetch.return_value = ([], ["AmazingData empty"])

        rows, gaps = _fetch_futures_basis({}, now=datetime(2026, 7, 20, 10, 0))

        self.assertEqual(rows, [])
        self.assertTrue(any("同花顺问财" in item for item in gaps))
        self.assertTrue(any("AmazingData empty" in item for item in gaps))
        amazingdata_fetch.assert_called_once()
        client.logout.assert_called_once()


if __name__ == "__main__":
    unittest.main()
