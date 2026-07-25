# Jin10 Event Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a product-owned, read-only Jin10 MCP event-intelligence pipeline that discovers and reconciles fast news, verifies critical claims, maps relevant events to holdings or market context, and emits shadow report evidence without trade authority.

**Architecture:** Keep Jin10 transport behind a source adapter, normalize provider items into typed events, persist an idempotent local ledger, and keep verification/relevance separate from report delivery. `event-intelligence` produces its own JSON/Markdown/HTML triplet; `after-close` consumes only the latest artifact as optional shadow evidence and never calls Jin10 directly.

**Tech Stack:** Python 3.10+, standard-library `urllib`/`json`/`dataclasses`, existing `requests`-based CNInfo adapter, `unittest`, existing report payload/rendering helpers, local JSON/JSONL state, standard MCP Streamable HTTP protocol `2025-11-25`.

## Global Constraints

- Current priority remains `feat-044`; execute this plan only after explicit reprioritization.
- The product runtime must not depend on the user-scoped Codex MCP configuration.
- Read `JIN10_MCP_TOKEN` only from repository-external environment state; never store or print its value.
- Use `result.structuredContent` as the exclusive machine source; `result.content` is human-readable fallback text only.
- Use request `cursor`, response `data.next_cursor`, and `data.has_more` for list pagination.
- Treat Jin10 as discovery evidence. Critical policy, filing, company, and state-capital claims require primary-source confirmation state.
- Keep missing fields, provider importance, APP red-highlight state, confirmation, pagination coverage, freshness, and quota state explicit.
- Do not infer APP red styling from text, HTML color, emojis, or ordering when structured metadata is absent.
- Do not sum incremental execution, recent/historical cumulative amounts, future commitments, targets/capacity, or unknown amounts.
- Approved holdings are the first relevance anchor; no holdings may produce market/style/sector mapping but never a forced candidate.
- No automatic order, trade authority, risk-budget override, cloud split, multi-provider bus, or active push automation.
- Preserve existing report formats and keep missing Jin10 evidence outside strict portfolio decision-ready coverage.

---

## File Map

| Path | Responsibility |
|---|---|
| `stock_assist/data_sources/jin10_mcp.py` | Standard MCP session, structured tool calls, pagination, sanitized errors |
| `stock_assist/event_intelligence/models.py` | Provider-neutral immutable event, magnitude, verification, relevance contracts |
| `stock_assist/event_intelligence/normalize.py` | Atomic-item normalization, digest detection/splitting, compound classification |
| `stock_assist/event_intelligence/ledger.py` | Deterministic identity, idempotent merge, atomic JSONL persistence |
| `stock_assist/event_intelligence/verification.py` | Primary-evidence matching and fail-closed verification state |
| `stock_assist/event_intelligence/relevance.py` | Holdings-first and market/style/sector relevance mapping |
| `stock_assist/workflows/event_intelligence.py` | Bounded collection, reconciliation, payload, Markdown, and HTML bundle |
| `configs/event_intelligence.json` | Live collection windows, terms, official domains, page/time bounds |
| `configs/event_intelligence.example.json` | Credential-free copyable configuration |
| `tests/test_jin10_mcp.py` | Transport, protocol, structured parsing, cursor, quota, and redaction tests |
| `tests/test_event_normalize.py` | Magnitude semantics, state-support false positives, digest reconciliation tests |
| `tests/test_event_ledger.py` | Stable IDs, idempotency, update linkage, and atomic persistence tests |
| `tests/test_event_verification.py` | Confirmation, conflict, missing-primary, and relevance tests |
| `tests/test_event_intelligence_workflow.py` | End-to-end shadow workflow and rendering contract tests |
| `stock_assist/cli.py`, `stock_assist/product.py` | `event-intelligence` command and product registry |
| `stock_assist/workflows/after_close.py` | Optional latest-artifact shadow consumption only |
| `tests/test_after_close_reliability.py` | Event evidence cannot change actions, risk budget, or strict readiness |
| `configs/architecture.json`, `docs/architecture.html` | Implemented workflow/source topology |

---

### Task 1: Standard MCP Transport and Secret Boundary

**Files:**
- Create: `stock_assist/data_sources/jin10_mcp.py`
- Create: `tests/test_jin10_mcp.py`

**Interfaces:**
- Produces: `Jin10McpClient.initialize() -> None`
- Produces: `Jin10McpClient.call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]`
- Produces: `Jin10McpClient.list_flash(cursor: str | None = None) -> dict[str, object]`
- Produces: `Jin10McpClient.search_flash(keyword: str) -> dict[str, object]`
- Produces: `Jin10McpClient.list_news(cursor: str | None = None) -> dict[str, object]`
- Produces: `Jin10McpClient.search_news(keyword: str, cursor: str | None = None) -> dict[str, object]`
- Produces: `Jin10McpClient.get_news(article_id: str) -> dict[str, object]`
- Produces: `Jin10McpClient.list_calendar() -> list[dict[str, object]]`
- Raises: `Jin10McpError(kind: str, code: object, message: str)` with sanitized messages only

- [ ] **Step 1: Write failing lifecycle and structured-content tests**

```python
class Jin10McpClientTests(unittest.TestCase):
    @patch("stock_assist.data_sources.jin10_mcp.urllib.request.urlopen")
    def test_initializes_then_reads_structured_content(self, urlopen):
        urlopen.side_effect = [
            FakeResponse(200, {"Mcp-Session-Id": "s1"}, rpc_result(1, {"protocolVersion": "2025-11-25", "serverInfo": {"name": "jin10"}})),
            FakeResponse(202, {}, b""),
            FakeResponse(200, {}, rpc_result(2, {"structuredContent": {"status": 200, "data": {"items": [], "next_cursor": "c1", "has_more": True}}, "content": [{"type": "text", "text": "not machine input"}]})),
        ]
        with patch.dict(os.environ, {"JIN10_MCP_TOKEN": "secret-value"}):
            client = Jin10McpClient()
            page = client.list_flash()
        self.assertEqual(page["next_cursor"], "c1")
        self.assertTrue(page["has_more"])
        self.assertNotIn("not machine input", json.dumps(page))
```

- [ ] **Step 2: Run the transport test and confirm the red state**

Run: `.venv\Scripts\python -m unittest tests.test_jin10_mcp.Jin10McpClientTests.test_initializes_then_reads_structured_content -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_assist.data_sources.jin10_mcp'`.

- [ ] **Step 3: Implement the bounded Streamable HTTP client**

```python
class Jin10McpClient:
    def __init__(self, url: str = "https://mcp.jin10.com/mcp", *, timeout: int = 30):
        self.url = url
        self.timeout = timeout
        self.session_id: str | None = None
        self._next_id = 1

    def initialize(self) -> None:
        result = self._rpc("initialize", {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "insight-radar", "version": "1.0"},
        })
        if result.get("protocolVersion") != "2025-11-25":
            raise Jin10McpError("protocol", None, "Jin10 MCP protocol version mismatch")
        self._notify("notifications/initialized")

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        if self.session_id is None:
            self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError") is True:
            raise Jin10McpError("business", None, "Jin10 tool returned isError=true")
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            raise Jin10McpError("contract", None, "Jin10 structuredContent is missing")
        if structured.get("status") != 200:
            raise Jin10McpError("business", structured.get("status"), str(structured.get("message") or "Jin10 request failed"))
        data = structured.get("data")
        if not isinstance(data, (dict, list)):
            raise Jin10McpError("contract", None, "Jin10 structuredContent.data is malformed")
        return structured

    def list_flash(self, cursor: str | None = None) -> dict[str, object]:
        structured = self.call_tool("list_flash", {} if cursor is None else {"cursor": cursor})
        data = structured["data"]
        if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not isinstance(data.get("has_more"), bool) or "next_cursor" not in data:
            raise Jin10McpError("contract", None, "Jin10 flash pagination contract is malformed")
        return data
```

Implement `_rpc`, `_notify`, JSON/SSE decoding, session-header reuse, one clean reinitialize after session loss, and sanitized `HTTPError`/JSON-RPC error mapping. Build Authorization only inside the request method from `os.environ["JIN10_MCP_TOKEN"]`; never include request headers or bodies in exception text.

- [ ] **Step 4: Add failure, cursor, quota, and secret-redaction tests**

Add these exact cases to `Jin10McpClientTests`:

- `test_missing_structured_content_does_not_parse_text`: return only `content` and assert `Jin10McpError.kind == "contract"`.
- `test_json_rpc_error_is_sanitized`: return JSON-RPC error code `-32602` containing a fake Authorization value and assert the exception keeps the code but contains neither the token nor `Authorization`.
- `test_is_error_is_business_error`: return `isError=true` and assert `kind == "business"` without parsing `content`.
- `test_cursor_is_the_only_pagination_argument`: inspect the decoded `tools/call` request and assert `arguments == {"cursor": "c1"}`.
- `test_daily_quota_message_has_beijing_reset_kind`: return the documented daily-limit message and assert `kind == "quota_daily"` plus reset timezone `Asia/Shanghai`.
- `test_exception_never_contains_token_or_authorization_header`: raise `HTTPError(401)` and assert both the fake token and the header name are absent from `str(error)` and `repr(error)`.
- `test_news_and_calendar_contracts_use_structured_data`: return a news page, one article, and a calendar array; assert list pagination uses only `cursor`, the detail includes `id/title/time/url/content`, and calendar data stays an array.

- [ ] **Step 5: Run the complete transport suite**

Run: `.venv\Scripts\python -m unittest tests.test_jin10_mcp -v`

Expected: all transport tests pass with no network access.

- [ ] **Step 6: Commit the transport boundary**

```powershell
git add stock_assist/data_sources/jin10_mcp.py tests/test_jin10_mcp.py
git commit -m "feat: add guarded Jin10 MCP transport"
```

---

### Task 2: Typed Events, Magnitude Semantics, and Digest Reconciliation

**Files:**
- Create: `stock_assist/event_intelligence/__init__.py`
- Create: `stock_assist/event_intelligence/models.py`
- Create: `stock_assist/event_intelligence/normalize.py`
- Create: `configs/event_intelligence.json`
- Create: `configs/event_intelligence.example.json`
- Create: `tests/test_event_normalize.py`

**Interfaces:**
- Produces: `NormalizedEvent`, `MagnitudeClaim`, `VerificationState`, `RelevanceResult`
- Produces: `normalize_flash_item(item: dict[str, object], fetched_at: datetime, config: dict[str, object]) -> NormalizedEvent`
- Produces: `split_digest(event: NormalizedEvent) -> list[NormalizedEvent]`
- Produces: `classify_event(event: NormalizedEvent, config: dict[str, object]) -> NormalizedEvent`

- [ ] **Step 1: Write failing tests for the two rescue cases and false positives**

```python
def test_china_reform_amount_is_historical_cumulative(self):
    event = normalize_flash_item(CHINA_REFORM_ITEM, NOW, CONFIG)
    self.assertIn("historical_cumulative", {claim.semantics for claim in event.magnitude_claims})
    self.assertNotIn("incremental_executed", {claim.semantics for claim in event.magnitude_claims})

def test_china_chengtong_has_recent_cumulative_and_future_commitment(self):
    event = normalize_flash_item(CHINA_CHENGTONG_ITEM, NOW, CONFIG)
    semantics = {claim.semantics for claim in event.magnitude_claims}
    self.assertIn("recent_cumulative", semantics)
    self.assertIn("future_commitment", semantics)

def test_sports_national_team_is_not_market_support(self):
    event = classify_event(normalize_flash_item(SPORTS_ITEM, NOW, CONFIG), CONFIG)
    self.assertNotEqual(event.event_type, "state_market_support")
```

- [ ] **Step 2: Run the semantic tests and confirm they fail**

Run: `.venv\Scripts\python -m unittest tests.test_event_normalize -v`

Expected: FAIL because the event-intelligence package does not exist.

- [ ] **Step 3: Define immutable provider-neutral contracts**

```python
@dataclass(frozen=True)
class MagnitudeClaim:
    value: Decimal | None
    unit: str
    semantics: Literal["incremental_executed", "recent_cumulative", "historical_cumulative", "future_commitment", "target_or_capacity", "unknown"]
    evidence_text: str

@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    provider: str
    provider_item_id: str
    source_url: str
    published_at: datetime
    fetched_at: datetime
    title: str
    content: str
    container_type: Literal["atomic_event", "digest"]
    digest_type: str | None
    parent_digest_id: str | None
    child_event_ids: tuple[str, ...]
    event_type: str
    entities: tuple[str, ...]
    actions: tuple[str, ...]
    affected_assets: tuple[str, ...]
    magnitude_claims: tuple[MagnitudeClaim, ...]
    provider_importance: str | None
    provider_red_highlight: bool | None
    verification_status: str
    official_source_urls: tuple[str, ...]
    data_gaps: tuple[str, ...]
```

Use the Jin10 detail ID from `source_url` when available; otherwise hash normalized publication time, title/content, entities, and URL. Do not hash fetch time.

- [ ] **Step 4: Implement compound classification and digest splitting**

```python
DIGEST_PATTERNS = ("重要消息汇总", "要闻汇总", "财经早餐", "午间要闻", "收盘要闻")
NUMBERED_LINE = re.compile(r"^\s*\d+[.、]\s*(.+?)\s*$")

def is_state_market_support(text: str, config: dict[str, object]) -> bool:
    institutions = _matches_any(text, config["state_support"]["institutions"])
    actions = _matches_any(text, config["state_support"]["actions"])
    objects = _matches_any(text, config["state_support"]["market_objects"])
    exclusions = _matches_any(text, config["state_support"]["exclude_terms"])
    return institutions and actions and objects and not exclusions

def split_digest(event: NormalizedEvent) -> list[NormalizedEvent]:
    children = []
    for line in event.content.splitlines():
        match = NUMBERED_LINE.match(line)
        if not match:
            continue
        child_content = match.group(1)
        children.append(replace(
            event,
            event_id=_stable_id(event.source_url, child_content),
            provider_item_id=f"{event.provider_item_id}#item-{len(children)+1}",
            content=child_content,
            container_type="atomic_event",
            digest_type=None,
            parent_digest_id=event.event_id,
            child_event_ids=(),
        ))
    return children
```

Add `provider_importance=None`, `provider_red_highlight=None`, and a visible gap when the item-key set lacks supported structured importance fields. The live and example configs contain only terms, official domains, bounded collection settings, and no credential.

- [ ] **Step 5: Add digest recovery and unknown-red tests**

Add these exact cases to `EventNormalizeTests`:

- `test_sunday_digest_splits_and_preserves_parent_url`: normalize a three-line “周日重要消息汇总” fixture and assert one digest parent, three deterministic children, and the same source URL on parent and children.
- `test_digest_child_matching_atomic_item_keeps_one_event`: reconcile a separately published atomic item with the same normalized body and assert one atomic event plus the digest parent link.
- `test_digest_recovers_previously_missing_child`: omit one atomic fixture, reconcile the digest, and assert exactly one child has recovery origin `digest_only`.
- `test_current_contract_keeps_red_and_importance_unknown`: pass an item containing only `title/content/time/url` and assert both provider fields are `None` plus `provider_importance_missing` in `data_gaps`.
- `test_text_fire_emoji_does_not_create_red_highlight`: include “火” and a fire emoji in content while omitting structured importance fields; assert `provider_red_highlight is None`.

- [ ] **Step 6: Run normalization tests and JSON validation**

Run: `.venv\Scripts\python -m unittest tests.test_event_normalize -v`

Run: `.venv\Scripts\python -m json.tool configs\event_intelligence.json > $null`

Run: `.venv\Scripts\python -m json.tool configs\event_intelligence.example.json > $null`

Expected: all tests and both JSON parses pass.

- [ ] **Step 7: Commit event contracts and rules**

```powershell
git add stock_assist/event_intelligence configs/event_intelligence.json configs/event_intelligence.example.json tests/test_event_normalize.py
git commit -m "feat: normalize Jin10 events and digests"
```

---

### Task 3: Idempotent Ledger and Bounded Collection

**Files:**
- Create: `stock_assist/event_intelligence/ledger.py`
- Create: `tests/test_event_ledger.py`
- Create: `stock_assist/workflows/event_intelligence.py`
- Create: `tests/test_event_intelligence_workflow.py`

**Interfaces:**
- Produces: `EventLedger(path: Path).merge(events: Iterable[NormalizedEvent]) -> LedgerMergeResult`
- Produces: `collect_events(client: Jin10McpClient, config: dict[str, object], ledger: EventLedger, now: datetime) -> CollectionResult`
- Writes: ignored `data/event_intelligence/events.jsonl` and `data/event_intelligence/collection_state.json`

- [ ] **Step 1: Write failing idempotency and atomic-write tests**

Add these exact cases:

- `test_merging_same_atomic_event_twice_writes_one_row`: merge the same fixture twice and assert one JSONL row, first result `inserted == 1`, second result `unchanged == 1`.
- `test_digest_link_updates_existing_event_without_duplicate`: merge an atomic event, then its digest-linked replacement, and assert one row with the unioned parent IDs and `updated == 1`.
- `test_failed_replace_preserves_previous_ledger`: seed one valid row, mock `os.replace` to raise `OSError`, and assert the original bytes are unchanged.
- `test_cursor_loop_stops_at_max_pages_and_reports_incomplete_coverage`: return `has_more=true` for every fake page, set `max_pages=2`, and assert exactly two calls plus `pagination_incomplete` in collection gaps.

- [ ] **Step 2: Run the ledger tests and confirm they fail**

Run: `.venv\Scripts\python -m unittest tests.test_event_ledger -v`

Expected: FAIL because `EventLedger` is undefined.

- [ ] **Step 3: Implement deterministic merge and atomic persistence**

```python
@dataclass(frozen=True)
class LedgerMergeResult:
    inserted: int
    updated: int
    unchanged: int
    total: int

class EventLedger:
    def merge(self, events: Iterable[NormalizedEvent]) -> LedgerMergeResult:
        current = {row["event_id"]: row for row in self._read_rows()}
        inserted = updated = unchanged = 0
        for event in events:
            row = event_to_dict(event)
            previous = current.get(event.event_id)
            merged = merge_event_rows(previous, row)
            if previous is None:
                inserted += 1
            elif merged != previous:
                updated += 1
            else:
                unchanged += 1
            current[event.event_id] = merged
        self._atomic_write(sorted(current.values(), key=lambda row: (row["published_at"], row["event_id"])))
        return LedgerMergeResult(inserted, updated, unchanged, len(current))
```

Write to a sibling temporary file, flush and `os.fsync`, then `os.replace`. Never persist request headers, Bearer values, raw MCP envelopes, or `content` fallback blocks.

- [ ] **Step 4: Implement bounded serial collection and reconciliation**

```python
def collect_events(client, config, ledger, now):
    cursor = None
    atomic: dict[str, NormalizedEvent] = {}
    digests: list[NormalizedEvent] = []
    gaps: list[str] = []
    for page_number in range(int(config["collection"]["max_pages"])):
        page = client.list_flash(cursor)
        for item in page["items"]:
            event = classify_event(normalize_flash_item(item, now, config), config)
            if event.container_type == "digest":
                digests.append(event)
            else:
                atomic[event.event_id] = event
        if not page["has_more"]:
            break
        cursor = str(page["next_cursor"])
        if not cursor:
            gaps.append("pagination_incomplete")
            break
    reconciled = reconcile_digests(tuple(atomic.values()), tuple(digests), config)
    merge = ledger.merge(reconciled.events)
    return CollectionResult(reconciled.events, merge, tuple(gaps + list(reconciled.gaps)))
```

Use dictionaries keyed by `event_id` in the real implementation, stop at configured page/time bounds, and call tools serially. After flash reconciliation, query configured material-news keywords with bounded `search_news`, fetch details only for newly relevant article IDs, and call `list_calendar` once per collection run; normalize articles and calendar entries as supporting evidence rather than duplicate alerts. Add the Beijing-date quota state to `collection_state.json`; a quota error prevents further calls to that tool until the stored reset date.

- [ ] **Step 5: Run ledger and workflow collection tests**

Run: `.venv\Scripts\python -m unittest tests.test_event_ledger tests.test_event_intelligence_workflow -v`

Expected: all ledger and collection tests pass without live network access.

- [ ] **Step 6: Commit the local event ledger**

```powershell
git add stock_assist/event_intelligence/ledger.py stock_assist/workflows/event_intelligence.py tests/test_event_ledger.py tests/test_event_intelligence_workflow.py
git commit -m "feat: persist deduplicated event evidence"
```

---

### Task 4: Primary Verification and Holdings-First Relevance

**Files:**
- Create: `stock_assist/event_intelligence/verification.py`
- Create: `stock_assist/event_intelligence/relevance.py`
- Create: `tests/test_event_verification.py`
- Modify: `stock_assist/workflows/event_intelligence.py`

**Interfaces:**
- Produces: `verify_event(event: NormalizedEvent, evidence: Iterable[PrimaryEvidence]) -> VerificationResult`
- Produces: `map_relevance(event: NormalizedEvent, portfolio: Portfolio, config: dict[str, object]) -> RelevanceResult`
- Consumes: existing `stock_assist.portfolio.load_portfolio`
- Consumes: existing CNInfo records for A-share filing categories; other unsupported claims remain pending

- [ ] **Step 1: Write failing confirmation, conflict, and relevance tests**

Add these exact cases:

- `test_fast_news_without_primary_source_stays_pending`: verify against an empty evidence tuple and assert `pending` plus `primary_source_missing`.
- `test_matching_official_record_confirms_material_claim`: use matching entity, action, amount semantics, and official URL; assert `confirmed` and that URL is retained.
- `test_conflicting_amount_blocks_confirmation`: use the same entity/action with a different executed amount and assert `conflicting` plus `primary_source_conflict`.
- `test_matching_holding_has_priority_over_generic_market_mapping`: supply a matching approved holding and generic market terms; assert scope `holding`, priority `high`, and only that holding code.
- `test_empty_portfolio_maps_sector_without_forcing_candidate`: supply no holdings and a sector term; assert sector mapping, empty holding codes, and empty candidate codes.

For every case, serialize the result and assert it contains neither an action code nor a risk-budget mutation.

- [ ] **Step 2: Run verification tests and confirm they fail**

Run: `.venv\Scripts\python -m unittest tests.test_event_verification -v`

Expected: FAIL because verification and relevance modules do not exist.

- [ ] **Step 3: Implement evidence matching without model guesses**

```python
@dataclass(frozen=True)
class PrimaryEvidence:
    source_type: str
    source_url: str
    published_at: datetime
    entities: tuple[str, ...]
    actions: tuple[str, ...]
    magnitude_claims: tuple[MagnitudeClaim, ...]

def verify_event(event, evidence):
    candidates = [item for item in evidence if entity_overlap(event.entities, item.entities)]
    if not candidates:
        return VerificationResult("pending", (), ("primary_source_missing",))
    if any(magnitude_conflicts(event.magnitude_claims, item.magnitude_claims) for item in candidates):
        return VerificationResult("conflicting", tuple(item.source_url for item in candidates), ("primary_source_conflict",))
    matched = [item for item in candidates if action_overlap(event.actions, item.actions)]
    return VerificationResult(
        "confirmed" if matched else "pending",
        tuple(item.source_url for item in matched),
        () if matched else ("primary_action_not_confirmed",),
    )
```

Add a CNInfo resolver only for categories supported by the existing adapter. Do not add a generic web search or manual “confirmed” override. Unsupported state-capital/policy claims remain `pending` until an official collector supplies typed evidence.

- [ ] **Step 4: Implement holdings-first relevance**

```python
def map_relevance(event, portfolio, config):
    matched = tuple(
        holding.code for holding in portfolio.holdings
        if holding.code in event.affected_assets or holding.name in event.content
    )
    if matched:
        return RelevanceResult("holding", matched, (), (), "high", ("approved_holding_match",))
    sectors = tuple(tag for tag in config["relevance"]["sector_terms"] if tag in event.content)
    styles = tuple(tag for tag in config["relevance"]["style_terms"] if tag in event.content)
    market = ("A-share",) if event.event_type in config["relevance"]["market_event_types"] else ()
    return RelevanceResult("market" if market or sectors or styles else "background", (), sectors, styles, "medium" if market else "low", ())
```

No relevance match is valid and must stay background. Candidate count remains zero unless a separate adopted candidate workflow supplies one.

- [ ] **Step 5: Run verification/relevance and workflow regression tests**

Run: `.venv\Scripts\python -m unittest tests.test_event_verification tests.test_event_intelligence_workflow -v`

Expected: all tests pass; unsupported critical events remain pending and visible.

- [ ] **Step 6: Commit verification and relevance**

```powershell
git add stock_assist/event_intelligence/verification.py stock_assist/event_intelligence/relevance.py stock_assist/workflows/event_intelligence.py tests/test_event_verification.py tests/test_event_intelligence_workflow.py
git commit -m "feat: verify and map material events"
```

---

### Task 5: Shadow Report, CLI, and Product Registry

**Files:**
- Modify: `stock_assist/workflows/event_intelligence.py`
- Modify: `stock_assist/cli.py`
- Modify: `stock_assist/product.py`
- Modify: `configs/architecture.json`
- Modify: `tests/test_event_intelligence_workflow.py`
- Modify: `tests/test_reports.py`

**Interfaces:**
- Produces: `build_event_intelligence_bundle(config_path: Path | None = None, *, client: Jin10McpClient | None = None, now: datetime | None = None) -> tuple[dict[str, object], str, str]`
- Produces: CLI `insight-radar event-intelligence --config PATH`
- Writes: matching `reports/*-event-intelligence.json/.md/.html`

- [ ] **Step 1: Write failing payload and CLI tests**

```python
def test_bundle_exposes_digest_coverage_and_provider_importance_gap(self):
    payload, markdown, html = build_event_intelligence_bundle(CONFIG_PATH, client=FAKE_CLIENT, now=NOW)
    self.assertEqual(payload["schema_version"], "insight-payload/v1")
    self.assertEqual(payload["workflow"], "event-intelligence")
    self.assertIn("digest_reconciliation", payload)
    self.assertIn("provider_importance_missing", payload["data_gaps"])
    self.assertIn("重要消息汇总", markdown)
    self.assertIn("<!doctype html>", html)
```

Add a CLI parser test asserting `event-intelligence` is registered and a report test asserting source links are labelled anchors.

- [ ] **Step 2: Run bundle and CLI tests and confirm they fail**

Run: `.venv\Scripts\python -m unittest tests.test_event_intelligence_workflow tests.test_reports -v`

Expected: FAIL because the bundle/command is not registered.

- [ ] **Step 3: Build the report triplet contract**

```python
def build_event_intelligence_bundle(config_path=None, *, client=None, now=None):
    config = json.loads((config_path or DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))
    current_time = now or datetime.now()
    collection = collect_events(client or Jin10McpClient(), config, EventLedger(DEFAULT_LEDGER_PATH), current_time)
    promoted = [item for item in collection.events if item.relevance.priority in {"high", "medium"}]
    payload = create_report_payload(
        kind="event_intelligence",
        workflow="event-intelligence",
        title="事件情报与关键预警影子报告",
        as_of=current_time.isoformat(timespec="seconds"),
        mode="shadow",
        events=[event_to_dict(item) for item in promoted],
        digest_reconciliation=collection.digest_stats,
        provider_state=collection.provider_state,
        data_gaps=list(collection.data_gaps),
        authority="发现、核验和映射事件；不自动下单，不单独改变风险预算。",
    )
    markdown = render_event_markdown(payload)
    return payload, markdown, markdown_report_to_html(markdown)
```

The first screen shows: conclusion, confirmed/pending/conflicting counts, digest recovered/duplicate counts, holdings-relevant events, market-relevant events, source links, next evidence, and gaps. No buy/sell action field is emitted.

- [ ] **Step 4: Register the CLI and product command**

Add `event-intelligence` with optional `--config` to `_build_parser`; call `build_event_intelligence_bundle`, then `write_payload_report_triplet("event-intelligence", ...)` in `main`. Add a `ProductCommand` under the market module with `JIN10_MCP_TOKEN`, config, portfolio, and typed primary evidence as inputs and report triplets plus the local ledger as outputs.

- [ ] **Step 5: Add architecture source/workflow nodes and regenerate the view**

Add `jin10_mcp` as a guarded Core data source, `event_intelligence` as a shadow Core workflow, and edges to `after_close` and `evolution`. Keep status `shadow` and no automation node.

Run: `.venv\Scripts\python -m stock_assist.cli architecture-view`

Expected: `docs/architecture.html` regenerates with the new source/workflow and command coverage remains complete.

- [ ] **Step 6: Run the report/CLI/product tests**

Run: `.venv\Scripts\python -m unittest tests.test_event_intelligence_workflow tests.test_reports -v`

Run: `.venv\Scripts\python -m stock_assist.cli --help`

Expected: tests pass and help lists `event-intelligence`.

- [ ] **Step 7: Commit the shadow product surface**

```powershell
git add stock_assist/workflows/event_intelligence.py stock_assist/cli.py stock_assist/product.py configs/architecture.json docs/architecture.html tests/test_event_intelligence_workflow.py tests/test_reports.py
git commit -m "feat: add event intelligence shadow report"
```

---

### Task 6: Optional After-Close Shadow Consumption

**Files:**
- Modify: `stock_assist/workflows/event_intelligence.py`
- Modify: `stock_assist/workflows/after_close.py`
- Modify: `tests/test_after_close_reliability.py`

**Interfaces:**
- Produces: `load_latest_event_summary(report_dir: Path, now: datetime) -> dict[str, object]`
- Produces: `render_event_shadow_markdown(summary: dict[str, object]) -> str`
- Extends: `build_after_close_payload(markdown: str, portfolio: Portfolio | None = None, *, report_dir: Path = REPORT_DIR, unified_decision: dict[str, object] | None = None, event_intelligence: dict[str, object] | None = None)`

- [ ] **Step 1: Write failing authority and missing-source tests**

```python
def test_event_shadow_does_not_change_actions_budget_or_readiness(self):
    baseline = build_after_close_payload(ACTION_MARKDOWN, portfolio=PORTFOLIO, event_intelligence=None)
    enriched = build_after_close_payload(ACTION_MARKDOWN, portfolio=PORTFOLIO, event_intelligence=EVENT_SUMMARY)
    self.assertEqual(enriched["actions"], baseline["actions"])
    self.assertEqual(enriched["reliability"], baseline["reliability"])
    self.assertEqual(enriched["unified_decision"]["risk_budget"], baseline["unified_decision"]["risk_budget"])
```

Also add two exact cases:

- `test_missing_event_report_is_optional_visible_gap`: point the loader at an empty temporary report directory; assert status `missing`, an empty event list, and the event-component gap while strict readiness remains unchanged.
- `test_stale_or_unconfirmed_event_cannot_be_promoted_as_plan_change`: provide a 25-hour-old pending event; assert status `stale`, no promoted plan-change entry, and unchanged actions/risk budget.

- [ ] **Step 2: Run the after-close tests and confirm they fail**

Run: `.venv\Scripts\python -m unittest tests.test_after_close_reliability -v`

Expected: FAIL because `event_intelligence` is not a supported payload argument.

- [ ] **Step 3: Add artifact-only optional consumption**

```python
def load_latest_event_summary(report_dir, now):
    paths = sorted(report_dir.glob("*-event-intelligence.json"), reverse=True)
    if not paths:
        return {"status": "missing", "events": [], "data_gaps": ["未找到事件情报影子报告。"]}
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    generated = _parse_datetime(payload.get("generated_at"))
    stale = generated is None or now - generated > timedelta(hours=24)
    events = [item for item in payload.get("events", []) if item.get("verification_status") in {"confirmed", "pending"}]
    return {"status": "stale" if stale else "current", "events": events, "data_gaps": list(payload.get("data_gaps", []))}
```

`after-close` reads this artifact only after `event-intelligence` has run. Add an `event_intelligence` payload component and a collapsed Markdown section. Missing/stale/provider-red gaps remain inside the component and do not enter `_build_core_reliability` strict readiness.

- [ ] **Step 4: Add promotion wording and no-authority checks**

Confirmed material events may say “改变观察优先级” or “需要复核现有计划”. Pending events say “待官方确认，不改变动作”. Conflicting events stay visible but never enter the promoted list. Do not add Jin10 to `MONITOR_PATTERNS`, because that would make provider availability a hard unified-decision dependency.

- [ ] **Step 5: Run focused and full after-close tests**

Run: `.venv\Scripts\python -m unittest tests.test_after_close_reliability tests.test_unified_decision -v`

Expected: all tests pass; risk budget, actions, and strict readiness match the baseline.

- [ ] **Step 6: Commit optional report integration**

```powershell
git add stock_assist/workflows/event_intelligence.py stock_assist/workflows/after_close.py tests/test_after_close_reliability.py
git commit -m "feat: surface verified events in after close"
```

---

### Task 7: Real Shadow Run, Acceptance Audit, and Governance Closure

**Files:**
- Modify: `feature_list.json`
- Modify: `progress.md`
- Modify: `session-handoff.md`
- Modify: `CURRENT_STATE.md` only if the verified baseline or next feature actually changes
- Modify: `docs/memory/product-state.md`
- Modify: `docs/harness.md` only when real acceptance reveals a contract correction

**Interfaces:**
- Consumes: all tasks above
- Produces: acceptance evidence, restartable state, and a pass/blocked verdict for `feat-055`

- [ ] **Step 1: Run all focused tests**

Run: `.venv\Scripts\python -m unittest tests.test_jin10_mcp tests.test_event_normalize tests.test_event_ledger tests.test_event_verification tests.test_event_intelligence_workflow tests.test_after_close_reliability tests.test_unified_decision -v`

Expected: all focused tests pass.

- [ ] **Step 2: Run the full regression and static validation**

Run: `.venv\Scripts\python -m unittest discover -s tests -v`

Run: `.venv\Scripts\python -m compileall stock_assist`

Run: `.venv\Scripts\python -m json.tool configs\event_intelligence.json > $null`

Run: `.venv\Scripts\python -m json.tool feature_list.json > $null`

Expected: all commands exit 0 with no skipped event-intelligence tests.

- [ ] **Step 3: Execute a bounded real shadow collection**

Run: `.venv\Scripts\python -m stock_assist.cli event-intelligence`

Expected: fresh matching JSON/Markdown/HTML paths, a bounded completion time, structured item counts, digest statistics, explicit provider-red unknown state, and no credential in stdout/stderr.

- [ ] **Step 4: Inspect the real state-support and digest cases**

Verify in the newest JSON:

- China Reform Holdings CNY50bn-plus is cumulative already-used support, not next-session incremental inflow.
- China Chengtong near-CNY10bn is recent cumulative executed buying plus separate future intent.
- Sports/industrial “国家队” items do not classify as state market support.
- “周日重要消息汇总” links existing events, recovers genuinely missing children, and does not duplicate alerts.
- `provider_importance` and `provider_red_highlight` are `null`/unknown with a visible gap under the current four-field item contract.
- Confirmed, pending, conflicting, stale, and missing-primary states render accurately.

- [ ] **Step 5: Run after-close and inspect all three formats**

Run: `.venv\Scripts\python -m stock_assist.cli after-close`

Expected: event evidence is visible as an optional shadow component; existing actions, risk veto, and strict readiness are unchanged; JSON/Markdown/HTML agree.

- [ ] **Step 6: Run architecture, memory, harness, secret, and diff gates**

Run: `.venv\Scripts\python -m stock_assist.cli architecture-view`

Run: `.venv\Scripts\python scripts\validate_project_memory.py`

Run: `node %USERPROFILE%\.codex\skills\harness-creator\scripts\validate-harness.mjs --target D:\work\InsightRadar`

Run a repository scan that compares the in-memory `JIN10_MCP_TOKEN` value against tracked/untracked files without printing the value. Then run `git diff --check`.

Expected: architecture command coverage is complete, project memory passes, Harness is 100/100, secret matches are zero, and diff check is clean.

- [ ] **Step 7: Record the evidence and commit governance closure**

Set `feat-055` to `pass` only if every acceptance criterion and real artifact check above passes. Otherwise keep it `pending` or `in_progress` with the exact blocker; never claim APP red-state support while the provider field is absent.

```powershell
git add feature_list.json progress.md session-handoff.md docs/memory/product-state.md CURRENT_STATE.md docs/harness.md
git commit -m "docs: verify Jin10 event intelligence"
```

Do not add an active scheduler or alert automation in this feature. Collect shadow precision, duplicate, missed-event, latency, quota, and failure samples first.

---

## Execution Choice

When `feat-055` is explicitly reprioritized after `feat-044`, use **subagent-driven development** as the recommended execution mode: one fresh implementation agent per task, specification review and code-quality review between tasks, and all repository writes serialized through the lead. Inline execution remains the fallback when concurrency is unavailable.
