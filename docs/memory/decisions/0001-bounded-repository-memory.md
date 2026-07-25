# ADR-0001: Bounded Repository Memory

- Status: accepted
- Date: 2026-07-14

## Context

Chat history, model memory, and large append-only progress files are not reliable startup context across windows, machines, or long product timelines. Reading all history at startup also consumes context and buries early invariants.

## Decision

Use a three-layer repository memory model:

1. `PROJECT_MEMORY.md` is a bounded routing index.
2. `CURRENT_STATE.md` is a bounded, always-read snapshot of product direction, verified baseline, gaps, and next feature.
3. Topic files, ADRs, `progress.md`, and `session-handoff.md` are loaded on demand.

Durable facts are written to their topic or ADR first. The index stores only routing metadata. Chronological logs remain evidence, not startup memory. Executable validation enforces caps, references, next-feature state, generated freshness, and architecture command coverage.

## Alternatives Rejected

- Chat/model memory as source of truth: not portable or reviewable.
- A second vector database or graph-memory framework: duplicates repository truth and adds synchronization risk.
- Reading all progress and handoff history on every startup: scales poorly and dilutes relevant context.

## Consequences

- New sessions recover with a small fixed context budget.
- Updating `CURRENT_STATE.md` becomes part of material handoff work.
- Historical details require targeted search by feature id, date, or topic.
- The memory validator must fail if the snapshot drifts outside its contract.
