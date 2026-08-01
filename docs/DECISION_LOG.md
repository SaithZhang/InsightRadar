# InsightRadar Decision Log

This is the concise public-facing decision record. Detailed historical ADRs remain under `docs/memory/decisions/`.

## 2026-08-01 — End the V3.0 scope freeze and open V3.1

- **Decision:** Preserve V3.0 as the historical implemented baseline and authorize V3.1 as the active incremental development line.
- **Basis:** The owner explicitly chose to resume version-by-version iteration; bounded product changes had already required individual authorization while the ten-run pilot remained incomplete.
- **Consequence:** Defect-only admission ends. Work still advances one admitted increment at a time, beginning with the already active `IR-002`; V3.2 and parallel redesign are not authorized.
- **Unchanged guardrails:** Exactly four first-level tasks, truthful real/synthetic/unknown states, local/private data boundaries, rule-first authority, human confirmation, and no automatic trading.
- **Evidence:** ADR-0015, `PRODUCT_VERSION.md`, and `docs/V3.1_DELTA.md`.

## 2026-07-25 — Freeze V3.0 as the product baseline

- **Decision:** Keep the implemented four-task V3 runtime and run ten real morning trials before authorizing V3.1.
- **Basis:** The code has a working local decision workspace, version-scoped responses, explicit source health, and a human-only authority boundary. The remaining uncertainty is real-use value, not another redesign.
- **Consequence:** Only data, mapping, persistence, security, and core-flow defects may change during the pilot.
- **Evidence:** ADR-0010, `stock_assist/after_close_workbench_html.py`, and `stock_assist/decision_workspace.py`.
- **Later status:** The freeze ended on 2026-08-01 before the planned ten-run trial completed; the baseline remains historical evidence.

## 2026-07-25 — Define InsightRadar as an independent AI risk officer

- **Decision:** Portfolio risk is the product center; security research explains evidence and cannot independently authorize an action.
- **Basis:** The durable user value is identifying the few facts that could justify a position change, with visible uncertainty and counter-evidence.
- **Consequence:** Facts, inferences, rumors, sentiment, and unknowns require distinct treatment. No automated trading, named-person copy trading, or disguised simulated capability is allowed.
- **Evidence:** `docs/PRODUCT_BASELINE.md`.

## 2026-07-25 — Treat V3.1 only as an incremental delta

- **Decision:** Do not create a replacement prototype or a fifth first-level route.
- **Basis:** V3 already expresses the Observe–Explain–Decide–Verify loop through four tasks.
- **Consequence:** Candidate changes remain `implemented`, `partial`, `not_implemented`, or `to_confirm` in `docs/V3.1_DELTA.md` until the pilot gate passes.

## 2026-07-25 — Publish only a sanitized public baseline

- **Decision:** The GitHub target may be Public, but only source, product documents, tests, schemas, examples, and synthetic review assets may be published.
- **Basis:** Local data includes credentials, account/portfolio state, response ledgers, reports, logs, caches, and browser artifacts. The legacy local Git history also contains a non-noreply author email and historical portfolio-linked examples.
- **Consequence:** Do not push legacy history to the public repository. Establish a fresh sanitized public baseline while retaining the full original history locally. Never rewrite or delete the local private archive as part of publication.
- **Evidence:** `docs/DATA_BOUNDARIES.md` and the 2026-07-25 repository audit.
