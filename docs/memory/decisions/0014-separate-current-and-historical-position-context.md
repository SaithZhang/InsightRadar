# ADR-0014: Separate Current Risk Context from Historical Entry Context

- Status: accepted
- Date: 2026-08-01

## Context

Strict decision readiness previously required one combined position-context predicate: natural-language entry thesis, original invalidation, current risk line, and review status all had to be complete. This correctly exposed unknown history, but it also blocked a present risk plan when the only missing fact was an entry-time condition that had never been recorded and must not be reconstructed with hindsight.

## Decision

- Define current decision context as the current risk rule plus a usable review state. Missing, placeholder, `needs_context`, or snapshot-conflicting `stale_context` state remains a hard blocker.
- Define historical entry context as the original entry thesis plus original entry invalidation.
- Keep missing historical entry context explicit as `unknown`; route it to Review as a strategy/execution-quality limitation instead of a current-plan blocker.
- Retain the existing natural-language fields and existing private data. Do not delete, infer, or backfill unknown history.
- Preserve `context_complete` in the JSON contract as a compatibility alias for `current_context_complete`; add explicit current/historical completeness and missing-field lists.
- AI may later extract a structured thesis draft or explain evidence changes, but cannot manufacture entry history, change rule output, or grant trade authority.

## Consequences

- A holding with a usable current risk rule may become decision-ready even when its original entry invalidation is unknown, provided all other snapshot, market, action, and reconciliation gates pass.
- Review must disclose that strategy-discipline and execution-quality conclusions are limited for holdings with incomplete historical context.
- Existing consumers of `context_complete` continue to work while newer consumers can distinguish current blocking gaps from historical audit gaps.
