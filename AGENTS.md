# InsightRadar V0.02

This is the canonical local InsightRadar application. Development continues from the V0.02 baseline. Read the frozen PRD, TECH and CHECKPOINT.md before changes. The PRD is the product contract. One backend, one PostgreSQL database, one Vue page. No account data, automation, trading, stock screening or multi-agent product features.

Implement only TECH-R1; preserve immutable reports and append-only plan evaluations. Never substitute mock data on runtime failure. Only confirmed prior-day final bars; exactly D+1 exchange session. Java owns numerical calculations. Python only transports provider data. Bind all services to 127.0.0.1. Keep credentials, data, PDFs, logs and generated output out of Git.

Use one coding agent. Run the narrow relevant tests and update docs/IMPLEMENTATION_PROGRESS.md and CHECKPOINT.md at milestones. The owner authorized publishing the V0.02 baseline to codex/v002-baseline on the original public SaithZhang/InsightRadar remote. Publish source and synthetic fixtures only. Preserve main and the local archive. PRs and merges require their own authorization. The old Python checkout is archived at ../insightradar-archive-20261109.

Owner update 2026-11-09: use native local dependencies unless Docker is necessary. PostgreSQL 17 is installed locally; scripts/postgres.sh manages only data/postgres-native on loopback port 15432. Integration tests use a disposable native cluster, never the application DB. This overrides Docker/Testcontainers deployment choices in the preserved handoff attachments; product rules are unchanged.

Owner update 2026-11-09: OpenAI API use is approved for this application's disclosure reports, with USD 100 per month and no daily limit. Production reuses validated model results for identical requests. Debug requests a fresh model response under the same monthly budget. Keep the credential in the existing local configuration and reference it at startup.

Owner update 2026-11-09: the holdings increment is approved and implemented. Follow docs/PRD-我的持仓.md and docs/TECH-持仓管理.md for the three views and local manual positions. A submitted analysis freezes its position context in the immutable report. Keep it out of provider requests and generated artifacts committed to Git.

Owner update 2026-11-09: reports distinguish pre-open, in-session, post-close and non-trading days in Asia/Shanghai. This supersedes the prior-day-only finality rule in the frozen attachments. The app first requests the same-day BaoStock close and adjustment data at 18:00 and requires a verified daily bar. Never reuse an earlier phase's quote as a current post-close result. Preserve historical reports and fixed D+1.

Owner update 2026-11-09: Tencent's confirmed after-close unadjusted price can be shown separately while BaoStock final daily bars and adjustment data are pending. A Tencent quote alone cannot update technical indicators, holding actions, or D+1. Keep stored reports immutable.
