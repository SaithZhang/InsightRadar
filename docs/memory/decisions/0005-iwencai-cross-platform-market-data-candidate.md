# ADR-0005: Treat Iwencai as a Cross-Platform Market Data Candidate

- Status: accepted
- Date: 2026-07-14

## Context

InsightRadar currently relies on Galaxy/AmazingData for important A-share market data paths. That SDK is not a viable portability foundation for ARM-based macOS and is unsuitable as the only provider for a future Linux or cloud deployment. A newly available `hithink-market-query` skill uses Python 3 standard-library HTTPS calls to the Iwencai OpenAPI and therefore has a materially better platform shape.

The Iwencai SkillHub 0.0.4 package and `hithink-market-query` skill were installed locally and a one-row live query succeeded on Windows. This proves basic connectivity and credential validity only. It does not establish production freshness, field semantics, quotas, historical stability, or cross-platform behavior. The vendor skill package was downloaded by its CLI from an HTTP URL without a published SHA-256 check, which is a supply-chain risk.

## Decision

Treat Iwencai as a candidate portable market-data provider, not as a new Core dependency during the active expansion freeze.

- Keep the existing Core roadmap order: close the workspace blocker and complete `feat-037` first.
- Do not call the installed skill directly from production workflows or replace Galaxy/AmazingData based on one successful query.
- When portability work becomes active, integrate Iwencai behind the existing data-source boundary and normalize it to InsightRadar-owned payload contracts.
- Preserve CNInfo as the first source for fresh critical filings; Iwencai is a market-query candidate, not a replacement for the filing source priority.
- Keep credentials outside the repository. Shell profiles may load `IWENCAI_API_KEY` from the operating system's user secret/environment store.
- On macOS ARM or Linux/cloud, Iwencai may become a primary quote/flow adapter only after the acceptance gates below pass; Galaxy/AmazingData remains an optional Windows-compatible provider rather than a universal runtime requirement.

## Acceptance Gates

1. Run the same adapter contract on Windows, macOS ARM, and the intended Linux/cloud runtime with no platform-specific dependency.
2. Reconcile a representative A-share/index/ETF basket against an independent source across multiple trading days, including timestamps, adjustment semantics, units, zero/non-positive values, suspensions, and missing fields.
3. Measure freshness, latency, quota/rate-limit behavior, error bodies, pagination, and fallback frequency before assigning production priority.
4. Ensure provider failure becomes an explicit data gap and cannot break `after-close`, `market-pulse`, or other Core reports.
5. Pin and verify vendor artifacts through HTTPS and checksums or a reviewed internal mirror before automated/cloud installation.
6. Add tests for field mapping, stale-day rejection, secret redaction, and deterministic provider selection before enabling the adapter in Core.

## Consequences

- InsightRadar gains a credible route away from a Windows/x86-only data-source constraint without violating the current Core reliability freeze.
- The local CLI and skill are available for manual evaluation immediately, but product code and architecture remain unchanged.
- Future portability work has an explicit evidence gate instead of treating vendor availability as production readiness.
- The vendor package's HTTP/no-checksum distribution path must be remediated before unattended or production deployment.

## Rollout

Phase 0 is complete: the Iwencai CLI, `hithink-market-query` skill, secure user-level environment configuration, new-shell loading, and a live one-row OpenAPI smoke passed on Windows. Phase 1 begins only after `feat-037` passes and must implement the acceptance gates as a separately scoped feature.

## Local Audit Snapshot

These SHA-256 values pin the locally reviewed 2026-07-14 installation; they are not vendor signatures:

- Iwencai CLI ZIP: `02959fb9292fa1ceb0fac8beec2d1a3ad08e5477f8801b043d54321bcf368a95`
- Iwencai CLI entrypoint: `b201537fb8f2a0ce5fcfb878c7a4f31c6221484d9dd9e4d628bab71b73e89a5d`
- Bundled SkillHub engine: `779ca0f856386816a1e6b8ea402b90804d41dbd3679761bf2b59fef4d18229c4`
- Installed skill `SKILL.md`: `6a530a183c1fc3db10f07c9636d1fc2fecf40fb4c2d07a7f8726f04793af92d1`
- Installed skill CLI: `f5d88bd51ddf702e12ca5efbc6012c08d62205e8ceba261deb09031bc9f6e425`
- Installed skill license: `1126322e2cc8d165adc4c792eeb195717de2bcc7b39be1ce77959d78e87ef685`
