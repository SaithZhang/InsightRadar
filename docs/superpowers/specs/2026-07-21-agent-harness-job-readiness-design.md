# Agent Harness Engineering and Job-Readiness Design

> This English document is the canonical, normative specification and AI guidance source. The adjacent Chinese review copy is non-normative; if the two differ, this English document controls.

- Status: approved; `feat-054` bootstrap independently verified PASS; `feat-056` pending
- Date: 2026-07-21
- Decision owner: user
- Product: InsightRadar, the user's first OPC product
- Public extraction working name: EvidenceHarness
- Target role: Agent Harness R&D / Engineering

## Decision Summary

InsightRadar will remain a useful private investment decision-intelligence product and become the first real-world proving ground for a reusable Agent Harness engineering system. The project will not be reframed as a toy multi-agent demo. It will use high-stakes, incomplete-data, cross-session investment and software-engineering tasks to measure whether context, memory, checkpointing, tool policy, and bounded subagents make agents more reliable.

The recommended strategy is **one real product, one reusable core, and two delivery surfaces**:

1. InsightRadar privately supplies real tasks, failures, corrections, and product-value constraints.
2. Reusable Harness control, observation, and evaluation contracts are developed behind explicit interfaces inside InsightRadar.
3. Stable generic components, synthetic tasks, sanitized failure patterns, and reproducible experiments are extracted into the public EvidenceHarness project.

The work targets a first job-ready public portfolio in six to eight weeks. Investment usefulness remains a release gate. A Harness change that produces a better demo but worse investment guidance, latency, privacy, or safety is rejected.

## Current Baseline

InsightRadar already has a strong project-level coding-agent harness:

- bounded startup instructions and routed project memory;
- explicit feature state, progress, handoff, and restart procedures;
- one-feature-at-a-time scope control and evidence-based completion;
- documented verification commands and real-artifact checks;
- fail-closed investment and data-quality boundaries;
- an approved product admission gate and a one-lead, bounded-task-agent operating design.

The repository's structural Harness validator currently scores 100/100. That score proves structural coverage, not behavioral effectiveness. The following job-relevant evidence is still missing:

- a versioned real-task benchmark and baseline comparisons;
- task-level traces, cost, latency, correction, and failure taxonomy;
- controlled checkpoint and long-horizon recovery experiments;
- context and memory ablations;
- measured single-agent versus multi-agent value;
- model-versus-Harness separation and backend comparisons;
- a reusable public implementation and reproducible technical report.

The `feat-054` bootstrap implements bounded product governance, read-only Codex role contracts, versioned task/trace/checkpoint/privacy contracts, and deterministic smoke evidence. Reopened contract hardening is complete, and ultimate independent read-only review at `d115e2e` returned PASS with no findings. The measured benchmark remains a separate pending increment and has not started.

## Goals

### Product goal

Make InsightRadar more reliable across long, interrupted, evidence-heavy investment and engineering tasks while preserving its existing evidence, uncertainty, privacy, and no-trade-authority contracts.

### Engineering goal

Build a model-backend-neutral Harness control, observation, and evaluation layer that can answer, with reproducible evidence, when context routing, structured memory, checkpointing, and bounded subagents improve agent performance.

### Job-readiness goal

Produce a public body of work that demonstrates architecture, implementation quality, developer experience, empirical evaluation, failure analysis, privacy engineering, and honest negative results for an Agent Harness R&D / Engineering role.

## Non-Goals

The first six-to-eight-week increment will not:

- add automatic trade execution or allow research evidence to grant trade authority;
- create an unbounded recursive agent swarm;
- train a foundation model or implement a KV-cache engine;
- make a vector database the default memory mechanism;
- build a complex web console before the CLI and evaluation contracts work;
- add cloud multi-tenancy, billing, or enterprise administration;
- publish holdings, broker data, personal risk rules, secrets, or raw private conversations;
- assume that more agents, more tools, or more features imply a better product.

## Approaches Considered

### Optimize InsightRadar only

This would improve the product quickly but provide weak evidence that the Harness work generalizes beyond a finance application.

### Build a generic Harness first

This would make an open-source portfolio easy to present but would lack real task pressure and risk becoming a framework demonstration without credible feedback.

### Real-product-driven extraction

Accepted. InsightRadar supplies real constraints and dogfooding. Generic interfaces stabilize privately before public extraction. Public tasks are synthetic or sanitized and must remain reproducible without InsightRadar's private data.

## Architecture

```text
InsightRadar private product
  -> real investment and engineering tasks
  -> failures, corrections, and usefulness evidence
        |
        v
Harness control and observation core
  -> task and goal state
  -> context and memory adapters
  -> tool registry and policy
  -> checkpoint and recovery
  -> bounded agent orchestration
  -> versioned traces
        |
        v
Harness evaluation layer
  -> deterministic acceptance
  -> baseline and ablation profiles
  -> failure taxonomy
  -> cost, latency, recovery, and safety metrics
        |
        v
EvidenceHarness public extraction
  -> generic CLI and schemas
  -> synthetic task suite
  -> reproducible experiments
  -> technical report and sanitized case study
```

The first version will not implement a new LLM agent runtime. Codex, Claude Code, or another compatible agent is treated as a replaceable execution backend. The project owns the Harness contracts, policies, traces, evaluation, and adoption decision.

## Component Contracts

| Component | Responsibility | Authority boundary |
|---|---|---|
| Product governance | Experiment admission, capacity, owner gate, review date, and kill criterion | Never starts or reprioritizes work automatically |
| Agent contracts | Role, inputs, outputs, tool permissions, and write ownership | Agent count is not a success metric |
| Task manifest | Goal, initial state, allowed tools, budget, expected artifacts, and acceptance | Contains references rather than embedded private data |
| Context builder | Loads the smallest task-relevant context and records what was loaded | Does not default to full history |
| Memory adapter | Reads structured memory, detects conflicts and staleness, proposes updates | Does not silently overwrite canonical memory |
| Tool registry | Declares capabilities, side-effect class, timeout, retry, and approval policy | Destructive behavior cannot be hidden |
| Trace recorder | Records state transitions, tool results, checkpoints, verification, cost, and failures | Does not record secrets or hidden chain-of-thought |
| Checkpoint manager | Persists recoverable task state and validates goal continuity | Chat history is not the sole task state |
| Evaluator | Runs deterministic checks, classifies failures, and compares profiles | Model judging is secondary, never sole acceptance |
| Privacy exporter | Applies classification, sanitization, secret scans, and public export | Private or secret data fails export closed |

Existing planned modules `stock_assist/product_governance.py` and `stock_assist/agent_contracts.py` remain the governance foundation. New generic evaluation behavior will be isolated behind a focused `stock_assist/harness_eval/` package until extraction boundaries are proven.

## Execution Data Flow

1. A versioned task manifest declares the goal, starting state, allowed capabilities, budget, success conditions, and privacy class.
2. A Harness profile selects the context, memory, agent-role, checkpoint, and recovery strategy.
3. An agent backend performs the task through the declared tool registry.
4. The trace recorder emits structured events and references artifacts without capturing hidden reasoning or secrets.
5. Checkpoints record goal state, verified progress, pending work, and artifact hashes.
6. Deterministic verification checks tests, artifacts, state consistency, permission boundaries, and safety rules.
7. The evaluator computes outcomes, costs, latency, corrections, and failure classes.
8. A strategy runs in shadow mode until adoption criteria are met.
9. The privacy exporter generates public tasks and results only from `public` or successfully transformed `sanitized` data.

Every completed run must make it possible to determine:

- what context and memory the agent received;
- which tools it used and which actions had side effects;
- which deterministic evidence proved completion;
- where an interrupted task resumed;
- what a human corrected;
- how the same task behaved under another Harness profile or model backend.

## Trace and Privacy Model

The trace format will be versioned JSONL. Initial event families are:

- `run_started` and `run_completed`;
- `context_loaded` and `memory_retrieved`;
- `tool_requested` and `tool_completed`;
- `checkpoint_saved` and `checkpoint_restored`;
- `verification_result` and `policy_blocked`;
- `human_correction` and `failure_classified`.

Events store structured state, identifiers, hashes or references, timing, token/cost data when available, error codes, and artifact paths. They do not store model hidden chain-of-thought.

Data uses four privacy classes:

1. `public`: safe for the public task suite.
2. `sanitized`: export requires deterministic transformation and a passing leak scan.
3. `private`: local evaluation only.
4. `secret`: never stored in traces; only availability or redacted error state may be recorded.

Holdings, broker exports, cost basis, account identifiers, personal investment rules, repository-external credentials, and raw private conversations are `private` or `secret`. Public export fails closed if a disallowed field, unresolved absolute private path, credential pattern, or unclassified payload remains.

## Failure Taxonomy and Recovery

The evaluation system will distinguish at least:

- missing or misrouted context;
- stale, conflicting, or incorrectly recalled memory;
- tool timeout, permission rejection, malformed result, or unexpected side effect;
- scope drift or unapproved feature expansion;
- tests passing while the real artifact is wrong;
- completion claims inconsistent with feature or handoff state;
- duplicate or conflicting agent work;
- missing, corrupt, or goal-inconsistent checkpoints;
- unsupported investment actions from missing or stale evidence;
- privacy, credential, or public-export leakage risk.

Recovery must not conceal a failure. When retry budget is exhausted, state continuity is uncertain, verification disagrees, or privacy classification is incomplete, the run stops with diagnostic evidence. Investment workflows continue to fail closed on new exposure.

## Evaluation Design

### Initial task suite

The first private and sanitized benchmark contains 20 to 30 tasks drawn from recurring InsightRadar failure modes:

- clean-session startup and exact feature recovery;
- bounded project-memory routing;
- stale or missing holdings behavior;
- official filing versus fast-news precedence;
- cumulative versus incremental event classification;
- interruption and checkpoint recovery;
- code, tests, real artifact, feature state, and handoff consistency;
- one-feature scope control under competing backlog pressure;
- tool timeout and provider degradation;
- secret and private-data export rejection.

Public tasks use synthetic companies, positions, reports, tools, paths, and credentials while preserving the failure structure.

### Baseline profiles

Every eligible task is evaluated under four profiles:

1. no project Harness;
2. root instructions only;
3. the current InsightRadar Harness;
4. the improved measured Harness.

Model-backend comparisons are added only after the task and trace contracts are stable. A backend comparison must keep the task, tool availability, budget, evaluator, and Harness profile fixed.

### Metrics

Primary metrics are:

- deterministic task success;
- evidence correctness;
- false-completion, unauthorized-action, scope-drift, and privacy-leak rates;
- checkpoint recovery success and context-recovery accuracy;
- tokens or context volume, tool calls, elapsed time, and human corrections;
- inappropriate investment-action rate under missing or stale evidence.

Semantic model judging may score clarity or usefulness, but deterministic contracts and blinded human review samples remain primary.

## Adoption and Kill Gates

### Safety and product invariants

- Unauthorized investment actions in critical tests: exactly zero.
- Critical privacy leaks, unauthorized writes, and false completion: exactly zero.
- Missing, stale, and conflicting inputs remain explicitly visible in every applicable case.
- Promoted external evidence retains source and time provenance.
- Existing strict decision-ready coverage and no-trade-authority behavior do not regress.

### Checkpointing

Controlled interruption recovery must reach at least 90% before checkpoint recovery is offered as a default workflow. Goal drift or unverified restored state is a failed recovery.

### Context strategy

Adopt only if token use or loaded-context volume falls by at least 25%, overall task success falls by no more than two percentage points, and critical safety cases do not regress.

### Memory strategy

Adopt only if cross-session context-recovery failures fall by at least 20% without increasing stale-memory overrides. Canonical memory changes remain validated or human-approved.

### Multi-agent strategy

Evaluate only on tasks with separable read-heavy work. Adopt as a default only if success improves by at least five percentage points or critical omissions materially fall, while token use remains no more than 1.8 times the single-agent profile. Otherwise retain the negative result and keep single-agent execution as the default.

These thresholds are preregistered first-version hypotheses. They may be adjusted once after the initial baseline, with the original threshold, evidence, new threshold, and reason preserved. Repeated goalpost changes are not allowed.

## Six-to-Eight-Week Delivery Plan

### Weeks 1-2: governance and observability

- implement and update the deferred `feat-054` control plane;
- enforce one active and two queued product experiments;
- add lead-only writes and read-only, non-recursive task-agent contracts;
- repair full-catalog `evolve` visibility;
- add task, trace, checkpoint, privacy, and failure schemas;
- produce real `agents` and `evolve` artifacts plus trace smoke evidence.

### Weeks 3-4: real-task evaluation

- build the first 20-to-30-task private/sanitized suite;
- implement the four Harness profiles;
- run deterministic verification and failure classification;
- generate a baseline benchmark with cost, latency, correction, recovery, and safety results.

### Weeks 5-6: focused Harness experiments

- bounded context versus full-history ablation;
- structured memory versus chat-history-only ablation;
- single-agent versus one-lead-and-bounded-read-only-agents ablation;
- checkpoint and controlled-interruption fault injection;
- shadow-adopt only strategies that meet the gates.

### Weeks 7-8: public extraction and portfolio packaging

- extract stable generic contracts into EvidenceHarness;
- publish the synthetic suite and one-command reproduction path;
- publish architecture, threat/privacy model, failure catalog, and benchmark results;
- produce Chinese and English documentation;
- publish a sanitized InsightRadar case study and a five-to-ten-minute demonstration script;
- write the technical report, "Building an Evaluated Agent Harness from a Real Investment Decision System."

## InsightRadar Product Integration

InsightRadar remains the product and release authority for private behavior. Harness experiments run in shadow mode and cannot block or modify the production `after-close`, `risk-watch`, `market-pulse`, portfolio-import, or other Core paths until their acceptance gates pass.

The product benefit expected from accepted changes is:

- accurate new-session recovery of current portfolio source, risk state, open work, and data gaps;
- no duplicate processing of the same material event;
- bounded recovery after interruption without repeating expensive or constrained providers;
- parallel read-only evidence or verification work when justified, with one integrated verdict;
- traceable guidance from source and context through verification and later review.

## Public Extraction Contract

EvidenceHarness must run without InsightRadar's private data or finance providers. It will include:

- generic task, trace, checkpoint, policy, and evaluation schemas;
- a CLI for running profiles and aggregating results;
- synthetic tasks and fault injectors;
- reproducible benchmark configuration;
- privacy and secret-scanning gates;
- architecture, developer guide, failure taxonomy, and limitations;
- a sanitized InsightRadar case study, not the private product or strategy.

The public project will report reproducible results and negative findings. It will not claim superiority over a model or competing Harness unless a controlled experiment supports that exact claim.

## Historical Activation Transition

The user explicitly approved reprioritizing the Agent Harness job-readiness program ahead of `feat-044`, approved this written specification, selected an execution approach, and resumed the bootstrap. The implementation source is `docs/superpowers/plans/2026-07-21-agent-harness-bootstrap.md`, which supersedes the governance-only `2026-07-19-agent-governed-product-iteration.md` where the scopes differ.

That activation transition registered `feat-054`, updated bounded state, and implemented one independently verifiable increment at a time while leaving `feat-044` and `feat-055` pending. Final whole-branch review subsequently reopened `feat-054` for contract hardening; ultimate independent read-only review at `d115e2e` returned PASS with no findings, so the bootstrap is closed. `feat-056` remains pending and is the sole queued Harness experiment; no pilot or benchmark implementation has started. The human owner still controls priority, scope expansion, experiment start, and release.

## Final Acceptance

The program is job-ready when the following evidence exists:

- `feat-054` passes with governance, agent, trace, checkpoint, privacy, and evaluator contracts;
- a 20-to-30-task private/sanitized suite and four baseline profiles run reproducibly;
- context, memory, checkpoint, and bounded multi-agent experiments report both gains and failures;
- critical unauthorized-action, privacy-leak, unauthorized-write, and false-completion counts are zero;
- production investment workflows show no safety or strict-readiness regression;
- EvidenceHarness runs from a clean environment with one documented command;
- public Chinese and English documentation, benchmark results, limitations, a case study, and a demonstration are complete;
- a reviewer can reproduce the central claims without access to the user's holdings or private repository state.
