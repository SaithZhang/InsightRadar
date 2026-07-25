# Macro Transmission Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a point-in-time, replayable macro shadow that distinguishes an oil observation from a confirmed energy-supply, technology-duration, or Korea import-stress state without changing `risk-watch` scores or budgets.

**Architecture:** Put deterministic state evaluation and replay in a focused `stock_assist.macro_transmission` module. The existing `risk-watch` workflow fetches the additional market series, builds the shadow object, and renders it in its existing JSON/Markdown/HTML triplet; `stock_assist.risk_watch` scoring remains untouched.

**Tech Stack:** Python 3.10+, standard-library `dataclasses`/`datetime`/`statistics`, existing `DailyPoint`/`DailySeries`, existing Yahoo daily-history adapter, JSON configuration, `unittest`, existing report payload and architecture renderers.

**Design Source:** [Energy, Technology, and HBM Shadow-Intelligence Design](../specs/2026-07-23-energy-tech-hbm-shadow-design.md). The independent HBM subsystem is planned in [HBM Profit Allocation Shadow Implementation Plan](2026-07-23-hbm-profit-allocation-shadow.md).

## Global Constraints

- Execute only after explicit queue reprioritization; `feat-056` remains the next and sole queued Harness experiment when this plan is written.
- The 2026-07-23 exploratory statistics are research evidence, not fixed production thresholds.
- Crude oil alone must never confirm technology duration pressure.
- Keep `energy_supply_shock`, `duration_pressure`, and `korea_import_stress` independent.
- Every state is one of `unavailable`, `observe`, `confirmed`, or `invalidated`.
- Every output keeps source URL, source/fetch/event timestamps, timezone, counter-evidence, gaps, event count, calibration state, and `authority="diagnostic_only"`.
- Use only observations available at `as_of`; future bars and later confirmation timestamps are excluded.
- Evaluate from the China after-close viewpoint: Western oil, yield, and US-equity closes use the last session completed before the configured Asia/Shanghai cutoff, while Korea may use its same-day completed close.
- Cluster overlapping triggers into independent episodes before counting calibration events.
- Show absolute and S&P 500-relative outcomes separately.
- Missing, stale, conflicting, or calendar-misaligned data remains explicit and cannot become zero or neutral.
- The shadow cannot mutate `RiskSnapshot`, signal families, risk lights, `RISK_BUDGETS`, `RISK_VETO`, strict decision readiness, or portfolio actions.
- Preserve the existing `risk-watch` JSON, Markdown, and HTML outputs.
- No new command, service, cloud dependency, automatic alert, order, or trade authority.
- Do not start or depend on the future Jin10 product adapter; configured event fixtures use primary-source metadata directly.

---

## File Map

| Path | Responsibility |
|---|---|
| `stock_assist/macro_transmission.py` | Typed states, point-in-time evaluation, event clustering, forward-outcome calibration |
| `stock_assist/data_sources/global_markets.py` | Exchange-timezone daily-bar date normalization for the reused Yahoo history adapter |
| `configs/macro_transmission.json` | Live symbols, source metadata, thresholds, event evidence, replay rules |
| `configs/macro_transmission.example.json` | Empty credential-free configuration contract |
| `tests/test_macro_transmission.py` | State rules, no-lookahead, invalidation, clustering, calibration gates |
| `tests/test_global_markets.py` | Exchange-local daily date parsing at UTC boundaries |
| `stock_assist/workflows/risk_watch.py` | Fetch extra series, attach shadow payload, render independent section |
| `tests/test_macro_transmission_workflow.py` | Workflow integration, rendering, gap behavior, budget non-interference |
| `configs/architecture.json` | Add macro-shadow inputs and diagnostic output to the existing `risk_watch` node |
| `docs/architecture.html` | Regenerated architecture view |
| `docs/harness.md` | Runtime and verification contract |
| `feature_list.json`, `progress.md`, `session-handoff.md`, `CURRENT_STATE.md` | Evidence and restart state only when implementation is explicitly activated |

---

### Task 1: Typed Point-in-Time State Evaluator

**Files:**
- Create: `stock_assist/macro_transmission.py`
- Create: `tests/test_macro_transmission.py`
- Modify: `stock_assist/data_sources/global_markets.py`
- Create: `tests/test_global_markets.py`
- Create: `configs/macro_transmission.json`
- Create: `configs/macro_transmission.example.json`

**Interfaces:**
- Produces: `SourceRef`
- Produces: `VerifiedMacroEvent`
- Produces: `ShadowState`
- Produces: `MacroTransmissionObservation`
- Produces: `evaluate_macro_transmission(series: dict[str, DailySeries], as_of: date, config: dict[str, object], events: tuple[VerifiedMacroEvent, ...] = (), previous: MacroTransmissionObservation | None = None) -> MacroTransmissionObservation`
- Consumes keys: `brent`, `wti`, `us10y`, `sp500`, `qqq`, `sox`, `kospi`

- [ ] **Step 1: Write failing oil-only and triple-confirmation tests**

```python
from __future__ import annotations

from datetime import date, timedelta
import unittest

from stock_assist.macro_transmission import (
    VerifiedMacroEvent,
    evaluate_macro_transmission,
)
from stock_assist.risk_watch import DailyPoint, DailySeries


def series(key: str, closes: list[float]) -> DailySeries:
    start = date(2026, 1, 1)
    return DailySeries(
        key=key,
        name=key,
        source=f"https://example.test/{key}",
        points=tuple(DailyPoint(start + timedelta(days=index), value) for index, value in enumerate(closes)),
    )


BASE_CONFIG = {
    "thresholds": {
        "oil_5d_return": 0.08,
        "yield_5d_change_pct_points": 0.15,
        "qqq_sp500_5d_relative": -0.03,
        "sox_sp500_5d_relative": -0.04,
        "kospi_sp500_5d_relative": -0.04,
        "oil_unwind_5d_return": -0.05,
    },
    "yield_divisor": 10.0,
    "event_max_age_days": 20,
}


class MacroTransmissionTests(unittest.TestCase):
    def test_oil_only_stays_observe_and_cannot_confirm_duration_pressure(self) -> None:
        inputs = {
            "brent": series("brent", [100.0] * 15 + [102, 104, 106, 108, 110]),
            "wti": series("wti", [100.0] * 20),
            "us10y": series("us10y", [44.0] * 20),
            "sp500": series("sp500", [100.0] * 20),
            "qqq": series("qqq", [100.0] * 20),
            "sox": series("sox", [100.0] * 20),
            "kospi": series("kospi", [100.0] * 20),
        }
        result = evaluate_macro_transmission(inputs, date(2026, 1, 20), BASE_CONFIG)
        self.assertEqual("observe", result.energy_supply_shock.status)
        self.assertNotEqual("confirmed", result.duration_pressure.status)
        self.assertIn("missing_verified_supply_event", result.energy_supply_shock.blocked_rule_ids)
        self.assertEqual("diagnostic_only", result.authority)

    def test_verified_supply_event_rates_and_relative_weakness_confirm_duration(self) -> None:
        inputs = {
            "brent": series("brent", [100.0] * 15 + [102, 104, 106, 108, 110]),
            "wti": series("wti", [100.0] * 15 + [102, 104, 106, 108, 109]),
            "us10y": series("us10y", [42.0] * 15 + [42.5, 43, 43.5, 44, 44.5]),
            "sp500": series("sp500", [100.0] * 20),
            "qqq": series("qqq", [100.0] * 15 + [99, 98, 97, 96, 95]),
            "sox": series("sox", [100.0] * 15 + [99, 97, 95, 94, 93]),
            "kospi": series("kospi", [100.0] * 15 + [99, 98, 97, 96, 95]),
        }
        event = VerifiedMacroEvent(
            event_id="supply-1",
            event_type="supply_disruption",
            published_at="2026-01-18T08:00:00+00:00",
            confirmed_at="2026-01-18T09:00:00+00:00",
            active_from=date(2026, 1, 18),
            active_until=None,
            verification_status="official",
            source_url="https://example.test/official/supply-1",
        )
        result = evaluate_macro_transmission(inputs, date(2026, 1, 20), BASE_CONFIG, (event,))
        self.assertEqual("confirmed", result.energy_supply_shock.status)
        self.assertEqual("confirmed", result.duration_pressure.status)
        self.assertEqual("confirmed", result.korea_import_stress.status)
        self.assertIn("oil_rates_tech_triple_confirmation", result.duration_pressure.triggered_rule_ids)
```

- [ ] **Step 2: Run the focused tests and confirm the red state**

Run: `.venv\Scripts\python -m unittest tests.test_macro_transmission.MacroTransmissionTests.test_oil_only_stays_observe_and_cannot_confirm_duration_pressure tests.test_macro_transmission.MacroTransmissionTests.test_verified_supply_event_rates_and_relative_weakness_confirm_duration -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_assist.macro_transmission'`.

- [ ] **Step 3: Implement the immutable contracts and deterministic evaluator**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from stock_assist.risk_watch import DailySeries


StateValue = Literal["unavailable", "observe", "confirmed", "invalidated"]


@dataclass(frozen=True)
class SourceRef:
    key: str
    url: str
    as_of: str
    fetched_at: str | None = None


@dataclass(frozen=True)
class VerifiedMacroEvent:
    event_id: str
    event_type: Literal["supply_disruption", "sanction", "producer_policy", "ceasefire", "supply_normalization"]
    published_at: str
    confirmed_at: str
    active_from: date
    active_until: date | None
    verification_status: Literal["official", "conflicting", "unavailable"]
    source_url: str


@dataclass(frozen=True)
class ShadowState:
    status: StateValue
    triggered_rule_ids: tuple[str, ...]
    blocked_rule_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    gaps: tuple[str, ...]
    next_review_condition: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "triggered_rule_ids": list(self.triggered_rule_ids),
            "blocked_rule_ids": list(self.blocked_rule_ids),
            "evidence": list(self.evidence),
            "counter_evidence": list(self.counter_evidence),
            "gaps": list(self.gaps),
            "next_review_condition": self.next_review_condition,
        }


@dataclass(frozen=True)
class MacroTransmissionObservation:
    as_of: date
    energy_supply_shock: ShadowState
    duration_pressure: ShadowState
    korea_import_stress: ShadowState
    metrics: dict[str, float | None]
    sources: tuple[SourceRef, ...]
    calibration_status: str
    independent_event_count: int
    authority: str = "diagnostic_only"

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of.isoformat(),
            "energy_supply_shock": self.energy_supply_shock.to_dict(),
            "duration_pressure": self.duration_pressure.to_dict(),
            "korea_import_stress": self.korea_import_stress.to_dict(),
            "metrics": self.metrics,
            "sources": [source.__dict__ for source in self.sources],
            "calibration_status": self.calibration_status,
            "independent_event_count": self.independent_event_count,
            "authority": self.authority,
        }
```

Implement these private helpers in the same file:

```python
def _close_on_or_before(
    series: DailySeries,
    as_of: date,
    *,
    calendar_lag_days: int,
) -> list[float]:
    cutoff = as_of - timedelta(days=calendar_lag_days)
    return [point.close for point in series.points if point.day <= cutoff]


def _return(
    series: DailySeries | None,
    as_of: date,
    sessions: int,
    *,
    calendar_lag_days: int,
) -> float | None:
    if series is None:
        return None
    closes = _close_on_or_before(series, as_of, calendar_lag_days=calendar_lag_days)
    if len(closes) <= sessions or closes[-sessions - 1] <= 0:
        return None
    return closes[-1] / closes[-sessions - 1] - 1


def _yield_change(
    series: DailySeries | None,
    as_of: date,
    sessions: int,
    *,
    divisor: float,
    calendar_lag_days: int,
) -> float | None:
    if series is None or divisor <= 0:
        return None
    closes = _close_on_or_before(series, as_of, calendar_lag_days=calendar_lag_days)
    if len(closes) <= sessions:
        return None
    return closes[-1] / divisor - closes[-sessions - 1] / divisor


def _relative_return(
    left: DailySeries | None,
    right: DailySeries | None,
    as_of: date,
    sessions: int,
    *,
    left_lag_days: int,
    right_lag_days: int,
) -> float | None:
    left_return = _return(left, as_of, sessions, calendar_lag_days=left_lag_days)
    right_return = _return(right, as_of, sessions, calendar_lag_days=right_lag_days)
    if left_return is None or right_return is None:
        return None
    return left_return - right_return


def _active_official_events(
    events: tuple[VerifiedMacroEvent, ...],
    as_of: date,
    max_age_days: int,
) -> tuple[VerifiedMacroEvent, ...]:
    usable: list[VerifiedMacroEvent] = []
    end_of_day = datetime.fromisoformat(f"{as_of.isoformat()}T23:59:59+00:00")
    for event in events:
        confirmed_at = datetime.fromisoformat(event.confirmed_at)
        if event.verification_status != "official" or confirmed_at > end_of_day:
            continue
        if event.active_from > as_of or (event.active_until is not None and event.active_until < as_of):
            continue
        if (as_of - event.active_from).days > max_age_days:
            continue
        usable.append(event)
    return tuple(usable)
```

`evaluate_macro_transmission` must calculate:

```python
lag = config.get("market_calendar_lag_days")
if not isinstance(lag, dict):
    lag = {}
brent_5d = _return(series.get("brent"), as_of, 5, calendar_lag_days=int(lag.get("brent", 1)))
wti_5d = _return(series.get("wti"), as_of, 5, calendar_lag_days=int(lag.get("wti", 1)))
us10y_5d = _yield_change(
    series.get("us10y"),
    as_of,
    5,
    divisor=float(config.get("yield_divisor", 10.0)),
    calendar_lag_days=int(lag.get("us10y", 1)),
)
qqq_relative = _relative_return(
    series.get("qqq"),
    series.get("sp500"),
    as_of,
    5,
    left_lag_days=int(lag.get("qqq", 1)),
    right_lag_days=int(lag.get("sp500", 1)),
)
sox_relative = _relative_return(
    series.get("sox"),
    series.get("sp500"),
    as_of,
    5,
    left_lag_days=int(lag.get("sox", 1)),
    right_lag_days=int(lag.get("sp500", 1)),
)
kospi_relative = _relative_return(
    series.get("kospi"),
    series.get("sp500"),
    as_of,
    5,
    left_lag_days=int(lag.get("kospi", 0)),
    right_lag_days=int(lag.get("sp500", 1)),
)
```

Apply these exact permissions:

- oil threshold without an active official supply event -> energy `observe`;
- oil threshold with active official disruption/sanction/producer event -> energy `confirmed`;
- confirmed energy plus yield threshold plus both QQQ and SOX relative thresholds -> duration `confirmed`;
- confirmed energy plus KOSPI relative threshold -> Korea `confirmed`;
- active official ceasefire/normalization plus oil-unwind threshold and a previously confirmed energy state -> energy `invalidated`;
- missing required series -> affected state `unavailable`;
- conflicting events -> retain `observe`, add `conflicting_primary_evidence`, and block confirmation.

- [ ] **Step 4: Add no-lookahead, invalidation, missing-data, and conflict tests**

Add these exact methods:

```python
def test_future_bars_and_later_event_confirmation_are_ignored(self) -> None:
    # Build one input with a shock after as_of and one event confirmed the next day.
    # Assert the result equals a physically truncated input and energy is not confirmed.

def test_china_after_close_view_uses_prior_completed_us_session(self) -> None:
    # Put a US shock on the same calendar date as the China report and set US lag to one.
    # Assert it is absent; set the lag to zero and assert the metric changes.

def test_ceasefire_requires_oil_unwind_and_previous_confirmation_to_invalidate(self) -> None:
    # Pass a previous confirmed observation, an official ceasefire, and <= -5% oil return.
    # Assert energy is invalidated but duration is not automatically marked repaired.

def test_missing_sp500_keeps_duration_and_korea_unavailable(self) -> None:
    # Omit sp500 and assert explicit `missing_series:sp500` gaps.

def test_conflicting_primary_event_blocks_confirmation(self) -> None:
    # Supply both official disruption and conflicting event records.
    # Assert energy remains observe and records the conflict.
```

- [ ] **Step 5: Add configuration contracts**

Create both configuration files with this exact top-level shape:

```json
{
  "history_range": "10y",
  "yield_divisor": 10.0,
  "evaluation_timezone": "Asia/Shanghai",
  "evaluation_time": "15:30:00",
  "market_calendar_lag_days": {
    "brent": 1,
    "wti": 1,
    "us10y": 1,
    "sp500": 1,
    "qqq": 1,
    "sox": 1,
    "kospi": 0
  },
  "event_max_age_days": 20,
  "episode_gap_sessions": 20,
  "minimum_promotion_events": 60,
  "forward_horizons": [5, 20],
  "symbols": {
    "brent": "BZ=F",
    "wti": "CL=F",
    "us10y": "^TNX",
    "sp500": "^GSPC",
    "qqq": "QQQ",
    "sox": "^SOX",
    "kospi": "^KS11"
  },
  "thresholds": {
    "oil_5d_return": 0.08,
    "yield_5d_change_pct_points": 0.15,
    "qqq_sp500_5d_relative": -0.03,
    "sox_sp500_5d_relative": -0.04,
    "kospi_sp500_5d_relative": -0.04,
    "oil_unwind_5d_return": -0.05
  },
  "events": []
}
```

The example file uses the same shape. Comments are not allowed in JSON. The live file may contain only primary-source event metadata and URLs, never credentials.

- [ ] **Step 6: Normalize Yahoo history timestamps to the exchange timezone**

First add this failing test:

```python
from datetime import datetime, timezone
import unittest

from stock_assist.data_sources.global_markets import _history_bars


class GlobalMarketHistoryTests(unittest.TestCase):
    def test_history_date_uses_exchange_timezone_not_host_timezone(self) -> None:
        timestamp = int(datetime(2026, 7, 23, 0, 30, tzinfo=timezone.utc).timestamp())
        result = {
            "meta": {"exchangeTimezoneName": "America/New_York", "gmtoffset": -14400},
            "timestamp": [timestamp],
            "indicators": {"quote": [{"close": [100.0], "volume": [1000]}]},
        }
        bars = _history_bars(result)
        self.assertEqual(date(2026, 7, 22), bars[0].day)
```

Run: `.venv\Scripts\python -m unittest tests.test_global_markets.GlobalMarketHistoryTests.test_history_date_uses_exchange_timezone_not_host_timezone -v`

Expected: FAIL because `_history_bars` does not exist.

Refactor `fetch_yahoo_history` to call:

```python
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _history_bars(result: dict[str, object]) -> list[MarketDailyBar]:
    meta = result.get("meta")
    timezone_name = meta.get("exchangeTimezoneName") if isinstance(meta, dict) else None
    try:
        exchange_timezone = ZoneInfo(str(timezone_name))
    except ZoneInfoNotFoundError:
        offset_seconds = int(meta.get("gmtoffset") or 0) if isinstance(meta, dict) else 0
        exchange_timezone = timezone(timedelta(seconds=offset_seconds))
    timestamps = result.get("timestamp", [])
    indicators = result.get("indicators", {})
    quote_rows = indicators.get("quote", [{}]) if isinstance(indicators, dict) else [{}]
    quote = quote_rows[0] if isinstance(quote_rows, list) and quote_rows and isinstance(quote_rows[0], dict) else {}
    closes = quote.get("close", [])
    volumes = quote.get("volume", [])
    bars: list[MarketDailyBar] = []
    for index, timestamp in enumerate(timestamps if isinstance(timestamps, list) else []):
        close = _to_float(closes[index] if isinstance(closes, list) and index < len(closes) else None)
        if close is None or close <= 0:
            continue
        volume = _to_float(volumes[index] if isinstance(volumes, list) and index < len(volumes) else None)
        local_day = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).astimezone(exchange_timezone).date()
        bars.append(MarketDailyBar(day=local_day, close=close, volume=volume))
    return bars
```

Retain the existing fewer-than-20-bars guard in `fetch_yahoo_history`. Add tests for an unknown timezone falling back to UTC and non-positive closes being filtered.

- [ ] **Step 7: Run and commit the evaluator**

Run: `.venv\Scripts\python -m unittest tests.test_macro_transmission tests.test_global_markets -v`

Expected: all evaluator tests pass without network access.

```powershell
git add stock_assist/macro_transmission.py stock_assist/data_sources/global_markets.py tests/test_macro_transmission.py tests/test_global_markets.py configs/macro_transmission.json configs/macro_transmission.example.json
git commit -m "feat: add macro transmission shadow states"
```

---

### Task 2: Independent-Episode Replay and Calibration Gate

**Files:**
- Modify: `stock_assist/macro_transmission.py`
- Modify: `tests/test_macro_transmission.py`

**Interfaces:**
- Produces: `MacroCalibrationResult`
- Produces: `replay_macro_transmission(series: dict[str, DailySeries], start: date, end: date, config: dict[str, object], events: tuple[VerifiedMacroEvent, ...]) -> tuple[MacroTransmissionObservation, ...]`
- Produces: `calibrate_macro_transmission(observations: tuple[MacroTransmissionObservation, ...], series: dict[str, DailySeries], config: dict[str, object]) -> MacroCalibrationResult`

- [ ] **Step 1: Write failing clustering and promotion-gate tests**

```python
def fake_observation(day: date, *, duration: str = "confirmed") -> MacroTransmissionObservation:
    quiet = ShadowState(
        status="observe",
        triggered_rule_ids=(),
        blocked_rule_ids=(),
        evidence=(),
        counter_evidence=(),
        gaps=(),
        next_review_condition="next completed session",
    )
    duration_state = ShadowState(
        status=duration,
        triggered_rule_ids=("oil_rates_tech_triple_confirmation",) if duration == "confirmed" else (),
        blocked_rule_ids=(),
        evidence=(),
        counter_evidence=(),
        gaps=(),
        next_review_condition="next completed session",
    )
    return MacroTransmissionObservation(
        as_of=day,
        energy_supply_shock=quiet,
        duration_pressure=duration_state,
        korea_import_stress=quiet,
        metrics={},
        sources=(),
        calibration_status="insufficient_events",
        independent_event_count=0,
    )


def forward_series_for_dates() -> dict[str, DailySeries]:
    start = date(2015, 12, 1)
    closes = [100.0 + index * 0.01 for index in range(4200)]
    return {
        key: DailySeries(
            key=key,
            name=key,
            source=f"https://example.test/{key}",
            points=tuple(
                DailyPoint(start + timedelta(days=index), value)
                for index, value in enumerate(closes)
            ),
        )
        for key in ("brent", "wti", "us10y", "sp500", "qqq", "sox", "kospi")
    }


def long_forward_series() -> dict[str, DailySeries]:
    return forward_series_for_dates()


def test_consecutive_trigger_days_form_one_independent_episode(self) -> None:
    observations = tuple(
        fake_observation(date(2026, 1, day), duration="confirmed")
        for day in (10, 11, 12, 30)
    )
    result = calibrate_macro_transmission(
        observations,
        forward_series_for_dates(),
        {"episode_gap_sessions": 10, "minimum_promotion_events": 60, "forward_horizons": [5, 20]},
    )
    self.assertEqual(2, result.independent_event_count)
    self.assertEqual("insufficient_events", result.calibration_status)

def test_sixty_independent_events_still_require_out_of_sample_rows(self) -> None:
    observations = tuple(
        fake_observation(date(2016, 1, 1) + timedelta(days=index * 30), duration="confirmed")
        for index in range(60)
    )
    result = calibrate_macro_transmission(
        observations,
        long_forward_series(),
        {
            "episode_gap_sessions": 20,
            "minimum_promotion_events": 60,
            "forward_horizons": [5, 20],
            "out_of_sample_start": "2025-01-01"
        },
    )
    self.assertEqual("missing_out_of_sample_events", result.calibration_status)
```

- [ ] **Step 2: Run the calibration tests and confirm they fail**

Run: `.venv\Scripts\python -m unittest tests.test_macro_transmission.MacroTransmissionTests.test_consecutive_trigger_days_form_one_independent_episode tests.test_macro_transmission.MacroTransmissionTests.test_sixty_independent_events_still_require_out_of_sample_rows -v`

Expected: FAIL because `calibrate_macro_transmission` and `MacroCalibrationResult` do not exist.

- [ ] **Step 3: Implement replay, clustering, and declared outcome metrics**

```python
@dataclass(frozen=True)
class MacroCalibrationResult:
    calibration_status: str
    independent_event_count: int
    in_sample_event_count: int
    out_of_sample_event_count: int
    outcomes: tuple[dict[str, object], ...]
    threshold_sensitivity: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "calibration_status": self.calibration_status,
            "independent_event_count": self.independent_event_count,
            "in_sample_event_count": self.in_sample_event_count,
            "out_of_sample_event_count": self.out_of_sample_event_count,
            "outcomes": list(self.outcomes),
            "threshold_sensitivity": list(self.threshold_sensitivity),
        }
```

Implementation requirements:

- replay on the sorted union of completed dates at or before `end`;
- call `evaluate_macro_transmission` once per date with the prior observation;
- define an episode start only when `duration_pressure` changes into `confirmed`;
- suppress another start until `episode_gap_sessions` completed S&P sessions pass;
- calculate 5/20-session absolute returns for QQQ/SOX/KOSPI;
- calculate QQQ/SOX/KOSPI minus S&P returns at the same horizon;
- retain `sample_size`, `mean`, `median`, `hit_rate_below_zero`, `max_drawdown`, and a bootstrap-free normal-approximation 95% interval only when `sample_size >= 30`; otherwise set the interval to `None`;
- label rows with unavailable forward bars instead of dropping the entire episode silently;
- split in/out of sample using `out_of_sample_start`;
- return `insufficient_events` below 60, `missing_out_of_sample_events` with no held-out episodes, and `shadow_calibrated_not_promoted` otherwise;
- never return an authority above `diagnostic_only`.

- [ ] **Step 4: Add oil-only comparison and threshold-sensitivity tests**

```python
def test_calibration_reports_oil_only_and_triple_confirmation_separately(self) -> None:
    observations = tuple(
        fake_observation(date(2026, 1, day), duration="confirmed")
        for day in (10, 11, 12, 30)
    )
    result = calibrate_macro_transmission(
        observations,
        forward_series_for_dates(),
        {
            "episode_gap_sessions": 10,
            "minimum_promotion_events": 60,
            "forward_horizons": [5, 20],
            "threshold_sensitivity_multipliers": [0.8, 1.0, 1.2],
        },
    )
    rule_sets = {row["rule_set"] for row in result.outcomes}
    self.assertEqual({"oil_only", "oil_plus_rates", "triple_confirmation"}, rule_sets)

def test_threshold_sensitivity_uses_declared_grid_without_selecting_a_winner(self) -> None:
    observations = tuple(
        fake_observation(date(2026, 1, day), duration="confirmed")
        for day in (10, 11, 12, 30)
    )
    result = calibrate_macro_transmission(
        observations,
        forward_series_for_dates(),
        {
            "episode_gap_sessions": 10,
            "minimum_promotion_events": 60,
            "forward_horizons": [5, 20],
            "threshold_sensitivity_multipliers": [0.8, 1.0, 1.2],
        },
    )
    self.assertGreaterEqual(len(result.threshold_sensitivity), 3)
    self.assertNotIn("best_threshold", result.to_dict())
```

Use a deterministic fixture generator in the test file; do not add random values or network access.

- [ ] **Step 5: Run and commit replay calibration**

Run: `.venv\Scripts\python -m unittest tests.test_macro_transmission -v`

Expected: all state and calibration tests pass.

```powershell
git add stock_assist/macro_transmission.py tests/test_macro_transmission.py
git commit -m "feat: replay macro transmission episodes"
```

---

### Task 3: Risk-Watch Shadow Integration and Rendering

**Files:**
- Modify: `stock_assist/workflows/risk_watch.py`
- Create: `tests/test_macro_transmission_workflow.py`

**Interfaces:**
- Consumes: `evaluate_macro_transmission`, `replay_macro_transmission`, `calibrate_macro_transmission`
- Produces payload field: `macro_transmission`
- Produces Markdown heading: `## 能源—科技宏观传导（影子）`
- Produces HTML section ID: `macro-transmission-shadow`

- [ ] **Step 1: Write a failing workflow non-interference test**

```python
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch
import unittest

from stock_assist.macro_transmission import MacroTransmissionObservation, ShadowState
from stock_assist.risk_watch import DailyPoint, DailySeries, PortfolioRiskProfile
from stock_assist.workflows.risk_watch import build_risk_watch_bundle


def stable_risk_series() -> dict[str, DailySeries]:
    start = date(2026, 1, 1)
    points = tuple(
        DailyPoint(start + timedelta(days=index), 100.0 + index * 0.05)
        for index in range(201)
    )
    return {
        key: DailySeries(key, key, f"https://example.test/{key}", points)
        for key in ("all_a", "shanghai", "chinext", "star50", "csi1000", "sp500", "qqq", "sox", "kospi", "nikkei")
    }


def confirmed_shadow_dict() -> dict[str, object]:
    state = {
        "status": "confirmed",
        "triggered_rule_ids": ["oil_rates_tech_triple_confirmation"],
        "blocked_rule_ids": [],
        "evidence": ["verified fixture"],
        "counter_evidence": [],
        "gaps": [],
        "next_review_condition": "next completed session",
    }
    return {
        "as_of": "2026-07-20",
        "energy_supply_shock": state,
        "duration_pressure": state,
        "korea_import_stress": state,
        "metrics": {},
        "sources": [{"key": "brent", "url": "https://example.test/brent", "as_of": "2026-07-20"}],
        "calibration_status": "insufficient_events",
        "independent_event_count": 9,
        "authority": "diagnostic_only",
        "data_gaps": [],
    }


class MacroTransmissionWorkflowTests(unittest.TestCase):
    @patch("stock_assist.workflows.risk_watch._load_macro_shadow")
    @patch("stock_assist.workflows.risk_watch._fetch_series")
    @patch("stock_assist.workflows.risk_watch._load_profile")
    def test_shadow_is_rendered_without_mutating_risk_state(
        self,
        load_profile,
        fetch_series,
        load_macro_shadow,
    ) -> None:
        series = stable_risk_series()
        load_profile.return_value = (PortfolioRiskProfile(), [])
        fetch_series.return_value = (series, [])
        load_macro_shadow.return_value = confirmed_shadow_dict()
        payload, markdown, html = build_risk_watch_bundle(as_of="2026-07-20", replay_start="2026-07-01")
        self.assertEqual("diagnostic_only", payload["macro_transmission"]["authority"])
        self.assertEqual(payload["latest"]["level"], payload["replay"]["rows"][-1]["level"])
        self.assertIn("能源—科技宏观传导（影子）", markdown)
        self.assertIn('id="macro-transmission-shadow"', html)
        self.assertNotIn("macro_transmission", {signal["family"] for signal in payload["latest"]["signals"]})
```

- [ ] **Step 2: Run the workflow test and confirm it fails**

Run: `.venv\Scripts\python -m unittest tests.test_macro_transmission_workflow.MacroTransmissionWorkflowTests.test_shadow_is_rendered_without_mutating_risk_state -v`

Expected: FAIL because `_load_macro_shadow` and the payload section do not exist.

- [ ] **Step 3: Add bounded fetch and event parsing**

In `stock_assist/workflows/risk_watch.py`:

```python
from stock_assist.macro_transmission import (
    VerifiedMacroEvent,
    calibrate_macro_transmission,
    evaluate_macro_transmission,
    replay_macro_transmission,
)

DEFAULT_MACRO_CONFIG_PATH = CONFIG_DIR / "macro_transmission.json"


def _load_macro_shadow(as_of: date) -> dict[str, object]:
    config, gaps = _load_json(DEFAULT_MACRO_CONFIG_PATH, optional=True)
    if not config:
        return {
            "as_of": as_of.isoformat(),
            "authority": "diagnostic_only",
            "calibration_status": "unavailable",
            "data_gaps": gaps or ["macro_transmission config unavailable"],
        }
    symbols = config.get("symbols")
    if not isinstance(symbols, dict):
        return {
            "as_of": as_of.isoformat(),
            "authority": "diagnostic_only",
            "calibration_status": "unavailable",
            "data_gaps": ["macro_transmission symbols are malformed"],
        }
    series: dict[str, DailySeries] = {}
    fetch_gaps: list[str] = []
    for key, symbol in symbols.items():
        try:
            bars = fetch_yahoo_history(str(symbol), range_name=str(config.get("history_range") or "10y"))
            series[str(key)] = DailySeries(
                str(key),
                str(key),
                f"https://finance.yahoo.com/quote/{symbol}/history",
                tuple(DailyPoint(bar.day, bar.close) for bar in bars if bar.day <= as_of),
            )
        except Exception as exc:
            fetch_gaps.append(f"{key} unavailable: {exc}")
    events = _parse_macro_events(config.get("events"))
    replay = replay_macro_transmission(series, min(point.day for item in series.values() for point in item.points), as_of, config, events)
    latest = replay[-1] if replay else evaluate_macro_transmission(series, as_of, config, events)
    calibration = calibrate_macro_transmission(replay, series, config)
    result = latest.to_dict()
    result["calibration"] = calibration.to_dict()
    result["data_gaps"] = list(dict.fromkeys([*fetch_gaps, *latest.energy_supply_shock.gaps, *latest.duration_pressure.gaps, *latest.korea_import_stress.gaps]))
    return result
```

`_parse_macro_events` must reject malformed dates, non-HTTPS source URLs, and any verification status other than `official`, `conflicting`, or `unavailable`; rejected records become data gaps rather than exceptions that abort `risk-watch`.

- [ ] **Step 4: Attach the shadow without touching score inputs**

Call `_load_macro_shadow(latest.day)` only after `latest = replay[-1]`. Pass its return value to `create_report_payload` as `macro_transmission=macro_shadow`.

Do not pass macro series into `replay_risk` or `score_risk`. Do not append macro states to `latest.signals`, `alerts`, `event_alerts`, or `actions`.

- [ ] **Step 5: Render independent Markdown and HTML sections**

Add:

```python
def _macro_state_label(value: object) -> str:
    return {
        "unavailable": "不可用",
        "observe": "观察",
        "confirmed": "已确认",
        "invalidated": "已失效",
    }.get(str(value), "未知")
```

Markdown must show the three states, calibration label/event count, counter-evidence, gaps, next review condition, and the fixed line:

```text
- 权限：仅诊断；本状态不改变风险灯、仓位上限或交易计划。
```

HTML must use `<section id="macro-transmission-shadow">`, include no combined numeric gauge, and expose `authority`, `calibration_status`, source links, and data gaps as visible text.

- [ ] **Step 6: Add provider-failure and rendering assertions**

Add:

```python
def test_provider_failure_keeps_risk_report_available_with_explicit_gap(self) -> None:
    # Patch every macro fetch to raise TimeoutError.
    # Assert the normal risk payload still exists, macro authority remains diagnostic,
    # and Markdown/HTML display the unavailable source gap.

def test_shadow_never_changes_actions_alerts_or_budget(self) -> None:
    # Build once with an unavailable shadow and once with a confirmed shadow.
    # Assert latest level/budget_level, actions, alerts, and event_alerts are identical.
```

- [ ] **Step 7: Run and commit workflow integration**

Run: `.venv\Scripts\python -m unittest tests.test_macro_transmission_workflow tests.test_risk_watch -v`

Expected: all tests pass without live network access.

```powershell
git add stock_assist/workflows/risk_watch.py tests/test_macro_transmission_workflow.py
git commit -m "feat: show macro shadow in risk watch"
```

---

### Task 4: Product Contract, Architecture, Real Replay, and Evidence

**Files:**
- Modify: `configs/architecture.json`
- Regenerate: `docs/architecture.html`
- Modify: `docs/harness.md`
- Modify when activated: `feature_list.json`
- Modify when activated: `progress.md`
- Modify when activated: `session-handoff.md`
- Modify only if verified baseline or next feature changes: `CURRENT_STATE.md`

**Interfaces:**
- Consumes: `risk-watch --as-of YYYY-MM-DD --replay-start YYYY-MM-DD`
- Produces: fresh `reports/*-risk-watch.json`, `.md`, and `.html`

- [ ] **Step 1: Add the executable harness contract**

Add a `Macro transmission shadow` subsection to `docs/harness.md` with these assertions:

- the three state objects and `authority=diagnostic_only` exist;
- oil-only remains `observe`;
- duration confirmation requires oil, verified supply evidence, yields, QQQ relative weakness, and SOX relative weakness;
- Korea confirmation requires verified energy/import evidence plus relative weakness;
- independent event count and absolute/relative forward outcomes are visible;
- fewer than 60 independent events cannot promote the layer;
- macro state cannot change risk score, budget, actions, alerts, or strict readiness;
- JSON/Markdown/HTML retain source URLs, as-of, calibration, counter-evidence, and gaps.

- [ ] **Step 2: Refresh the architecture source**

Update only the existing `risk_watch` node:

```json
{
  "inputs": [
    "existing inputs",
    "Brent/WTI/US10Y/SP500/QQQ/SOX/KOSPI point-in-time history",
    "primary-source macro event evidence"
  ],
  "outputs": [
    "existing outputs",
    "diagnostic-only macro transmission shadow and replay calibration"
  ]
}
```

Do not add a new command or an edge into portfolio execution.

- [ ] **Step 3: Run focused and full verification**

Run:

```powershell
.\.venv\Scripts\python -m unittest tests.test_macro_transmission tests.test_macro_transmission_workflow tests.test_risk_watch -v
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m compileall stock_assist
.\.venv\Scripts\python scripts\validate_project_memory.py
.\.venv\Scripts\python -m stock_assist.cli architecture-view
.\.venv\Scripts\python scripts\validate_project_memory.py
```

Expected: every command exits `0`; architecture validation passes after regeneration.

- [ ] **Step 4: Generate and inspect a real artifact**

Run:

```powershell
.\.venv\Scripts\python -m stock_assist.cli risk-watch --as-of 2026-07-23 --replay-start 2016-01-01
```

Inspect the newest triplet and assert:

```powershell
$json = Get-ChildItem reports\*-risk-watch.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$payload = Get-Content -LiteralPath $json.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
if ($payload.macro_transmission.authority -ne 'diagnostic_only') { throw 'macro authority changed' }
if (-not $payload.macro_transmission.calibration.independent_event_count) { throw 'missing event count' }
if (-not (Test-Path ($json.FullName -replace '\.json$','.md'))) { throw 'missing Markdown peer' }
if (-not (Test-Path ($json.FullName -replace '\.json$','.html'))) { throw 'missing HTML peer' }
```

Record the actual latest market dates, source gaps, event count, calibration status, and whether the 2026 episode is confirmed. Do not manufacture the design-stage return figures if the live series differ.

- [ ] **Step 5: Record implementation evidence and commit**

Only after explicit feature activation, update `feature_list.json`, `progress.md`, and `session-handoff.md` with exact test counts, artifact paths, event count, residual gaps, and the fact that authority remains diagnostic. Change `CURRENT_STATE.md` only if the verified baseline or next feature changes.

```powershell
git add configs/architecture.json docs/architecture.html docs/harness.md feature_list.json progress.md session-handoff.md
git diff --cached --check
git commit -m "docs: verify macro transmission shadow"
```

Do not stage unrelated pre-existing working-tree changes.
