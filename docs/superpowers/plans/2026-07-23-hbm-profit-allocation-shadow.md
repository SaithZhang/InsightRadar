# HBM Profit Allocation Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an official-evidence HBM shadow that separates contracted volume visibility, pricing power, margin realization, and capacity/budget competition inside `ai-capex-watch`.

**Architecture:** Put HBM evidence validation and state transitions in a focused `stock_assist.hbm_profit_allocation` module. `score_ai_capex_watch` calls it with point-in-time config records and returns a separate `hbm_profit_allocation` object; existing CapEx, optical, and supplier metrics remain unchanged during shadow mode.

**Tech Stack:** Python 3.10+, standard-library `dataclasses`/`datetime`/`decimal`, existing JSON configuration and report bundle, `unittest`, existing report payload and architecture renderers.

**Design Source:** [Energy, Technology, and HBM Shadow-Intelligence Design](../specs/2026-07-23-energy-tech-hbm-shadow-design.md). The independent macro subsystem is planned in [Macro Transmission Shadow Implementation Plan](2026-07-23-macro-transmission-shadow.md).

## Global Constraints

- Execute only after explicit queue reprioritization; `feat-056` remains the next and sole queued Harness experiment when this plan is written.
- A contract or qualification milestone can improve volume visibility but cannot by itself prove pricing power or margin realization.
- Keep `volume_visibility`, `pricing_power`, `margin_realization`, and `capex_budget_competition` independent.
- Missing contract price, customer, mix, yield, cost, shipment, or financial fields remain `unknown`; never infer zero or neutral.
- Only `verification_status="official"` records observed on or before `as_of` can affect a state.
- Keep publication/observation date, filing period, source URL, freshness, conflicts, and gaps explicit.
- Require shipment/revenue plus yield/cost/margin evidence before positive margin realization.
- Inventory, receivables, customer concentration, cancellation, or requalification evidence remains visible counter-evidence.
- Track at least two reporting quarters after a contract/qualification milestone before promotion readiness.
- During shadow mode, do not change existing `metrics`, weighted score, conclusion, risk budget, candidate, action authority, or strict readiness.
- `ai-capex-watch` remains read-only and cannot override `risk-watch` or trigger orders.
- Preserve the existing JSON, Markdown, and HTML outputs.
- Jin10 may later discover HBM clues, but this implementation consumes verified primary-source records only and does not start `feat-055`.
- No new command, service, cloud dependency, generic HBM news feed, or inferred undisclosed contract economics.

---

## File Map

| Path | Responsibility |
|---|---|
| `stock_assist/hbm_profit_allocation.py` | Typed HBM evidence, independent states, counter-evidence, quarter realization gate |
| `tests/test_hbm_profit_allocation.py` | Point-in-time filters, unknown preservation, state confirmation, two-quarter gate |
| `configs/ai_capex_watch.json` | Add live `hbm_evidence` records and shadow thresholds |
| `configs/ai_capex_watch.example.json` | Add an empty, credential-free HBM contract |
| `stock_assist/ai_capex_watch.py` | Call the evaluator and attach its separate result without changing current metrics |
| `stock_assist/workflows/ai_capex_watch.py` | Render HBM shadow in JSON/Markdown/HTML |
| `tests/test_ai_capex_watch.py` | Score non-interference and stale/unverified integration |
| `tests/test_hbm_profit_allocation_workflow.py` | Report rendering and source/gap contract |
| `configs/architecture.json` | Add HBM evidence and profit-allocation output to the existing `ai_capex_watch` node |
| `docs/architecture.html` | Regenerated architecture view |
| `docs/harness.md` | Runtime and verification contract |
| `feature_list.json`, `progress.md`, `session-handoff.md`, `CURRENT_STATE.md` | Evidence and restart state only when implementation is explicitly activated |

---

### Task 1: Typed HBM Evidence and Independent States

**Files:**
- Create: `stock_assist/hbm_profit_allocation.py`
- Create: `tests/test_hbm_profit_allocation.py`

**Interfaces:**
- Produces: `HbmEvidence`
- Produces: `HbmState`
- Produces: `HbmProfitAllocation`
- Produces: `evaluate_hbm_profit_allocation(records: list[dict[str, object]], as_of: date, config: dict[str, object]) -> HbmProfitAllocation`

- [ ] **Step 1: Write failing independence and unknown-preservation tests**

```python
from __future__ import annotations

from datetime import date
import unittest

from stock_assist.hbm_profit_allocation import evaluate_hbm_profit_allocation


def official(
    evidence_id: str,
    evidence_type: str,
    *,
    supplier: str = "MemoryCo",
    observed_at: str = "2026-07-01",
    reporting_period: str | None = None,
    verification_status: str = "official",
    **values: object,
) -> dict[str, object]:
    record: dict[str, object] = {
        "evidence_id": evidence_id,
        "supplier": supplier,
        "evidence_type": evidence_type,
        "observed_at": observed_at,
        "published_at": f"{observed_at}T08:00:00+00:00",
        "fetched_at": f"{observed_at}T09:00:00+00:00",
        "timezone": "UTC",
        "verification_status": verification_status,
        "source_url": f"https://example.test/ir/{evidence_id}",
    }
    if reporting_period is not None:
        record["reporting_period"] = reporting_period
    record.update(values)
    return record


def complete_positive_records(periods: tuple[str, ...]) -> list[dict[str, object]]:
    records = [
        official(
            "contract",
            "long_term_agreement",
            observed_at="2026-07-01",
            contract_start="2026-07-01",
            contract_end="2027-06-30",
        )
    ]
    observed_dates = {"2026-Q3": "2026-10-31", "2026-Q4": "2027-01-31"}
    for period in periods:
        observed_at = observed_dates[period]
        records.extend([
            official(
                f"shipment-{period}",
                "shipment",
                observed_at=observed_at,
                reporting_period=period,
                shipment_realized=True,
            ),
            official(
                f"financial-{period}",
                "financial_realization",
                observed_at=observed_at,
                reporting_period=period,
                hbm_revenue_realized=True,
                gross_margin_yoy_pct=4.0,
                operating_cash_flow_positive=True,
            ),
        ])
    return records


class HbmProfitAllocationTests(unittest.TestCase):
    def test_contract_improves_volume_but_not_pricing_or_margin(self) -> None:
        records = [official(
            "contract-1",
            "long_term_agreement",
            contract_start="2026-07-01",
            contract_end="2027-06-30",
            hbm_generation="HBM4",
        )]
        result = evaluate_hbm_profit_allocation(records, date(2026, 7, 23), {})
        self.assertEqual("positive", result.volume_visibility.status)
        self.assertEqual("unknown", result.pricing_power.status)
        self.assertEqual("unknown", result.margin_realization.status)
        self.assertEqual("diagnostic_only", result.authority)

    def test_unverified_and_future_records_are_excluded_with_gaps(self) -> None:
        records = [
            official(
                "rumor",
                "pricing",
                verification_status="media_report",
                price_direction="up",
            ),
            official(
                "future",
                "financial_realization",
                observed_at="2026-08-01",
                gross_margin_yoy_pct=5,
            ),
        ]
        result = evaluate_hbm_profit_allocation(records, date(2026, 7, 23), {})
        self.assertEqual("unknown", result.pricing_power.status)
        self.assertEqual("unknown", result.margin_realization.status)
        self.assertTrue(any("excluded_unverified" in gap for gap in result.data_gaps))
        self.assertTrue(any("excluded_future" in gap for gap in result.data_gaps))
```

- [ ] **Step 2: Run the focused tests and confirm the red state**

Run: `.venv\Scripts\python -m unittest tests.test_hbm_profit_allocation.HbmProfitAllocationTests.test_contract_improves_volume_but_not_pricing_or_margin tests.test_hbm_profit_allocation.HbmProfitAllocationTests.test_unverified_and_future_records_are_excluded_with_gaps -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_assist.hbm_profit_allocation'`.

- [ ] **Step 3: Define contracts and strict record parsing**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal


HbmStatus = Literal["unknown", "observe", "positive", "negative", "mixed", "invalidated"]


@dataclass(frozen=True)
class HbmEvidence:
    evidence_id: str
    supplier: str
    evidence_type: str
    observed_at: date
    published_at: str
    fetched_at: str
    timezone: str
    verification_status: str
    source_url: str
    reporting_period: str | None
    values: dict[str, object]


@dataclass(frozen=True)
class HbmState:
    status: HbmStatus
    evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    gaps: tuple[str, ...]
    next_review_condition: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "evidence_ids": list(self.evidence_ids),
            "counter_evidence_ids": list(self.counter_evidence_ids),
            "gaps": list(self.gaps),
            "next_review_condition": self.next_review_condition,
        }


@dataclass(frozen=True)
class HbmProfitAllocation:
    as_of: date
    volume_visibility: HbmState
    pricing_power: HbmState
    margin_realization: HbmState
    capex_budget_competition: HbmState
    confidence: str
    reporting_quarters_observed: int
    promotion_readiness: str
    sources: tuple[dict[str, str], ...]
    data_gaps: tuple[str, ...]
    authority: str = "diagnostic_only"

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of.isoformat(),
            "volume_visibility": self.volume_visibility.to_dict(),
            "pricing_power": self.pricing_power.to_dict(),
            "margin_realization": self.margin_realization.to_dict(),
            "capex_budget_competition": self.capex_budget_competition.to_dict(),
            "confidence": self.confidence,
            "reporting_quarters_observed": self.reporting_quarters_observed,
            "promotion_readiness": self.promotion_readiness,
            "sources": list(self.sources),
            "data_gaps": list(self.data_gaps),
            "authority": self.authority,
        }
```

`_parse_records` must:

- require non-empty `evidence_id`, `supplier`, `evidence_type`, `observed_at`, timezone-aware `published_at`, timezone-aware `fetched_at`, `timezone`, and HTTPS `source_url`;
- keep only `verification_status="official"` and `observed_at <= as_of`;
- reject a record when `published_at` is later than the end of `as_of` in the record's declared timezone;
- exclude records older than configured `max_age_days` from state transitions while retaining an `excluded_stale:<evidence_id>` gap;
- deduplicate by `evidence_id`, treating conflicting duplicate values as a visible conflict;
- retain `reporting_period` as `YYYY-QN` only when valid;
- return accepted records and explicit exclusion/conflict gaps.

- [ ] **Step 4: Implement independent rule evaluation**

Use these exact evidence types:

```python
VOLUME_TYPES = {"long_term_agreement", "customer_nomination", "qualification", "shipment"}
PRICING_TYPES = {"pricing", "product_mix", "contract_price_mechanism"}
MARGIN_TYPES = {"financial_realization", "yield_cost", "shipment"}
COMPETITION_TYPES = {"capacity_allocation", "dram_opportunity_cost", "packaging_constraint", "customer_budget"}
```

Apply these rules:

- volume `positive` when an official agreement, nomination, qualification, or realized shipment exists and is not cancelled/requalified;
- pricing `positive` only when a pricing/mix record has `price_direction="up"`, `mix_direction="premium"`, or a disclosed fixed/indexed mechanism with favorable realized evidence;
- pricing stays `unknown` for a contract record with no pricing fields;
- margin `positive` only when the same supplier/reporting period has realized shipment or HBM revenue plus `gross_margin_yoy_pct > 0` and either `operating_cash_flow_positive=true` or `yield_direction="up"` with `unit_cost_direction="down"`;
- margin `negative` when gross margin falls, operating cash flow is negative, or inventory/receivables growth exceeds revenue growth by the configured counter-evidence threshold;
- customer concentration at or above the configured threshold is counter-evidence for both volume durability and margin realization, never proof of cancellation;
- conflicting positive/negative records produce `mixed`;
- capacity allocation, DRAM opportunity cost, packaging constraint, or customer-budget evidence produces competition `observe` until a quantified realized effect exists;
- cancellation or failed requalification invalidates the affected volume state;
- absent evidence remains `unknown`.

- [ ] **Step 5: Add realization and counter-evidence tests**

```python
def test_margin_requires_shipment_and_financial_confirmation(self) -> None:
    records = [
        official("ship", "shipment", reporting_period="2026-Q3", shipment_realized=True),
        official(
            "fin",
            "financial_realization",
            reporting_period="2026-Q3",
            hbm_revenue_realized=True,
            gross_margin_yoy_pct=4.0,
            operating_cash_flow_positive=True,
        ),
    ]
    result = evaluate_hbm_profit_allocation(records, date(2026, 10, 31), {})
    self.assertEqual("positive", result.margin_realization.status)

def test_inventory_and_receivables_can_make_margin_mixed(self) -> None:
    records = [
        official("ship", "shipment", reporting_period="2026-Q3", shipment_realized=True),
        official(
            "fin",
            "financial_realization",
            reporting_period="2026-Q3",
            hbm_revenue_realized=True,
            gross_margin_yoy_pct=4.0,
            operating_cash_flow_positive=True,
            revenue_yoy_pct=20.0,
            inventory_yoy_pct=45.0,
            receivables_yoy_pct=42.0,
        ),
    ]
    result = evaluate_hbm_profit_allocation(
        records,
        date(2026, 10, 31),
        {"working_capital_excess_pct_points": 15.0},
    )
    self.assertEqual("mixed", result.margin_realization.status)
    self.assertIn("fin", result.margin_realization.counter_evidence_ids)

def test_cancellation_invalidates_contract_volume_visibility(self) -> None:
    records = [
        official("contract", "long_term_agreement", contract_end="2027-06-30"),
        official("cancel", "cancellation", related_evidence_id="contract"),
    ]
    result = evaluate_hbm_profit_allocation(records, date(2026, 9, 1), {})
    self.assertEqual("invalidated", result.volume_visibility.status)

def test_customer_concentration_is_counter_evidence_not_cancellation(self) -> None:
    records = [
        official("contract", "long_term_agreement", customer_concentration_pct=65.0),
    ]
    result = evaluate_hbm_profit_allocation(
        records,
        date(2026, 7, 23),
        {"customer_concentration_warning_pct": 50.0},
    )
    self.assertEqual("positive", result.volume_visibility.status)
    self.assertIn("contract", result.volume_visibility.counter_evidence_ids)
```

- [ ] **Step 6: Run and commit the typed evaluator**

Run: `.venv\Scripts\python -m unittest tests.test_hbm_profit_allocation -v`

Expected: all HBM evaluator tests pass.

```powershell
git add stock_assist/hbm_profit_allocation.py tests/test_hbm_profit_allocation.py
git commit -m "feat: add HBM profit allocation states"
```

---

### Task 2: Two-Quarter Realization and Promotion Gate

**Files:**
- Modify: `stock_assist/hbm_profit_allocation.py`
- Modify: `tests/test_hbm_profit_allocation.py`

**Interfaces:**
- Produces: `evaluate_hbm_promotion_readiness(records: tuple[HbmEvidence, ...], states: HbmProfitAllocation, config: dict[str, object]) -> tuple[int, str]`

- [ ] **Step 1: Write failing quarter-gate tests**

```python
def test_one_reporting_quarter_cannot_be_promotion_ready(self) -> None:
    records = complete_positive_records(periods=("2026-Q3",))
    result = evaluate_hbm_profit_allocation(records, date(2026, 11, 1), {})
    self.assertEqual(1, result.reporting_quarters_observed)
    self.assertEqual("insufficient_reporting_quarters", result.promotion_readiness)

def test_two_quarters_only_reach_shadow_calibrated(self) -> None:
    records = complete_positive_records(periods=("2026-Q3", "2026-Q4"))
    result = evaluate_hbm_profit_allocation(records, date(2027, 2, 1), {})
    self.assertEqual(2, result.reporting_quarters_observed)
    self.assertEqual("shadow_calibrated_not_promoted", result.promotion_readiness)
    self.assertEqual("diagnostic_only", result.authority)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv\Scripts\python -m unittest tests.test_hbm_profit_allocation.HbmProfitAllocationTests.test_one_reporting_quarter_cannot_be_promotion_ready tests.test_hbm_profit_allocation.HbmProfitAllocationTests.test_two_quarters_only_reach_shadow_calibrated -v`

Expected: FAIL because quarter readiness is not implemented.

- [ ] **Step 3: Implement milestone-linked quarter counting**

`evaluate_hbm_promotion_readiness` must:

- find the earliest official agreement, nomination, or qualification date per supplier;
- count unique later `reporting_period` values with both shipment/revenue evidence and financial-realization evidence;
- never count a period before the milestone;
- never count two records from one quarter twice;
- return `no_confirmed_milestone`, `insufficient_reporting_quarters`, `conflicting_realization`, or `shadow_calibrated_not_promoted`;
- never return `promoted`, because promotion requires separate user approval.

Call it from `evaluate_hbm_profit_allocation` and populate both fields.

- [ ] **Step 4: Add no-lookahead and duplicate-quarter tests**

```python
def test_later_filing_does_not_count_at_earlier_as_of(self) -> None:
    result = evaluate_hbm_profit_allocation(
        complete_positive_records(periods=("2026-Q3", "2026-Q4")),
        date(2026, 11, 1),
        {},
    )
    self.assertEqual(1, result.reporting_quarters_observed)

def test_same_date_record_published_after_cutoff_is_excluded(self) -> None:
    record = official("late", "pricing", price_direction="up")
    record["published_at"] = "2026-07-24T00:30:00+00:00"
    result = evaluate_hbm_profit_allocation([record], date(2026, 7, 23), {})
    self.assertEqual("unknown", result.pricing_power.status)
    self.assertTrue(any("excluded_future_publication" in gap for gap in result.data_gaps))

def test_duplicate_records_in_one_quarter_count_once(self) -> None:
    records = complete_positive_records(periods=("2026-Q3",)) + [
        official(
            "fin-copy",
            "financial_realization",
            observed_at="2026-10-31",
            reporting_period="2026-Q3",
            hbm_revenue_realized=True,
            gross_margin_yoy_pct=4.0,
            operating_cash_flow_positive=True,
        )
    ]
    result = evaluate_hbm_profit_allocation(records, date(2026, 11, 1), {})
    self.assertEqual(1, result.reporting_quarters_observed)
```

- [ ] **Step 5: Run and commit the promotion gate**

Run: `.venv\Scripts\python -m unittest tests.test_hbm_profit_allocation -v`

Expected: all HBM state and quarter-gate tests pass.

```powershell
git add stock_assist/hbm_profit_allocation.py tests/test_hbm_profit_allocation.py
git commit -m "feat: gate HBM shadow on quarterly realization"
```

---

### Task 3: AI-CapEx Integration Without Score Mutation

**Files:**
- Modify: `configs/ai_capex_watch.json`
- Modify: `configs/ai_capex_watch.example.json`
- Modify: `stock_assist/ai_capex_watch.py`
- Modify: `tests/test_ai_capex_watch.py`

**Interfaces:**
- Consumes: `evaluate_hbm_profit_allocation`
- Produces result field: `hbm_profit_allocation`
- Existing `metrics`, `score`, `conclusion`, and `actions` remain byte-for-byte equivalent for the same non-HBM inputs during shadow mode

- [ ] **Step 1: Write a failing score non-interference test**

```python
def test_hbm_shadow_does_not_change_existing_metrics_conclusion_or_actions(self) -> None:
    base = {
        "companies": [{
            "name": "CloudCo",
            "observed_at": "2026-07-01",
            "verification_status": "official",
            "guidance_low_billion_usd": 20,
            "guidance_high_billion_usd": 20,
            "prior_guidance_low_billion_usd": 10,
            "prior_guidance_high_billion_usd": 10,
            "prior_actual_capex_billion_usd": 10,
            "guidance_direction": "up",
            "ai_dc_link": "explicit",
        }],
        "optical_evidence": [
            {
                "observed_at": "2026-07-01",
                "verification_status": "official",
                "category": category,
                "direction": "positive",
                "strength": 1,
            }
            for category in ("network_revenue", "network_allocation", "module_demand")
        ],
        "supplier_checks": [{"label": "gross margin", "status": "official"}],
    }
    with_hbm = {
        **base,
        "hbm_evidence": [{
            "evidence_id": "contract-1",
            "supplier": "MemoryCo",
            "evidence_type": "long_term_agreement",
            "observed_at": "2026-07-01",
            "published_at": "2026-07-01T08:00:00+00:00",
            "fetched_at": "2026-07-01T09:00:00+00:00",
            "timezone": "UTC",
            "verification_status": "official",
            "source_url": "https://example.test/ir/contract-1",
            "contract_end": "2027-06-30"
        }],
    }
    without_result = score_ai_capex_watch(base, date(2026, 7, 23))
    with_result = score_ai_capex_watch(with_hbm, date(2026, 7, 23))
    self.assertEqual(without_result["metrics"], with_result["metrics"])
    self.assertEqual(without_result["score"], with_result["score"])
    self.assertEqual(without_result["conclusion"], with_result["conclusion"])
    self.assertEqual(without_result["actions"], with_result["actions"])
    self.assertEqual("diagnostic_only", with_result["hbm_profit_allocation"]["authority"])
```

- [ ] **Step 2: Run the integration test and confirm it fails**

Run: `.venv\Scripts\python -m unittest tests.test_ai_capex_watch.AiCapexWatchTests.test_hbm_shadow_does_not_change_existing_metrics_conclusion_or_actions -v`

Expected: FAIL because `hbm_profit_allocation` is absent.

- [ ] **Step 3: Attach the evaluator result after current scoring**

In `stock_assist/ai_capex_watch.py`:

```python
from stock_assist.hbm_profit_allocation import evaluate_hbm_profit_allocation
```

At the end of `score_ai_capex_watch`, after all existing metrics/conclusion/actions are calculated:

```python
hbm_records = _as_records(config.get("hbm_evidence"))
hbm_config = config.get("hbm_shadow")
if not isinstance(hbm_config, dict):
    hbm_config = {}
hbm = evaluate_hbm_profit_allocation(hbm_records, as_of, hbm_config)
```

Return `"hbm_profit_allocation": hbm.to_dict()` as a new sibling field. Do not pass HBM state into `_weighted_score`, `_conclusion`, or `_conditional_actions`.

- [ ] **Step 4: Extend both config contracts**

Add:

```json
{
  "hbm_shadow": {
    "max_age_days": 365,
    "minimum_reporting_quarters": 2,
    "working_capital_excess_pct_points": 15.0,
    "customer_concentration_warning_pct": 50.0
  },
  "hbm_evidence": []
}
```

Preserve existing `companies`, `optical_evidence`, and `supplier_checks`. The live config may include only source-linked official records; no inferred customer, price, or margin fields.

- [ ] **Step 5: Add malformed, stale, and missing-field integration tests**

Add:

```python
def test_hbm_missing_fields_remain_unknown_not_zero(self) -> None:
    result = score_ai_capex_watch(
        {"hbm_evidence": [{
            "evidence_id": "contract-no-economics",
            "supplier": "MemoryCo",
            "evidence_type": "long_term_agreement",
            "observed_at": "2026-07-01",
            "published_at": "2026-07-01T08:00:00+00:00",
            "fetched_at": "2026-07-01T09:00:00+00:00",
            "timezone": "UTC",
            "verification_status": "official",
            "source_url": "https://example.test/ir/contract-no-economics",
            "contract_end": "2027-06-30",
        }]},
        date(2026, 7, 23),
    )
    hbm = result["hbm_profit_allocation"]
    self.assertEqual("unknown", hbm["pricing_power"]["status"])
    self.assertEqual("unknown", hbm["margin_realization"]["status"])

def test_stale_hbm_record_is_visible_but_does_not_change_capex_score(self) -> None:
    config = {
        "hbm_shadow": {"max_age_days": 30},
        "hbm_evidence": [{
            "evidence_id": "old-contract",
            "supplier": "MemoryCo",
            "evidence_type": "long_term_agreement",
            "observed_at": "2026-01-01",
            "published_at": "2026-01-01T08:00:00+00:00",
            "fetched_at": "2026-01-01T09:00:00+00:00",
            "timezone": "UTC",
            "verification_status": "official",
            "source_url": "https://example.test/ir/old-contract",
            "contract_end": "2027-06-30",
        }],
    }
    result = score_ai_capex_watch(config, date(2026, 7, 23))
    self.assertTrue(any("stale" in gap for gap in result["hbm_profit_allocation"]["data_gaps"]))
    self.assertIsNone(result["metrics"][0]["score"])
```

- [ ] **Step 6: Run and commit score integration**

Run: `.venv\Scripts\python -m unittest tests.test_hbm_profit_allocation tests.test_ai_capex_watch -v`

Expected: all tests pass and existing AI-CapEx assertions remain unchanged.

```powershell
git add configs/ai_capex_watch.json configs/ai_capex_watch.example.json stock_assist/ai_capex_watch.py tests/test_ai_capex_watch.py
git commit -m "feat: attach HBM shadow to AI capex watch"
```

---

### Task 4: Report Rendering, Product Contract, and Real Artifact

**Files:**
- Modify: `stock_assist/workflows/ai_capex_watch.py`
- Create: `tests/test_hbm_profit_allocation_workflow.py`
- Modify: `configs/architecture.json`
- Regenerate: `docs/architecture.html`
- Modify: `docs/harness.md`
- Modify when activated: `feature_list.json`
- Modify when activated: `progress.md`
- Modify when activated: `session-handoff.md`
- Modify only if verified baseline or next feature changes: `CURRENT_STATE.md`

**Interfaces:**
- Produces Markdown heading: `## HBM 利润分配（影子）`
- Produces HTML section ID: `hbm-profit-allocation-shadow`
- Produces fresh `reports/*-ai-capex-watch.json`, `.md`, and `.html`

- [ ] **Step 1: Write failing report-contract tests**

```python
from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from stock_assist.workflows.ai_capex_watch import build_ai_capex_watch_bundle


def complete_workflow_config() -> dict[str, object]:
    return {
        "companies": [],
        "optical_evidence": [],
        "supplier_checks": [],
        "hbm_shadow": {
            "max_age_days": 365,
            "minimum_reporting_quarters": 2,
            "working_capital_excess_pct_points": 15.0,
            "customer_concentration_warning_pct": 50.0,
        },
        "hbm_evidence": [
            {
                "evidence_id": "contract",
                "supplier": "MemoryCo",
                "evidence_type": "long_term_agreement",
                "observed_at": "2026-07-01",
                "published_at": "2026-07-01T08:00:00+00:00",
                "fetched_at": "2026-07-01T09:00:00+00:00",
                "timezone": "UTC",
                "verification_status": "official",
                "source_url": "https://example.test/ir/contract",
                "contract_start": "2026-07-01",
                "contract_end": "2027-06-30",
            },
            {
                "evidence_id": "shipment-2026-Q3",
                "supplier": "MemoryCo",
                "evidence_type": "shipment",
                "observed_at": "2026-10-31",
                "published_at": "2026-10-31T08:00:00+00:00",
                "fetched_at": "2026-10-31T09:00:00+00:00",
                "timezone": "UTC",
                "verification_status": "official",
                "source_url": "https://example.test/ir/shipment-2026-Q3",
                "reporting_period": "2026-Q3",
                "shipment_realized": True,
            },
            {
                "evidence_id": "financial-2026-Q3",
                "supplier": "MemoryCo",
                "evidence_type": "financial_realization",
                "observed_at": "2026-10-31",
                "published_at": "2026-10-31T08:00:00+00:00",
                "fetched_at": "2026-10-31T09:00:00+00:00",
                "timezone": "UTC",
                "verification_status": "official",
                "source_url": "https://example.test/ir/financial-2026-Q3",
                "reporting_period": "2026-Q3",
                "hbm_revenue_realized": True,
                "gross_margin_yoy_pct": 4.0,
                "operating_cash_flow_positive": True,
            },
        ],
    }


class HbmProfitAllocationWorkflowTests(unittest.TestCase):
    def test_hbm_states_sources_gaps_and_authority_render_in_all_formats(self) -> None:
        config = complete_workflow_config()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ai-capex.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            payload, markdown, html = build_ai_capex_watch_bundle(path, as_of="2026-10-31")
        hbm = payload["hbm_profit_allocation"]
        self.assertEqual("diagnostic_only", hbm["authority"])
        self.assertIn("HBM 利润分配（影子）", markdown)
        self.assertIn("https://example.test/ir/contract", markdown)
        self.assertIn('id="hbm-profit-allocation-shadow"', html)
        self.assertIn("仅诊断", html)
        self.assertIn("promotion_readiness", json.dumps(payload, ensure_ascii=False))
```

- [ ] **Step 2: Run the report test and confirm it fails**

Run: `.venv\Scripts\python -m unittest tests.test_hbm_profit_allocation_workflow.HbmProfitAllocationWorkflowTests.test_hbm_states_sources_gaps_and_authority_render_in_all_formats -v`

Expected: FAIL because no HBM report section exists.

- [ ] **Step 3: Render a separate Markdown section**

Append after existing supplier checks and before general data gaps:

```python
def _hbm_state_label(value: object) -> str:
    return {
        "unknown": "未知",
        "observe": "观察",
        "positive": "正向",
        "negative": "负向",
        "mixed": "正反证并存",
        "invalidated": "已失效",
    }.get(str(value), "未知")
```

The section must list all four independent states, confidence, observed quarter count, promotion readiness, source links, counter-evidence, and data gaps. End with:

```text
- 权限：仅诊断；HBM 影子状态不改变现有 CapEx 分数、风险预算或交易计划。
```

- [ ] **Step 4: Render the HTML section without a combined gauge**

Add `<section id="hbm-profit-allocation-shadow">` with four state cards. Each card must display status, evidence IDs, counter-evidence IDs, gaps, and next review condition. Show source URLs as clickable links, `reporting_quarters_observed`, `promotion_readiness`, and the authority line.

Do not add HBM to the existing metric-card loop and do not create a numeric HBM score.

- [ ] **Step 5: Add the harness and architecture contracts**

In `docs/harness.md`, require:

- contract-only evidence can improve volume but leaves pricing and margin unknown;
- margin needs shipment/revenue and yield/cost/margin confirmation;
- working-capital counter-evidence is visible;
- two later reporting quarters are required for `shadow_calibrated_not_promoted`;
- future, unverified, stale, malformed, and conflicting records are explicit;
- existing AI-CapEx score/conclusion/actions remain unchanged in shadow mode;
- JSON/Markdown/HTML show all states, sources, gaps, quarter count, readiness, and `diagnostic_only`.

Update only the existing `ai_capex_watch` architecture node to add `official HBM contract, qualification, shipment, pricing, yield/cost and financial evidence` as input and `diagnostic-only HBM profit-allocation shadow` as output.

- [ ] **Step 6: Run focused and full verification**

Run:

```powershell
.\.venv\Scripts\python -m unittest tests.test_hbm_profit_allocation tests.test_ai_capex_watch tests.test_hbm_profit_allocation_workflow -v
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m compileall stock_assist
.\.venv\Scripts\python scripts\validate_project_memory.py
.\.venv\Scripts\python -m stock_assist.cli architecture-view
.\.venv\Scripts\python scripts\validate_project_memory.py
```

Expected: every command exits `0`.

- [ ] **Step 7: Generate and inspect a real artifact**

Populate the live config only with currently verified official records, leaving undisclosed fields absent. Then run:

```powershell
.\.venv\Scripts\python -m stock_assist.cli ai-capex-watch --as-of 2026-07-23
```

Inspect:

```powershell
$json = Get-ChildItem reports\*-ai-capex-watch.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$payload = Get-Content -LiteralPath $json.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
if ($payload.hbm_profit_allocation.authority -ne 'diagnostic_only') { throw 'HBM authority changed' }
if ($payload.hbm_profit_allocation.reporting_quarters_observed -lt 0) { throw 'invalid quarter count' }
if (-not (Test-Path ($json.FullName -replace '\.json$','.md'))) { throw 'missing Markdown peer' }
if (-not (Test-Path ($json.FullName -replace '\.json$','.html'))) { throw 'missing HTML peer' }
```

Verify manually that contract-only evidence leaves pricing and margin unknown, source links open, and undisclosed fields are not rendered as zero.

- [ ] **Step 8: Record evidence and commit**

Only after explicit feature activation, update `feature_list.json`, `progress.md`, and `session-handoff.md` with exact test counts, artifact paths, official-source coverage, reporting-quarter count, readiness, and remaining gaps. Change `CURRENT_STATE.md` only if the verified baseline or next feature changes.

```powershell
git add stock_assist/workflows/ai_capex_watch.py tests/test_hbm_profit_allocation_workflow.py configs/architecture.json docs/architecture.html docs/harness.md feature_list.json progress.md session-handoff.md
git diff --cached --check
git commit -m "docs: verify HBM profit allocation shadow"
```

Do not stage unrelated pre-existing working-tree changes.
