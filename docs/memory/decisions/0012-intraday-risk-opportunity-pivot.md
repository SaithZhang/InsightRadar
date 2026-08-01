# ADR-0012: Pivot the Core to Point-in-Time Intraday Risk and Opportunity

- Status: accepted
- Date: 2026-08-01

## Context

The owner explicitly reprioritized the product after the after-close workbench proved its audit and remembered-plan contracts. The highest-value unresolved moments are now 09:25, 09:35, and 10:00: protect an account-level profit peak, distinguish an A-share catalyst failure from external weakness, prevent impulsive re-entry, and notice relative strength outside the held theme.

## Decision

- Position InsightRadar as “A股盘前/盘中风险与机会雷达，叠加持仓与候选逻辑记忆”.
- Keep exactly four first-level route ids: `today`, `portfolio`, `lookup`, and `review`; relabel them 今日雷达、持仓风险、机会发现、复盘验证.
- Make immutable minute archives, point-in-time snapshots, deterministic risk/opportunity rules, and no-lookahead replay the Core decision seam.
- Keep after-close planning, data health, evidence chains, and version ledgers as secondary capabilities inside the same four pages.
- Keep the modular monolith, 127.0.0.1 service, self-contained HTML, JSON/JSONL/SQLite boundaries, human confirmation, and zero automatic trade authority.
- Start with the private IR-001 acceptance case and a bounded 20-30-theme universe. Do not scan all A shares.

## Consequences

- ADR-0010 remains authoritative for the four-route shell and authority boundaries, but its deferral of intraday monitoring is superseded by this owner-approved pivot.
- Real holdings, case inputs, minute archives, and runtime reports remain private and ignored; tracked tests use synthetic data.
- Same-time external mapping remains a visible gap until a verified point-in-time source replaces the IR-001 scenario input.
- Threshold promotion requires live shadow evidence; an offline pass does not prove general profitability.
