# ADR-0015: Conclude the V3.0 Scope Freeze and Open Sequential V3.1 Iteration

- Status: accepted
- Date: 2026-08-01

## Context

ADR-0010 accepted the V3.0 P0 runtime and limited changes to defects while ten consecutive real morning trials were planned. Before that gate completed, the owner explicitly reprioritized point-in-time intraday Core work, authorized bounded Today and data-contract repairs, and then chose to end the frozen-baseline phase so InsightRadar can advance version by version.

The transition must not pretend the ten-run pilot completed, rewrite the V3.0 evidence, or turn authorization to develop into a claim that V3.1 is already released. It must also preserve the safety and truth boundaries that are independent of the temporary scope freeze.

## Decision

- End the active V3.0 defect-only scope freeze on 2026-08-01.
- Keep **InsightRadar V3.0 Pilot — Scope Frozen** as an immutable historical implementation, comparison, and rollback baseline.
- Open **InsightRadar V3.1 — Incremental Development** as the active owner-authorized product line.
- Advance one admitted product increment at a time. `IR-002` remains the current active experiment; another increment may start only after it passes, is killed, or is explicitly parked by the owner.
- Do not open V3.2 or a parallel replacement architecture until V3.1 has an explicit acceptance decision.
- Preserve exactly four first-level tasks during V3.1: `today`, `portfolio`, `lookup`, and `review`.
- Preserve truthful real/synthetic/unknown labeling, provenance and freshness, local/private data boundaries, rule-first authority, explicit human confirmation, and no automatic trading.
- Keep candidate and partial V3.1 items labelled as such. Authorization to develop does not promote them to implemented or accepted.

## Consequences

- ADR-0010 remains accepted historical evidence, but its active freeze and ten-run authorization gate are superseded.
- The ten planned morning trials are recorded as incomplete, not passed or silently discarded.
- Product work may now include admitted improvements rather than defect-only repairs, while `configs/product_governance.json`, `CURRENT_STATE.md`, and `feature_list.json` continue to limit active work and preserve evidence.
- V3.0 documentation remains historical. New runtime behavior belongs in the V3.1 delta register, feature evidence, progress log, and later release acceptance.
- ADR-0011 and `docs/DATA_BOUNDARIES.md` remain fully effective for public-repository safety.
