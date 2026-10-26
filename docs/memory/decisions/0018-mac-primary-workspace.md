# ADR-0018: Mac as the primary development workspace

Date: 2026-10-22

Status: Accepted by explicit owner direction; operational verification is recorded under feat-058.

## Decision

The owner moved primary InsightRadar development and local use to macOS. This supersedes the Windows-only canonical path and the macOS deferral in ADR-0004/0006 for this bounded adaptation. Windows remains a compatible historical runtime; its private data is not copied or replaced automatically.

Preserve the Python modular monolith, existing loopback HTTP service, four routes, report triplet, approval-gated imports, and rule/user/trade boundaries. `InsightRadar.command` delegates to `scripts/macos.sh`; the launcher installs only into the project virtual environment, opens the application, reuses the same checkout's service, and refuses unrelated port occupants. It installs no daemon or scheduled job.

The base dependency set runs on Mac without AmazingData/tgw. Dedicated SDK, MCP and collector dependencies are explicit extras. Making an SDK optional does not provide its data: unavailable sources keep existing failure and provenance semantics. The startup page shows genuine setup state, with no synthetic holdings, returns, or executable plans.

Existing process credentials, `.env`, and repository-external key storage retain their precedence. The migration does not overwrite keys, select a new AI provider, or move credentials between services.

## Acceptance and limits

Acceptance requires a project-local install, real foreground start/restart, safe duplicate/conflicting-port handling, four working routes, preview without implicit approval, preserved stale-workspace rejection, browser layout checks, and a real fresh after-close triplet. Full account/data acceptance additionally requires an owner-approved portfolio and working data sources; an empty-portfolio run is not that evidence.

This remains a bounded feat-058 usability increment. IR-002 calibration, live notification admission, new clients, automatic trading, cloud deployment and additional product increments stay parked. Stop after the Mac acceptance checks pass.
