# InsightRadar Agent Notes

The canonical checkout and all active project context use `InsightRadar`. The internal Python package remains `stock_assist`, and legacy CLI aliases remain compatible.

## Versioned Product Baseline

- Read `docs/PRODUCT_BASELINE.md`, `docs/V3.0_FROZEN.md`, `docs/V3.1_DELTA.md`, and `docs/DATA_BOUNDARIES.md` before any product, navigation, data-contract, or publishing change.
- V3.0 is the historical frozen baseline. V3.1 is the active, owner-authorized incremental development line from 2026-08-01; do not describe a planned V3.1 delta as implemented behavior.
- Advance one admitted V3.1 increment at a time. Do not start V3.2 or a parallel product redesign until V3.1 has an explicit acceptance decision.
- Preserve the four first-level tasks and route ids: `今日工作台` (`today`), `组合风险` (`portfolio`), `标的研究` (`lookup`), and `复盘账本` (`review`). Do not add a fifth first-level menu.
- Keep portfolio risk at the product center; security research is an evidence/explanation layer.
- Distinguish fact, inference, rumor, sentiment, and unknown. Show counter-evidence, provenance, as-of time, freshness, and gaps.
- Never disguise synthetic or prototype data as runtime capability.
- Never add automatic trade execution. Every position action remains human-confirmed.
- The formal product cannot depend on named-person copy trading or influencer identity.

## Startup Workflow

Before writing code:

1. Confirm the working directory is `D:\work\InsightRadar`.
2. Read this file completely.
3. Read the versioned product documents named above when the task touches product behavior, navigation, data, or release boundaries.
4. Read `PROJECT_MEMORY.md` and `CURRENT_STATE.md` for non-trivial work, then load only the matching topic under `docs/memory/`.
5. Query only the exact feature entry and matching recent `progress.md` / `session-handoff.md` section; load the relevant contract from `docs/harness.md`. Do not read append-only history in full unless the task is historical.
6. Review recent commits with `git log --oneline -10`.
7. Run relevant verification before claiming done; use `init.sh` where available, or the Windows commands below.

## Data Freshness

- For just-released A-share performance forecasts and critical filings, use this source priority:
  1. CNInfo latest announcement direct lookup.
  2. Jin10 or other 7x24 fast-news feeds.
  3. AmazingData structured financial data such as `get_profit_notice`.
  4. Manual override only when the official announcement is verified but structured sources lag.
- AmazingData can lag fresh after-close filings. Treat it as structured confirmation, not the first source for same-evening announcements.
- CNInfo announcements can be dated the next calendar day even when released after market close the prior evening. Query through tomorrow when running evening checks.

## SkillHub On Windows

- In PowerShell, the `skillhub` command is a bash wrapper and can behave unreliably.
- Prefer direct CLI invocation:
  `python "$env:USERPROFILE\.skillhub\skills_store_cli.py" install <slug> --dir "$env:USERPROFILE\.codex\skills"`
- If installation ends with a Unicode/GBK print error, check `%USERPROFILE%\.codex\skills` before retrying; the skill may already be installed.

## AmazingData

- Do not parallelize AmazingData login/query commands on the same account.
- Filter non-positive daily K-line close values before computing latest close or moving averages.

## Harness Operating Loop

- For non-trivial changes, follow `docs/harness.md`.
- Use `CURRENT_STATE.md` to find the next feature, then query its exact `feature_list.json` entry and matching history before planning multi-file work.
- One feature at a time: pick one unfinished feature from `feature_list.json`; stay in scope unless the user changes priority.
- Respect the active product rings and expansion-freeze plan in `docs/extractions/README.md`; Lab and Extension work stays parked while `CURRENT_STATE.md` points to a Core reliability feature.
- Preserve generated Markdown reports when adding richer report formats such as HTML.
- Do not mark report or data-source work done until the relevant CLI command has actually run and produced a fresh artifact.

## Project Memory

- `PROJECT_MEMORY.md` is the bounded always-on index; keep detailed context in routed `docs/memory/*.md` topics.
- `CURRENT_STATE.md` is the bounded always-on snapshot; keep chronological evidence in `progress.md` and `session-handoff.md`, loaded by feature id or recent tail only.
- For durable memory writes, update the topic first and the index pointer second.
- Link to sources of truth rather than copying volatile status into memory topics.
- Record durable architectural and product-scope decisions as ADRs under `docs/memory/decisions/` and link them from `docs/memory/decision-log.md`.
- Use two-phase extraction for separately deployed components: verify the standalone copy and external ownership before deleting the original rollback path.
- Architecture/module changes must refresh `configs/architecture.json`, regenerate `docs/architecture.html`, and pass `scripts/validate_project_memory.py`.

## Public Repository Safety

- Public Git history starts from the sanitized V3 baseline. Never push the local legacy/private history.
- Track source, tests, product documents, reproducible configs, schemas, examples, and synthetic review assets only.
- Keep `.env`, credentials, cookies, tokens, real holdings/accounts/trades, account screenshots, local databases, reports, caches, logs, and raw authenticated data local.
- Stage explicit paths only. Do not use `git add -A` in a mixed worktree.
- After the user explicitly authorizes a GitHub write operation, use the authenticated `gh` CLI directly for push, pull-request creation, and merge; do not try the GitHub App connector first. The connector remains appropriate for read-only lookup and triage.
- If a secret is suspected in any candidate public commit, stop publication and report the path and remediation without echoing the value.

## Definition of Done

A feature is done only when:

- Target behavior is implemented without stubs or hidden TODOs.
- Required verification actually ran.
- Evidence is recorded in `feature_list.json` or `progress.md`.
- The repo is restartable from the documented startup path.

## End of Session

- Update `progress.md` with current state, blockers, files changed, and recommended next step.
- Update `feature_list.json` status and evidence without deleting feature descriptions.
- Update `session-handoff.md` for larger or interrupted work.
- Refresh `CURRENT_STATE.md` when the verified baseline, product direction, gaps, or next feature changed.
- Leave enough verification evidence that the next session can restart cleanly.

## Verification Commands

Use the narrowest relevant check:

```powershell
.venv\Scripts\python -m compileall stock_assist
.venv\Scripts\python scripts\validate_project_memory.py
.venv\Scripts\python -m stock_assist.cli after-close
.venv\Scripts\python -m stock_assist.cli evolve
.venv\Scripts\python -m stock_assist.data_sources.xysz doctor --code 000001.SZ
```
