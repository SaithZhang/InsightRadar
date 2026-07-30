# Risk Card Decision Service P0 Implementation Plan

**Status:** Approved by product owner on 2026-07-30

**Goal:** Make the portfolio-risk workbench usable as a local decision-support service by replacing cost-anchored pseudo-technical triggers, exposing actionable evidence instead of source-status prose, and moving data refresh out of the import request into a persistent asynchronous job.

**Architecture:** Preserve the frozen four-task product shell and the canonical JSON/Markdown/HTML audit artifacts. Add three deep, bounded interfaces: a pure holding-decision builder, a decision-evidence contract consumed by the workbench, and a loopback refresh coordinator backed by SQLite. Provider access remains in existing Core workflows; the presentation layer never fetches providers or grants trade authority.

## Frozen boundaries

- Preserve exactly `今日计划`, `组合风险`, `标的研究`, and `复盘账本` as first-level tasks.
- Keep portfolio risk at the product center; security research remains an evidence and explanation layer.
- No cloud dependency, continuous monitoring, automatic order placement, or automatic holdings overwrite.
- Keep fact, inference, rumor, sentiment, and unknown distinct. Stale and blocked inputs cannot authorize new exposure.
- Keep JSON/Markdown/HTML audit files. SQLite stores local service state; it does not replace reproducible report artifacts.
- Never commit real holdings, account screenshots, authenticated raw data, or local databases.

## Confirmed P0 defects

1. A large unrealized loss can return early from holding-plan generation and use the broker cost as the upside trigger. Cost is an account reference, not a technical level.
2. The workspace maps the same sentence into incompatible `IF` and `THEN` semantics, so the displayed plan can contradict itself.
3. Holding context can remain labelled as profit protection after a newer broker snapshot shows a loss.
4. The evidence panel associates a holding reason with a source-health row by list position, creating false attribution.
5. The evidence drawer exposes freshness metadata but not the facts, counter-evidence, gaps, or plan impact needed for a decision.
6. Portfolio import saves and runs the full refresh chain synchronously. The browser receives no durable job state and can appear permanently stuck.
7. The required refresh chain omits `ai-capex-watch`, leaving industry evidence stale even after a successful import.

## Target interfaces

### 1. Holding decision

Provide one pure interface that consumes a holding plus completed OHLCV context and returns:

- technical snapshot: close, MA20, MA60, slopes, support, resistance, ATR14, volume ratio, and available relative-strength context;
- `cost_reference` with `authority=reference_only`;
- three mutually understandable branches: `repair_observe`, `risk_reduce_review`, and `continue_waiting`;
- for each branch: measurable trigger, persistence window, human-confirmed action, invalidation, review time, source time, and adjustment basis;
- a reachability label that prevents a multi-session threshold from being described as a next-session condition.

Invariants:

- Identical OHLCV with different costs produces the same technical state and technical levels.
- No technical trigger is synthesized from `cost`, `last * 0.97`, or another arbitrary account-relative multiplier.
- Missing technical evidence remains `unknown`; it is never filled with zero.
- A newer broker snapshot invalidates conflicting stale narrative context.

### 2. Decision evidence

Provide one normalized evidence contract containing:

- top conclusion: overall stance, technology stance, dividend stance, confidence, top reasons, counter-evidence, and invalidation;
- evidence item: stable id, scope, fact class, claim, change, source reference, source time, freshness, supported/opposed conclusion, plan impact, counter-evidence, gaps, and authority;
- holding plans linked to evidence by stable ids rather than list position.

Presentation rules:

- Render an actionable conclusion card before detailed evidence.
- Keep the evidence-chain drawer separate from the data-health drawer.
- A user should be able to answer within 30 seconds: what is the market stance, which style is stronger, what each holding should wait for, what changes the plan, and which evidence is stale or blocked.

### 3. Local refresh service

Provide a loopback-only refresh coordinator with:

- `POST /api/refresh` returning HTTP 202 and a durable `run_id` within one second;
- `GET /api/refresh/{run_id}` returning run and step state;
- one active serial Core refresh, duplicate-click idempotency, and recovery of interrupted state after a page reload or service restart;
- default refresh of stale/failed sources and an explicit full-refresh option;
- portfolio save committed before refresh starts, so refresh failure cannot roll back or obscure the approved holdings update;
- `ai-capex-watch` included before the final `after-close` run, or surfaced as an explicit failed step.

SQLite tables used by the local service:

- `refresh_runs` and `refresh_steps` for durable task state;
- `source_snapshots` for last-good source metadata;
- `evidence_items` and `plan_versions` for versioned decision state;
- `user_responses` for explicit human confirmation.

Existing JSONL and report artifacts remain compatible during migration.

## Implementation sequence

### Task A — Decision semantics

- Add focused regression tests for cost invariance, arbitrary multiplier removal, three-branch completeness, missing evidence, and stale-context invalidation.
- Introduce the pure decision module and adapt the after-close workflow to it.
- Correct workspace `IF / THEN / 无动作 / 失效` mapping.

### Task B — Evidence contract and workbench

- Add evidence normalization tests and stable evidence ids.
- Populate market, style, industry, and holding evidence from existing report payloads only.
- Replace positional attribution with id-based links.
- Add the conclusion card and separate evidence/data-health drawers without changing first-level navigation.

### Task C — Asynchronous refresh and SQLite

- Add the refresh coordinator, schema migration, serial worker, single-flight guard, and idempotency key.
- Change import apply to save first and enqueue refresh second.
- Add refresh start/status endpoints and page-reload recovery.
- Add a visible refresh control and per-step progress/failure UI.
- Include `ai-capex-watch` in the canonical refresh chain.

### Task D — Verification and closeout

- Run focused decision, workspace, renderer, import, server, and refresh-coordinator tests.
- Run the full unit suite, compileall, memory validation, architecture regeneration, and `git diff --check`.
- Generate and inspect a fresh local artifact without committing private reports or the SQLite database.
- Record verified evidence in `feature_list.json`, `progress.md`, `session-handoff.md`, and `CURRENT_STATE.md` where the baseline changes.

## Acceptance gates

- Cost-invariance and no-arbitrary-level tests pass.
- Every displayed conclusion and holding branch has correctly linked supporting or opposing evidence, source time, freshness, and invalidation.
- Evidence chain contains decision facts; data health contains only availability/freshness/repair metadata.
- Refresh start returns promptly, survives page reload, deduplicates repeated clicks, and reports the exact failed workflow while preserving the last-good artifact as stale.
- A completed full refresh includes `ai-capex-watch` and a final `after-close`.
- No hidden failure, synthetic runtime claim, fifth route, cloud dependency, or trade execution is introduced.

## Rollback

- The new decision builder remains behind the after-close adapter, so the prior renderer contract can be restored without changing provider workflows.
- SQLite is additive local state. Removing the database restores a clean state without deleting JSON/Markdown/HTML artifacts.
- Import save and refresh are separate transactions; a refresh rollback cannot undo an approved portfolio snapshot.
