# Harness Public V1 Structural Policy Implementation Plan

- Status: executed and independently verified PASS at `d115e2e` on 2026-07-22; `feat-054` is closed `pass` and `feat-056` is pending next.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkboxes so interrupted work can resume safely.

**Goal:** Replace semantic public-manifest trade prose classification with a structural, fail-closed v1 policy that rejects trade/authority lexemes in free text, sensitive or private material in every public string, and non-allowlisted project references.

**Architecture:** Keep the shared public-material walker responsible for bounded structural string and key checks. Route manifest `title` and `goal` through an additional zero-tolerance trade/authority lexeme check, while preserving approved structured acceptance checks and the fixed Harness no-trade boundary. Apply a manifest-only public reference allowlist so runtime trace/checkpoint artifact references retain their separate bounded-reference contract.

**Tech Stack:** Python 3.10 standard library, `unittest`, PowerShell, existing Harness CLI and validators.

## Execution-Time Constraints

- During implementation, keep `feat-054` `in_progress` and next; keep `feat-056` pending and the sole queued feature.
- Do not add model/provider/network calls, benchmark or pilot work, trade authority, or investment side effects.
- Use RED/GREEN TDD and marker-free CLI failures with no runtime residue.
- Preserve the PUBLIC-only smoke boundary; SANITIZED remains fail closed without a verified transformation record.
- The implementer must not claim final verification before a fresh independent verifier returns a verdict.

---

## Task 1: Specify the structural public free-text policy

**Files:**
- Modify: `tests/test_harness_manifest.py`
- Modify: `tests/test_harness_integration.py`

- [ ] Change all formerly accepted negated, conjunction, and benign-compound trade/authority prose examples to expected rejection.
- [ ] Add exact English and Chinese trade/authority lexeme variants, including negated and conjunctive forms.
- [ ] Prove the canonical structured acceptance check and safe canonical goal still load.
- [ ] Run the focused manifest and integration tests and record the expected RED failures.

## Task 2: Specify sensitive/private string and public-reference contracts

**Files:**
- Modify: `tests/test_harness_manifest.py`
- Modify: `tests/test_harness_integration.py`

- [ ] Add a normalized sensitive-assignment matrix (`password`, `passwd`, `pwd`, `token`, `secret`, API/access key, credential, session, account identifier) using both `=` and `:`.
- [ ] Add holdings, positions, shares, broker export/account, cost basis, personal risk, raw conversation, and reasoning phrase rejection examples in nested public strings.
- [ ] Add accepted PUBLIC project references for `.codex/agents/`, `configs/`, `docs/`, `stock_assist/`, `tests/`, and the exact safe root files.
- [ ] Add rejected `data/`, `reports/`, portfolio, broker, risk-profile, and arbitrary-root references; prove PRIVATE manifests retain bounded local references.
- [ ] Run the exact new tests and record RED before production changes.

## Task 3: Implement and simplify structural validation

**Files:**
- Modify: `stock_assist/harness_eval/validation.py`
- Modify: `stock_assist/harness_eval/manifest.py`
- Modify: `docs/harness.md`

- [ ] Add simple bounded scanners for sensitive assignments, private phrases, and trade/authority lexemes.
- [ ] Remove cue-parity, negation, conjunction, benign-compound, and authority-value semantic parsing from the public path; delete unused helpers/constants.
- [ ] Apply shared structural material checks to the entire PUBLIC/SANITIZED manifest and trade/authority zero tolerance specifically to free-text `title` and `goal`.
- [ ] Add the manifest-only public project-reference allowlist and preserve generic reference validation for PRIVATE manifests, trace/checkpoint refs, expected runtime artifacts, and acceptance targets.
- [ ] Update the Harness contract documentation to describe structural v1 and the reference allowlist.
- [ ] Run focused tests to GREEN, then refactor and rerun them.

## Task 4: Exercise real CLI fail-closed behavior

**Files:**
- Temporarily create and remove bounded probe manifests under the worktree.

- [ ] Run real CLI probes for negated/conjunctive trade prose, sensitive assignments, and forbidden public references.
- [ ] Assert exit 1, marker-free output, and no created runtime artifact directory.
- [ ] Run the canonical PUBLIC smoke task and inspect its fresh report, checkpoint, trace, and final status.

## Task 5: Verify, record evidence, and commit

**Files:**
- Modify: `feature_list.json`
- Modify: `progress.md`
- Modify: `session-handoff.md`
- Modify: `.superpowers/sdd/branch-fixes-implementer-report.md`

- [ ] Run focused and full Harness tests, Python 3.10 parse/compile checks, agent contract validation, project-memory validation, and the Harness validator.
- [ ] Record the RED/GREEN, no-residue CLI, fresh artifact, and validator evidence without changing feature status or queue order.
- [ ] Commit implementation and evidence in reviewable commits.
- [ ] Re-read verification-before-completion instructions, rerun fresh post-commit verification, and confirm a clean worktree.
