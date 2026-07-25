# ADR-0003: Extract the Discipline Reminder and Freeze Expansion

- Status: accepted
- Date: 2026-07-14

## Context

The native Windows discipline reminder is a personal resident application with its own executable, configuration, scheduled task, and user-control lifecycle. It does not consume the A-share decision payload and does not need InsightRadar at runtime. Meanwhile factor, crypto, collector, and client expansion risk diluting the core portfolio decision loop.

## Decision

Prepare the reminder as a self-contained standalone repository package and perform a two-phase cutover. Do not delete the original source until the new repository has built, taken ownership of Task Scheduler, passed user-control checks, and retained a rollback path through one real launch/logon cycle.

Freeze new Lab and Extension capabilities. Replace `feat-033` as the immediate next feature with a core reliability baseline. Keep factor work parked rather than extracting it until its PIT exposure and payload contracts are stable.

## Consequences

- The reminder bundle carries its own AGENTS/state/verification/handoff files and can be resumed without chat history.
- InsightRadar keeps a temporary duplicate until standalone cutover is confirmed.
- Crypto/X improvements and factor expansion are deferred.
- The next InsightRadar sprint measures and hardens the existing Observe-Explain-Decide-Verify loop rather than adding features.

## Rollback

Before original-source removal, reinstalling from `stock-assist` was the rollback path. After verified cutover and explicit retirement authorization, rollback ownership moved to the standalone repository at `D:\work\reminder`.

## Outcome

Completed on 2026-07-14. The standalone project published and validated the Release executable, took ownership of `InsightRadar-DisciplineReminder`, passed visible banner/acknowledge/snooze, speech, and restart checks, and migrated 128 historical log entries. The C-drive intermediate copy and all original source/config/scripts/docs/export artifacts were then removed from `stock-assist`.
