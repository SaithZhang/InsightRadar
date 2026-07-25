from __future__ import annotations

from datetime import datetime
import unittest
from unittest.mock import patch

from stock_assist.data_sources.a_share_market import fetch_iwencai_futures_basis


SPOT_CLOSES = {
    "000300.SH": ("沪深300", 4529.0953),
    "000016.SH": ("上证50", 2827.6713),
    "000905.SH": ("中证500", 7513.7627),
    "000852.SH": ("中证1000", 7167.9959),
}


FUTURES_CLOSES = {
    "IF": (4505.0, 4473.8),
    "IH": (2810.6, 2796.4),
    "IC": (7444.2, 7389.0),
    "IM": (7118.8, 7065.2),
}


def _spot_payload(stamp: str = "20260717") -> dict[str, object]:
    return {
        "datas": [
            {
                "指数代码": code,
                "指数简称": label,
                f"收盘价[{stamp}]": close,
            }
            for code, (label, close) in SPOT_CLOSES.items()
        ]
    }


def _futures_payload(stamp: str = "20260717") -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for family, prices in FUTURES_CLOSES.items():
        rows.append(
            {
                "合约代码": f"{family}2607.CFE",
                "品种代码": family,
                f"收盘价[{stamp}]": prices[0] + 50,
                f"成交量[{stamp}]": 100,
                f"持仓量[{stamp}]": 0,
            }
        )
        for offset, (month, price) in enumerate(zip(("2608", "2609"), prices), start=1):
            rows.append(
                {
                    "合约代码": f"{family}{month}.CFE",
                    "品种代码": family,
                    f"收盘价[{stamp}]": price,
                    f"成交量[{stamp}]": 10_000 * offset,
                    f"持仓量[{stamp}]": 20_000 * offset,
                    f"日增仓[{stamp}]": 1_000 * offset,
                }
            )
    return {"datas": rows}


class IwencaiFuturesBasisTests(unittest.TestCase):
    @patch("stock_assist.data_sources.a_share_market._query_iwencai")
    def test_maps_aligned_closes_and_selects_nearest_positive_oi_contracts(self, query) -> None:
        query.side_effect = [_spot_payload(), _futures_payload()]

        rows, gaps = fetch_iwencai_futures_basis(now=datetime(2026, 7, 19, 10, 0))

        self.assertEqual(gaps, [])
        self.assertEqual(len(rows), 8)
        self.assertEqual([item.contract for item in rows[:2]], ["IF2608.CFE", "IF2609.CFE"])
        self.assertNotIn("IF2607.CFE", {item.contract for item in rows})
        first = rows[0]
        self.assertAlmostEqual(first.basis or 0, 4505.0 - 4529.0953, places=4)
        self.assertAlmostEqual(first.basis_pct or 0, (4505.0 / 4529.0953 - 1) * 100, places=4)
        self.assertEqual(first.as_of_date, "2026-07-17")
        self.assertEqual(first.volume, 10_000)
        self.assertEqual(first.open_interest, 20_000)
        self.assertEqual(first.open_interest_change, 1_000)
        self.assertEqual(first.quote_kind, "completed_close")
        self.assertIn("同花顺问财", first.source)
        self.assertEqual(query.call_count, 2)

    @patch("stock_assist.data_sources.a_share_market._query_iwencai")
    def test_rejects_misaligned_spot_dates(self, query) -> None:
        payload = _spot_payload()
        payload["datas"][0].pop("收盘价[20260717]")
        payload["datas"][0]["收盘价[20260716]"] = 4529.0953
        query.return_value = payload

        with self.assertRaisesRegex(RuntimeError, "dates are not aligned"):
            fetch_iwencai_futures_basis(now=datetime(2026, 7, 19, 10, 0))

    @patch("stock_assist.data_sources.a_share_market._query_iwencai")
    def test_rejects_previous_close_during_current_live_session(self, query) -> None:
        query.return_value = _spot_payload()

        with self.assertRaisesRegex(RuntimeError, "not current live session"):
            fetch_iwencai_futures_basis(
                now=datetime(2026, 7, 20, 10, 0),
                require_same_day=True,
            )

    @patch("stock_assist.data_sources.a_share_market._query_iwencai")
    def test_empty_response_retries_once_with_retry_header(self, query) -> None:
        query.side_effect = [{"datas": []}, _spot_payload(), _futures_payload()]

        rows, gaps = fetch_iwencai_futures_basis(now=datetime(2026, 7, 19, 10, 0))

        self.assertEqual(len(rows), 8)
        self.assertEqual(gaps, [])
        self.assertEqual(query.call_count, 3)
        self.assertEqual(query.call_args_list[1].kwargs["call_type"], "retry")


if __name__ == "__main__":
    unittest.main()
