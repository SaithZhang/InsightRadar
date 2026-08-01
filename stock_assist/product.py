"""Product module and runtime surface registry for InsightRadar."""

from __future__ import annotations

from dataclasses import dataclass

from stock_assist.branding import PRODUCT_NAME, PRODUCT_SLUG


@dataclass(frozen=True)
class ProductModule:
    key: str
    title: str
    purpose: str
    primary_users: tuple[str, ...]
    outcomes: tuple[str, ...]


@dataclass(frozen=True)
class ProductCommand:
    name: str
    module_key: str
    help: str
    run_hint: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    retry: str


@dataclass(frozen=True)
class ProductFile:
    path: str
    kind: str
    module_key: str
    description: str


MODULES: tuple[ProductModule, ...] = (
    ProductModule(
        key="portfolio",
        title="Portfolio Intelligence",
        purpose="Overlay holdings and thesis memory on premarket and intraday risk decisions, with after-close audit retained as a secondary capability.",
        primary_users=("personal trader", "risk reviewer"),
        outcomes=("conditional next-day actions", "position risk gaps", "thesis and falsification checks"),
    ),
    ProductModule(
        key="research",
        title="Research Intelligence",
        purpose="Collect research reports, filings, industry context, and public viewpoints into auditable evidence.",
        primary_users=("researcher", "portfolio reviewer"),
        outcomes=("matched report deltas", "source-linked viewpoints", "industry candidate pools"),
    ),
    ProductModule(
        key="market",
        title="Market Radar",
        purpose="Monitor A-share, cross-market, crypto, event, and liquidity-risk signals without executing trades.",
        primary_users=("market watcher", "risk reviewer"),
        outcomes=("market temperature", "event risk windows", "crypto anomaly snapshots"),
    ),
    ProductModule(
        key="ops",
        title="Product Ops",
        purpose="Keep InsightRadar restartable, auditable, and able to turn gaps into the next product sprint.",
        primary_users=("builder", "coding agent"),
        outcomes=("capability map", "verification history", "self-evolution backlog"),
    ),
)


COMMANDS: tuple[ProductCommand, ...] = (
    ProductCommand(
        name="intraday-replay",
        module_key="portfolio",
        help="replay the private IR-001 acceptance case without future-data leakage",
        run_hint="Run offline from the local archive; add --refresh-archive only when AmazingData should refresh immutable minute evidence.",
        inputs=("data/intraday/cases/IR-001.json", "configs/intraday_universe.json", "data/intraday/minute/*.jsonl"),
        outputs=("reports/*-intraday-replay.json", "reports/*-intraday-replay.md", "reports/*-intraday-replay.html"),
        retry="Refresh the archive serially, inspect per-symbol failures, and rerun without replacing unknown with zero.",
    ),
    ProductCommand(
        name="intraday-poll",
        module_key="market",
        help="poll the bounded intraday universe into the local risk-and-opportunity runtime",
        run_hint="Double-click 盘中雷达.cmd for one serial refresh plus reliable 09:25/09:35/10:00 scheduling; IR-002 stays shadow_only.",
        inputs=("configs/intraday_universe.json", "data/portfolio.json", "data/intraday/execution_ledger.jsonl", "data/intraday/reentry_confirmation_ledger.jsonl", ".env with AmazingData credentials"),
        outputs=("data/intraday/minute/**/*.jsonl", "data/intraday/quotes/**/*.jsonl", "data/intraday/alerts/*.jsonl", "data/intraday/runtime.json"),
        retry="Inspect per-symbol gaps; public fallback is local and partial, while unavailable fields stay unknown.",
    ),
    ProductCommand(
        name="after-close",
        module_key="portfolio",
        help="generate the after-close portfolio dashboard",
        run_hint="Run after the A-share close with portfolio data and AmazingData credentials available.",
        inputs=(
            "data/portfolio.manual.tsv, data/portfolio.json, or data/portfolio.galaxy.tsv",
            "data/portfolio_context.json",
            ".env with AmazingData credentials",
            "configs/event_calendar.json",
            "data/research_deltas.jsonl",
        ),
        outputs=("reports/*-after-close.json", "reports/*-after-close.md", "reports/*-after-close.html"),
        retry="Fill missing local data shown in the report data gaps, then rerun `insight-radar after-close`.",
    ),
    ProductCommand(
        name="portfolio-import",
        module_key="portfolio",
        help="preview and explicitly approve a local broker TSV import",
        run_hint="Run with --serve for the loopback UI, or pass --file and review preview output before adding --approve.",
        inputs=("local broker TSV", "explicit beta classifications", "data/portfolio.json", "data/risk_watch_profile.json"),
        outputs=("atomic portfolio/risk-profile save with backups", "fresh market-levels/risk-watch/market-pulse/after-close reports"),
        retry="Fix validation or reconciliation gaps; the command never writes without --approve and never places orders.",
    ),
    ProductCommand(
        name="research-monitor",
        module_key="research",
        help="monitor public research reports and thesis deltas",
        run_hint="Run before or after the daily report to refresh research evidence.",
        inputs=("configs/research_sources.json", "data/portfolio_context.json", "report-cli / Eastmoney access"),
        outputs=("reports/*-research-monitor.md", "data/research_deltas.jsonl"),
        retry="Check configs/research_sources.json and rerun `insight-radar research-monitor`.",
    ),
    ProductCommand(
        name="industry-pool",
        module_key="research",
        help="render an industry candidate pool",
        run_hint="Pass an industry name configured in configs/industries.json.",
        inputs=("configs/industries.json",),
        outputs=("reports/*-industry-pool.md",),
        retry="Add the requested industry to configs/industries.json, then rerun the command.",
    ),
    ProductCommand(
        name="influencer-skills",
        module_key="research",
        help="render influencer viewpoint skill cards",
        run_hint="Use after updating influencer configs or observation streams.",
        inputs=("configs/influencers.json", "data/influencer_observations.jsonl"),
        outputs=("reports/*-influencer-skills.md",),
        retry="Check configs/influencers.json and data/influencer_observations.jsonl, then rerun the command.",
    ),
    ProductCommand(
        name="influencer-sentiment",
        module_key="research",
        help="render reply-thread sentiment for influencer posts",
        run_hint="Use after updating thread captures.",
        inputs=("data/influencer_threads.json", "data/influencer_threads.schema.json"),
        outputs=("reports/*-influencer-sentiment.md",),
        retry="Check data/influencer_threads.json, then rerun the command.",
    ),
    ProductCommand(
        name="nga-auth",
        module_key="research",
        help="store, inspect, or clear the local NGA session cookie",
        run_hint="Run once after copying an authenticated NGA Cookie, and again only when the session expires.",
        inputs=("interactive hidden Cookie input",),
        outputs=("%LOCALAPPDATA%/InsightRadar/secrets/nga_cookie.txt",),
        retry="Log in to NGA, copy the request Cookie locally, then rerun `insight-radar nga-auth set`.",
    ),
    ProductCommand(
        name="nga-monitor",
        module_key="research",
        help="capture NGA Great Times topics and rank reply-velocity heat",
        run_hint="Use the scheduled premarket/after-close captures; run manually only for exceptional event-day snapshots.",
        inputs=("configs/nga_monitor.json", "local NGA Cookie"),
        outputs=("data/nga/board_snapshots.jsonl", "reports/*-nga-monitor.md"),
        retry="Run `insight-radar nga-auth status`, refresh the Cookie if needed, then rerun `insight-radar nga-monitor`.",
    ),
    ProductCommand(
        name="llm-auth",
        module_key="research",
        help="store, inspect, or clear the local OpenAI-compatible API key",
        run_hint="Run once with hidden input before enabling AI synthesis; the key remains outside the repository.",
        inputs=("interactive hidden API key input",),
        outputs=("%LOCALAPPDATA%/InsightRadar/secrets/openai_api_key.txt",),
        retry="Obtain a current key for the configured OpenAI-compatible gateway, then rerun `insight-radar llm-auth set`.",
    ),
    ProductCommand(
        name="nga-daily",
        module_key="research",
        help="generate the NGA Great Times daily topic and sentiment digest",
        run_hint="Use --window morning before the session or --window day after close; add --llm only for the parked external synthesis path.",
        inputs=("configs/nga_monitor.json", "local NGA Cookie", "optional local AI API key"),
        outputs=("reports/*-nga-morning.*", "reports/*-nga-daily.*"),
        retry="Refresh NGA auth; if AI is unavailable, rerun without --llm for an explicitly labelled rule-based report.",
    ),
    ProductCommand(
        name="x-user-posts",
        module_key="research",
        help="collect recent X/Twitter posts for a handle",
        run_hint="Use only when local Twitter auth is configured.",
        inputs=("browser cookies or twitter-cli auth", "handle argument"),
        outputs=("data/twitter_raw/*.json",),
        retry="Refresh local Twitter auth and rerun `insight-radar x-user-posts <handle> -n 5`.",
    ),
    ProductCommand(
        name="x-sync-observations",
        module_key="research",
        help="sync raw X/Twitter captures into observations",
        run_hint="Use after collecting raw posts.",
        inputs=("data/twitter_raw/*.json", "data/influencer_observations.schema.json"),
        outputs=("data/influencer_observations.jsonl",),
        retry="Collect raw posts first, then rerun `insight-radar x-sync-observations`.",
    ),
    ProductCommand(
        name="crypto-monitor",
        module_key="market",
        help="generate a read-only Hyperliquid monitoring report",
        run_hint="Use for crypto/RWA market radar without private keys.",
        inputs=("configs/crypto_watchlist.json", "Hyperliquid Info API"),
        outputs=("reports/*-crypto-monitor.md",),
        retry="Check configs/crypto_watchlist.json and network access, then rerun `insight-radar crypto-monitor`.",
    ),
    ProductCommand(
        name="market-pulse",
        module_key="market",
        help="generate a real-time A-share market pulse board",
        run_hint="Run during the A-share session or midday review to judge index direction, ETF support, and missing derivatives/flow evidence.",
        inputs=(
            "configs/a_share_pulse.json",
            "optional IWENCAI_API_KEY for dated IF/IH/IC/IM close basis",
            ".env with AmazingData credentials for live-session fallback and ETF-share history",
        ),
        outputs=("reports/*-market-pulse.json", "reports/*-market-pulse.md", "reports/*-market-pulse.html"),
        retry="Check IWENCAI_API_KEY, .env / AmazingData access, and configs/a_share_pulse.json, then rerun `insight-radar market-pulse`.",
    ),
    ProductCommand(
        name="market-levels",
        module_key="market",
        help="map multi-timeframe A-share index support, resistance, and response conditions",
        run_hint="Run after a large index move or during review to compare monthly, weekly, daily, 60m, 15m, and 3m structure.",
        inputs=("configs/market_levels.json", "public Tencent K-line access with Eastmoney fallback"),
        outputs=("reports/*-market-levels.json", "reports/*-market-levels.md", "reports/*-market-levels.html"),
        retry="Check network access and configs/market_levels.json, then rerun `insight-radar market-levels`.",
    ),
    ProductCommand(
        name="style-rotation",
        module_key="market",
        help="compare technology, financial and high-dividend styles with persistence gates",
        run_hint="Run after close before after-close; fixed ETF proxy baskets remain diagnostic and cannot authorize trades.",
        inputs=("configs/style_rotation.json", "public Tencent/Eastmoney daily ETF K-lines"),
        outputs=("reports/*-style-rotation.json", "reports/*-style-rotation.md", "reports/*-style-rotation.html"),
        retry="Check per-proxy data gaps and coverage, then rerun without substituting missing evidence with zero.",
    ),
    ProductCommand(
        name="risk-watch",
        module_key="market",
        help="score daily cross-market and portfolio risk with a no-lookahead replay",
        run_hint="Run after the A-share close to update green/yellow/orange/red risk budgets before the next session.",
        inputs=(
            "configs/risk_watch.json",
            "configs/macro_transmission.json",
            "data/risk_watch_profile.json",
            "optional IWENCAI_API_KEY for 同花顺全A, turnover concentration, and fixed-anchor breadth; missing access remains a visible gap",
            "Tencent/Eastmoney A-share and Yahoo Finance global daily K-lines",
        ),
        outputs=(
            "reports/*-risk-watch.json",
            "reports/*-risk-watch.md",
            "reports/*-risk-watch.html",
            "9·24 anchor breadth and equivalent-point diagnostics",
            "diagnostic-only macro transmission shadow and replay calibration",
        ),
        retry="Check the reported data gaps, update the private profile, then rerun `insight-radar risk-watch`.",
    ),
    ProductCommand(
        name="ai-capex-watch",
        module_key="research",
        help="monitor hyperscaler capex and optical-module demand transmission",
        run_hint="Run after official hyperscaler or optical-supply-chain earnings updates; daily runs expose freshness and evidence gaps.",
        inputs=(
            "configs/ai_capex_watch.json",
            "official hyperscaler investor-relations disclosures",
            "official networking and optical-supplier results",
        ),
        outputs=("reports/*-ai-capex-watch.json", "reports/*-ai-capex-watch.md", "reports/*-ai-capex-watch.html"),
        retry="Refresh timestamped official evidence in configs/ai_capex_watch.json, then rerun `insight-radar ai-capex-watch`.",
    ),
    ProductCommand(
        name="factor-lab",
        module_key="research",
        help="run a leakage-aware local A-share multi-factor walk-forward study",
        run_hint="Run after close to rank an explicit research universe and validate five-day benchmark-relative returns out of sample.",
        inputs=("configs/factor_lab.json", ".env with AmazingData credentials or a configured local CSV"),
        outputs=("reports/*-factor-lab.json", "reports/*-factor-lab.md", "reports/*-factor-lab.html"),
        retry="Check the explicit universe, AmazingData access, and sample length, then rerun `insight-radar factor-lab`.",
    ),
    ProductCommand(
        name="factor-pipeline",
        module_key="research",
        help="update the personal factor ledger, train a challenger, and promote only validated models",
        run_hint="Run once after each completed A-share session; labels mature five sessions later before entering training.",
        inputs=("configs/factor_pipeline.json", "configs/factor_lab.json", ".env with AmazingData credentials"),
        outputs=("data/factor_pipeline/observations.csv", "data/factor_pipeline/models/*.json", "reports/*-factor-pipeline.*"),
        retry="Check AmazingData access and both factor configs, then rerun `insight-radar factor-pipeline`.",
    ),
    ProductCommand(
        name="factor-universe-sync",
        module_key="research",
        help="sync point-in-time CSI 1000 membership intervals for leakage-aware research",
        run_hint="Run before enabling the historical CSI 1000 factor config or whenever membership data is refreshed.",
        inputs=(".env with AmazingData credentials", "AmazingData get_index_constituent"),
        outputs=("data/factor_universe/csi1000_membership.csv", "reports/*-factor-universe.*"),
        retry="Check AmazingData access, then rerun `insight-radar factor-universe-sync`.",
    ),
    ProductCommand(
        name="agents",
        module_key="ops",
        help="render the current agent roster",
        run_hint="Use when changing operating roles or review boundaries.",
        inputs=("configs/agents.json", ".codex/agents/*.toml"),
        outputs=("reports/*-agents.md",),
        retry="Check configs/agents.json, then rerun `insight-radar agents`.",
    ),
    ProductCommand(
        name="harness-smoke",
        module_key="ops",
        help="run deterministic Agent Harness task, trace, privacy, and checkpoint contracts",
        run_hint="Run after Harness contract changes; it performs no model call, network request, or trade action.",
        inputs=(
            "configs/harness_eval/smoke_task.json",
            "configs/product_governance.json",
            "feature_list.json",
            "configs/agents.json",
            ".codex/agents/*.toml",
        ),
        outputs=("data/harness_eval/runs/*", "reports/*-harness-smoke.md"),
        retry="Fix the manifest, privacy, trace, or checkpoint contract named in the error and rerun `insight-radar harness-smoke`.",
    ),
    ProductCommand(
        name="architecture-view",
        module_key="ops",
        help="generate the static workflow architecture view",
        run_hint="Use after architecture config changes.",
        inputs=("configs/architecture.json",),
        outputs=("docs/architecture.html",),
        retry="Fix configs/architecture.json and rerun `insight-radar architecture-view`.",
    ),
    ProductCommand(
        name="evolve",
        module_key="ops",
        help="scan recent reports and generate the next backlog",
        run_hint="Use after report-generating workflows have fresh evidence.",
        inputs=("feature_list.json", "configs/product_governance.json", "reports/*.md", "local config/data state"),
        outputs=("reports/*-evolution.md",),
        retry="Generate at least one business report first, then rerun `insight-radar evolve`.",
    ),
    ProductCommand(
        name="product-map",
        module_key="ops",
        help="render the InsightRadar product module and data map",
        run_hint="Use when orienting a new user, agent, or product sprint.",
        inputs=("stock_assist/product.py", "current repo files"),
        outputs=("reports/*-product-map.md",),
        retry="Run `insight-radar product-map` from the repository root.",
    ),
)


FILES: tuple[ProductFile, ...] = (
    ProductFile("configs/agents.json", "product_config", "ops", "Agent role boundaries and responsibilities."),
    ProductFile("configs/product_governance.json", "product_config", "ops", "Bounded product-experiment admission and kill gates."),
    ProductFile(".codex/agents/*.toml", "agent_contract", "ops", "Project-scoped read-only task-agent contracts."),
    ProductFile("configs/harness_eval/*.json", "schema", "ops", "Versioned Harness task manifests and reproducible smoke inputs."),
    ProductFile("data/harness_eval/*", "private_runtime_data", "ops", "Ignored local traces, checkpoints, and benchmark run state."),
    ProductFile("configs/architecture.json", "product_config", "ops", "Workflow graph used by docs/architecture.html."),
    ProductFile("configs/industries.json", "product_config", "research", "Industry frameworks and candidate pools."),
    ProductFile("configs/influencers.json", "product_config", "research", "Influencer/source assumptions and weights."),
    ProductFile("configs/event_calendar.json", "product_config", "market", "Upcoming event and filing-risk windows."),
    ProductFile("configs/crypto_watchlist.json", "product_config", "market", "Crypto/RWA watchlist, dex, addresses, and thresholds."),
    ProductFile("configs/a_share_pulse.json", "product_config", "market", "A-share live pulse watchlist for indexes, ETFs, futures basis, and state-team ETF proxies."),
    ProductFile("configs/intraday_universe.json", "product_config", "market", "Bounded 20-30-theme intraday ETF and representative-stock universe."),
    ProductFile("configs/market_levels.json", "product_config", "market", "Multi-timeframe index target and level-analysis settings."),
    ProductFile("configs/decision_rules.json", "product_config", "portfolio", "Auditable bear-bull state-machine rules, thresholds, vetoes, hysteresis, and daily change cap."),
    ProductFile("configs/style_rotation.json", "product_config", "market", "Fixed technology, financial, dividend and benchmark ETF proxy definitions plus confirmation gates."),
    ProductFile("configs/risk_watch.json", "product_config", "market", "Daily cross-market risk replay, fixed-anchor breadth, coverage gates, and history settings."),
    ProductFile("configs/macro_transmission.json", "product_config", "market", "Diagnostic-only energy, duration, and Korea macro-transmission shadow with point-in-time replay calibration."),
    ProductFile("configs/ai_capex_watch.json", "product_config", "research", "Official hyperscaler CapEx, optical transmission, and supplier realization evidence."),
    ProductFile("configs/factor_lab.json", "product_config", "research", "Explicit research universe, benchmark, walk-forward, and cost settings."),
    ProductFile("configs/factor_pipeline.json", "product_config", "research", "Daily ledger, validation window, and champion-promotion gates."),
    ProductFile("data/factor_pipeline/*", "private_runtime_data", "research", "Local observations, candidate models, champion model, and version registry."),
    ProductFile("data/factor_universe/*", "private_runtime_data", "research", "Versioned point-in-time index membership contracts."),
    ProductFile("configs/research_sources.json", "product_config", "research", "Research-report providers and watch themes."),
    ProductFile("configs/nga_monitor.json", "product_config", "research", "NGA Great Times board, heat ranking, and watch terms."),
    ProductFile("configs/*.example.json", "template", "ops", "Copyable examples for product config files."),
    ProductFile("data/portfolio.json", "private_runtime_data", "portfolio", "Manual holdings input; ignored by git."),
    ProductFile("data/portfolio.manual.tsv", "private_runtime_data", "portfolio", "Manually pasted broker holdings table; ignored by git."),
    ProductFile("data/portfolio.galaxy.tsv", "private_runtime_data", "portfolio", "Broker-export holdings table; ignored by git."),
    ProductFile("data/portfolio.manual.example.tsv", "template", "portfolio", "Copyable template for manually pasted broker holdings."),
    ProductFile("data/portfolio_context.json", "private_runtime_data", "portfolio", "Local thesis, risk-line, and review memory; ignored by git."),
    ProductFile("data/intraday/*", "private_runtime_data", "portfolio", "Private intraday cases, minute/quote archives, point-time runtime, and replay inputs; ignored by git."),
    ProductFile("data/risk_watch_profile.json", "private_runtime_data", "portfolio", "Current exposure, concentration, high-beta share, and optional behavior flags; ignored by git."),
    ProductFile("data/bear_bull_score_state.json", "private_runtime_data", "portfolio", "Persisted finalized score, per-market-day rule deduplication, and state transition memory; ignored by git."),
    ProductFile("data/research_deltas.jsonl", "private_runtime_data", "research", "Append-only research thesis changes; ignored by git."),
    ProductFile("data/influencer_observations.jsonl", "private_runtime_data", "research", "Auditable public-viewpoint stream; ignored by git."),
    ProductFile("data/influencer_threads.json", "private_runtime_data", "research", "Thread/reply sentiment source; ignored by git."),
    ProductFile("data/nga/*", "private_runtime_data", "research", "Local NGA board snapshots and daily evidence inputs."),
    ProductFile("data/*.example.*", "template", "ops", "Copyable examples for local runtime data."),
    ProductFile("data/*.schema.json", "schema", "ops", "Lightweight contracts for local runtime data."),
    ProductFile("reports/*", "generated_output", "ops", "Generated Markdown and HTML artifacts; ignored by git."),
    ProductFile(".env", "private_runtime_data", "market", "AmazingData credentials and host settings; ignored by git."),
    ProductFile("%LOCALAPPDATA%/InsightRadar/secrets/nga_cookie.txt", "private_runtime_data", "research", "Repository-external NGA session secret."),
    ProductFile("%LOCALAPPDATA%/InsightRadar/secrets/openai_api_key.txt", "private_runtime_data", "research", "Repository-external OpenAI-compatible API secret."),
)


def module_for(key: str) -> ProductModule:
    for module in MODULES:
        if module.key == key:
            return module
    raise KeyError(key)


def command_for(name: str) -> ProductCommand:
    for command in COMMANDS:
        if command.name == name:
            return command
    raise KeyError(name)


def command_names() -> tuple[str, ...]:
    return tuple(command.name for command in COMMANDS)


def product_cli_epilog() -> str:
    module_lines = "; ".join(f"{module.title}: {module.purpose}" for module in MODULES)
    return (
        f"{PRODUCT_NAME} modules -> {module_lines}\n"
        f"Primary command: {PRODUCT_SLUG}. Compatibility commands: shenyan-radar, stock-assist."
    )


def command_failure_advice(command_name: str) -> str:
    command = command_for(command_name)
    inputs = ", ".join(command.inputs) if command.inputs else "no local inputs"
    outputs = ", ".join(command.outputs) if command.outputs else "command output"
    return (
        f"Expected inputs: {inputs}\n"
        f"Expected outputs: {outputs}\n"
        f"Suggested fix: {command.retry}"
    )
