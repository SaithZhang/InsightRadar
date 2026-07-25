# Jin10 Event Intelligence Design

> This English document is the canonical, normative specification and AI guidance source. The [Chinese human-review copy](2026-07-20-jin10-event-intelligence-design.zh-CN.md) is non-normative; if the two differ, this English document controls.

- Status: approved
- Date: 2026-07-20
- Feature: `feat-055`
- Decision owner: user
- Product lead: primary Codex agent
- Implementation status: not started

## Decision Summary

InsightRadar will integrate Jin10 through an independent event-intelligence layer rather than coupling provider responses directly into `after-close` or alert rendering.

The accepted flow is:

`Jin10 discovery -> normalized event -> classification and deduplication -> primary-source verification -> portfolio/market relevance -> impact assessment -> report or key alert`

Jin10 is a fast discovery source. It cannot independently authorize a trade, change the risk budget, or turn a cumulative amount into an assumed next-session inflow.

`feat-055` is queued behind the existing `feat-044` priority. It does not replace `feat-044`, activate implementation, or resume the separately deferred agent-governance plan.

## Problem

Material A-share events arrive through fragmented fast-news, official announcements, policy releases, and market responses. A raw feed creates three failure modes:

1. important events can be missed when the user does not search the right entity;
2. keyword searches can produce false positives, such as sports or industrial uses of “国家队”;
3. a true fact can still be misinterpreted, such as treating an already-used cumulative support amount as new money arriving tomorrow.

The product needs fast discovery without becoming a news terminal or a headline-driven trading oracle.

## Scope

### In scope

- Standard MCP access to Jin10 fast news, articles, and the economic calendar.
- Machine parsing from `result.structuredContent`; `result.content` is supplementary human-readable text only.
- Cursor pagination using request `cursor`, response `data.next_cursor`, and `data.has_more`.
- Event normalization, deterministic deduplication, entity/action/asset classification, and magnitude semantics.
- Recognition of Jin10 daily/weekend/pre-open/midday/after-close digest items as reconciliation checkpoints rather than duplicate standalone events.
- Primary-source verification state for material policy, filing, company, and state-capital claims.
- Portfolio-first relevance mapping with market, index, style, sector, and candidate fallback when holdings are absent.
- Promotion into the unified report and key-alert queue only after relevance and evidence gates pass.
- Explicit errors, stale data, source conflicts, missing confirmation, and provider quota state.

### Out of scope

- Automatic order placement or standalone trade authority.
- Using Jin10 sentiment or headline count as a calibrated market score.
- Replacing CNInfo, exchanges, ministries, central banks, or company investor-relations pages as primary sources.
- Rebuilding quote and K-line coverage already owned by market-data workflows. Jin10 quote/K-line tools remain available for later source reconciliation, not the first event-intelligence increment.
- A multi-provider event bus, cloud deployment, or a new service split.
- Real-time push infrastructure before alert precision and missed-event behavior are measured.
- Reverse-engineering APP-only red styling or inferring provider importance when the MCP response does not expose a structured importance field.

## Runtime Boundary

The user-scoped Codex MCP installation proves source feasibility and supports manual development analysis. It is not the standalone InsightRadar runtime.

The future product adapter must implement the standard MCP lifecycle itself:

1. `initialize` with protocol version `2025-11-25`;
2. `notifications/initialized`;
3. `tools/list` and `resources/list` for capability verification;
4. bounded `tools/call` requests;
5. session reuse, timeout handling, and clean reconnect.

The Bearer token is read from the repository-external `JIN10_MCP_TOKEN` environment variable. No token, Authorization header value, or raw credential may enter Git, normal reports, logs, audit payloads, fixtures, or exception messages.

## Logical Components

| Component | Responsibility | Boundary |
|---|---|---|
| Jin10 MCP adapter | Session lifecycle, tool calls, cursor pagination, structured result parsing, bounded retries | Provider-specific; no investment interpretation |
| Event normalizer | Stable IDs, timestamps, source provenance, text cleanup, duplicate and summary linkage | Deterministic and replayable |
| Event classifier | Entity, action, asset, event type, amount and time-semantics classification | Rules first; uncertain fields remain unknown |
| Verification gate | Find and compare primary sources; record confirmed, pending, conflicting, or unavailable | Fast news alone cannot become confirmed evidence |
| Relevance mapper | Map to approved holdings first, then market/index/style/sector/candidates | No forced relevance and no forced candidate quota |
| Impact assessor | Positive, negative and counter-transmission paths; horizon; plan/risk relevance | Conditional interpretation, not an order |
| Delivery adapter | Background evidence, unified report item, or key alert | Uses existing report/alert contracts |

The design remains inside the modular monolith. Provider-specific code must sit behind a typed source interface so the normalizer and decision layers do not depend on Jin10 response shapes.

## Normalized Event Contract

Each event records at least:

- stable event ID and provider item identity;
- source name, source URL, publication time, fetch time, and timezone;
- original title/body plus a normalized factual summary;
- entities, actions, affected assets, market/sector/style tags, and event type;
- numeric magnitude, unit, and magnitude semantics when available;
- verification status, primary-source links, conflicts, and unresolved gaps;
- deduplication group and relationship to later summaries or updates;
- container type (`atomic_event` or `digest`), digest window/type, and child-event relationships;
- provider importance/red-highlight state with field provenance, or explicit `unknown` when the provider does not expose it;
- portfolio/market relevance, likely horizon, impact paths, counter-evidence, and confidence state;
- promotion state and next review point.

Magnitude semantics use explicit values such as:

- `incremental_executed`;
- `recent_cumulative`;
- `historical_cumulative`;
- `future_commitment`;
- `target_or_capacity`;
- `unknown`.

Amounts with different semantics are never summed into a single “new inflow” figure.

## Classification and Deduplication

Material-event detection uses compound evidence rather than one keyword. A state-support candidate, for example, requires a relevant institution or policy actor, a capital-market action, and an affected market object.

The classifier must distinguish:

- state-capital support from sports or industrial “national team” usage;
- executed purchases from financing capacity or future intent;
- a new event from a later news summary;
- policy tools from actual deployment;
- direct stock/ETF activity from general confidence statements.

Search and list results may contain the same item. Stable provider identity is preferred; otherwise a deterministic fingerprint over normalized time, entities, action, amount, and source URL is used. A summary links to underlying events without generating duplicate alerts.

## Digest Checkpoints and Provider Importance

Jin10 publishes multiple compilation items, especially around weekends, the next trading-day open, midday, after close, and evening. Examples include [“周日重要消息汇总”](https://flash.jin10.com/detail/20260719225915777800). These are useful high-density reconciliation checkpoints.

A digest is a container, not one new market event. The ingestion layer:

1. detects digest title/body patterns and records its publication window without assuming a permanently fixed schedule;
2. splits numbered or clearly separated items into child discovery candidates while preserving the original digest URL;
3. reconciles each child against already-seen atomic events;
4. links existing events to the digest and creates only genuinely missing candidates;
5. uses digest coverage to measure missed-event behavior, not to inflate event or alert counts.

The 2026-07-20 live MCP check found that `search_flash("重要消息汇总")` returned 52 items. Across those structured items the only item keys were `content`, `time`, `title`, and `url`; the target Sunday digest itself exposed `content`, `time`, and `url`. No `importance`, `is_red`, `hot_level`, tag, or presentation-style field was available.

Therefore `provider_importance` and `provider_red_highlight` remain `unknown` under the current contract. The product must not infer APP red styling from wording, HTML appearance, emojis, or list position. If Jin10 later adds a structured field, the adapter may ingest it with provider-field provenance and validate it against real samples, but provider highlighting still cannot independently authorize action.

## Verification and Promotion State Machine

The event lifecycle is:

`discovered -> normalized -> classified -> verification_pending -> confirmed | conflicting | confirmation_unavailable -> mapped -> background | report | key_alert -> reviewed`

Promotion requires:

1. materiality to an approved holding, market/risk state, adopted thesis, or active candidate;
2. a clear new-versus-cumulative classification;
3. primary-source confirmation for critical claims, or an explicit unconfirmed label when confirmation is temporarily unavailable;
4. a credible positive and negative transmission path;
5. a statement of whether the existing plan or risk budget changes, remains unchanged, or cannot yet be assessed;
6. deduplication and freshness checks.

Missing confirmation does not erase a material clue, but it prevents the clue from becoming decision authority.

## Delivery Contract

A promoted event answers, in concise Chinese:

- what happened and what is genuinely new;
- why it matters to the user’s holdings or current market plan;
- likely positive, negative, and uncertain transmission paths;
- intraday, tactical, or thesis-level horizon;
- confirmation, invalidation, and next evidence to watch;
- whether it changes a plan, only changes monitoring priority, or changes nothing;
- source links, freshness, verification state, and explicit gaps.

Alerts remain sparse. Background items are archived but do not interrupt the user. An event cannot override a red risk veto or missing decision-ready portfolio data.

## Failure Handling

- Missing token: fail with an explicit source-unavailable gap and no credential leakage.
- MCP `isError=true`: treat as a provider business error.
- JSON-RPC `error`: treat as a protocol error and retain code plus a sanitized message.
- Missing or malformed `structuredContent`: fail parsing; do not machine-parse `content` as a substitute.
- Rate limit: stop calls to that tool until the next Beijing calendar day and retain the last successful as-of with a stale label.
- Timeout/session loss: use bounded retry and one clean reinitialize; never loop indefinitely.
- Pagination inconsistency: stop the page walk, preserve collected items, and expose incomplete coverage.
- Primary-source conflict: retain both claims and block confirmation-dependent promotion.

## Acceptance Criteria

The implementation is accepted only when all of the following are evidenced:

1. A product-owned MCP client completes the required lifecycle without depending on Codex configuration.
2. The token remains external and secret-redaction tests cover config, logs, reports, fixtures, and exceptions.
3. `structuredContent` is the exclusive machine source and list pagination follows the declared cursor contract.
4. Repeated list/search/summary copies produce one event and no duplicate alert.
5. The phrase “国家队” in sports or unrelated industrial context does not classify as market support.
6. The 2026-07-19 China Reform Holdings item is classified as already-used cumulative support, not next-session incremental inflow.
7. The 2026-07-19 China Chengtong item is classified as recent cumulative executed buying plus future intent, without manufacturing transaction detail.
8. Critical events retain primary-source confirmation state and cannot gain trade authority from Jin10 alone.
9. Approved holdings receive first relevance; an empty portfolio can map to market/style/sector without forcing a candidate.
10. Provider failures, rate limits, stale data, incomplete pagination, and source conflicts are visible and bounded.
11. The same normalized event can render consistently in JSON and any enabled Markdown/HTML/alert surface.
12. A Sunday/daily digest reconciles child items with atomic events, recovers missing discoveries, and does not create duplicate events or alerts.
13. When the MCP contract lacks structured importance/red fields, the normalized values remain unknown and an explicit data gap is emitted; no visual or textual guess is made.
14. Focused tests, full regression, real artifact verification, project-memory validation, harness validation, and secret scans pass.

## Alternatives Considered

### Directly embed Jin10 in `after-close`

Rejected. It is fast initially but couples provider transport, event interpretation, and presentation, making deduplication, verification, reuse, and testing fragile.

### Independent event-intelligence layer

Accepted. It keeps provider access replaceable, creates one evidence contract for reports and alerts, and enforces verification before decision impact.

### General multi-provider event bus now

Deferred. It offers broad extensibility but adds infrastructure before one provider’s precision, latency, failure behavior, and product value are measured.

## Rollout and Kill/Merge Criteria

The smallest useful implementation begins with Jin10 fast news, article detail, calendar inputs, digest detection/reconciliation, deterministic normalization, state-support/policy/filing/geopolitical categories, confirmation state, and report-only shadow output.

Key alerts activate only after shadow evidence shows acceptable duplicate rate, false-positive rate, missed-material-event behavior, latency, and source reliability. If the layer cannot improve material-event recall or reduce manual verification work without increasing low-value alerts, it is merged into background research ingestion or parked.

This design authorizes a later implementation plan. It does not start `feat-055` implementation or change `CURRENT_STATE.md` `next_feature_id` from `feat-044`.

Implementation source: [2026-07-20-jin10-event-intelligence.md](../plans/2026-07-20-jin10-event-intelligence.md).
