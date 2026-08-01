# ADR-0013: Derive Portfolio Beta from Deterministic Market Evidence

- Status: accepted
- Date: 2026-08-01

## Context

The approved broker snapshot contains position facts but does not supply a reliable beta field. The prior import flow therefore asked the user to classify every holding manually. Missing classifications correctly failed closed, but the manual step was unnecessary for a statistic that can be reproduced from dated market prices and was causing the portfolio risk reconciliation to remain blocked.

## Decision

- Add a `portfolio-beta` workflow before `risk-watch` in every approved full refresh and before any stale refresh that includes `risk-watch`.
- Use `000300.SH` as the benchmark, simple daily close-to-close returns, a 120-trading-session window, a minimum of 60 valid observations, and `beta >= 1.20` for `high_beta`; otherwise a valid result is `normal`.
- Use adjusted public A-share daily bars for holdings and provider-native index daily bars for the benchmark. Record source and as-of explicitly.
- Persist beta, R², benchmark, window, minimum and actual observations, benchmark/asset as-of, source, data quality, fit quality, calculation formula, and derived classification with the private portfolio and risk profile.
- Require the holding and benchmark to share the latest session. Insufficient history, stale dates, zero/invalid benchmark variance, non-finite values, unsupported codes, and provider failure all produce `unknown`.
- Keep R² visible as explanatory-fit evidence. A weak R² is not relabelled strong, but it does not silently change the pre-registered beta formula or threshold.
- Remove manual beta selection from the import UI. Deprecated CLI classification input is ignored and cannot override deterministic evidence.
- Keep AI and trade authority out of this workflow.

## Consequences

- An approved import is initially beta-pending and risk-blocked; the background workflow may clear only the beta portion of reconciliation after valid evidence is atomically written.
- `portfolio-beta` changes the portfolio content version, so the refresh coordinator must rebind final `after-close` artifact validation to the post-beta version.
- Real per-holding beta evidence remains ignored private runtime data. Tracked tests use synthetic symbols and price paths.
- Missing holding context, account data, stale unrelated evidence, or other rule blockers remain independent; successful beta reconciliation cannot bypass them.
