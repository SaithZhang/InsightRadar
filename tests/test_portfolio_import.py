from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stock_assist.execution_plans import calculate_executable_trim
from stock_assist.portfolio import load_portfolio
from stock_assist.portfolio_import import (
    apply_portfolio_import,
    preview_portfolio_import,
    rerun_required_workflows,
)

HEADER = "操作\t证券代码\t证券名称\t自有股份可用\t股票余额\t成本价\t市价\t盈亏\t盈亏比例(%)\t当日盈亏\t当日盈亏比(%)\t市值\t仓位占比(%)\t交易市场\t当前持仓\t股份可用"
ROW = "\t300308\t中际旭创\t100\t100\t1336.141\t979.460\t-35668.080\t-26.695\t-13354.00\t-12.00\t97946.000\t19.17\t深Ａ\t100\t100"
TSV = f"{HEADER}\n{ROW}\n"


class PortfolioImportTests(unittest.TestCase):
    def test_shanghai_market_label_normalizes_code_for_provider_contract(self) -> None:
        synthetic_row = (
            "\tTEST01\t合成沪市ETF\t100\t100\t\t\t\t\t\t\t\t20.00"
            "\t上海Ａ股\t100\t100"
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = preview_portfolio_import(
                f"{HEADER}\n{synthetic_row}\n",
                portfolio_path=root / "portfolio.json",
                risk_profile_path=root / "risk.json",
            )

        code = preview["proposed_portfolio"]["holdings"][0]["code"]
        security_code, exchange = code.split(".")
        self.assertEqual(security_code, "TEST01")
        self.assertEqual(exchange, "SH")

    def test_saved_shanghai_market_label_is_normalized_when_loaded(self) -> None:
        with TemporaryDirectory() as tmp:
            portfolio_path = Path(tmp) / "portfolio.json"
            portfolio_path.write_text(
                json.dumps(
                    {
                        "holdings": [
                            {
                                "code": "TEST01",
                                "name": "合成沪市ETF",
                                "shares": 100,
                                "market": "上海Ａ股",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            portfolio = load_portfolio(portfolio_path)

        self.assertEqual(portfolio.holdings[0].code, "TEST01.SH")

    def test_galaxy_preview_preserves_nulls_and_shows_old_new_diff(self) -> None:
        sparse_row = "\t300308\t中际旭创\t100\t100\t\t\t\t\t\t\t\t20.00\t深Ａ\t100\t100"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            portfolio_path = root / "portfolio.json"
            risk_path = root / "risk.json"
            portfolio_path.write_text(json.dumps({"holdings": [{"code": "000001.SZ", "name": "旧持仓", "shares": 100}]}), encoding="utf-8")
            risk_path.write_text("{}", encoding="utf-8")
            preview = preview_portfolio_import(
                f"{HEADER}\n{sparse_row}\n",
                classifications={"300308.SZ": "high_beta"},
                portfolio_path=portfolio_path,
                risk_profile_path=risk_path,
            )

        holding = preview["proposed_portfolio"]["holdings"][0]
        self.assertIsNone(holding["cost"])
        self.assertIsNone(holding["market_price"])
        self.assertIsNone(holding["pnl"])
        self.assertEqual(holding["shares"], 100)
        self.assertEqual(holding["beta_classification"], "unknown")
        self.assertTrue(
            any("已忽略手工beta分类" in item for item in preview["validation"]["warnings"])
        )
        self.assertEqual({item["status"] for item in preview["differences"]}, {"added", "removed"})

    def test_unknown_beta_is_not_inferred_and_blocks_reconciliation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = preview_portfolio_import(
                TSV,
                portfolio_path=root / "portfolio.json",
                risk_profile_path=root / "risk.json",
            )
        holding = preview["proposed_portfolio"]["holdings"][0]
        self.assertEqual(holding["beta_classification"], "unknown")
        self.assertEqual(preview["risk_reconciliation"]["status"], "blocked")
        self.assertIsNone(preview["proposed_risk_profile"]["high_beta_exposure_pct"])

    def test_unapproved_apply_never_writes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            portfolio_path = root / "portfolio.json"
            risk_path = root / "risk.json"
            portfolio_path.write_text('{"old":true}', encoding="utf-8")
            risk_path.write_text('{"old":true}', encoding="utf-8")
            preview = preview_portfolio_import(
                TSV,
                classifications={"300308.SZ": "high_beta"},
                portfolio_path=portfolio_path,
                risk_profile_path=risk_path,
            )
            with self.assertRaises(PermissionError):
                apply_portfolio_import(preview, approved=False, portfolio_path=portfolio_path, risk_profile_path=risk_path, rerun=False)
            self.assertEqual(portfolio_path.read_text(encoding="utf-8"), '{"old":true}')
            self.assertEqual(risk_path.read_text(encoding="utf-8"), '{"old":true}')

    def test_approved_apply_atomically_saves_but_beta_stays_blocked_until_refresh(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            portfolio_path = root / "portfolio.json"
            risk_path = root / "risk.json"
            portfolio_path.write_text('{"holdings":[]}', encoding="utf-8")
            risk_path.write_text('{"fomo_flag":true}', encoding="utf-8")
            preview = preview_portfolio_import(
                TSV,
                classifications={"300308.SZ": "high_beta"},
                portfolio_path=portfolio_path,
                risk_profile_path=risk_path,
                as_of="2026-07-19",
            )
            result = apply_portfolio_import(
                preview,
                approved=True,
                portfolio_path=portfolio_path,
                risk_profile_path=risk_path,
                rerun=False,
                open_report=False,
            )
            saved = json.loads(portfolio_path.read_text(encoding="utf-8"))
            risk = json.loads(risk_path.read_text(encoding="utf-8"))

            self.assertTrue(result["saved"])
            self.assertTrue(Path(result["portfolio_backup"]).exists())
            self.assertTrue(Path(result["risk_profile_backup"]).exists())
            self.assertEqual(saved["risk_reconciliation"]["status"], "blocked")
            self.assertEqual(saved["beta_model_status"], "pending_refresh")
            self.assertEqual(risk["total_exposure_pct"], 19.17)
            self.assertIsNone(risk["high_beta_exposure_pct"])
            self.assertTrue(risk["fomo_flag"])

    def test_reruns_are_serial_and_stop_on_failure(self) -> None:
        calls: list[str] = []

        def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(command[-1])
            return subprocess.CompletedProcess(command, 0, stdout=f"{command[-1]} ok", stderr="")

        results = rerun_required_workflows(runner=runner)
        self.assertEqual(
            calls,
            [
                "portfolio-beta",
                "market-levels",
                "risk-watch",
                "market-pulse",
                "style-rotation",
                "ai-capex-watch",
                "after-close",
            ],
        )
        self.assertEqual(
            [item["returncode"] for item in results],
            [0, 0, 0, 0, 0, 0, 0],
        )

    def test_board_lot_floor_never_overshoots_ratio_or_available_shares(self) -> None:
        too_small = calculate_executable_trim(100, 100, 0.25)
        self.assertEqual(too_small["raw_target_shares"], 25)
        self.assertEqual(too_small["executable_lot_shares"], 0)
        self.assertEqual(too_small["execution_readiness"], "blocked")
        self.assertIn("无法按25%整手执行", too_small["reason"])

        limited = calculate_executable_trim(1000, 150, 0.25)
        self.assertEqual(limited["raw_target_shares"], 250)
        self.assertEqual(limited["executable_lot_shares"], 100)
        self.assertLessEqual(limited["executable_lot_shares"], limited["available_shares"])
        self.assertEqual(limited["execution_readiness"], "ready_limited_by_available")


if __name__ == "__main__":
    unittest.main()
