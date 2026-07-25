# ADR-0011: Publish a Sanitized V3 Baseline Without Legacy Private History

- Status: Accepted
- Date: 2026-07-25

## Context

The owner approved publishing InsightRadar as a Public GitHub repository after personal and account data are removed. The local tree contains a valid V3 runtime plus ignored credentials, real account state, reports, caches, logs, and browser/build artifacts. The legacy Git history uses a non-noreply personal email and chronological logs contain user-specific paths and portfolio-linked examples.

## Decision

Publish a fresh sanitized V3 baseline rather than the 98-commit private history.

- Keep the original history locally and do not delete or rewrite it.
- Start the public default branch from reviewed source, tests, configs, documentation, examples, and synthetic assets only.
- Publish baseline documentation through `chore/freeze-v3-baseline` and a Draft PR.
- Use a GitHub noreply author email for public commits.
- Keep every real account, credential, runtime ledger, report, cache, log, and raw authenticated artifact outside Git.

## Consequences

- The public repository has a clean, reviewable security boundary.
- Private development history remains recoverable locally but is intentionally not a public provenance source.
- Public traceability starts at the V3 freeze date through the baseline commit, decision log, verification record, and Draft PR.
- Future work must preserve the four-task V3 boundary unless an approved V3.1 decision changes it.
