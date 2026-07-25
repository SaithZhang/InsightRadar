# ADR-0004: Canonical InsightRadar Workspace

- Status: accepted
- Date: 2026-07-14

## Context

Two main-project directories existed: a current Git working tree at `%USERPROFILE%\Documents\stock-assist` and an older uncommitted checkout at `D:\work\stock-assist`. The older D-drive checkout retained unique early committee artifacts, but it lacked the current harness, project memory, features, and July 14 work. Codex and the weekday brief still targeted the C-drive path even though the product name was already InsightRadar.

## Decision

Use `D:\work\InsightRadar` as the sole canonical main-project workspace. Use InsightRadar for active repository, Codex project, automation, and user-facing context. Preserve `stock_assist` as the internal Python package and keep legacy CLI aliases so existing scripts do not break.

Archive the older D-drive checkout without merging it into the current product. Preserve historical `stock-assist` references in append-only evidence and migration provenance rather than rewriting history.

## Migration Contract

1. Copy the entire current working tree, including Git metadata, private ignored data, and uncommitted changes.
2. Verify matching Git HEAD, worktree status, and mirror contents before changing the destination.
3. Update active harness, project memory, Codex project registration, and recurring automation to the new path.
4. Keep a temporary compatibility path only when required to avoid breaking an active Codex task; all new changes must land in the D-drive workspace.

## Outcome

Accepted and executed on 2026-07-14. The D-drive InsightRadar workspace became authoritative and the legacy D-drive checkout moved under `D:\work\_archive` for recoverability. After restart, the old C-drive reminder shell was replaced with a junction to `D:\work\reminder`. The old main checkout contents were deleted, but the root remains as a two-file compatibility shell because this resumed task is still bound to the old path. Opening `D:\work\InsightRadar` as a new Codex project is the final prerequisite for replacing that shell with a junction and retargeting the automation project id.
