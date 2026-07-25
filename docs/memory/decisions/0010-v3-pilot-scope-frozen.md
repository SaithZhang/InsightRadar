# ADR-0010: Freeze InsightRadar V3.0 Pilot for Ten Real Morning Trials

- Status: accepted
- Date: 2026-07-25

## Context

The owner accepted the final P0 repair after the real four-route after-close runtime demonstrated consistent pending counts, fail-closed blocked responses, truthful version/state rendering, 250/250 full tests, 3/3 targeted tests, and zero browser runtime or console errors.

Continuing to refine the interface before real use would prevent the product from testing its actual job: helping the user remember, revalidate, and confirm morning plans.

## Decision

Mark the current product:

**InsightRadar V3.0 Pilot — Scope Frozen**

- Freeze the Today, Portfolio, Lookup, and Review information architecture.
- Freeze the `Observe -> Explain -> Decide -> Verify` loop and the rule/user/AI/trade responsibility boundary.
- Do not start P1 research orchestration, the backtest history center, or P2 five-minute monitoring.
- Run ten consecutive real morning decision trials.
- During the trial, admit only data errors, plan mismatches, response/state persistence failures, security issues, or core-flow blockers.
- Record ordinary experience suggestions without implementing them.
- Hold one consolidated review after trial ten before deciding whether to authorize V3.1.

## Consequences

- `feat-058` remains the sole active experiment for value validation, but its P0 implementation and visual scope are accepted.
- A proposal that changes pages, navigation, authority, or deferred phases is out of scope during the trial.
- Every admitted repair requires reproducible evidence and regression coverage.
- Trial records, defects, and ordinary observations are kept distinct.
- No automatic trading or forced blocked override is introduced.
