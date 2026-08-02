# ADR-0016: Separate Holding-Management Consent from Data Quality

- Status: accepted
- Date: 2026-08-02

## Context

The after-close workflow treated a missing or conflicting `portfolio_context.json` row as a core data gap. That made an unconfirmed personal management preference indistinguishable from an untrustworthy account snapshot, symbol mapping, adjustment basis, or price series. The local UI could read the private context but could not create or update it, so ordinary users were told to repair a field for which no product entry point existed.

The owner selected a bounded V3.1 repair: the system must generate the first proposal from existing structured evidence, while the user only adopts, adjusts, or leaves it uncertain. This must not weaken fail-closed data behavior or add model/trade authority.

## Decision

- Represent holding management on two independent axes:
  - `context_status`: `system_proposed`, `user_confirmed`, `user_modified`, or `stale`.
  - `data_status`: `ready` or `data_blocked` for the capabilities that depend on the affected data.
- Generate `system_proposed` plans with deterministic rules only. The first version uses trusted broker/account fields, portfolio exposure and risk budget, and a technical contract only when its provider result passed validation.
- Missing or stale user context does not block base portfolio analysis. It keeps personalized tracking pending and visible.
- Invalid, missing, stale, or quarantined account/market data remains fail closed. A holding-level price fault pauses moving-average, support/resistance, and price-threshold judgments without erasing trusted cost, weight, or portfolio-exposure analysis.
- User confirmation never changes `data_status` and cannot clear a quarantine.
- Preserve `current_risk_line` and `review_status` as compatibility fields in the existing private context file. Add source, confirmation time, report binding, plan version, and structured management-rule fields to that same record instead of creating a second fact store.
- The loopback UI provides adopt, fixed single-choice adjustment, and uncertain actions. It validates and atomically writes private context, then runs only `after-close`. It never creates an order or makes free text mandatory.

## Consequences

- `after-close.data_gaps` now represents actual core data faults; per-holding technical quarantine is exposed separately as a capability issue.
- A holding can simultaneously be user-confirmed and data-blocked. This is expected and prevents consent from masquerading as evidence.
- Legacy usable context remains readable as confirmed historical local context, with an unknown confirmation timestamp when none exists. Conflicting legacy context becomes stale and receives a replacement system proposal.
- AI is not used for the proposal or for missing-history reconstruction. Later AI explanations, if admitted, cannot change these deterministic states.
- The four-route shell, private-data boundary, human trade authority, and no-automatic-execution rule remain unchanged.
