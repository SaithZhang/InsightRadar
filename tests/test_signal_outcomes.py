from __future__ import annotations

import json
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd

from stock_assist.data_sources.contracts import (
    PriceBasis,
    ProviderResult,
    ProviderStatus,
)
from stock_assist.signal_outcomes import (
    build_outcome_snapshot,
    price_basis_quarantine_reason,
    refresh_signal_outcomes,
)

CODE = "900001.SH"


def _daily_frame(
    code: str = CODE,
    closes: tuple[float, ...] = (10.0, 11.0),
) -> pd.DataFrame:
    trade_dates = pd.bdate_range(end="2026-07-31", periods=len(closes))
    return pd.DataFrame(
        {
            "code": [code] * len(closes),
            "trade_date": trade_dates,
            "open": closes,
            "high": [value + 0.2 for value in closes],
            "low": [value - 0.2 for value in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
            "amount": [10000.0] * len(closes),
        }
    )


def _provider_result(
    *,
    status: ProviderStatus = "ok",
    gaps: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
    price_basis: PriceBasis = "unadjusted",
    frame: pd.DataFrame | None = None,
) -> ProviderResult[dict[str, pd.DataFrame]]:
    data = frame if frame is not None else _daily_frame()
    return ProviderResult(
        provider="amazingdata",
        schema_version="daily-ohlcv/v1",
        source_time=None,
        fetched_at=datetime.fromisoformat("2026-07-31T15:05:00+08:00"),
        trade_date=(data["trade_date"].iloc[-1].date() if not data.empty else None),
        status=status,
        gaps=gaps,
        errors=errors,
        price_basis=price_basis,
        data={CODE: data},
    )


class _ContractOnlyClient:
    def __init__(self, result: ProviderResult[dict[str, pd.DataFrame]]) -> None:
        self.result = result
        self.calls: list[tuple[list[str], int, int]] = []

    def query_daily_kline_result(
        self,
        codes: list[str],
        begin_date: int,
        end_date: int,
    ) -> ProviderResult[dict[str, pd.DataFrame]]:
        self.calls.append((codes, begin_date, end_date))
        return self.result

    def __getattr__(self, name: str) -> object:
        if name == "query_daily_kline":
            raise AssertionError("bare query_daily_kline bypassed ProviderResult")
        raise AttributeError(name)


def _signal(*, reason: str = "规则保持不变") -> dict[str, object]:
    return {
        "signal_date": "2026-07-30",
        "code": CODE,
        "name": "合成标的",
        "action": "持有",
        "reason": reason,
    }


def _refresh(
    result: ProviderResult[dict[str, pd.DataFrame]],
    *,
    signal: dict[str, object] | None = None,
    existing: dict[str, object] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], _ContractOnlyClient]:
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        ledger = root / "signal_outcomes.jsonl"
        reports = root / "reports"
        reports.mkdir()
        if existing is not None:
            ledger.write_text(json.dumps(existing, ensure_ascii=False) + "\n", encoding="utf-8")
        client = _ContractOnlyClient(result)
        snapshot = refresh_signal_outcomes(
            client,
            [signal or _signal()] if existing is None else (),
            report_dir=reports,
            ledger_path=ledger,
            as_of=date(2026, 7, 31),
        )
        row = json.loads(ledger.read_text(encoding="utf-8"))
    return snapshot, row, client


class SignalOutcomeProviderContractTests(unittest.TestCase):
    def test_ok_uses_contract_only_and_calculates_return(self) -> None:
        snapshot, row, client = _refresh(_provider_result())
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(row["return_1d"], 0.1)
        self.assertEqual(row["provider_status"], "ok")
        self.assertEqual(row["evaluation_status"], "eligible")
        self.assertEqual(row["evaluation_source"], "provider-contract")
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 1)

    def test_partial_requires_an_explicit_safe_gap_allowlist(self) -> None:
        cases = (
            (f"{CODE}:timestamps_reordered", True),
            (f"{CODE}:stale_trade_date:2026-07-30<2026-07-31", False),
            (f"{CODE}:unrecognised_gap", False),
        )
        for gap, eligible in cases:
            with self.subTest(gap=gap):
                snapshot, row, _ = _refresh(
                    _provider_result(status="partial", gaps=(gap,))
                )
                self.assertEqual(row["evaluation_status"], "eligible" if eligible else "quarantined")
                self.assertEqual(snapshot["horizons"]["1d"]["matured"], int(eligible))

    def test_quarantined_discontinuity_uses_structured_gap(self) -> None:
        gap = f"{CODE}:price_discontinuity:0.618819"
        snapshot, row, _ = _refresh(
            _provider_result(status="quarantined", gaps=(gap,))
        )
        self.assertEqual(snapshot["tracked_signals"], 0)
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 0)
        self.assertEqual(row["evaluation_status"], "quarantined")
        self.assertIn(gap, row["quarantine_reason"])

    def test_invalid_contract_excludes_residual_outcome_fields(self) -> None:
        existing = {
            **_signal(),
            "signal_id": f"2026-07-30:{CODE}",
            "action_class": "hold",
            "status": "complete",
            "return_1d": 0.25,
            "effect_1d": 0.25,
            "hit_1d": True,
        }
        snapshot, row, _ = _refresh(
            _provider_result(status="invalid", errors=(f"{CODE}:code_mismatch",)),
            existing=existing,
        )
        self.assertEqual(row["provider_status"], "invalid")
        self.assertEqual(row["evaluation_status"], "quarantined")
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 0)

    def test_empty_missing_series_stays_pending(self) -> None:
        empty = _daily_frame().iloc[0:0]
        snapshot, row, _ = _refresh(
            _provider_result(
                status="empty",
                gaps=(f"{CODE}:missing_series",),
                frame=empty,
            )
        )
        self.assertEqual(row["provider_status"], "empty")
        self.assertEqual(row["evaluation_status"], "pending")
        self.assertEqual(row["status"], "pending")
        self.assertNotIn("reference_price", row)
        self.assertNotIn("return_1d", row)
        self.assertEqual(snapshot["pending_signals"], 1)
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 0)

    def test_unknown_or_non_price_basis_fails_closed(self) -> None:
        for basis in ("unknown", "not_applicable"):
            with self.subTest(price_basis=basis):
                snapshot, row, _ = _refresh(_provider_result(price_basis=basis))
                self.assertEqual(row["evaluation_status"], "quarantined")
                self.assertIn(f"price_basis={basis}", row["quarantine_reason"])
                self.assertEqual(snapshot["horizons"]["1d"]["matured"], 0)

    def test_price_basis_must_remain_consistent_across_evaluations(self) -> None:
        existing = {
            **_signal(),
            "signal_id": f"2026-07-30:{CODE}",
            "action_class": "hold",
            "record_schema_version": "signal-outcome/v2",
            "evaluation_source": "provider-contract",
            "price_basis": "forward_adjusted",
            "evaluation_status": "eligible",
            "status": "partial",
        }
        snapshot, row, _ = _refresh(_provider_result(), existing=existing)

        self.assertEqual(row["evaluation_status"], "quarantined")
        self.assertIn("price_basis_changed", row["quarantine_reason"])
        self.assertEqual((row["price_basis"], row["provider_price_basis"]), ("forward_adjusted", "unadjusted"))
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 0)

    def test_new_records_never_use_legacy_reason_regex(self) -> None:
        reason = "收盘价 10.00 低于20日线 100.00"
        self.assertIsNotNone(price_basis_quarantine_reason(reason, 10.0))

        snapshot, row, _ = _refresh(_provider_result(), signal=_signal(reason=reason))

        self.assertEqual(row["evaluation_status"], "eligible")
        self.assertEqual(snapshot["tracked_signals"], 1)
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 1)


class SignalOutcomeLegacyCompatibilityTests(unittest.TestCase):
    def test_unknown_structured_marker_fails_closed_without_legacy_fallback(self) -> None:
        snapshot: Any = build_outcome_snapshot(
            [{"record_schema_version": "signal-outcome/v3", "evaluation_source": "provider-contract", "action_class": "hold", "return_1d": 0.2}]
        )
        self.assertEqual(snapshot["tracked_signals"], 0)
        self.assertEqual(snapshot["quarantined_signals"], 1)
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 0)

    def test_legacy_text_fallback_is_limited_to_unversioned_rows(self) -> None:
        records = [
            {
                "signal_id": "2026-07-28:900002.SH",
                "signal_date": "2026-07-28",
                "code": "900002.SH",
                "action_class": "risk_reduce",
                "reason": "收盘价 1.18 低于20日线 3.40",
                "reference_price": 1.18,
                "return_1d": -0.02,
                "effect_1d": 0.02,
                "hit_1d": True,
                "status": "partial",
            },
            {
                "signal_id": "2026-07-28:900003.SH",
                "signal_date": "2026-07-28",
                "code": "900003.SH",
                "action_class": "hold",
                "reason": "收盘价仍在20日线 7.03 附近",
                "reference_price": 7.16,
                "return_1d": -0.01,
                "effect_1d": -0.01,
                "hit_1d": False,
                "status": "partial",
            },
        ]

        snapshot: Any = build_outcome_snapshot(records)

        self.assertEqual(snapshot["tracked_signals"], 1)
        self.assertEqual(snapshot["quarantined_signals"], 1)
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 1)
        self.assertEqual(snapshot["quarantined_latest"][0]["evaluation_status"], "quarantined")

    def test_explicit_legacy_quarantine_remains_fail_closed(self) -> None:
        snapshot: Any = build_outcome_snapshot(
            [
                {
                    "signal_id": "2026-07-28:900002.SH",
                    "signal_date": "2026-07-28",
                    "code": "900002.SH",
                    "action_class": "hold",
                    "evaluation_status": "quarantined",
                    "return_1d": 0.01,
                    "effect_1d": 0.01,
                    "hit_1d": True,
                    "status": "partial",
                }
            ]
        )

        self.assertEqual(snapshot["tracked_signals"], 0)
        self.assertEqual(snapshot["quarantined_signals"], 1)
        self.assertEqual(snapshot["horizons"]["1d"]["matured"], 0)


if __name__ == "__main__":
    unittest.main()
