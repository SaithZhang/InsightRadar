from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from stock_assist.portfolio import load_portfolio
from stock_assist.portfolio_import import apply_portfolio_beta_evidence
from stock_assist.workflows.portfolio_beta import (
    BetaConfig,
    PricePoint,
    calculate_beta,
)


def _config(*, threshold: float = 1.2) -> BetaConfig:
    return BetaConfig(
        benchmark="000300.SH",
        benchmark_name="沪深300",
        benchmark_secid="1.000300",
        benchmark_tencent_code="sh000300",
        window_sessions=120,
        minimum_observations=60,
        history_limit=180,
        high_beta_threshold=threshold,
        require_same_latest_session=True,
        moderate_r_squared=0.1,
        strong_r_squared=0.3,
    )


def _prices(returns: list[float], *, initial: float = 100.0) -> list[PricePoint]:
    session = date(2026, 1, 1)
    close = initial
    result = [PricePoint(session=session, close=close)]
    for index, value in enumerate(returns, start=1):
        close *= 1 + value
        result.append(
            PricePoint(session=session + timedelta(days=index), close=close)
        )
    return result


class PortfolioBetaTests(unittest.TestCase):
    def test_exact_linear_returns_produce_deterministic_high_beta(self) -> None:
        benchmark_returns = [((index % 9) - 4) / 1000 for index in range(120)]
        result = calculate_beta(
            "900001.SH",
            _prices([1.5 * value for value in benchmark_returns]),
            _prices(benchmark_returns),
            _config(),
            source="synthetic adjusted daily bars",
        )

        self.assertEqual(result.quality_status, "ready")
        self.assertEqual(result.classification, "high_beta")
        self.assertAlmostEqual(result.beta or 0, 1.5, places=6)
        self.assertAlmostEqual(result.r_squared or 0, 1.0, places=6)
        self.assertEqual(result.observations, 120)

    def test_threshold_boundary_is_high_beta(self) -> None:
        benchmark_returns = [((index % 7) - 3) / 1000 for index in range(80)]
        result = calculate_beta(
            "900002.SZ",
            _prices([1.2 * value for value in benchmark_returns]),
            _prices(benchmark_returns),
            _config(),
            source="synthetic adjusted daily bars",
        )

        self.assertEqual(result.classification, "high_beta")
        self.assertAlmostEqual(result.beta or 0, 1.2, places=6)

    def test_insufficient_overlap_remains_unknown(self) -> None:
        returns = [0.001, -0.001] * 10
        result = calculate_beta(
            "900003.SH",
            _prices(returns),
            _prices(returns),
            _config(),
            source="synthetic adjusted daily bars",
        )

        self.assertEqual(result.quality_status, "insufficient")
        self.assertEqual(result.classification, "unknown")
        self.assertIsNone(result.beta)

    def test_stale_asset_session_remains_unknown(self) -> None:
        benchmark_returns = [((index % 5) - 2) / 1000 for index in range(80)]
        benchmark = _prices(benchmark_returns)
        result = calculate_beta(
            "900004.SZ",
            _prices(benchmark_returns)[:-1],
            benchmark,
            _config(),
            source="synthetic adjusted daily bars",
        )

        self.assertEqual(result.quality_status, "stale")
        self.assertEqual(result.classification, "unknown")
        self.assertNotEqual(result.asset_as_of, result.as_of)

    def test_zero_benchmark_variance_fails_closed(self) -> None:
        flat_returns = [0.0] * 80
        asset_returns = [((index % 5) - 2) / 1000 for index in range(80)]
        result = calculate_beta(
            "900005.SH",
            _prices(asset_returns),
            _prices(flat_returns),
            _config(),
            source="synthetic adjusted daily bars",
        )

        self.assertEqual(result.quality_status, "failed")
        self.assertEqual(result.classification, "unknown")
        self.assertIsNone(result.beta)

    def test_persistence_updates_beta_evidence_and_risk_reconciliation(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            portfolio_path = root / "portfolio.json"
            risk_path = root / "risk.json"
            portfolio_path.write_text(
                json.dumps(
                    {
                        "schema_version": "insightradar-portfolio/v3",
                        "as_of": "2026-07-31",
                        "cash": None,
                        "risk_reconciliation": {"status": "blocked"},
                        "holdings": [
                            {
                                "code": "900006.SH",
                                "name": "合成样本乙",
                                "weight_pct": 25.0,
                                "beta_classification": "unknown",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            risk_path.write_text("{}", encoding="utf-8")
            result = apply_portfolio_beta_evidence(
                [
                    {
                        "code": "900006.SH",
                        "classification": "high_beta",
                        "beta": 1.35,
                        "r_squared": 0.42,
                        "benchmark": "000300.SH",
                        "window_sessions": 120,
                        "minimum_observations": 60,
                        "observations": 120,
                        "as_of": "2026-07-31",
                        "asset_as_of": "2026-07-31",
                        "source": "synthetic adjusted daily bars",
                        "quality_status": "ready",
                        "fit_quality": "strong",
                        "reason": "synthetic test",
                        "calculation": "deterministic",
                    }
                ],
                model={
                    "benchmark": "000300.SH",
                    "window_sessions": 120,
                    "minimum_observations": 60,
                    "calculation": "deterministic",
                },
                portfolio_path=portfolio_path,
                risk_profile_path=risk_path,
            )
            portfolio = load_portfolio(portfolio_path)
            risk = json.loads(risk_path.read_text(encoding="utf-8"))

        self.assertTrue(result["saved"])
        self.assertEqual(portfolio.holdings[0].beta_classification, "high_beta")
        assert portfolio.holdings[0].beta_evidence is not None
        self.assertEqual(portfolio.holdings[0].beta_evidence.observations, 120)
        self.assertEqual(portfolio.risk_reconciliation_status, "reconciled")
        self.assertEqual(risk["high_beta_exposure_pct"], 25.0)
        self.assertEqual(risk["reconciliation_status"], "reconciled")


if __name__ == "__main__":
    unittest.main()
