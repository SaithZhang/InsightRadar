# ADR-0008: Enable a Guarded Iwencai Futures-Basis Adapter in Local Core

- Status: accepted
- Date: 2026-07-19

## Context

`market-pulse` previously depended on AmazingData for IF/IH/IC/IM intraday basis. The adapter is verified during the live session, but the SDK is Windows-specific, must query serially, and is deliberately skipped outside the A-share continuous session after a real weekend timeout. Consequently, the workday 16:20 Core run could expose a basis gap even when a dated completed-close snapshot was available.

ADR-0005 allowed an Iwencai evaluation behind an InsightRadar-owned boundary after the Core reliability baseline. Since then, the repository has verified standard-library HTTPS access, secret isolation, pagination/failure guards for A-share breadth, and a same-date 2026-07-17 reconciliation for all four spot indexes and sixteen CFFEX contract rows. The user explicitly approved implementing and committing the futures-basis integration.

## Decision

Enable Iwencai as the first provider for a narrowly scoped completed-close futures-basis contract in the local Core product.

- Production code calls the OpenAPI through the existing project-owned HTTPS adapter. It does not execute an installed skill script or require `thsdk` guest mode.
- Resolve the latest completed spot-index date first, then query every IF/IH/IC/IM contract for that exact date.
- Require all four spot indexes to share one date, require positive futures closes and open interest, discard expired zero-open-interest contracts, and select the nearest configured contracts from actual provider codes rather than hard-coding months.
- Store basis as `future - spot`, basis rate, volume, open interest, optional daily open-interest change, quote kind, and as-of date. Provider details remain in the backend audit log.
- A completed-close row has no invented four-minute change. It is diagnostic-only and cannot independently authorize a trade or increase the market-pulse score.
- During an A-share live session, reject a previous-day Iwencai close and fall back to the existing serial AmazingData realtime adapter. Outside the live session, skip AmazingData and keep bounded, explicit gaps if Iwencai is missing, stale, misaligned, or unavailable.
- Read `IWENCAI_API_KEY` only from the environment. Never serialize credentials, request headers, or tokens into reports, audit rows, exceptions, or configuration.

## Acceptance Evidence

- Unit tests cover date alignment, dynamic contract selection, expired-contract rejection, one bounded empty-result retry, weekend completed-close use, and live-session AmazingData fallback.
- A real 2026-07-19 run generated eight IF/IH/IC/IM rows for 2026-07-17, covering 2608 and 2609 contracts with matching spot closes, volume, open interest, partial daily open-interest changes, and eight error-free backend audit rows.
- The real report labels completed-close data as diagnostic-only and retains missing long/short seats, historical basis percentile, and four-minute change as explicit limitations.

## Consequences

- The local after-close Core run gains a useful dated basis and positioning diagnostic without reopening the weekend AmazingData timeout.
- Iwencai becomes a guarded local Core dependency for this narrow contract, but it is not declared a universal production provider. ADR-0005 cross-platform, multi-day reconciliation, quota/latency, and supply-chain gates remain open before cloud or unattended deployment.
- Futu OpenD remains a spot/proxy cross-check only because the current search surface does not expose CFFEX IF/IH/IC/IM contracts and the available Singapore A50 proxy lacks quote permission.
