# Web-Codex Collaboration

## Executable Handoff Contract

1. Identify the target object and its owner before reading or writing shared state.
2. Load only the active task's required Notion page, current object version, applicable Rule/Thesis, and source references. Exclude superseded and unrelated history.
3. The owner may append a new authoritative version. A non-owner emits a Patch Proposal or State Proposal and leaves the owner version unchanged.
4. Preserve `as_of`, `origin`, `owner`, status, data quality, supporting and contradicting evidence, invalidation, and next check.
5. Keep raw data and intermediate computation in the Local Data Plane. Share only the bounded evidence/state delta another lane must consume.
6. Codex evidence, including `a-stock-data` and `wavecycle`, always has `trade_authority=none`. Only Web plus the human owner may promote evidence into Trading Permission; only the human executes outside InsightRadar.

## Shared Object Minimum Schema

```yaml
object_id: stable identifier
as_of: source or decision time with timezone
origin: WEB | HUMAN | BROKER | CODEX | TOOL
owner: authoritative lane or human owner
status: ACTIVE | SUPERSEDED | DEGRADED | BLOCKED | CONFLICT | PROPOSED
data_quality: explicit quality state and gaps
previous_state: prior authoritative state or unknown
new_evidence: bounded evidence references and summary
state_delta: what changed and what did not change
confidence: explicit value or unknown
supports: supported state or claim
contradicts: counter-evidence or none observed
invalidation: condition that invalidates the proposal/state
next_check: time or evidence checkpoint
proposed_permission_delta: proposal only, or not_applicable
source_refs: stable local artifact ids or source links
trade_authority: none
```

A Patch Proposal additionally carries `proposal_id`, `target_object_id`, `target_owner`, `requested_changes`, and `proposal_status: pending_owner_review | accepted | rejected | superseded`.

## Ownership Table

| Object | Owner / writer | Non-owner rule | Authoritative storage |
|---|---|---|---|
| Portfolio Truth and confirmed executions | Broker / User | Propose reconciliation; never infer or overwrite | Broker evidence and private Local Data Plane |
| Trading Permission, Thesis, Trading Rule, final Decision | Web + Human | Codex submits State/Patch Proposal only | Web-owned Notion control plane |
| Data Quality, Runtime Run, Tool output, replay/test state | Codex | Web reports an issue or requests a run; it does not rewrite results | Local artifacts/DB; concise Notion handoff |
| Technical and Wave Evidence | Codex | Web may accept, challenge, or route it; it cannot rewrite raw computation | Local raw data and computation; concise Notion handoff |
| Shared Evidence/State Handoff | Originating owner appends its record | Consumer references the record or proposes a delta | Notion Shared Zone |
| Public engineering code, schema, config, tests, ADR | Codex + repository maintainer | Changes use explicit review and public-safety gates | GitHub |

## Conflict Protocol

1. Stop owner-state mutation when Web and Codex disagree.
2. Preserve `web_view`, `codex_evidence`, both source versions, and the conflict `as_of`.
3. Append `status: CONFLICT`; do not average confidence or silently merge conclusions.
4. Route resolution to the authoritative owner. High-impact Thesis, Risk, Permission, or Position conflicts require independent evidence, deterministic guard, or frozen external Eval.
5. Append the resolution with resolver, evidence, and resulting version. Supersede prior objects without deleting history.

## Authoritative Notion Entrypoints

- [人工 InsightRadar v0.4｜实盘运行台](https://app.notion.com/p/3b544bc3d1cd8144a097eb5fa6cbcdf7)
- [99｜Operating Manual｜人工实盘工作流与自动化边界](https://app.notion.com/p/3bc44bc3d1cd81eaa727deaba0d69859)
- [System Learning Loop v0.1｜无微调的长期改进闭环](https://app.notion.com/p/3bd44bc3d1cd8103b203f9bea0389e3b)
- [InsightRadar 架构与可靠性路线图](https://app.notion.com/p/3b044bc3d1cd811d8b26d982338287af)
- [09｜Shared Handoff｜Web ↔ Codex](https://app.notion.com/p/3c344bc3d1cd813687a8eafb9f363cbf)

Fetch the latest required page by exact title or URL. Do not load or copy the entire Notion control plane by default.
