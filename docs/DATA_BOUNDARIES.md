# InsightRadar Data Boundaries

Status: **Public-repository safety contract**

Applicability: **V3.0 historical baseline, active V3.1 development, and later versions until explicitly replaced by a stricter contract. Ending the V3.0 scope freeze does not relax these boundaries.**

## May Be Published

- Source code and tests.
- Product, architecture, decision, and contributor documentation.
- Reproducible non-secret configuration.
- Database schemas or migrations if they are added later.
- `.env.example` containing placeholders only.
- `*.example.*` and `*.schema.*` data that is synthetic and reviewed.
- Synthetic screenshots and synthetic HTML review artifacts with visible labeling.
- Aggregated verification results that contain no account, credential, or private-provider payload.

## Must Remain Local

- `.env` and any environment-specific variants containing real values.
- API keys, PATs, bearer tokens, passwords, cookies, session tokens, and certificates.
- Real portfolio snapshots, account equity, cash, cost basis, weights, drawdown, risk profile, and broker exports.
- Trade confirmations, settlement statements, transaction ledgers, and original account screenshots.
- Local databases and unredacted research cases.
- NGA, X/Twitter, AI-gateway, or other authenticated session state.
- Private market-data caches and raw provider responses that are not redistributable.
- Real intraday cases, auction/minute archives, point-time account snapshots, strategy comparisons, and replay reports, even when they contain only aggregate account values.
- `data/`, `reports/`, `tmp/`, `.venv/`, IDE state, logs, browser profiles, caches, and review archives.

## Repository File Classes

| Class | Examples | Git policy |
|---|---|---|
| Source | `stock_assist/`, `tests/`, `scripts/` | Track |
| Product config | `configs/*.json` | Track only after confirming no account linkage or secret |
| Example/schema | `data/*.example.*`, `data/*.schema.*` | Track after synthetic-data review |
| Private runtime | `.env`, real `data/*`, `%LOCALAPPDATA%` secrets | Ignore; never stage |
| Generated runtime | `reports/`, `tmp/`, `dist/`, caches | Ignore |
| Review asset | `review-package/`, selected prototype screenshots | Track only when synthetic and metadata-safe |

## Truth and Redaction Rules

1. Missing shares, cost, price, P&L, weight, beta, cash, and account equity remain `unknown`; redaction must not replace them with zero.
2. Synthetic account/security names must be visibly artificial and must not preserve a reversible mapping to the real account.
3. Screenshots may be committed only when they use synthetic data and contain no username, local path, email, browser profile, or account identifier.
4. Logs and exceptions must not print credentials or raw authenticated headers.
5. A public example must be sufficient to explain the schema but insufficient to reconstruct the user's positions or identity.
6. Provider credentials stay in `.env`, process environment, OS keyring, or `%LOCALAPPDATA%\InsightRadar\secrets`.
7. Derived beta is publishable only as code/config/synthetic tests. Real per-holding beta, R², classification, as-of, source evidence, and reconciled exposure remain private runtime data with the portfolio.

## Public-History Policy

The local legacy repository contains useful private development history, but it also contains:

- a non-noreply author email in historical commit metadata;
- user-specific absolute paths;
- historical portfolio-linked examples in chronological logs.

Therefore the Public GitHub repository must begin from a fresh sanitized baseline. The original history remains local and recoverable but is not pushed. Do not use force-push or history rewriting against an existing public remote.

## Required Pre-Push Checks

1. `git status --short --branch` and explicit-path staging only.
2. Confirm `.env`, real `data/`, `reports/`, `tmp/`, IDE state, logs, and archives are ignored.
3. Scan the current tree and all candidate public commits for secret patterns without echoing matched values.
4. Review large files and compressed archives.
5. Verify screenshots are synthetic and carry no sensitive metadata.
6. Confirm the GitHub repository visibility and default branch.
7. Push only the sanitized baseline and review branch.

## Current Audit Snapshot — 2026-07-25

- `.env`, `.ca.crt`, `.venv/`, real `data/*`, `reports/`, `dist/`, and `*.egg-info/` were already ignored.
- No high-confidence secret pattern was found across 98 local commits.
- The local private/runtime directories contain hundreds of megabytes and must not be staged.
- The tracked review ZIP contains only the synthetic review package and passed the same text secret scan.
- The historical author email is not a GitHub noreply address, so legacy history is excluded from the public remote.
