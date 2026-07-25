# After-Close Decision Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the long-form after-close HTML dashboard with a market-first, five-interface decision workbench while preserving the canonical JSON payload, Markdown report, conditional authority, and explicit data gaps.

**Architecture:** Keep the existing timestamp-aligned JSON/Markdown/HTML triplet. Add bounded 30-session trajectories to the existing risk-watch payload, normalize after-close data into a typed workbench view model, and render one self-contained HTML file with hash routes for `今日`, `持仓`, `市场`, `研究`, and `复盘`. The HTML renderer reads only the final after-close payload and embedded Markdown-derived sections; it never queries a provider.

**Tech Stack:** Python 3.13, standard-library `dataclasses`, `json`, `html`, `datetime`, existing InsightRadar report payloads, self-contained HTML/CSS/JavaScript, `unittest`, Codex in-app browser QA.

## Global Constraints

- Work in an isolated `codex/feat-058-after-close-decision-workbench` worktree created with `superpowers:using-git-worktrees`.
- Use one active product experiment only. Activate `feat-058`; keep `feat-056` pending and queued.
- Preserve `reports/*-after-close.json`, `.md`, and `.html` with one timestamp.
- JSON remains the canonical client contract; Markdown remains a supported renderer.
- Do not add or calibrate a 0–100 global-market temperature score.
- Do not add Hong Kong technology or China government-bond providers in this feature.
- Do not make diagnostic macro states part of risk scoring, budget authority, or trade authority.
- Do not display missing values as zero or use an old value as a current fallback.
- Do not display raw provider exceptions in the normal workbench UI.
- Preserve the local, explicit portfolio-import flow; no report may overwrite holdings or place an order.
- The HTML must work when opened directly from `file://`; optional portfolio import remains an explicit loopback workflow.
- Use plain Chinese user-facing labels; internal enum values stay in the payload or audit disclosure.
- Preserve unrelated user files, including `300308_cninfo_filings.json` and `tmp/`.

---

## File Map

### New files

- `stock_assist/after_close_workbench.py`
  - Typed workbench view model.
  - Safe loading and normalization of the latest risk-watch payload already referenced by `unified_decision.source_reports`.
  - Market-matrix grouping, freshness, plain-language gaps, portfolio translation, and per-route data.
- `stock_assist/after_close_workbench_html.py`
  - Self-contained HTML/CSS/JavaScript renderer.
  - App shell, five routes, market matrix, holding action playbooks, research, review, mobile behavior, and optional portfolio-import controls.
- `tests/test_after_close_workbench.py`
  - Pure view-model and HTML contract tests.

### Modified files

- `stock_assist/workflows/risk_watch.py`
  - Add bounded `series_30d` data to the existing diagnostic macro payload.
- `stock_assist/workflows/after_close.py`
  - Add the normalized `market_matrix` contract to JSON.
  - Use the new workbench renderer for after-close HTML only.
- `stock_assist/reports.py`
  - Expose the existing portfolio-import HTML pieces through one public helper; keep generic and NGA Markdown rendering unchanged.
- `tests/test_macro_transmission_workflow.py`
  - Verify bounded trajectories and provider-failure behavior.
- `tests/test_after_close_reliability.py`
  - Verify additive payload fields and holding-count consistency.
- `tests/test_reports.py`
  - Verify the legacy generic/NGA renderer remains unchanged.
- `tests/test_harness_integration.py`
  - Verify feature activation and final closeout state.
- `feature_list.json`
  - Register and later close `feat-058`.
- `configs/product_governance.json`
  - Activate and later remove `feat-058`.
- `CURRENT_STATE.md`
  - Track `feat-058` during implementation and restore `feat-056` after PASS.
- `progress.md`
  - Append activation and final evidence.
- `session-handoff.md`
  - Record branch, scope, verification, and restart instructions.
- `docs/harness.md`
  - Add the workbench acceptance contract.
- `docs/memory/architecture.md`
  - Record the renderer boundary.
- `configs/architecture.json`
  - Add the workbench renderer and market-matrix contract to Portfolio Intelligence outputs.
- `docs/architecture.html`
  - Regenerate from `configs/architecture.json`.

---

### Task 1: Activate the bounded `feat-058` experiment

**Files:**
- Modify: `feature_list.json`
- Modify: `configs/product_governance.json`
- Modify: `CURRENT_STATE.md`
- Modify: `progress.md`
- Modify: `session-handoff.md`
- Modify: `tests/test_harness_integration.py`

**Interfaces:**
- Consumes: approved design `docs/superpowers/specs/2026-07-23-after-close-decision-workbench-design.md`
- Produces: active feature id `feat-058`; `feat-056` remains the only queued experiment

- [ ] **Step 1: Create the isolated implementation worktree**

Invoke `superpowers:using-git-worktrees`, then create or select:

```powershell
git worktree add D:\work\InsightRadar\.worktrees\feat-058-after-close-decision-workbench -b codex/feat-058-after-close-decision-workbench
```

Expected: the new worktree starts from commit `b9d4b80` or its verified descendant, and `git status --short` is empty inside that worktree.

- [ ] **Step 2: Write the failing governance assertion**

Add this method to `HarnessIntegrationTests` in `tests/test_harness_integration.py`:

```python
def test_restart_snapshot_activates_after_close_workbench(self) -> None:
    current_state = (PROJECT_ROOT / "CURRENT_STATE.md").read_text(encoding="utf-8")
    self.assertIn('"next_feature_id": "feat-058"', current_state)

    feature_payload = json.loads(
        (PROJECT_ROOT / "feature_list.json").read_text(encoding="utf-8")
    )
    feature_status = {
        item["id"]: item["status"]
        for item in feature_payload["features"]
    }
    self.assertEqual(feature_status["feat-056"], "pending")
    self.assertEqual(feature_status["feat-058"], "in_progress")

    governance = json.loads(
        (PROJECT_ROOT / "configs" / "product_governance.json").read_text(
            encoding="utf-8"
        )
    )
    self.assertEqual(
        [item["feature_id"] for item in governance["active_experiments"]],
        ["feat-058"],
    )
    self.assertEqual(
        [item["feature_id"] for item in governance["queued_experiments"]],
        ["feat-056"],
    )
```

- [ ] **Step 3: Run the assertion and verify RED**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_harness_integration.py -v
```

Expected: FAIL because `feat-058` is not registered or active.

- [ ] **Step 4: Register and activate the feature**

Append this object after `feat-057` in `feature_list.json`:

```json
{
  "id": "feat-058",
  "name": "After-close decision workbench",
  "description": "Replace the long-form after-close HTML dashboard with a market-first, five-interface, single-file decision workbench that preserves the JSON and Markdown contracts, keeps stale and blocked inputs explicit, and maps diagnostic market context into conditional holding actions without adding trade authority.",
  "dependencies": ["feat-047", "feat-057"],
  "status": "in_progress",
  "evidence": "Activated from the user-approved 2026-07-23 design and implementation plan. feat-056 remains pending and queued; no 0-100 temperature score, Hong Kong technology provider, China government-bond provider, automatic execution, or trade authority is in scope."
}
```

Set `configs/product_governance.json` to:

```json
{
  "schema_version": "insightradar-product-governance/v1",
  "limits": {
    "max_active_experiments": 1,
    "max_queued_experiments": 2
  },
  "active_experiments": [
    {
      "feature_id": "feat-058",
      "problem": "The after-close HTML mixes decisions, market data, research, audit text, and raw failures into one long page, so the user cannot move quickly from market state to portfolio action.",
      "loop_stage": "decide",
      "baseline": "The 2026-07-23 after-close HTML is 3616 pixels tall on desktop and 7786 pixels on mobile, exposes raw provider exceptions, conflicts on holdings and freshness, and does not surface the macro shadow.",
      "outcome_metric": "At 1440x900 the first viewport shows market conclusion, matrix, portfolio translation, and the start of holding actions; all five routes work from file://; JSON/Markdown/HTML agree; raw exceptions are absent from the normal UI; mobile has no page overflow.",
      "smallest_experiment": "Reuse existing risk-watch, macro, style, reliability, action, and outcome payloads to build one self-contained after-close HTML workbench with no new provider.",
      "safety_boundaries": [
        "No uncalibrated 0-100 market-temperature score",
        "No new Hong Kong technology or China government-bond provider",
        "No diagnostic macro state may alter risk score, risk budget, or trade authority",
        "Missing and stale values remain explicit and cannot authorize new exposure",
        "No automatic order placement or holdings overwrite"
      ],
      "kill_criterion": "Reject or simplify the workbench if it changes trade authority, duplicates provider fetching in presentation code, cannot keep JSON/HTML consistent, or remains slower to scan than the existing action table.",
      "review_date": "2026-08-07"
    }
  ],
  "queued_experiments": [
    {
      "feature_id": "feat-056",
      "problem": "InsightRadar has a structurally complete Harness but no behavioral baseline proving which controls improve real tasks.",
      "loop_stage": "verify",
      "baseline": "Harness structure scores 100/100, but no versioned 20-30-task suite or four-profile comparison exists.",
      "outcome_metric": "Every eligible task reports deterministic success, evidence correctness, false completion, scope drift, privacy, recovery, token or context volume when available, tool calls, elapsed time, and human corrections across declared profiles.",
      "smallest_experiment": "Plan and run a five-task pilot across the four profiles before scaling the accepted schema to 20-30 tasks.",
      "safety_boundaries": [
        "Use synthetic or private local tasks only",
        "No holdings, broker data, credentials, or raw private conversations in public artifacts",
        "Deterministic checks are primary; model judging is secondary",
        "No benchmark result grants trade authority or model-superiority claims"
      ],
      "kill_criterion": "Stop expansion if the five-task pilot cannot produce reproducible deterministic verdicts or leaks private/secret data.",
      "review_date": "2026-08-17"
    }
  ]
}
```

Update the `CURRENT_STATE.md` manifest to `"next_feature_id": "feat-058"`, add one short `feat-058` activation bullet, and keep `feat-056` explicitly pending. Append matching activation sections to `progress.md` and `session-handoff.md`.

- [ ] **Step 5: Run governance validation and verify GREEN**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_harness_integration.py -v
C:\Python313\python.exe scripts\validate_project_memory.py
```

Expected: both commands PASS.

- [ ] **Step 6: Commit activation**

```powershell
git add feature_list.json configs/product_governance.json CURRENT_STATE.md progress.md session-handoff.md tests/test_harness_integration.py
git commit -m "docs: activate after-close decision workbench"
```

---

### Task 2: Persist bounded 30-session macro trajectories

**Files:**
- Modify: `stock_assist/workflows/risk_watch.py:342-433`
- Modify: `tests/test_macro_transmission_workflow.py`

**Interfaces:**
- Consumes: `dict[str, DailySeries]` built inside `_load_macro_shadow`
- Produces: `macro_transmission.series_30d[key]` with `source`, `as_of`, and at most 30 `{date, close}` rows

- [ ] **Step 1: Write failing trajectory tests**

Import `MarketDailyBar` at the top of `tests/test_macro_transmission_workflow.py`:

```python
from stock_assist.data_sources.global_markets import MarketDailyBar
```

Add these tests:

```python
@patch("stock_assist.workflows.risk_watch.fetch_yahoo_history")
def test_macro_shadow_exposes_only_last_30_completed_closes(
    self,
    fetch_history: object,
) -> None:
    start = date(2026, 5, 1)
    bars = [
        MarketDailyBar(start + timedelta(days=index), 100.0 + index)
        for index in range(90)
    ]
    fetch_history.return_value = bars

    result = _load_macro_shadow(date(2026, 7, 20))

    brent = result["series_30d"]["brent"]
    self.assertEqual(len(brent["points"]), 30)
    self.assertEqual(brent["points"][-1]["date"], "2026-07-20")
    self.assertEqual(brent["points"][-1]["close"], 180.0)
    self.assertEqual(brent["as_of"], "2026-07-20")
    self.assertTrue(brent["source"].startswith("https://"))

@patch(
    "stock_assist.workflows.risk_watch.fetch_yahoo_history",
    side_effect=TimeoutError("provider timeout"),
)
def test_macro_shadow_failure_keeps_empty_series_contract(
    self,
    fetch_history: object,
) -> None:
    result = _load_macro_shadow(date(2026, 7, 20))

    self.assertEqual(result["series_30d"], {})
    self.assertEqual(result["authority"], "diagnostic_only")
    self.assertTrue(
        any("provider timeout" in gap for gap in result["data_gaps"])
    )
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_macro_transmission_workflow.py -v
```

Expected: FAIL with missing `series_30d`.

- [ ] **Step 3: Add the bounded serialization helper**

Add below `_load_macro_shadow` in `stock_assist/workflows/risk_watch.py`:

```python
def _bounded_series_payload(
    series: dict[str, DailySeries],
    *,
    limit: int = 30,
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in series.items():
        points = item.points[-limit:]
        if not points:
            continue
        result[key] = {
            "source": item.source,
            "as_of": points[-1].day.isoformat(),
            "points": [
                {
                    "date": point.day.isoformat(),
                    "close": point.close,
                }
                for point in points
            ],
        }
    return result
```

In both return paths of `_load_macro_shadow`, set a stable additive contract:

```python
result["series_30d"] = _bounded_series_payload(series)
```

For the no-series branch, use:

```python
result["series_30d"] = {}
```

Do not add this data to risk scoring, alerts, or actions.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_macro_transmission_workflow.py -v
C:\Python313\python.exe -m unittest discover -s tests -p test_macro_transmission.py -v
```

Expected: both suites PASS and existing authority assertions remain unchanged.

- [ ] **Step 5: Commit bounded trajectories**

```powershell
git add stock_assist/workflows/risk_watch.py tests/test_macro_transmission_workflow.py
git commit -m "feat: expose bounded macro trajectories"
```

---

### Task 3: Build the market-matrix and freshness contract

**Files:**
- Create: `stock_assist/after_close_workbench.py`
- Create: `tests/test_after_close_workbench.py`
- Modify: `stock_assist/workflows/after_close.py:356-467`
- Modify: `tests/test_after_close_reliability.py`

**Interfaces:**
- Consumes: `unified_decision.source_reports`, risk-watch `replay.rows`, `macro_transmission.series_30d`, `payload.actions`, `payload.reliability`
- Produces:
  - `build_market_matrix_contract(unified_decision, report_dir, generated_at) -> dict[str, object]`
  - additive `after-close.json["market_matrix"]`
  - `plain_gap(value: object) -> str`

- [ ] **Step 1: Write failing pure contract tests**

Create `tests/test_after_close_workbench.py`:

```python
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stock_assist.after_close_workbench import (
    build_market_matrix_contract,
    plain_gap,
)


class AfterCloseWorkbenchContractTests(unittest.TestCase):
    def test_matrix_has_two_semantic_groups_and_no_temperature_score(self) -> None:
        with TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            risk_path = report_dir / "20260723-risk-watch.json"
            risk_path.write_text(
                json.dumps(
                    {
                        "as_of": "2026-07-23",
                        "latest": {
                            "metrics": {
                                "star50": {
                                    "as_of": "2026-07-23",
                                    "day_return": -0.01,
                                    "return_5d": -0.03,
                                    "ma20_gap": -0.04,
                                }
                            }
                        },
                        "replay": {
                            "rows": [
                                {
                                    "date": f"2026-07-{day:02d}",
                                    "metrics": {
                                        "star50": {
                                            "close": 1000.0 + day,
                                            "ma20_gap": -0.04,
                                        }
                                    },
                                }
                                for day in range(1, 24)
                            ]
                        },
                        "macro_transmission": {
                            "authority": "diagnostic_only",
                            "energy_supply_shock": {"status": "observe"},
                            "duration_pressure": {"status": "unavailable"},
                            "series_30d": {
                                "brent": {
                                    "source": "https://example.test/brent",
                                    "as_of": "2026-07-22",
                                    "points": [
                                        {"date": "2026-07-21", "close": 80.0},
                                        {"date": "2026-07-22", "close": 82.0},
                                    ],
                                }
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            decision = {
                "source_reports": [
                    {
                        "workflow": "risk_watch",
                        "path": str(risk_path),
                        "as_of": "2026-07-23",
                    }
                ],
                "risk_budget": {"risk_level": "yellow"},
            }

            matrix = build_market_matrix_contract(
                decision,
                report_dir=report_dir,
                generated_at=datetime(2026, 7, 23, 16, 20),
            )

        self.assertEqual(
            [group["id"] for group in matrix["groups"]],
            ["risk_assets", "macro_pressure"],
        )
        cards = [
            card
            for group in matrix["groups"]
            for card in group["cards"]
        ]
        self.assertEqual(
            [card["id"] for card in cards],
            [
                "a_share_technology",
                "us_technology",
                "us_semiconductors",
                "korea",
                "japan",
                "crude_oil",
                "us_duration",
            ],
        )
        self.assertNotIn("score", cards[0])
        self.assertEqual(cards[0]["state_label"], "低于20日均线")
        self.assertEqual(cards[1]["freshness"], "unavailable")
        self.assertEqual(cards[5]["authority"], "diagnostic_only")

    def test_raw_provider_exception_becomes_plain_chinese(self) -> None:
        raw = (
            "HTTPSConnectionPool(host='query1.finance.yahoo.com', port=443): "
            "Read timed out. (read timeout=10.0)"
        )
        self.assertEqual(plain_gap(raw), "上游市场数据源超时")
        self.assertNotIn("HTTPSConnectionPool", plain_gap(raw))
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_workbench.py -v
```

Expected: FAIL because `stock_assist.after_close_workbench` does not exist.

- [ ] **Step 3: Implement safe source loading and matrix normalization**

Create `stock_assist/after_close_workbench.py` with these public interfaces:

```python
"""Typed normalization for the after-close decision workbench."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Mapping


CARD_SPECS = (
    ("risk_assets", "a_share_technology", "A股科技", "risk", "star50"),
    ("risk_assets", "us_technology", "美股科技", "macro", "qqq"),
    ("risk_assets", "us_semiconductors", "美股半导体", "macro", "sox"),
    ("risk_assets", "korea", "韩国", "macro", "kospi"),
    ("risk_assets", "japan", "日本", "risk", "nikkei"),
    ("macro_pressure", "crude_oil", "原油与能源", "macro", "brent"),
    ("macro_pressure", "us_duration", "美国10年期利率", "macro", "us10y"),
)


def plain_gap(value: object) -> str:
    text = " ".join(str(value or "").split())
    lowered = text.lower()
    if "httpsconnectionpool" in lowered or "read timed out" in lowered:
        return "上游市场数据源超时"
    if "connection" in lowered and "closed" in lowered:
        return "上游市场数据源连接中断"
    if "missing_series:" in lowered:
        return "所需市场序列不可用"
    return text or "数据不可用"


def build_market_matrix_contract(
    unified_decision: Mapping[str, object],
    *,
    report_dir: Path,
    generated_at: datetime,
) -> dict[str, object]:
    risk_payload = _load_risk_payload(unified_decision, report_dir)
    cards = [
        _card(spec, risk_payload, generated_at.date())
        for spec in CARD_SPECS
    ]
    return {
        "authority": "diagnostic_only",
        "groups": [
            {
                "id": "risk_assets",
                "label": "全球科技与风险资产",
                "cards": [
                    card for card in cards if card["group"] == "risk_assets"
                ],
            },
            {
                "id": "macro_pressure",
                "label": "宏观压力",
                "cards": [
                    card for card in cards if card["group"] == "macro_pressure"
                ],
            },
        ],
        "portfolio_translation": _portfolio_translation(
            unified_decision,
            cards,
        ),
    }


def _load_risk_payload(
    unified_decision: Mapping[str, object],
    report_dir: Path,
) -> dict[str, object]:
    sources = unified_decision.get("source_reports")
    if not isinstance(sources, list):
        return {}
    root = report_dir.resolve()
    for item in sources:
        if not isinstance(item, dict) or item.get("workflow") != "risk_watch":
            continue
        raw_path = item.get("path")
        if not raw_path:
            return {}
        path = Path(str(raw_path)).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _card(
    spec: tuple[str, str, str, str, str],
    risk_payload: Mapping[str, object],
    report_date: date,
) -> dict[str, object]:
    group, card_id, label, family, key = spec
    if family == "risk":
        source = _risk_series(risk_payload, key)
    else:
        source = _macro_series(risk_payload, key)
    if not source:
        return {
            "group": group,
            "id": card_id,
            "label": label,
            "state": "unavailable",
            "state_label": "不可用",
            "day_change": None,
            "as_of": None,
            "freshness": "unavailable",
            "source": None,
            "points": [],
            "authority": "diagnostic_only",
            "gap": "数据源超时或该序列尚未形成有效收盘数据",
        }
    as_of = _parse_date(source.get("as_of"))
    points = source.get("points")
    values = points if isinstance(points, list) else []
    return {
        "group": group,
        "id": card_id,
        "label": label,
        "state": _state(source),
        "state_label": _state_label(source),
        "day_change": _day_change(values),
        "as_of": as_of.isoformat() if as_of else None,
        "freshness": _freshness(as_of, report_date),
        "source": source.get("source"),
        "points": values[-30:],
        "authority": "diagnostic_only",
        "gap": None,
    }


def _risk_series(
    risk_payload: Mapping[str, object],
    key: str,
) -> dict[str, object]:
    replay = risk_payload.get("replay")
    rows = replay.get("rows") if isinstance(replay, dict) else None
    if not isinstance(rows, list):
        return {}
    points: list[dict[str, object]] = []
    latest_metrics: dict[str, object] = {}
    for row in rows[-30:]:
        if not isinstance(row, dict):
            continue
        metrics = row.get("metrics")
        metric = metrics.get(key) if isinstance(metrics, dict) else None
        if not isinstance(metric, dict) or metric.get("close") is None:
            continue
        points.append({"date": row.get("date"), "close": metric["close"]})
        latest_metrics = metric
    if not points:
        return {}
    return {
        "source": latest_metrics.get("source") or "risk-watch",
        "as_of": points[-1]["date"],
        "points": points,
        "ma20_gap": latest_metrics.get("ma20_gap"),
    }


def _macro_series(
    risk_payload: Mapping[str, object],
    key: str,
) -> dict[str, object]:
    macro = risk_payload.get("macro_transmission")
    trajectories = macro.get("series_30d") if isinstance(macro, dict) else None
    item = trajectories.get(key) if isinstance(trajectories, dict) else None
    return item if isinstance(item, dict) else {}


def _state(source: Mapping[str, object]) -> str:
    gap = number(source.get("ma20_gap"))
    if gap is None:
        return "observed"
    if gap < -0.005:
        return "below_ma20"
    if gap > 0.005:
        return "above_ma20"
    return "near_ma20"


def _state_label(source: Mapping[str, object]) -> str:
    return {
        "below_ma20": "低于20日均线",
        "above_ma20": "高于20日均线",
        "near_ma20": "20日均线附近",
        "observed": "观察中",
    }[_state(source)]


def _day_change(points: list[object]) -> float | None:
    valid = [
        number(item.get("close"))
        for item in points
        if isinstance(item, dict)
    ]
    values = [value for value in valid if value is not None]
    if len(values) < 2 or values[-2] == 0:
        return None
    return values[-1] / values[-2] - 1


def _freshness(as_of: date | None, report_date: date) -> str:
    if as_of is None:
        return "unavailable"
    return "fresh" if (report_date - as_of).days <= 1 else "stale"


def _portfolio_translation(
    unified_decision: Mapping[str, object],
    cards: list[dict[str, object]],
) -> str:
    unavailable = sum(card["freshness"] == "unavailable" for card in cards)
    first_action = str(
        unified_decision.get("first_action")
        or "市场矩阵不改变当前持仓计划"
    )
    if unavailable:
        return f"{first_action}；{unavailable}项跨市场数据不可用，不据此升级风险预算。"
    return f"{first_action}；矩阵仅用于解释环境，不独立授权交易。"


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
```

Remove the unused `dataclass` import before committing if the final module does not yet define view dataclasses.

- [ ] **Step 4: Add the matrix to the canonical after-close payload**

In `stock_assist/workflows/after_close.py`, import:

```python
from datetime import datetime

from stock_assist.after_close_workbench import build_market_matrix_contract
```

Before `create_report_payload(...)` in `build_after_close_payload`, compute:

```python
generated_at = datetime.now()
market_matrix = build_market_matrix_contract(
    unified_decision,
    report_dir=report_dir,
    generated_at=generated_at,
)
```

Pass both the aligned timestamp and additive field:

```python
return create_report_payload(
    kind="after_close",
    workflow="after-close",
    title=first_markdown_title(markdown, "盘后持仓操作指引"),
    generated_at=generated_at.isoformat(timespec="seconds"),
    market_matrix=market_matrix,
```

Keep every existing payload field unchanged.

- [ ] **Step 5: Add payload consistency assertions**

In `tests/test_after_close_reliability.py`, after building a payload, assert:

```python
matrix = payload["market_matrix"]
self.assertEqual(matrix["authority"], "diagnostic_only")
self.assertEqual(
    [group["id"] for group in matrix["groups"]],
    ["risk_assets", "macro_pressure"],
)
self.assertEqual(
    payload["reliability"]["holding_count"],
    len(payload["unified_decision"]["holding_plans"]),
)
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_workbench.py -v
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_reliability.py -v
```

Expected: PASS. No existing payload key is removed.

- [ ] **Step 7: Commit the additive contract**

```powershell
git add stock_assist/after_close_workbench.py stock_assist/workflows/after_close.py tests/test_after_close_workbench.py tests/test_after_close_reliability.py
git commit -m "feat: add after-close market matrix contract"
```

---

### Task 4: Build the typed workbench view model

**Files:**
- Modify: `stock_assist/after_close_workbench.py`
- Modify: `tests/test_after_close_workbench.py`

**Interfaces:**
- Consumes: complete after-close payload and Markdown string
- Produces:
  - `FreshnessBadge`
  - `MatrixCardView`
  - `HoldingActionView`
  - `WorkbenchView`
  - `build_workbench_view(payload, markdown) -> WorkbenchView`

- [ ] **Step 1: Write failing view-model tests**

Add to `tests/test_after_close_workbench.py`:

```python
from stock_assist.after_close_workbench import build_workbench_view


class AfterCloseWorkbenchViewTests(unittest.TestCase):
    def test_view_uses_payload_holdings_not_markdown_broker_parser(self) -> None:
        payload = {
            "generated_at": "2026-07-23T16:20:00",
            "reliability": {
                "holding_count": 3,
                "decision_ready_holdings": 0,
            },
            "actions": [],
            "unified_decision": {
                "plan_date": "2026-07-24",
                "stance": "谨慎持有",
                "first_action": "未触发条件前不操作",
                "risk_budget": {
                    "risk_level": "yellow",
                    "risk_score": 49,
                },
                "holding_plans": [
                    {
                        "name": "????D",
                        "code": "HOLDING-D.EX",
                        "position_action": "等待，不抢跑",
                        "upside_trigger": "收复126.12且板块修复",
                        "flat_trigger": "继续观察",
                        "downside_trigger": "跌破112.27才考虑减仓",
                        "priority": "高",
                    },
                    {
                        "name": "????C",
                        "code": "HOLDING-C.EX",
                        "position_action": "等待，不抢跑",
                        "upside_trigger": "收复1336.14且板块修复",
                        "flat_trigger": "继续观察",
                        "downside_trigger": "跌破1040.34才考虑减仓",
                        "priority": "高",
                    },
                    {
                        "name": "中国人寿",
                        "code": "601628.SH",
                        "position_action": "继续持有",
                        "upside_trigger": "不追涨",
                        "flat_trigger": "继续持有",
                        "downside_trigger": "放量跌破38.45再减仓",
                        "priority": "中",
                    },
                ],
                "blocked_actions": ["持仓字段不完整"],
                "data_gaps": ["关键价位数据已过期"],
                "source_reports": [
                    {
                        "workflow": "market_levels",
                        "as_of": "2026-07-21",
                        "status": "current",
                    }
                ],
            },
            "market_matrix": {
                "authority": "diagnostic_only",
                "groups": [],
                "portfolio_translation": "高Beta暂不加仓",
            },
            "sections": [],
            "signal_outcomes": {"horizons": {}},
            "data_gaps": [],
        }

        view = build_workbench_view(payload, "# 盘后持仓操作指引")

        self.assertEqual(view.holding_count, 3)
        self.assertEqual(view.decision_ready_text, "0/3")
        self.assertEqual(len(view.holdings), 3)
        self.assertEqual(view.holdings[0].name, "????D")
        self.assertEqual(view.holdings[0].downside, "跌破112.27才考虑减仓")
        self.assertEqual(view.default_route, "today")
        market_levels = next(
            item for item in view.freshness if item.id == "market_levels"
        )
        self.assertEqual(market_levels.state, "stale")

    def test_view_translates_internal_status_and_raw_errors(self) -> None:
        payload = {
            "generated_at": "2026-07-23T16:20:00",
            "reliability": {
                "holding_count": 0,
                "decision_ready_holdings": 0,
            },
            "unified_decision": {
                "stance": "谨慎持有",
                "risk_budget": {"risk_level": "yellow", "risk_score": 49},
                "holding_plans": [],
                "blocked_actions": [],
                "data_gaps": [
                    "HTTPSConnectionPool(host='query1.finance.yahoo.com'): "
                    "Read timed out."
                ],
                "source_reports": [],
            },
            "market_matrix": {
                "authority": "diagnostic_only",
                "groups": [],
                "portfolio_translation": "市场矩阵不改变当前计划",
            },
            "sections": [],
            "signal_outcomes": {},
            "data_gaps": [],
        }

        view = build_workbench_view(payload, "# 盘后持仓操作指引")

        self.assertEqual(view.risk_label, "黄灯")
        self.assertIn("上游市场数据源超时", view.gaps)
        self.assertFalse(
            any("HTTPSConnectionPool" in item for item in view.gaps)
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_workbench.py -v
```

Expected: FAIL because the view dataclasses and builder do not exist.

- [ ] **Step 3: Implement the typed model**

Add to `stock_assist/after_close_workbench.py`:

```python
@dataclass(frozen=True)
class FreshnessBadge:
    id: str
    label: str
    as_of: str | None
    state: str


@dataclass(frozen=True)
class MatrixCardView:
    id: str
    label: str
    state_label: str
    day_change: float | None
    as_of: str | None
    freshness: str
    source: str | None
    authority: str
    gap: str | None
    points: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class MatrixGroupView:
    id: str
    label: str
    cards: tuple[MatrixCardView, ...]


@dataclass(frozen=True)
class HoldingActionView:
    name: str
    code: str
    action: str
    upside: str
    flat: str
    downside: str
    priority: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class WorkbenchView:
    generated_at: str
    plan_date: str
    stance: str
    first_action: str
    risk_label: str
    risk_score: int | None
    holding_count: int
    decision_ready_text: str
    freshness: tuple[FreshnessBadge, ...]
    matrix_groups: tuple[MatrixGroupView, ...]
    portfolio_translation: str
    holdings: tuple[HoldingActionView, ...]
    gaps: tuple[str, ...]
    research_sections: tuple[dict[str, object], ...]
    signal_outcomes: Mapping[str, object]
    default_route: str = "today"


def build_workbench_view(
    payload: Mapping[str, object],
    markdown: str,
) -> WorkbenchView:
    decision = (
        payload.get("unified_decision")
        if isinstance(payload.get("unified_decision"), dict)
        else {}
    )
    reliability = (
        payload.get("reliability")
        if isinstance(payload.get("reliability"), dict)
        else {}
    )
    budget = (
        decision.get("risk_budget")
        if isinstance(decision.get("risk_budget"), dict)
        else {}
    )
    holding_rows = (
        decision.get("holding_plans")
        if isinstance(decision.get("holding_plans"), list)
        else []
    )
    blockers = tuple(
        plain_gap(item)
        for item in decision.get("blocked_actions", [])
        if str(item).strip()
    ) if isinstance(decision.get("blocked_actions"), list) else ()
    holdings = tuple(
        HoldingActionView(
            name=str(item.get("name") or item.get("code") or "未命名持仓"),
            code=str(item.get("code") or ""),
            action=str(
                item.get("position_action")
                or item.get("action")
                or "等待确认"
            ),
            upside=str(item.get("upside_trigger") or "不追涨"),
            flat=str(item.get("flat_trigger") or "维持原计划"),
            downside=str(item.get("downside_trigger") or "复核风险线"),
            priority=str(item.get("priority") or "中"),
            blockers=blockers,
        )
        for item in holding_rows
        if isinstance(item, dict)
    )
    matrix = (
        payload.get("market_matrix")
        if isinstance(payload.get("market_matrix"), dict)
        else {}
    )
    gaps = _plain_gaps(payload, decision)
    holding_count = int(reliability.get("holding_count") or len(holdings))
    ready = int(reliability.get("decision_ready_holdings") or 0)
    generated_at_text = str(payload.get("generated_at") or "")
    generated_date = _parse_datetime(generated_at_text).date()
    score = number(budget.get("risk_score"))
    return WorkbenchView(
        generated_at=generated_at_text,
        plan_date=str(decision.get("plan_date") or "待确认"),
        stance=str(decision.get("stance") or "等待确认"),
        first_action=str(decision.get("first_action") or "等待确认"),
        risk_label={
            "green": "绿灯",
            "yellow": "黄灯",
            "orange": "橙灯",
            "red": "红灯",
        }.get(str(budget.get("risk_level")), "待确认"),
        risk_score=int(score) if score is not None else None,
        holding_count=holding_count,
        decision_ready_text=f"{ready}/{holding_count}",
        freshness=_freshness_badges(decision, generated_date),
        matrix_groups=_matrix_groups(matrix),
        portfolio_translation=str(
            matrix.get("portfolio_translation")
            or "市场矩阵不改变当前计划。"
        ),
        holdings=holdings,
        gaps=gaps,
        research_sections=_research_sections(payload),
        signal_outcomes=(
            payload.get("signal_outcomes")
            if isinstance(payload.get("signal_outcomes"), dict)
            else {}
        ),
    )
```

Add complete helpers:

```python
def _freshness_badges(
    decision: Mapping[str, object],
    report_date: date,
) -> tuple[FreshnessBadge, ...]:
    rows = decision.get("source_reports")
    sources = rows if isinstance(rows, list) else []
    badges: list[FreshnessBadge] = []
    labels = {
        "risk_watch": "市场风险",
        "market_pulse": "盘中脉冲",
        "market_levels": "关键价位",
        "ai_capex_watch": "产业研究",
        "style_rotation": "风格轮动",
    }
    for item in sources:
        if not isinstance(item, dict):
            continue
        workflow = str(item.get("workflow") or "")
        as_of = str(item.get("as_of") or "") or None
        status = str(item.get("status") or "unavailable")
        source_date = _parse_date(as_of)
        if status != "current" or source_date is None:
            state = "unavailable"
        elif (report_date - source_date).days > 1:
            state = "stale"
        else:
            state = "fresh"
        badges.append(
            FreshnessBadge(
                id=workflow,
                label=labels.get(workflow, workflow),
                as_of=as_of,
                state=state,
            )
        )
    return tuple(badges)


def _matrix_groups(
    matrix: Mapping[str, object],
) -> tuple[MatrixGroupView, ...]:
    raw_groups = matrix.get("groups")
    groups = raw_groups if isinstance(raw_groups, list) else []
    result: list[MatrixGroupView] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        raw_cards = group.get("cards")
        cards = raw_cards if isinstance(raw_cards, list) else []
        result.append(
            MatrixGroupView(
                id=str(group.get("id") or ""),
                label=str(group.get("label") or ""),
                cards=tuple(
                    MatrixCardView(
                        id=str(card.get("id") or ""),
                        label=str(card.get("label") or ""),
                        state_label=str(card.get("state_label") or "不可用"),
                        day_change=number(card.get("day_change")),
                        as_of=str(card.get("as_of") or "") or None,
                        freshness=str(card.get("freshness") or "unavailable"),
                        source=str(card.get("source") or "") or None,
                        authority=str(
                            card.get("authority") or "diagnostic_only"
                        ),
                        gap=(
                            plain_gap(card.get("gap"))
                            if card.get("gap")
                            else None
                        ),
                        points=tuple(
                            (
                                str(point.get("date") or ""),
                                float(point["close"]),
                            )
                            for point in (
                                card.get("points")
                                if isinstance(card.get("points"), list)
                                else []
                            )
                            if isinstance(point, dict)
                            and number(point.get("close")) is not None
                        ),
                    )
                    for card in cards
                    if isinstance(card, dict)
                ),
            )
        )
    return tuple(result)


def _plain_gaps(
    payload: Mapping[str, object],
    decision: Mapping[str, object],
) -> tuple[str, ...]:
    values: list[object] = []
    for source in (payload.get("data_gaps"), decision.get("data_gaps")):
        if isinstance(source, list):
            values.extend(source)
    return tuple(dict.fromkeys(plain_gap(value) for value in values))


def _research_sections(
    payload: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    sections = payload.get("sections")
    rows = sections if isinstance(sections, list) else []
    markers = ("公告", "研究", "研报", "假设", "同行", "AI", "产业")
    return tuple(
        item
        for item in rows
        if isinstance(item, dict)
        and any(marker in str(item.get("title") or "") for marker in markers)
    )


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime(1970, 1, 1)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_workbench.py -v
```

Expected: all contract and view tests PASS.

- [ ] **Step 5: Commit the view model**

```powershell
git add stock_assist/after_close_workbench.py tests/test_after_close_workbench.py
git commit -m "feat: build typed after-close workbench view"
```

---

### Task 5: Render the market-first app shell, Today, and Market routes

**Files:**
- Create: `stock_assist/after_close_workbench_html.py`
- Modify: `tests/test_after_close_workbench.py`

**Interfaces:**
- Consumes: `WorkbenchView`
- Produces:
  - `render_after_close_workbench(payload, markdown) -> str`
  - complete HTML with `#today` and `#market`
  - no provider access or local `fetch()` dependency

- [ ] **Step 1: Write failing renderer tests**

Add to `tests/test_after_close_workbench.py`:

```python
from stock_assist.after_close_workbench_html import (
    render_after_close_workbench,
)


class AfterCloseWorkbenchHTMLTests(unittest.TestCase):
    def _payload(self) -> dict[str, object]:
        return {
            "title": "盘后持仓操作指引",
            "generated_at": "2026-07-23T16:20:00",
            "reliability": {
                "holding_count": 1,
                "decision_ready_holdings": 0,
            },
            "unified_decision": {
                "plan_date": "2026-07-24",
                "stance": "谨慎持有",
                "first_action": "未触发条件前不操作",
                "risk_budget": {
                    "risk_level": "yellow",
                    "risk_score": 49,
                },
                "holding_plans": [
                    {
                        "name": "????D",
                        "code": "HOLDING-D.EX",
                        "position_action": "等待，不抢跑",
                        "upside_trigger": "收复126.12且板块修复",
                        "flat_trigger": "继续观察",
                        "downside_trigger": "跌破112.27才考虑减仓",
                        "priority": "高",
                    }
                ],
                "blocked_actions": ["持仓字段不完整"],
                "data_gaps": [],
                "source_reports": [],
            },
            "market_matrix": {
                "authority": "diagnostic_only",
                "portfolio_translation": "高Beta暂不加仓",
                "groups": [
                    {
                        "id": "risk_assets",
                        "label": "全球科技与风险资产",
                        "cards": [
                            {
                                "group": "risk_assets",
                                "id": "a_share_technology",
                                "label": "A股科技",
                                "state": "below_ma20",
                                "state_label": "低于20日均线",
                                "day_change": -0.01,
                                "as_of": "2026-07-23",
                                "freshness": "fresh",
                                "source": "risk-watch",
                                "points": [
                                    {"date": "2026-07-22", "close": 1000.0},
                                    {"date": "2026-07-23", "close": 990.0},
                                ],
                                "authority": "diagnostic_only",
                                "gap": None,
                            }
                        ],
                    },
                    {
                        "id": "macro_pressure",
                        "label": "宏观压力",
                        "cards": [],
                    },
                ],
            },
            "sections": [],
            "signal_outcomes": {},
            "data_gaps": [],
        }

    def test_html_is_market_first_and_has_file_safe_routes(self) -> None:
        html = render_after_close_workbench(
            self._payload(),
            "# 盘后持仓操作指引",
        )

        self.assertIn('data-route="today"', html)
        self.assertIn('id="route-today"', html)
        self.assertIn('id="route-market"', html)
        self.assertLess(html.index("今日市场结论"), html.index("明日持仓动作"))
        self.assertIn("全球科技与风险资产", html)
        self.assertIn("高Beta暂不加仓", html)
        self.assertIn("低于20日均线", html)
        self.assertIn("location.hash", html)
        self.assertNotIn('fetch("', html)
        self.assertNotIn("0 / 100", html)

    def test_sparkline_is_accessible_and_has_no_external_asset(self) -> None:
        html = render_after_close_workbench(
            self._payload(),
            "# 盘后持仓操作指引",
        )

        self.assertIn("<svg", html)
        self.assertIn('aria-label="A股科技30日轨迹"', html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link rel=", html)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_workbench.py -v
```

Expected: FAIL because the HTML module does not exist.

- [ ] **Step 3: Implement safe HTML primitives and sparklines**

Create `stock_assist/after_close_workbench_html.py`:

```python
"""Self-contained HTML renderer for the after-close decision workbench."""

from __future__ import annotations

from html import escape
import json
from typing import Mapping

from stock_assist.after_close_workbench import (
    MatrixCardView,
    WorkbenchView,
    build_workbench_view,
    number,
    plain_gap,
)
from stock_assist.branding import PRODUCT_NAME


def render_after_close_workbench(
    payload: Mapping[str, object],
    markdown: str,
) -> str:
    view = build_workbench_view(payload, markdown)
    return _document(view)


def _sparkline(card: MatrixCardView) -> str:
    values = [value for _, value in card.points]
    if len(values) < 2:
        return '<div class="spark-empty">暂无有效30日轨迹</div>'
    low = min(values)
    high = max(values)
    spread = high - low or 1.0
    coordinates = " ".join(
        f"{index * 100 / (len(values) - 1):.1f},"
        f"{36 - ((value - low) / spread * 32):.1f}"
        for index, value in enumerate(values)
    )
    return (
        f'<svg class="spark" viewBox="0 0 100 40" role="img" '
        f'aria-label="{escape(card.label)}30日轨迹">'
        f'<polyline points="{coordinates}" /></svg>'
    )


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.2%}"


def _json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")
```

- [ ] **Step 4: Implement the shell and route script**

Add:

```python
def _document(
    view: WorkbenchView,
    portfolio_button: str = "",
    portfolio_modal: str = "",
    portfolio_script: str = "",
) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(PRODUCT_NAME)} · 盘后决策工作台</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><span>IR</span>{escape(PRODUCT_NAME)}</div>
      <nav aria-label="工作台导航">
        {_nav_button("today", "今日", True)}
        {_nav_button("holdings", "持仓", False)}
        {_nav_button("market", "市场", False)}
        {_nav_button("research", "研究", False)}
        {_nav_button("review", "复盘", False)}
      </nav>
      <p class="authority">条件式决策支持<br>不连接交易，不自动下单</p>
    </aside>
    <div class="workspace">
      {_topbar(view, portfolio_button)}
      {_today_route(view)}
      {_market_route(view)}
      <main id="route-holdings" class="route" data-route-panel="holdings"></main>
      <main id="route-research" class="route" data-route-panel="research"></main>
      <main id="route-review" class="route" data-route-panel="review"></main>
    </div>
  </div>
  <nav class="mobile-nav" aria-label="移动导航">
    {_nav_button("today", "今日", True)}
    {_nav_button("holdings", "持仓", False)}
    {_nav_button("market", "市场", False)}
    {_nav_button("research", "研究", False)}
    {_nav_button("review", "复盘", False)}
  </nav>
  {portfolio_modal}
  <script>{_route_script()}</script>
  {portfolio_script}
</body>
</html>"""


def _nav_button(route: str, label: str, active: bool) -> str:
    selected = ' aria-current="page"' if active else ""
    return (
        f'<button type="button" data-route="{route}"{selected}>'
        f"{escape(label)}</button>"
    )


def _route_script() -> str:
    return """
const routes = new Set(["today", "holdings", "market", "research", "review"]);
function selectRoute(requested) {
  const route = routes.has(requested) ? requested : "today";
  document.querySelectorAll("[data-route-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.routePanel === route);
  });
  document.querySelectorAll("[data-route]").forEach((button) => {
    const active = button.dataset.route === route;
    button.toggleAttribute("aria-current", active);
  });
}
document.querySelectorAll("[data-route]").forEach((button) => {
  button.addEventListener("click", () => {
    location.hash = button.dataset.route;
  });
});
window.addEventListener("hashchange", () => {
  selectRoute(location.hash.slice(1));
});
selectRoute(location.hash.slice(1) || "today");
"""
```

- [ ] **Step 5: Implement Today and Market route renderers**

Add complete route helpers:

```python
def _topbar(view: WorkbenchView, portfolio_button: str = "") -> str:
    badges = "".join(
        f'<span class="freshness {escape(item.state)}">'
        f'{escape(item.label)} {escape(item.as_of or "不可用")}</span>'
        for item in view.freshness
    )
    return (
        '<header class="topbar">'
        f'<div class="freshness-list">{badges}</div>'
        f'<div class="topbar-actions"><span>生成于 {escape(view.generated_at)}</span>'
        f"{portfolio_button}</div>"
        "</header>"
    )


def _today_route(view: WorkbenchView) -> str:
    matrix = "".join(_matrix_group(group) for group in view.matrix_groups)
    actions = "".join(
        "<tr>"
        f'<td><button type="button" class="holding-link" '
        f'data-holding="holding-{index}"><strong>{escape(item.name)}</strong>'
        f'<small>{escape(item.code)}</small></button></td>'
        f'<td>{escape(item.action)}</td>'
        f'<td>{escape(item.downside)}</td>'
        f'<td>{escape("；".join(item.blockers) or "无新增阻断")}</td>'
        f'<td>{escape(item.priority)}</td>'
        "</tr>"
        for index, item in enumerate(view.holdings)
    )
    return f"""
<main id="route-today" class="route active" data-route-panel="today">
  <header class="page-heading">
    <div><h1>今日市场与明日计划</h1>
    <p>{escape(view.plan_date)} · 先判断环境，再处理持仓</p></div>
    <div class="stance">{escape(view.stance)} · {escape(view.risk_label)}
    {escape(str(view.risk_score) if view.risk_score is not None else "—")}</div>
  </header>
  <section class="conclusion">
    <div><span>今日市场结论</span>
    <h2>{escape(_market_conclusion(view))}</h2>
    <p>市场矩阵使用既有状态、变化和轨迹，不提供自创温度分。</p></div>
    <div><span>对持仓的直接含义</span>
    <strong>{escape(view.portfolio_translation)}</strong></div>
  </section>
  <section>
    <header class="section-heading"><div><h2>全球市场矩阵</h2>
    <p>全球科技与风险资产 / 宏观压力</p></div>
    <button type="button" data-route="market">进入市场全景</button></header>
    {matrix}
  </section>
  <section class="action-panel">
    <header class="section-heading"><div><h2>明日持仓动作</h2>
    <p>{view.holding_count}只持仓 · 严格就绪 {escape(view.decision_ready_text)}</p></div>
    <button type="button" data-route="holdings">进入全部持仓</button></header>
    <div class="table-wrap"><table>
      <thead><tr><th>持仓</th><th>首要动作</th><th>触发条件</th><th>阻断</th><th>优先级</th></tr></thead>
      <tbody>{actions}</tbody>
    </table></div>
  </section>
</main>"""


def _market_route(view: WorkbenchView) -> str:
    groups = "".join(_matrix_group(group, expanded=True) for group in view.matrix_groups)
    gaps = "".join(f"<li>{escape(item)}</li>" for item in view.gaps)
    return f"""
<main id="route-market" class="route" data-route-panel="market">
  <header class="page-heading"><div><h1>市场</h1>
  <p>解释市场状态为什么改变或不改变持仓计划</p></div>
  <div class="stance">诊断层 · 不授权交易</div></header>
  {groups}
  <details class="audit"><summary>数据口径与缺口</summary><ul>{gaps}</ul></details>
</main>"""


def _matrix_group(group: object, expanded: bool = False) -> str:
    cards = "".join(_matrix_card(card, expanded) for card in group.cards)
    return (
        f'<section class="matrix-group"><header><h3>{escape(group.label)}</h3></header>'
        f'<div class="matrix">{cards}</div></section>'
    )


def _matrix_card(card: MatrixCardView, expanded: bool) -> str:
    gap = (
        f'<p class="gap">{escape(card.gap)}</p>'
        if card.gap
        else ""
    )
    source = (
        f"<p>来源：{escape(card.source or '未提供')}</p>"
        if expanded
        else ""
    )
    return f"""
<article class="matrix-card {escape(card.freshness)}">
  <header><strong>{escape(card.label)}</strong>
  <span>{escape(card.state_label)}</span></header>
  <div class="change">{escape(_pct(card.day_change))}</div>
  {_sparkline(card)}
  <footer>{escape(card.as_of or "不可用")} · 诊断</footer>
  {gap}{source}
</article>"""


def _market_conclusion(view: WorkbenchView) -> str:
    unavailable = sum(
        card.freshness == "unavailable"
        for group in view.matrix_groups
        for card in group.cards
    )
    if unavailable:
        return f"市场状态仍需谨慎解释，{unavailable}项跨市场数据不可用"
    return "跨市场状态已更新，当前风险预算维持不变"
```

- [ ] **Step 6: Add self-contained responsive CSS**

Implement `_css()` as one returned string containing all selectors used above. The minimum exact rules are:

```python
def _css() -> str:
    return """
:root{color-scheme:dark;--bg:#071014;--panel:#0d171c;--line:#203039;--text:#e6eeee;--muted:#7e9098;--green:#65d7a0;--yellow:#e9ba60;--red:#ef8088}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:13px/1.5 system-ui,"Microsoft YaHei",sans-serif;overflow-x:hidden}
button{font:inherit}
.app-shell{min-height:100vh;display:grid;grid-template-columns:164px minmax(0,1fr)}
.sidebar{position:sticky;top:0;height:100vh;padding:18px 12px;background:#091419;border-right:1px solid #19292f;display:flex;flex-direction:column}
.brand{display:flex;align-items:center;gap:9px;font-weight:800;margin:0 6px 24px}
.brand span{width:30px;height:30px;border-radius:8px;background:var(--green);color:#062117;display:grid;place-items:center}
.sidebar nav{display:grid;gap:5px}
[data-route]{border:0;background:transparent;color:#83959c;text-align:left;padding:10px;border-radius:8px;cursor:pointer}
[data-route][aria-current="page"]{background:#183329;color:#eaf8f1}
.authority{margin-top:auto;color:#61737a;border-top:1px solid #1b2a31;padding-top:12px}
.workspace{min-width:0}
.topbar{min-height:44px;padding:7px 18px;border-bottom:1px solid #18272e;display:flex;justify-content:space-between;gap:12px;align-items:center;color:var(--muted)}
.freshness-list{display:flex;gap:6px;flex-wrap:wrap}
.freshness{border:1px solid #2b433c;border-radius:999px;padding:3px 7px}
.freshness.stale{color:var(--yellow);border-color:#5a4828}
.freshness.unavailable,.freshness.blocked{color:var(--red);border-color:#583238}
.route{display:none;padding:22px 24px 36px}.route.active{display:block}
.page-heading,.section-heading,.conclusion{display:flex;justify-content:space-between;gap:16px}
.page-heading h1{margin:0 0 4px;font-size:25px}.page-heading p,.section-heading p{margin:0;color:var(--muted)}
.stance{border:1px solid #5a4828;background:#231d11;color:var(--yellow);border-radius:9px;padding:7px 10px;height:max-content}
.conclusion{margin:14px 0;padding:14px;border:1px solid var(--line);border-radius:11px;background:var(--panel)}
.conclusion>div{flex:1}.conclusion span{color:var(--muted)}.conclusion h2{margin:5px 0;font-size:18px}
.section-heading{align-items:end;margin:14px 0 8px}.section-heading h2{margin:0;font-size:16px}
.matrix-group{margin-bottom:10px}.matrix-group h3{font-size:12px;color:var(--muted)}
.matrix{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));border:1px solid var(--line);border-radius:10px;overflow:hidden}
.matrix-card{min-width:0;padding:11px;background:#0b151a;border-right:1px solid var(--line)}
.matrix-card header{display:flex;justify-content:space-between;gap:6px}.matrix-card header span{color:var(--muted);font-size:10px}
.matrix-card.stale{opacity:.68}.matrix-card.unavailable{filter:grayscale(1);opacity:.58}.matrix-card .gap{color:var(--yellow)}
.change{font-size:18px;font-weight:800;margin:7px 0}.spark{width:100%;height:42px}.spark polyline{fill:none;stroke:var(--green);stroke-width:2}
.spark-empty{height:42px;display:grid;place-items:center;color:var(--muted);background:#091216;border-radius:6px}
.matrix-card footer{color:var(--muted);font-size:10px}
.action-panel,.audit{border:1px solid var(--line);border-radius:11px;background:var(--panel);padding:12px;margin-top:12px}
.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{padding:9px;border-top:1px solid var(--line);text-align:left}td small{display:block;color:var(--muted)}
.mobile-nav{display:none}
@media(max-width:760px){
  body{padding-bottom:60px}
  .app-shell{grid-template-columns:1fr}.sidebar{display:none}.route{padding:14px 12px 28px}
  .topbar{display:block}.freshness-list{margin-bottom:5px}
  .page-heading,.conclusion{display:block}.stance{margin-top:9px}
  .matrix{display:flex;overflow-x:auto;scroll-snap-type:x mandatory}.matrix-card{min-width:78vw;scroll-snap-align:start}
  .action-panel table,.action-panel tbody,.action-panel tr,.action-panel td{display:block}
  .action-panel thead{display:none}.action-panel tr{border:1px solid var(--line);border-radius:9px;margin:8px 0;padding:8px}
  .action-panel td{border:0;padding:4px}
  .mobile-nav{position:fixed;z-index:5;display:grid;grid-template-columns:repeat(5,1fr);left:0;right:0;bottom:0;background:#091419;border-top:1px solid var(--line)}
  .mobile-nav button{text-align:center;padding:12px 3px}
}
"""
```

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_workbench.py -v
```

Expected: PASS. HTML contains no external CSS/JS and no uncalibrated score.

- [ ] **Step 8: Commit shell, Today, and Market routes**

```powershell
git add stock_assist/after_close_workbench_html.py tests/test_after_close_workbench.py
git commit -m "feat: render market-first after-close shell"
```

---

### Task 6: Add Holdings, Research, Review, and portfolio-import controls

**Files:**
- Modify: `stock_assist/after_close_workbench_html.py`
- Modify: `stock_assist/reports.py:1484-1605`
- Modify: `tests/test_after_close_workbench.py`
- Modify: `tests/test_reports.py`

**Interfaces:**
- Consumes: `WorkbenchView.holdings`, `research_sections`, `signal_outcomes`
- Produces: complete `#holdings`, `#research`, `#review` routes and public `portfolio_import_html_parts()`

- [ ] **Step 1: Write failing route and regression tests**

Add to `AfterCloseWorkbenchHTMLTests`:

```python
def test_html_has_all_five_interfaces_and_action_playbook_first(self) -> None:
    html = render_after_close_workbench(
        self._payload(),
        "# 盘后持仓操作指引",
    )

    for route in ("today", "holdings", "market", "research", "review"):
        self.assertIn(f'id="route-{route}"', html)
        self.assertIn(f'data-route="{route}"', html)
    holdings = html[html.index('id="route-holdings"'):]
    self.assertLess(holdings.index("明日动作剧本"), holdings.index("关键价位与走势"))
    self.assertLess(holdings.index("关键价位与走势"), holdings.index("研究证据"))
    self.assertIn("上涨情境", holdings)
    self.assertIn("横盘情境", holdings)
    self.assertIn("下跌情境", holdings)
    self.assertIn('data-holding="holding-0"', html)
    self.assertIn("信号仍在成熟", html)

def test_normal_ui_does_not_show_raw_provider_exception(self) -> None:
    payload = self._payload()
    payload["unified_decision"]["data_gaps"] = [
        "HTTPSConnectionPool(host='query1.finance.yahoo.com'): Read timed out."
    ]

    html = render_after_close_workbench(
        payload,
        "# 盘后持仓操作指引",
    )

    self.assertNotIn("HTTPSConnectionPool", html)
    self.assertIn("上游市场数据源超时", html)

def test_portfolio_import_controls_remain_local_and_explicit(self) -> None:
    html = render_after_close_workbench(
        self._payload(),
        "# 盘后持仓操作指引",
    )

    self.assertIn("portfolio-import-open", html)
    self.assertIn("127.0.0.1:8765", html)
    self.assertNotIn("showSaveFilePicker", html)
```

In `tests/test_reports.py`, add:

```python
def test_generic_markdown_renderer_still_uses_collapsed_sections(self) -> None:
    html = markdown_report_to_html("# T\n\n## S\n\n- evidence")
    self.assertIn('<details class="report-section">', html)
    self.assertNotIn('id="route-today"', html)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_workbench.py -v
C:\Python313\python.exe -m unittest discover -s tests -p test_reports.py -v
```

Expected: workbench tests FAIL because three routes are empty and import controls are absent; generic renderer test PASS.

- [ ] **Step 3: Expose the existing portfolio-import HTML parts**

Add this public wrapper to `stock_assist/reports.py` immediately before `_portfolio_import_button`:

```python
def portfolio_import_html_parts() -> tuple[str, str, str]:
    """Return the existing local-only portfolio import button, modal, and script."""

    return (
        _portfolio_import_button(),
        _portfolio_import_modal(),
        _portfolio_import_script(),
    )
```

Import it in `stock_assist/after_close_workbench_html.py`:

```python
from stock_assist.reports import portfolio_import_html_parts
```

After building `view` inside `render_after_close_workbench`, call:

```python
portfolio_button, portfolio_modal, portfolio_script = portfolio_import_html_parts()
return _document(
    view,
    portfolio_button=portfolio_button,
    portfolio_modal=portfolio_modal,
    portfolio_script=portfolio_script,
)
```

In `render_after_close_workbench`, replace `return _document(view)` with the exact call above. The Task 5 `_document` and `_topbar` signatures already accept these strings. Keep all existing loopback-only safety text unchanged.

- [ ] **Step 4: Render Holdings and action playbooks**

Add:

```python
def _holdings_route(view: WorkbenchView) -> str:
    cards = "".join(_holding_card(item, index) for index, item in enumerate(view.holdings))
    return f"""
<main id="route-holdings" class="route" data-route-panel="holdings">
  <header class="page-heading"><div><h1>持仓</h1>
  <p>先看动作剧本，再看价位和研究证据</p></div>
  <div class="stance">{view.holding_count}只 · 就绪 {escape(view.decision_ready_text)}</div></header>
  <div class="holding-list">{cards}</div>
</main>"""


def _holding_card(item: object, index: int) -> str:
    blockers = "；".join(item.blockers) or "无新增阻断"
    return f"""
<article class="holding-card" id="holding-{index}" tabindex="-1">
  <header><div><h2>{escape(item.name)}</h2><small>{escape(item.code)}</small></div>
  <strong>{escape(item.action)}</strong></header>
  <section class="playbook"><h3>明日动作剧本</h3>
    <div class="scenario up"><span>上涨情境</span><b>{escape(item.upside)}</b></div>
    <div class="scenario flat"><span>横盘情境</span><b>{escape(item.flat)}</b></div>
    <div class="scenario down"><span>下跌情境</span><b>{escape(item.downside)}</b></div>
  </section>
  <div class="blocker"><b>当前阻断</b>{escape(blockers)}</div>
  <details><summary>关键价位与走势</summary>
  <p>价格与关键价位只用于确认是否触发，不置于动作剧本之前。</p></details>
  <details><summary>研究证据</summary>
  <p>公告、产业证据与反证统一进入研究界面。</p></details>
</article>"""
```

Replace the empty holdings route in `_document` with `_holdings_route(view)`.

- [ ] **Step 5: Render Research and Review**

Add:

```python
def _research_route(view: WorkbenchView) -> str:
    cards = "".join(
        "<article class=\"research-card\">"
        f"<h2>{escape(str(section.get('title') or '研究证据'))}</h2>"
        f"<ul>{''.join(f'<li>{escape(plain_gap(item))}</li>' for item in section.get('items', []) if str(item).strip())}</ul>"
        "</article>"
        for section in view.research_sections
    )
    if not cards:
        cards = '<div class="empty-state">当前没有可展示的持仓相关研究变化。</div>'
    return f"""
<main id="route-research" class="route" data-route-panel="research">
  <header class="page-heading"><div><h1>研究</h1>
  <p>公告、产业证据、假设和反证集中在这里</p></div>
  <div class="stance">证据不独立授权交易</div></header>
  <div class="research-grid">{cards}</div>
</main>"""


def _review_route(view: WorkbenchView) -> str:
    horizons = (
        view.signal_outcomes.get("horizons")
        if isinstance(view.signal_outcomes.get("horizons"), dict)
        else {}
    )
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(label))}</td>"
        f"<td>{escape(str(item.get('matured', 0)))}</td>"
        f"<td>{escape(str(item.get('pending', 0)))}</td>"
        f"<td>{escape(_hit_rate(item.get('hit_rate')))}</td>"
        "</tr>"
        for label, item in horizons.items()
        if isinstance(item, dict)
    )
    return f"""
<main id="route-review" class="route" data-route-panel="review">
  <header class="page-heading"><div><h1>复盘</h1>
  <p>事前计划与事后结果分开记录</p></div>
  <div class="stance">信号仍在成熟</div></header>
  <div class="table-wrap"><table>
    <thead><tr><th>窗口</th><th>已成熟</th><th>待成熟</th><th>命中率</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="muted">样本不足时保持 Pending，不宣称稳定优势。</p>
</main>"""


def _hit_rate(value: object) -> str:
    parsed = number(value)
    return "Pending" if parsed is None else f"{parsed:.0%}"
```

Use the public `number()` and `plain_gap()` imports already added to `stock_assist.after_close_workbench_html`.

Extend `_route_script()` after the route-button listeners so a Today action row opens the corresponding action playbook:

```javascript
document.querySelectorAll("[data-holding]").forEach((button) => {
  button.addEventListener("click", () => {
    const targetId = button.dataset.holding;
    selectRoute("holdings");
    location.hash = "holdings";
    window.requestAnimationFrame(() => {
      const target = document.getElementById(targetId);
      if (target) {
        target.scrollIntoView({behavior: "smooth", block: "start"});
        target.focus({preventScroll: true});
      }
    });
  });
});
```

The holding-card snippet already includes `tabindex="-1"` so the focus call is valid.

Replace the empty research and review routes in `_document`.

- [ ] **Step 6: Add the route-specific responsive styles**

Append to `_css()`:

```css
.holding-list{display:grid;gap:12px}.holding-card,.research-card,.empty-state{border:1px solid var(--line);border-radius:11px;background:var(--panel);padding:14px}
.holding-card>header{display:flex;justify-content:space-between;gap:12px}.holding-card h2{margin:0}.holding-card small,.muted{color:var(--muted)}
.playbook{margin:12px 0}.playbook h3{font-size:13px}.scenario{display:grid;grid-template-columns:90px 1fr;gap:10px;padding:9px;border-top:1px solid var(--line)}
.scenario.up b{color:var(--green)}.scenario.flat b{color:var(--yellow)}.scenario.down b{color:var(--red)}
.blocker{border:1px solid #583238;background:#251417;color:#e8a0a5;border-radius:8px;padding:9px}.blocker b{display:block}
.holding-card details{margin-top:9px;border-top:1px solid var(--line);padding-top:8px}
.holding-link{border:0;background:transparent;color:inherit;text-align:left;padding:0;cursor:pointer}.holding-link small{display:block;color:var(--muted)}
.research-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.research-card h2{font-size:15px}
.topbar-actions{display:flex;align-items:center;gap:10px}.ui-button{appearance:none;border:1px solid rgba(101,215,160,.38);border-radius:8px;padding:8px 13px;color:#07110d;background:linear-gradient(135deg,var(--green),#8aebba);font:inherit;font-weight:800;cursor:pointer}.ui-button.secondary{color:var(--text);background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.14)}
.import-modal{width:min(900px,calc(100% - 28px));max-height:calc(100vh - 36px);padding:0;border:1px solid rgba(255,255,255,.14);border-radius:12px;color:var(--text);background:#0d1317;box-shadow:0 30px 100px rgba(0,0,0,.72)}.import-modal::backdrop{background:rgba(0,0,0,.72);backdrop-filter:blur(5px)}.import-shell{padding:20px}.import-head{display:flex;justify-content:space-between;gap:18px;align-items:start}.import-head h2{margin:0 0 4px}.import-head p,.import-hint{color:var(--muted);font-size:12px}.import-close{border:0;color:var(--muted);background:transparent;font-size:26px;cursor:pointer}.import-input{width:100%;min-height:210px;margin-top:12px;padding:12px;resize:vertical;border:1px solid rgba(255,255,255,.13);border-radius:8px;color:var(--text);background:#070b0e;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}.import-toolbar{display:flex;flex-wrap:wrap;gap:9px;margin:12px 0;align-items:center}.import-status{margin-left:auto;color:var(--muted);font-size:12px}.import-preview{max-height:230px;overflow:auto;border:1px solid rgba(255,255,255,.08);border-radius:8px}.import-preview table{width:100%;border-collapse:collapse;font-size:12px}.import-preview th,.import-preview td{padding:8px 9px;border-bottom:1px solid rgba(255,255,255,.07);text-align:left;white-space:nowrap}.import-preview th{position:sticky;top:0;color:var(--muted);background:#121a1f}
@media(max-width:760px){.research-grid{grid-template-columns:1fr}.scenario{grid-template-columns:1fr}}
```

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_workbench.py -v
C:\Python313\python.exe -m unittest discover -s tests -p test_reports.py -v
```

Expected: PASS. The old generic/NGA renderer remains unchanged.

- [ ] **Step 8: Commit complete routes**

```powershell
git add stock_assist/after_close_workbench_html.py stock_assist/reports.py tests/test_after_close_workbench.py tests/test_reports.py
git commit -m "feat: add workbench holdings research and review"
```

---

### Task 7: Integrate the workbench renderer and verify a real artifact

**Files:**
- Modify: `stock_assist/workflows/after_close.py:19,322-353`
- Modify: `tests/test_after_close_reliability.py`
- Modify: `tests/test_unified_decision.py`

**Interfaces:**
- Consumes: final after-close payload and Markdown
- Produces: CLI-generated `reports/<timestamp>-after-close.html` using `render_after_close_workbench`

- [ ] **Step 1: Write failing bundle integration assertions**

Add to `tests/test_after_close_reliability.py`:

```python
@patch("stock_assist.workflows.after_close.build_after_close_report")
@patch("stock_assist.workflows.after_close.build_after_close_payload")
def test_bundle_uses_payload_driven_workbench_renderer(
    self,
    build_payload: object,
    build_report: object,
) -> None:
    build_report.return_value = ACTION_MARKDOWN
    payload = {
        "generated_at": "2026-07-23T16:20:00",
        "reliability": {
            "holding_count": 0,
            "decision_ready_holdings": 0,
        },
        "unified_decision": {
            "holding_plans": [],
            "holding_execution_plans": [],
            "risk_budget": {},
            "blocked_actions": [],
            "data_gaps": [],
            "source_reports": [],
        },
        "market_matrix": {
            "authority": "diagnostic_only",
            "groups": [],
            "portfolio_translation": "不改变当前计划",
        },
        "sections": [],
        "signal_outcomes": {},
        "data_gaps": [],
    }
    build_payload.side_effect = [payload, payload]

    result, markdown, html = build_after_close_bundle(
        portfolio=Portfolio(
            cash=None,
            holdings=[],
            source=Path("data/portfolio.json"),
        ),
    )

    self.assertIs(result, payload)
    self.assertIn('id="route-today"', html)
    self.assertIn("不改变当前计划", html)
    self.assertNotIn('class="dashboard"', html)
```

Add `build_after_close_bundle` to the existing import from
`stock_assist.workflows.after_close`; `Path` and `Portfolio` are already imported
by this test module.

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_reliability.py -v
```

Expected: FAIL because `build_after_close_bundle` still calls `markdown_report_to_html`.

- [ ] **Step 3: Switch only after-close to the new renderer**

In `stock_assist/workflows/after_close.py`, import:

```python
from stock_assist.after_close_workbench_html import (
    render_after_close_workbench,
)
```

Change the final return in `build_after_close_bundle` from:

```python
return payload, markdown, markdown_report_to_html(markdown)
```

to:

```python
return payload, markdown, render_after_close_workbench(payload, markdown)
```

Remove `markdown_report_to_html` from this module's imports if no other code uses it.

- [ ] **Step 4: Run all affected tests**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_workbench.py -v
C:\Python313\python.exe -m unittest discover -s tests -p test_after_close_reliability.py -v
C:\Python313\python.exe -m unittest discover -s tests -p test_unified_decision.py -v
C:\Python313\python.exe -m unittest discover -s tests -p test_reports.py -v
C:\Python313\python.exe -m unittest discover -s tests -p test_macro_transmission_workflow.py -v
```

Expected: all PASS.

- [ ] **Step 5: Generate a fresh real triplet**

Run:

```powershell
$env:PYTHONPATH='D:\work\_archive\stock-assist-legacy-20260707\.venv\Lib\site-packages'
C:\Python313\python.exe -m stock_assist.cli risk-watch
C:\Python313\python.exe -m stock_assist.cli after-close
```

Expected:

- fresh matching JSON, Markdown, and HTML timestamps;
- `after-close.json` contains `market_matrix.groups`;
- `after-close.html` contains `route-today`, `route-holdings`, `route-market`, `route-research`, and `route-review`;
- macro timeouts remain explicit unavailable cards;
- no trade or portfolio write occurs.

- [ ] **Step 6: Validate artifact consistency with a bounded script**

Run:

```powershell
@'
import json
from pathlib import Path

report_dir = Path("reports")
payload_path = sorted(report_dir.glob("*-after-close.json"))[-1]
html_path = payload_path.with_suffix(".html")
markdown_path = payload_path.with_suffix(".md")
payload = json.loads(payload_path.read_text(encoding="utf-8"))
html = html_path.read_text(encoding="utf-8")
markdown = markdown_path.read_text(encoding="utf-8")

holding_count = int(payload["reliability"]["holding_count"])
plans = payload["unified_decision"]["holding_plans"]
assert holding_count == len(plans), (holding_count, len(plans))
assert payload["market_matrix"]["authority"] == "diagnostic_only"
assert "HTTPSConnectionPool" not in html
assert "route-today" in html
assert "route-holdings" in html
assert "route-market" in html
assert "route-research" in html
assert "route-review" in html
assert markdown.startswith("# ")
print(payload_path.name, holding_count, "CONSISTENT")
'@ | C:\Python313\python.exe -
```

Expected: one line ending in `CONSISTENT`.

- [ ] **Step 7: Browser QA desktop and mobile**

Use `browser:control-in-app-browser` with the newest HTML:

1. Open the file directly.
2. At 1440×900, verify:
   - first viewport shows market conclusion, both matrix groups, and portfolio translation;
   - holding actions begin in the viewport or after one short scroll;
   - all five navigation buttons change routes;
   - no console errors;
   - no horizontal overflow.
3. At 390×844, verify:
   - bottom navigation is visible;
   - matrix cards scroll horizontally;
   - holding table becomes holding cards;
   - no page-level horizontal overflow;
   - every detail is reachable without hover.
4. Click one holding and verify action playbook order:
   - `明日动作剧本`;
   - `关键价位与走势`;
   - `研究证据`.
5. Search visible text for:
   - `HTTPSConnectionPool`;
   - `support_testing`;
   - `candidate`;
   - contradictory holding counts.

Expected: none of the internal or raw strings are visible in normal routes.

- [ ] **Step 8: Commit integration**

```powershell
git add stock_assist/workflows/after_close.py tests/test_after_close_reliability.py tests/test_unified_decision.py
git commit -m "feat: use decision workbench for after-close"
```

Do not add generated reports unless the repository already tracks that exact artifact class.

---

### Task 8: Document, validate, independently review, and close `feat-058`

**Files:**
- Modify: `docs/harness.md`
- Modify: `docs/memory/architecture.md`
- Modify: `configs/architecture.json`
- Regenerate: `docs/architecture.html`
- Modify: `feature_list.json`
- Modify: `configs/product_governance.json`
- Modify: `CURRENT_STATE.md`
- Modify: `progress.md`
- Modify: `session-handoff.md`
- Modify: `tests/test_harness_integration.py`

**Interfaces:**
- Consumes: verified real workbench artifact and test evidence
- Produces: `feat-058=pass`; no active experiment; `feat-056` restored as pending next

- [ ] **Step 1: Add the Harness acceptance contract**

Under `### After-Close Report` in `docs/harness.md`, add:

```markdown
- The after-close HTML is a self-contained five-interface workbench with `today`, `holdings`, `market`, `research`, and `review` hash routes.
- `today` is market-first: conclusion, two-group market matrix, portfolio translation, then holding actions.
- Matrix cards use explicit states, changes, bounded trajectories, dates, freshness, and diagnostic authority; no uncalibrated 0-100 temperature score is allowed.
- A holding action playbook appears before price charts or research evidence.
- Stale, unavailable, and blocked states remain distinct; raw provider exceptions stay out of normal routes.
- Direct `file://` use, 1440x900 desktop, and 390px mobile must pass route, overflow, and console checks.
```

- [ ] **Step 2: Update architecture sources**

In `configs/architecture.json`, add these outputs to the existing Portfolio Intelligence or after-close node:

```json
"additive market-matrix contract with bounded 30-session trajectories",
"self-contained five-route after-close decision workbench"
```

Add the new modules to its source or implementation file list:

```json
"stock_assist/after_close_workbench.py",
"stock_assist/after_close_workbench_html.py"
```

Update `docs/memory/architecture.md` with one durable paragraph:

```markdown
The after-close JSON remains the canonical client contract. The HTML renderer now consumes a typed workbench view derived from that payload and renders five hash-routed interfaces in one file. Provider access remains upstream in Core monitor workflows; the workbench renderer performs no provider queries.
```

- [ ] **Step 3: Regenerate architecture and run full verification**

Run:

```powershell
$env:PYTHONPATH='D:\work\_archive\stock-assist-legacy-20260707\.venv\Lib\site-packages'
C:\Python313\python.exe -m unittest discover -s tests -v
C:\Python313\python.exe -m compileall stock_assist
C:\Python313\python.exe scripts\validate_project_memory.py
C:\Python313\python.exe -m stock_assist.cli architecture
C:\Python313\python.exe scripts\validate_project_memory.py
C:\Python313\python.exe -m stock_assist.cli harness-smoke
```

Expected:

- all tests PASS;
- compileall PASS;
- architecture artifact matches its source digest;
- project-memory validation PASS;
- Harness smoke reports 100/100.

- [ ] **Step 4: Request independent read-only review**

Invoke `superpowers:requesting-code-review` with this bounded contract:

```text
Review feat-058 against docs/superpowers/specs/2026-07-23-after-close-decision-workbench-design.md and docs/superpowers/plans/2026-07-23-after-close-decision-workbench.md.

Verify:
1. JSON and Markdown compatibility;
2. no provider query in presentation code;
3. no uncalibrated market-temperature score;
4. market-first route order and all five routes;
5. holding action playbook precedes chart/research evidence;
6. freshness/unavailable/blocked precedence;
7. no raw provider errors in normal UI;
8. file://, desktop, and mobile evidence;
9. macro diagnostic authority remains unchanged;
10. no unrelated user files are committed.

Return Critical/Important/Minor findings and PASS only if no required change remains.
```

Expected: PASS with no Critical or Important findings. Fix any finding with a focused RED/GREEN test and rerun affected verification before closeout.

- [ ] **Step 5: Write the failing closeout assertion**

Replace the activation method in `tests/test_harness_integration.py` with:

```python
def test_restart_snapshot_records_workbench_closeout(self) -> None:
    current_state = (PROJECT_ROOT / "CURRENT_STATE.md").read_text(encoding="utf-8")
    self.assertIn('"next_feature_id": "feat-056"', current_state)

    feature_payload = json.loads(
        (PROJECT_ROOT / "feature_list.json").read_text(encoding="utf-8")
    )
    feature_status = {
        item["id"]: item["status"]
        for item in feature_payload["features"]
    }
    self.assertEqual(feature_status["feat-056"], "pending")
    self.assertEqual(feature_status["feat-058"], "pass")

    governance = json.loads(
        (PROJECT_ROOT / "configs" / "product_governance.json").read_text(
            encoding="utf-8"
        )
    )
    self.assertEqual(governance["active_experiments"], [])
    self.assertEqual(
        [item["feature_id"] for item in governance["queued_experiments"]],
        ["feat-056"],
    )
```

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_harness_integration.py -v
```

Expected: FAIL until the closeout documents are updated.

- [ ] **Step 6: Close the feature truthfully**

Set `feat-058.status` to `pass` and replace its evidence with:

```text
Implemented and independently verified on codex/feat-058-after-close-decision-workbench. The after-close triplet preserves canonical JSON and Markdown while HTML now provides market-first today, holdings, market, research, and review routes in one file. The matrix is split into global technology/risk assets and macro pressure, uses bounded trajectories and explicit freshness without an uncalibrated temperature score, keeps missing series unavailable, and preserves diagnostic-only macro authority. JSON/Markdown/HTML consistency, file:// navigation, 1440x900 desktop, 390px mobile, raw-error suppression, full tests, compileall, project-memory validation, generated architecture parity, Harness 100/100, and independent read-only review all pass. feat-056 remains pending next.
```

Set `active_experiments` to `[]`, retain the queued `feat-056` object unchanged, restore `CURRENT_STATE.md` to `"next_feature_id": "feat-056"`, and append final evidence to `progress.md` and `session-handoff.md`.

- [ ] **Step 7: Run final closeout verification**

Run:

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p test_harness_integration.py -v
C:\Python313\python.exe scripts\validate_project_memory.py
git diff --check
git status --short
```

Expected:

- focused integration tests PASS;
- project-memory validation PASS;
- no whitespace errors;
- only intended tracked changes remain;
- `.superpowers/`, `300308_cninfo_filings.json`, and `tmp/` remain untracked and untouched.

- [ ] **Step 8: Commit closeout**

```powershell
git add docs/harness.md docs/memory/architecture.md configs/architecture.json docs/architecture.html feature_list.json configs/product_governance.json CURRENT_STATE.md progress.md session-handoff.md tests/test_harness_integration.py
git commit -m "docs: verify after-close decision workbench"
```

- [ ] **Step 9: Finish the branch**

Invoke `superpowers:finishing-a-development-branch`. Present merge, PR, keep-branch, or discard options only after every verification command and the independent review pass.

---

## Execution Checkpoints

Review after each commit:

1. `docs: activate after-close decision workbench`
2. `feat: expose bounded macro trajectories`
3. `feat: add after-close market matrix contract`
4. `feat: build typed after-close workbench view`
5. `feat: render market-first after-close shell`
6. `feat: add workbench holdings research and review`
7. `feat: use decision workbench for after-close`
8. `docs: verify after-close decision workbench`

Stop and request user direction if:

- activating `feat-058` would displace another active experiment besides the explicitly pending `feat-056`;
- a new market provider is required to make the first version useful;
- the renderer would need to query providers;
- preserving portfolio import would require a new write path;
- diagnostic matrix data would change risk score, risk budget, or holding actions;
- the real artifact cannot keep JSON/HTML holding counts and source dates consistent.
