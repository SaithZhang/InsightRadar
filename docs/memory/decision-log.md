# Decision Log

This file is the bounded decision index. Full context, alternatives, and consequences live in ADRs under `docs/memory/decisions/`.

## ADR Index

- [ADR-0001: Bounded Repository Memory](decisions/0001-bounded-repository-memory.md)
- [ADR-0002: Modular Monolith with Product Rings](decisions/0002-modular-monolith-product-rings.md)
- [ADR-0003: Extract the Discipline Reminder and Freeze Expansion](decisions/0003-extract-discipline-reminder-and-freeze-expansion.md)
- [ADR-0004: Canonical InsightRadar Workspace](decisions/0004-canonical-insightradar-workspace.md)
- [ADR-0005: Treat Iwencai as a Cross-Platform Market Data Candidate](decisions/0005-iwencai-cross-platform-market-data-candidate.md)
- [ADR-0006: Validate Core Investment Value Locally Before Cloud Delivery](decisions/0006-local-first-core-value-validation.md)
- [ADR-0007: Keep Viewpoint Discipline Contracts Evidence-Bound](decisions/0007-evidence-bound-discipline-contracts.md)
- [ADR-0008: Enable a Guarded Iwencai Futures-Basis Adapter in Local Core](decisions/0008-guarded-iwencai-futures-basis.md)
- [ADR-0009: Make Personal Investment Decision Intelligence the Product North Star](decisions/0009-personal-investment-decision-intelligence.md)
- [ADR-0010: Freeze InsightRadar V3.0 Pilot for Ten Real Morning Trials](decisions/0010-v3-pilot-scope-frozen.md)
- [ADR-0011: Publish a Sanitized V3 Baseline Without Legacy Private History](decisions/0011-public-v3-baseline.md)
- [ADR-0012: Pivot the Core to Point-in-Time Intraday Risk and Opportunity](decisions/0012-intraday-risk-opportunity-pivot.md)
- [ADR-0013: Derive Portfolio Beta from Deterministic Market Evidence](decisions/0013-deterministic-portfolio-beta.md)
- [ADR-0014: Separate Current Risk Context from Historical Entry Context](decisions/0014-separate-current-and-historical-position-context.md)
- [ADR-0015: Conclude the V3.0 Scope Freeze and Open Sequential V3.1 Iteration](decisions/0015-open-sequential-v3-1-iteration.md)
- [ADR-0016: Separate Holding-Management Consent from Data Quality](decisions/0016-separate-management-consent-from-data-quality.md)

## 2026-07-14 - Repository memory, not chat history

- Decision: use a bounded root index plus on-demand topic files for long-term project memory.
- Reason: chat history and model-side memory are helpful but are not portable, reviewable, or guaranteed across machines. Version-controlled project facts are.
- Consequence: `PROJECT_MEMORY.md` is always read for non-trivial work; detailed topics are loaded only when triggered.
- Superseded detail: ADR-0001 adds `CURRENT_STATE.md` as the bounded startup snapshot and makes chronological logs on-demand only.

## 2026-07-14 - Modular monolith, explicit product rings

- Decision: keep one repository, but classify capabilities as Core, Lab, Satellite, Extension, or Governance.
- Reason: avoid premature service/repository cost without letting optional experiments blur the A-share product promise.
- Consequence: module extraction requires the criteria in ADR-0002 and `docs/product-charter.md`.

## 2026-07-14 - Reminder extraction and expansion freeze

- Decision: package the Windows reminder as a standalone personal app, retain rollback until external cutover passes, and pause Lab/Extension expansion.
- Reason: the reminder has an independent lifecycle while the A-share core needs reliability and calibration work more than new surfaces.
- Consequence: `feat-037` replaces factor neutralization as the immediate next sprint; see ADR-0003 and `docs/extractions/README.md`.

## 2026-07-14 - Reminder ownership transfer completed

- Decision: the standalone repository at `D:\work\reminder` now exclusively owns the Windows reminder and scheduled task.
- Evidence: D-drive Release publish, task/process path verification, visible acknowledge/snooze controls, SAPI test, normal restart, and 138 merged historical/current log records passed.
- Consequence: the C-drive intermediate repository and all reminder source/config/scripts/docs/export artifacts were removed from `stock-assist`; rollback now belongs to the standalone project.

## 2026-07-14 - Architecture is a maintained product asset

- Decision: keep `configs/architecture.json` as the visual graph source and regenerate `docs/architecture.html`; validate command coverage against `stock_assist/product.py`.
- Reason: the topology existed but became stale because no lifecycle gate connected new commands to the graph.
- Consequence: adding or removing a product command requires architecture-memory validation; generated HTML carries the config SHA-256 so freshness survives cross-machine Git checkout.

## 2026-07-14 - Canonical InsightRadar workspace

- Decision: `D:\work\InsightRadar` is the sole canonical main-project workspace and all active Codex/automation context uses the InsightRadar name.
- Reason: the C-drive working tree was newer than the abandoned D-drive `stock-assist` copy, while duplicate names and locations made ownership unclear.
- Consequence: the complete C-drive working tree was migrated with its uncommitted changes; the old D-drive copy was archived rather than merged, and `stock_assist` remains only an internal package/compatibility identifier.

## 2026-07-14 - Iwencai is a portability candidate, not a Core dependency yet

- Decision: install and evaluate Iwencai as a cross-platform market-data candidate while keeping it outside production Core during the expansion freeze.
- Reason: Galaxy/AmazingData is not a universal ARM macOS/Linux runtime, while the Iwencai skill uses portable Python HTTPS calls; one successful smoke is not enough to establish production reliability.
- Consequence: complete `feat-037` first, then require cross-platform, reconciliation, freshness/quota, failure-isolation, secret, and supply-chain gates before any Core integration; see ADR-0005.

## 2026-07-14 - Local Core value before cloud delivery

- Decision: keep InsightRadar local-first and defer production Docker, cloud deployment, and platform migration until the Core reliability and outcome-value gates pass.
- Reason: the product must first prove that its guidance improves benchmark-relative decision outcomes with sufficient samples, controlled backtests, acceptable drawdown, and regime stability; win rate alone is insufficient.
- Consequence: finish the workspace prerequisite and `feat-037`, then prioritize outcome maturation, replay/backtest integrity, attribution, and calibration. Revisit delivery infrastructure only through an explicit evidence review; see ADR-0006.

## 2026-07-16 - Viewpoint discipline contracts remain evidence-bound

- Decision: retain reusable author/user discipline frameworks with provenance, but keep their thresholds separate from product defaults and current market facts.
- Reason: the technology-mainline framework is useful for structuring decisions, while its static MA20 judgments had already drifted and the source page was not independently retrievable during review.
- Consequence: NGA reports may show a strategy-contract and falsification check, but Core actions still require user-specific risk settings plus independently verified market, filing, financial, and outcome evidence; see ADR-0007.

## 2026-07-19 - Guarded Iwencai futures-basis close adapter enters local Core

- Decision: use the project-owned Iwencai HTTPS boundary as the first source for date-aligned completed-close IF/IH/IC/IM basis, volume, and open interest; keep serial AmazingData as the live-session fallback.
- Reason: the real 16:20/weekend Core run should not lose all derivatives context merely because the realtime Windows SDK is session-gated, while static close data must not be mislabeled as four-minute confirmation.
- Consequence: dynamic active-contract discovery, same-date joins, stale rejection, secret isolation, diagnostic-only close semantics, and explicit gaps are mandatory; cross-platform/cloud readiness remains unproven. See ADR-0008.

## 2026-07-19 - Personal investment decision intelligence is the North Star

- Decision: keep approved holdings as the primary relevance anchor, add a zero-to-five candidate fallback when holdings are absent, and treat Alpha Report variants as delivery rather than mission.
- Reason: information aggregation, guidance, key alerts, and outcome calibration form one durable user loop; time-of-day labels and agent-generated feature volume do not.
- Consequence: Core admission now requires evidence-backed user pain, a measurable outcome, explicit safety/data boundaries, and a kill criterion. Multi-agent roles are temporary and operate under one lead. See ADR-0009.

## 2026-07-25 - InsightRadar V3.0 Pilot scope frozen

- Decision: accept P0, freeze the four-page architecture and responsibility boundary, and run ten consecutive real morning trials.
- Reason: the implementation now passes state-consistency, blocked-response, version-truth, full regression, and browser runtime gates; the next uncertainty is real-use value rather than more design.
- Consequence: only data, plan-mapping, persistence, security, or core-flow defects are admitted during the trial. P1/P2 and ordinary experience improvements wait for the consolidated post-trial review. See ADR-0010.

## 2026-07-25 - Sanitized public V3 baseline

- Decision: publish a fresh sanitized V3 baseline and keep the local legacy history private.
- Reason: public source and synthetic review assets are suitable for open source, while legacy commit metadata and chronological logs include personal paths and portfolio-linked context.
- Consequence: no force-push or destructive history rewrite; public traceability begins with the sanitized baseline, verification record, and Draft PR. See ADR-0011.

## 2026-08-01 - Point-in-time intraday risk and opportunity becomes Core

- Decision: shift the primary decision moments to 09:25, 09:35, and 10:00 while preserving the four-route shell and human trade authority.
- Reason: IR-001 tests whether account profit protection, catalyst-failure detection, re-entry discipline, and cross-theme opportunity recognition improve the actual morning decision loop.
- Consequence: immutable minute archives and typed point-time rules become the Core seam; after-close planning and audit remain secondary. See ADR-0012.

## 2026-08-01 - Portfolio beta becomes deterministic evidence

- Decision: replace manual beta classification in the import UI with a deterministic calculation against `000300.SH` using 120 simple daily returns, at least 60 observations, and a 1.20 high-beta threshold.
- Reason: beta is a reproducible market statistic and should not be guessed from a ticker or manually re-entered when current daily history is available.
- Consequence: beta value, R², window, observations, as-of, source, and quality are stored locally; any stale, insufficient, failed, or invalid input remains `unknown` and blocks reconciliation. See ADR-0013.

## 2026-08-01 - Current risk context is separate from historical entry context

- Decision: require the current risk rule and usable review state for present decision readiness, while treating an unknown original thesis or entry-time invalidation as a visible Review limitation rather than a current-plan blocker.
- Reason: entry history that was never recorded must remain unknown, but its absence should not prevent a user from reviewing a current evidence-backed risk rule.
- Consequence: JSON preserves `context_complete` as a compatibility alias and adds explicit current/historical context states plus missing fields; AI cannot backfill history or grant authority. See ADR-0014.

## 2026-08-01 - V3.0 scope freeze concluded; V3.1 iteration opened

- Decision: retain V3.0 as the immutable historical baseline and authorize V3.1 as the active incremental development line.
- Reason: the owner explicitly ended the frozen-baseline phase and chose version-by-version iteration; bounded product work had already moved beyond the original defect-only pilot gate.
- Consequence: `IR-002` remains the single active increment, the incomplete ten-run trial is not reported as passed, and V3.2 or a parallel redesign remains unauthorized. Four routes, truthful data states, privacy, human confirmation, and no automatic trading remain guardrails. See ADR-0015.

## 2026-08-02 - Holding-management consent is separate from data quality

- Decision: generate deterministic holding-management proposals when context is missing or stale, and track user consent independently from account/market data quality.
- Reason: user uncertainty is a personalization state, not missing market evidence; the old read-only context path incorrectly blocked the whole report and offered no UI repair flow.
- Consequence: confirmation never clears a quarantine, per-capability data faults remain fail closed, compatible private context is written atomically through the loopback UI, and only after-close is regenerated. See ADR-0016.

## Existing durable decisions

- User-facing product, canonical checkout, Codex project, and automation context use InsightRadar; `stock_assist` and legacy CLI aliases remain compatible implementation identifiers.
- Report conclusions are conditional and evidence-based, never unconditional trading orders.
- Same-evening critical A-share filings prioritize CNInfo; structured sources are confirmation when they lag.
- The factor pipeline promotes only candidates that pass hard gates; no threshold is loosened merely to force a champion.
