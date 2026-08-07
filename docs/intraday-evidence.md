# Intraday Evidence Layer

## Purpose and boundary

The Intraday Evidence Layer is a read-only A-share, ETF, and supported-index tape interface for human trade review. It answers where price was, how volume and VWAP behaved, how a symbol compared with a benchmark, and what happened after a user-confirmed execution. It never places, changes, or cancels an order and never turns a risk signal into trade authority.

The first version is admitted as `feat-059` inside the existing four-route V3.1 product. It adds no route and does not promote IR-002 alerts or notifications.

## Architecture

```text
Eastmoney / Tencent
        -> Provider adapters -> ProviderResult[IntradayTape]
        -> IntradayEvidenceService -> EvidenceEnvelope[T]
        -> JSON CLI / read-only MCP tools
```

Raw Eastmoney positions such as `f51...f58` and Tencent whitespace rows exist only in `stock_assist/intraday/evidence_providers.py`. Downstream code receives `InstrumentRef`, `TapeMinute`, `IntradayTape`, and an explicit evidence envelope. One returned tape always belongs to one provider; fallback never fills holes by mixing rows from two sources.

Every envelope carries:

- `status`: `ok`, `degraded`, `stale`, `blocked`, or `no_data`;
- `reason`, `gaps`, and any `conflicts`;
- provider `source_time` separately from local `fetched_at`;
- per-symbol `provenance` and provider-contract status;
- `analysis_authority=read_only_evidence` and `trade_authority=none`.

The primary provider is Eastmoney. Tencent is queried only when Eastmoney is empty, invalid, quarantined, or partial. A usable Tencent fallback returns `degraded / eastmoney_failed_tencent_fallback`. If two usable partial observations disagree beyond the fixed price tolerance, the result is `degraded / source_conflict`, retains both provenance records, and keeps one complete primary tape instead of merging them.

Current-session requests use a 20-second in-process TTL cache. Historical requests still fail explicitly when neither provider exposes the requested minute date; there is no hidden synthetic history.

## Reference implementation and data sources

The local source reference is `%USERPROFILE%\Desktop\市场\dashboard.cmd`, SHA-256 `B79D59B76DD525890C6488551E85F1C7E5801EB80D11DC3277F633131B785CF6`. It is not modified or tracked.

The adapters reuse these fixed routes and verified semantics:

- Eastmoney minute/index tape: `https://push2delay.eastmoney.com/api/qt/stock/trends2/get`, then `push2` and `push2his`; `fields2=f51...f58`, `ndays=5`. Adapter mapping is timestamp, price, high, low, volume, minute amount, and average-price line.
- Tencent current-minute fallback: `https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=...`. Cumulative volume and amount are validated and differenced into minute increments. Counter reversal, duplicate time, or non-monotonic time quarantines the series. Tencent can label the live partial tail with the next minute; a timestamp after `fetched_at` is dropped before counter validation, differencing, and unit inference rather than shifted or treated as completed, and the remaining tape is explicitly partial.
- Tencent recent-day amount fallback: `https://web.ifzq.gtimg.cn/appstock/app/day/query?code=...`. This fixed route and cumulative-to-increment repair came from the maintained IntradayMarketDesk extraction; it was not present in the original CMD.
- CN A-share same-time amount: sum `1.000001` and `0.399001`, require the current and preceding common trade dates, align an exact common `HH:MM`, accumulate complete minute CNY amounts, then calculate delta and delta percent. Any missing minute amount fails closed instead of lowering the sum.
- Symbol mapping: normal securities use an explicit `.SH`/`.SZ` identity or bounded exchange-prefix rules. Benchmarks use a fixed registry: `000688.SH`, `000001.SH`, `000300.SH`, and `399006.SZ`. A bare code also present in the benchmark registry is blocked on the ordinary-security path; callers must use an explicit suffix or the benchmark argument.

Eastmoney and Tencent endpoints used here are public, non-official application interfaces. InsightRadar has no provider SLA, entitlement guarantee, or assurance that response fields and availability will remain unchanged. Provider failure, rate limiting, malformed counters, missing sessions, and conflicts stay visible.

## Tool schemas

All tools return a typed `EvidenceEnvelope` as structured JSON. Required top-level fields are `schema_version`, `status`, `reason`, `source_time`, `fetched_at`, `stale_seconds`, `data`, `provenance`, `gaps`, `conflicts`, `analysis_authority`, and `trade_authority`. MCP publishes a concrete Pydantic output schema for each tool rather than an open-ended object.

### `get_intraday`

Input:

```json
{"symbol":"588200","date":"2026-08-07","time":"10:41"}
```

`time` is optional. Data includes identity, session OHLC, previous close, last price, day return, VWAP, 5/15/30-minute returns, distance to VWAP/high, volume acceleration, explicit amount/volume units, and normalized minutes.

### `get_intraday_compare`

Input:

```json
{"symbols":["588200","002364"],"benchmark":"000688","date":"2026-08-07","time":"10:42"}
```

`symbols` accepts 1-20 items. Rows contain return from open, 5/15-minute return, VWAP/high distance, volume acceleration, benchmark-relative return, and a transparent rank. Every ranked series is aligned to one latest common minute; an alignment downgrade is explicit.

### `get_market_amount_compare`

Input:

```json
{"date":"2026-08-07","time":"10:50"}
```

Data contains the aligned minute, both trade dates, today/prior cumulative amount, delta, and delta percent.

### `review_trades`

Input (synthetic example):

```json
{
  "benchmark":"000688",
  "trades":[{
    "trade_date":"2026-07-01",
    "time":"10:11:10",
    "symbol":"510300",
    "side":"sell",
    "quantity":123,
    "price":4.123
  }]
}
```

`trades` accepts 1-100 finite, positive-price/quantity rows. Each item separates `decision_context` from `outcome`. Here `decision_context` specifically means the no-lookahead pre-execution tape context; it is not the product-wide Current Decision Context defined in `CONTEXT.md`. It uses only completed minutes before execution: at `10:11:10`, the latest admissible minute is `10:10`.

Decision context reports price versus VWAP/high/low, range position, prior 5/15-minute returns, benchmark-relative strength, last completed minute volume, prior-five-minute average, and volume acceleration. Outcome reports 5/15/30-minute return; buys add MAE/MFE, while sells add maximum continued rise and maximum decline. An unobserved horizon remains `null` and appears in `pending_horizons`. When a fallback exposes point prices but no minute high/low, extrema metrics remain `null` with an explicit gap.

## JSON CLI

Run from the repository root:

```powershell
.venv\Scripts\python -m stock_assist.cli intraday-evidence get 588200 --date 2026-08-07
.venv\Scripts\python -m stock_assist.cli intraday-evidence compare 588200 002364 --benchmark 000688 --date 2026-08-07 --time 10:42
.venv\Scripts\python -m stock_assist.cli intraday-evidence amount --date 2026-08-07 --time 10:50
.venv\Scripts\python -m stock_assist.cli intraday-evidence review data\intraday\reviews\trades.json --benchmark 000688
```

The review file is private runtime input under ignored `data/intraday/`; do not commit real holdings or executions.

## MCP server

The server exposes exactly four read-only tools: `get_intraday`, `get_intraday_compare`, `get_market_amount_compare`, and `review_trades`. Tool annotations declare `read_only_hint=true`; there are no order, buy, sell, cancel, account, or broker tools.

Local subprocess transport:

```powershell
.venv\Scripts\python -m stock_assist.intraday.mcp_server --transport stdio
```

- transport: `stdio`
- host/port/endpoint: none; the MCP host launches the subprocess

Local HTTP verification transport:

```powershell
.venv\Scripts\python -m stock_assist.intraday.mcp_server --transport streamable-http --host 127.0.0.1 --port 8766 --endpoint /mcp
```

- transport: Streamable HTTP
- host: `127.0.0.1` only
- port: `8766`
- endpoint: `http://127.0.0.1:8766/mcp`
- mode: stateless JSON response

The implementation follows the current stable [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/) v2 server and Streamable HTTP contract.

## ChatGPT Web and Secure MCP Tunnel preparation

The loopback endpoint is not directly reachable by ChatGPT Web. OpenAI's current [developer-mode and MCP app guidance](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta) says a server on a developer machine or private network needs Secure MCP Tunnel, or it must be deployed as an authenticated remote MCP endpoint. This repository completes only the local read-only server and loopback smoke boundary. It does not create a tunnel, expose a public port, configure OAuth, or publish an app.

The next deployment step is outside this feature: first confirm that the current ChatGPT plan and workspace permit the intended developer-mode/full-MCP app path, then put the Streamable HTTP endpoint behind Secure MCP Tunnel or a separately reviewed HTTPS deployment, add authentication and least-privilege access, and scan and approve the four tools. Do not forward raw localhost or remove the loopback guard merely to make it reachable.

## Intraday Analysis Protocol

1. Tape first, narrative second: call market evidence before discussing news or a macro story.
2. Price action alone cannot change a long-term fundamental thesis.
3. Fed comments, forecasts, unimplemented policy, crowding, and one-day moves are risk signals, not automatic sell signals.
4. Only evidence such as material EPS revisions, orders, CapEx guidance, enacted policy, or business-model damage can support a strategic fundamental change.
5. Report Decision Quality and Outcome Quality separately; a later rise does not by itself make a sale wrong, and a later decline does not by itself make a buy wrong.
6. Without real minute evidence, state that execution timing cannot be evaluated. A screenshot's last price is not a historical tape.

The repository has no existing AI Skill packaging convention, so V1 does not invent one. These rules live in the deep-module contract, MCP instructions/tool descriptions, and this document.

## Known limitations

- These non-official sources can change or disappear without notice.
- Eastmoney `trends2` and Tencent recent-day responses expose only a bounded recent window; older requested dates may be `no_data` unless already held by a separate trusted archive.
- Historical exchange-holiday detection is provider-result based; weekends are rejected locally, while weekday holidays become explicit missing-session evidence.
- Minute data cannot reconstruct second-level tape or order-book state. Review deliberately uses the previous completed minute for decision context.
- Sector-relative strength is not included in V1; only the four fixed benchmarks are admitted.
- The market-amount fallback is labelled degraded even when Tencent succeeds because Eastmoney did not supply two common sessions.
- TTL caching is in-process only; there is no distributed cache.
- The tool returns facts and deterministic measurements. It does not verify self-reported fills, assign a subjective good/bad decision label, forecast direction, or authorize a trade.
