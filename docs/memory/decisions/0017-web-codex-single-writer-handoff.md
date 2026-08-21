# ADR-0017: Use Single-Writer Handoffs Between Web and Codex

- Status: accepted
- Date: 2026-08-21

## Context

InsightRadar now has two complementary operating lanes. ChatGPT Web and the human owner manage research synthesis and investment-decision state in Notion, while Codex manages the repository, local data execution, deterministic tooling, replay, and engineering evidence. Both lanes can read selected Notion context, but shared access does not authorize both lanes to rewrite the same state.

Without an explicit ownership and handoff contract, the lanes can silently overwrite newer state, mix evidence with permission, copy private runtime data into the wrong store, or treat two different MCP systems as one capability. The repository therefore needs a bounded recovery entry that points to the current Notion control plane without copying it wholesale.

## Decision

### Lanes and shared zone

- **Web Lane** is owned by ChatGPT Web plus the human. It owns external research synthesis, scenarios, Daily Journal, Thesis, Trading Rule, Portfolio/Risk Permission, final Decision state, and human Eval judgments.
- **Codex Lane** is owned by Codex. It owns repository engineering, data collection and normalization, Data Quality, Runtime state, tools and MCP implementation, batch computation, replay, tests, and Technical/Wave Evidence.
- **Shared Zone** contains only the small structured objects another lane must consume. It is a handoff boundary, not a shared dump of chat history, raw market data, or intermediate reasoning.

### Single Writer and proposals

- Every authoritative object has one default owner and writer. Access to Notion does not grant write authority over another owner's state.
- A non-owner that believes an owner field should change must append a **Patch Proposal** or **State Proposal** with the target object, proposed delta, evidence, `as_of`, `origin`, and target `owner`. It must not overwrite the owner field.
- Shared objects always carry `as_of`, `origin`, `owner`, and an explicit status. Missing or uncertain values remain `unknown`; stale, degraded, blocked, superseded, and conflicting states remain distinct.
- Conflicts are never silently averaged or rewritten into a compromise. Preserve the Web view, Codex evidence, a `CONFLICT` record, and the owner or independent Eval resolution.

### Authority

- **Portfolio Truth** belongs to the broker and user. Account quantities, costs, executions, and cash change only from broker evidence or explicit user confirmation.
- **Trading Permission, Thesis, Trading Rule, and final Decision state** belong to Web plus the human owner.
- **Data Quality, Runtime state, Technical/Wave Evidence, replay, and test evidence** belong to Codex.
- `a-stock-data` and `wavecycle` are Codex execution/evidence capabilities. Their output may propose evidence or state deltas but never owns Trading Permission.
- All Codex technical, wave, market-data, replay, and MCP output has `trade_authority=none`. InsightRadar never executes a trade automatically.

### Storage boundaries

- **Local Data Plane** stores raw K-lines, minute data, funds flow, private portfolio/account files, SQLite/DuckDB/Parquet, caches, replay inputs, raw evidence, and intermediate computations. Credentials, cookies, tokens, and authenticated session state stay local and are never copied into Notion or GitHub.
- **Notion** is the human-readable control plane for shared state, handoffs, Thesis, Rules, Decision Episodes, Eval, and concise evidence summaries. It does not become the raw market database or a second machine-runtime store.
- **GitHub** stores public-safe code, schemas, deterministic configuration, skills/prompts, tests, sanitized Eval fixtures, ADRs, and engineering documentation. It never stores real holdings, executions, private runtime reports, authenticated data, or daily trading state.

### Distinct MCP identities

- The Web-facing **Intraday Market Desk MCP** is a separately operated system whose Web reachability is governed by its own tunnel and runtime evidence.
- Repository feature `feat-059` is InsightRadar's local four-tool read-only MCP over stdio or loopback Streamable HTTP. Its localhost server is not evidence that ChatGPT Web can reach it.
- Neither system inherits readiness, tool coverage, provenance, or authority from the other.

### Named sources

- A named Anchor Source may exist as private Web Evidence and may affect human research priority.
- Named-person copying or influencer identity cannot become a formal InsightRadar product dependency, deterministic permission source, or automatic trade authority.

## Consequences

- New Codex sessions can recover the executable contract from `docs/memory/web-codex-collaboration.md` and then fetch only the Notion pages required for the active task.
- Web and Codex can exchange evidence without creating two writers for Portfolio Truth, Thesis, Rule, Permission, Runtime, or Data Quality.
- Raw data stays in its authoritative plane; Notion receives concise handoffs and GitHub receives only public-safe engineering assets.
- This decision changes governance and recovery only. It does not modify product behavior, Runtime, `IR-002`, `feat-058`, `feat-059`, route structure, or trade authority.
