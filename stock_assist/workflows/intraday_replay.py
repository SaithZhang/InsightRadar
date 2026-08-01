"""IR-001 point-in-time minute replay and self-contained report bundle."""

from __future__ import annotations

from datetime import date, datetime
from html import escape
import json
from pathlib import Path
from typing import Iterable, Mapping

from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.intraday.archive import MinuteArchive
from stock_assist.intraday.backtest import compare_strategies
from stock_assist.intraday.contracts import PointQuote, contract_dict
from stock_assist.intraday.providers import (
    fetch_amazingdata_auction_quotes,
    fetch_amazingdata_minute_bars,
    fetch_eastmoney_minute_bars,
)
from stock_assist.intraday.rules import IntradayDecisionEngine, ReentryPositionState
from stock_assist.intraday.snapshots import IntradaySnapshotBuilder
from stock_assist.intraday.universe import load_intraday_universe
from stock_assist.paths import DATA_DIR


DEFAULT_IR001_CASE = DATA_DIR / "intraday" / "cases" / "IR-001.json"


def build_intraday_replay_bundle(
    case_path: Path | None = None,
    *,
    refresh_archive: bool = False,
    allow_fallback: bool = True,
) -> tuple[dict[str, object], str, str]:
    case = _load_case(case_path or DEFAULT_IR001_CASE)
    universe = load_intraday_universe()
    themes = _active_themes(case, universe)
    archive = MinuteArchive()
    provider_status: dict[str, object] = {"primary": "not_requested", "fallback": "not_requested"}
    if refresh_archive:
        provider_status = refresh_case_archive(
            case,
            themes,
            archive=archive,
            allow_fallback=allow_fallback,
        )
    _ensure_initial_quotes(case, archive)
    trade_date = date.fromisoformat(str(case["trade_date"]))
    symbols = _case_symbols(case, themes, str(universe.get("benchmark") or "000300.SH"))
    bars_by_date = {
        day: archive.read_bars(day, symbols=symbols)
        for day in archive.available_dates()
        if day <= trade_date
    }
    quotes = archive.read_quotes(trade_date)
    target_bars = bars_by_date.get(trade_date, {})
    if not target_bars:
        raise RuntimeError("IR-001 分钟归档为空；请先使用 --refresh-archive。")
    if not refresh_archive:
        provider_status = _archived_provider_status(
            symbols,
            bars_by_date,
            quotes,
        )
    timepoints = sorted(
        {
            datetime.fromisoformat(str(case["initial_timestamp"])),
            *(quote.timestamp for quote in quotes),
            *(
                bar.timestamp
                for rows in target_bars.values()
                for bar in rows
            ),
        }
    )
    builder = IntradaySnapshotBuilder(
        case=case,
        themes=themes,
        bars_by_date=bars_by_date,
        quotes=quotes,
        benchmark=str(universe.get("benchmark") or "000300.SH"),
    )
    engine = IntradayDecisionEngine(
        technology_theme_ids=_strings(case.get("technology_theme_ids")),
        catalyst_theme_ids=_strings(case.get("catalyst_theme_ids")),
        opportunity_theme_ids=_strings(case.get("opportunity_theme_ids")),
    )
    reentry_states = (
        ReentryPositionState(
            target_id=theme_id,
            sold_at="2026-07-31T09:25:00",
            sold_fraction=0.5,
            sale_price=0.0,
            account_profit_floor=_float(case.get("account_profit_floor")),
        )
        for theme_id in _strings(case.get("technology_theme_ids"))
    )
    reentry_states = tuple(reentry_states)
    snapshots = []
    timeline = []
    seen: set[tuple[object, ...]] = set()
    no_lookahead_violations: list[str] = []
    for timestamp in timepoints:
        snapshot = builder.build(timestamp, previous=snapshots)
        future_times = [item for item in snapshot.source_times if item > timestamp]
        if future_times:
            no_lookahead_violations.append(
                f"{timestamp.isoformat()} consumed {max(future_times).isoformat()}"
            )
        evaluation = engine.evaluate(
            snapshot,
            history=snapshots,
            reentry_states=reentry_states,
        )
        for alert in evaluation.alerts:
            signature = (
                alert.type,
                alert.target_id,
                alert.severity,
                alert.title,
                alert.action_state,
            )
            if signature in seen:
                continue
            seen.add(signature)
            timeline.append(contract_dict(alert))
        snapshots.append(snapshot)
    if no_lookahead_violations:
        raise RuntimeError("IR-001 no-lookahead audit failed: " + "; ".join(no_lookahead_violations[:3]))
    backtest = compare_strategies(
        snapshots,
        technology_theme_ids=_strings(case.get("technology_theme_ids")),
        actual_operations=case.get("actual_operations", []) if isinstance(case.get("actual_operations"), list) else [],
    )
    data_gaps = sorted(
        {
            str(case.get("actual_operations_gap")) if not case.get("actual_operations") else "",
            *(snapshots[-1].data_gaps if snapshots else ()),
        }
        - {""}
    )
    payload: dict[str, object] = {
        "schema_version": "intraday-replay/v1",
        "case": {
            "case_id": case["case_id"],
            "title": case["title"],
            "trade_date": case["trade_date"],
            "classification": case.get("case_classification"),
            "actual_operations_status": "unknown" if not case.get("actual_operations") else "provided",
        },
        "contract_versions": {
            "snapshot": "IntradaySnapshot/v1",
            "theme": "ThemeSnapshot/v1",
            "alert": "IntradayAlert/v1",
        },
        "data_lineage": {
            "archive_root": str(archive.root),
            "primary": "Galaxy AmazingData query_kline/min1 and query_snapshot",
            "fallback": "Eastmoney public 1m K-line, per-symbol only",
            "provider_status": provider_status,
            "external_mapping_note": "外部映射涨幅为 IR-001 验收情境输入，不冒充实盘数据。",
        },
        "no_lookahead": {
            "status": "pass",
            "policy": "每个快照仅消费 source_time <= snapshot.timestamp 的本地归档记录。",
            "snapshot_count": len(snapshots),
            "violations": [],
        },
        "timeline": timeline,
        "snapshots": [contract_dict(item) for item in snapshots],
        "backtest": backtest,
        "data_gaps": data_gaps,
    }
    markdown = render_intraday_replay_markdown(payload)
    return payload, markdown, render_intraday_replay_html(payload)


def refresh_case_archive(
    case: Mapping[str, object],
    themes: Iterable[Mapping[str, object]],
    *,
    archive: MinuteArchive,
    allow_fallback: bool,
) -> dict[str, object]:
    trade_date = date.fromisoformat(str(case["trade_date"]))
    start = date(2026, 7, 24)
    symbols = _case_symbols(case, themes, "000300.SH")
    client = AmazingDataClient()
    primary_error: str | None = None
    bars = []
    quotes = []
    try:
        bars = fetch_amazingdata_minute_bars(client, symbols, start=start, end=trade_date)
        quotes = fetch_amazingdata_auction_quotes(client, symbols, trade_date=trade_date)
    except Exception as exc:
        primary_error = f"{type(exc).__name__}: {exc}"
    finally:
        client.logout()
    if bars:
        archive.write_bars(bars)
    if quotes:
        archive.write_quotes(quotes)
    archived = archive.read_bars(trade_date, symbols=symbols)
    missing = sorted(set(symbols) - set(archived))
    fallback_failures: dict[str, str] = {}
    fallback_count = 0
    if allow_fallback and missing:
        fallback_bars, fallback_failures = fetch_eastmoney_minute_bars(
            missing,
            start=start,
            end=trade_date,
        )
        fallback_count = len(fallback_bars)
        if fallback_bars:
            archive.write_bars(fallback_bars)
    remaining = sorted(set(symbols) - set(archive.read_bars(trade_date, symbols=symbols)))
    return {
        "primary": "partial" if primary_error or remaining else "ok",
        "primary_error": primary_error,
        "primary_bar_count": len(bars),
        "auction_quote_count": len(quotes),
        "fallback": "partial" if fallback_failures else "used" if fallback_count else "not_needed",
        "fallback_bar_count": fallback_count,
        "symbol_failures": fallback_failures,
        "remaining_missing_symbols": remaining,
    }


def render_intraday_replay_markdown(payload: Mapping[str, object]) -> str:
    case = payload["case"]
    timeline = payload["timeline"]
    strategies = payload["backtest"]["strategies"]
    lines = [
        f"# {case['case_id']} 逐分钟回放",
        "",
        f"> {case['title']}",
        "",
        "## 验收结论",
        "",
        "- 点时审计：PASS；所有快照仅使用当时已可见的 source_time。",
        "- 账户动作：只输出风险变化区间与人工确认门槛，不自动下单。",
        "- 实际操作改善：unknown；缺少可核验逐笔成交，不用代理策略冒充。",
        "",
        "## 规则触发时间线",
        "",
        "| 时间 | 级别 | 类型 | 目标 | 结论 |",
        "|---|---|---|---|---|",
    ]
    for item in timeline:
        lines.append(
            f"| {str(item['timestamp'])[11:16]} | {item['severity']} | {item['type']} | "
            f"{item['target_id']} | {item['conclusion']} |"
        )
    lines.extend(
        [
            "",
            "## 策略对照",
            "",
            "| 策略 | 最终收益 | 最大利润回吐 | 最大回撤 | 卖飞率 | 交易次数 | 接回成功率 | 相对全程持有改善 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in strategies:
        success = "unknown" if item["reentry_success_rate_pct"] is None else f"{item['reentry_success_rate_pct']:.2f}%"
        lines.append(
            f"| {item['label']} | {item['final_return_pct']:+.4f}% | {item['max_profit_giveback']:,.0f} | "
            f"{item['max_drawdown_pct']:.4f}% | {item['sold_too_early_rate_pct']:.2f}% | "
            f"{item['trade_count']} | {success} | {item['improvement_vs_full_hold']:+,.0f} |"
        )
    lines.extend(["", "## 数据缺口", ""])
    lines.extend(f"- {item}" for item in payload.get("data_gaps", []))
    return "\n".join(lines)


def render_intraday_replay_html(payload: Mapping[str, object]) -> str:
    case = payload["case"]
    timeline_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item['timestamp'])[11:16])}</td>"
        f"<td><span class='sev {escape(str(item['severity']))}'>{escape(str(item['severity']))}</span></td>"
        f"<td>{escape(str(item['type']))}</td><td>{escape(str(item['target_id']))}</td>"
        f"<td>{escape(str(item['conclusion']))}</td></tr>"
        for item in payload["timeline"]
    )
    strategy_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item['label']))}</td><td>{float(item['final_return_pct']):+.4f}%</td>"
        f"<td>{float(item['max_profit_giveback']):,.0f}</td><td>{float(item['max_drawdown_pct']):.4f}%</td>"
        f"<td>{float(item['sold_too_early_rate_pct']):.2f}%</td><td>{item['trade_count']}</td>"
        f"<td>{'unknown' if item['reentry_success_rate_pct'] is None else str(item['reentry_success_rate_pct']) + '%'}</td>"
        f"<td>{float(item['improvement_vs_full_hold']):+,.0f}</td></tr>"
        for item in payload["backtest"]["strategies"]
    )
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(str(case['case_id']))} 回放</title>
<style>:root{{--bg:#071015;--panel:#111c22;--ink:#eaf3f0;--muted:#90a29e;--line:#29404a;--red:#ff667d;--orange:#f3a65a;--yellow:#e8cf63;--info:#5dd6a5}}*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(155deg,#071015,#0b1419);color:var(--ink);font:14px/1.55 'Segoe UI','Microsoft YaHei',sans-serif}}main{{max-width:1460px;margin:auto;padding:28px}}h1{{font-size:28px;margin:0 0 6px}}p{{color:var(--muted)}}section{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;margin:16px 0;overflow:auto}}.cards{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}.card{{background:#0c171d;border:1px solid var(--line);border-radius:10px;padding:14px}}.card strong{{display:block;font-size:21px}}table{{width:100%;border-collapse:collapse;min-width:900px}}th,td{{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{color:#9eb4ae}}.sev{{font-weight:700}}.red{{color:var(--red)}}.orange{{color:var(--orange)}}.yellow{{color:var(--yellow)}}.info{{color:var(--info)}}@media(max-width:760px){{.cards{{grid-template-columns:1fr}}main{{padding:14px}}}}</style></head>
<body><main><h1>{escape(str(case['case_id']))} 逐分钟回放</h1><p>{escape(str(case['title']))}</p>
<div class='cards'><div class='card'><span>点时审计</span><strong>PASS</strong><small>无未来数据</small></div><div class='card'><span>分钟快照</span><strong>{payload['no_lookahead']['snapshot_count']}</strong><small>source_time 可追溯</small></div><div class='card'><span>实际操作比较</span><strong>unknown</strong><small>缺少逐笔成交</small></div></div>
<section><h2>规则触发时间线</h2><table><thead><tr><th>时间</th><th>级别</th><th>类型</th><th>目标</th><th>结论</th></tr></thead><tbody>{timeline_rows}</tbody></table></section>
<section><h2>策略对照</h2><table><thead><tr><th>策略</th><th>最终收益</th><th>最大利润回吐</th><th>最大回撤</th><th>卖飞率</th><th>交易</th><th>接回成功率</th><th>相对全程持有改善</th></tr></thead><tbody>{strategy_rows}</tbody></table></section>
<section><h2>数据边界</h2><p>外部映射强度是验收情境输入；账户动作始终需要用户确认；行情源按 symbol 局部降级。</p></section></main></body></html>"""


def _ensure_initial_quotes(case: Mapping[str, object], archive: MinuteArchive) -> None:
    timestamp = datetime.fromisoformat(str(case["initial_timestamp"]))
    quotes: list[PointQuote] = []
    raw_quotes = case.get("initial_quotes")
    for item in raw_quotes if isinstance(raw_quotes, list) else []:
        if not isinstance(item, Mapping):
            continue
        quotes.append(
            PointQuote(
                symbol=str(item["symbol"]).upper(),
                timestamp=timestamp,
                price=float(item["price"]),
                pre_close=_float(item.get("pre_close")),
                open=_float(item.get("open")),
                high=_float(item.get("price")),
                low=_float(item.get("price")),
                volume=None,
                amount=None,
                source_time=timestamp,
                fetched_at=timestamp,
                source="user-provided broker snapshot",
                phase="auction_estimate",
            )
        )
    archive.write_quotes(quotes)


def _archived_provider_status(
    symbols: Iterable[str],
    bars_by_date: Mapping[date, Mapping[str, list]],
    quotes: Iterable[PointQuote],
) -> dict[str, object]:
    source_counts: dict[str, int] = {}
    observed: set[str] = set()
    bar_count = 0
    for day_rows in bars_by_date.values():
        for symbol, rows in day_rows.items():
            observed.add(symbol)
            for bar in rows:
                bar_count += 1
                source_counts[bar.source] = source_counts.get(bar.source, 0) + 1
    quote_counts: dict[str, int] = {}
    for quote in quotes:
        quote_counts[quote.source] = quote_counts.get(quote.source, 0) + 1
    missing = sorted(set(symbols) - observed)
    primary_present = any("AmazingData" in source for source in source_counts)
    fallback_present = any("Eastmoney" in source for source in source_counts)
    return {
        "primary": "archived_complete" if primary_present and not missing else "archived_partial",
        "archive_bar_count": bar_count,
        "bar_sources": source_counts,
        "quote_sources": quote_counts,
        "fallback": "archived" if fallback_present else "not_used",
        "remaining_missing_symbols": missing,
    }


def _load_case(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("case_id") != "IR-001":
        raise ValueError("the first offline replay only accepts IR-001")
    return payload


def _active_themes(
    case: Mapping[str, object],
    universe: Mapping[str, object],
) -> list[dict[str, object]]:
    wanted = set(_strings(case.get("active_theme_ids")))
    raw = universe.get("themes")
    themes = [dict(item) for item in raw if isinstance(item, Mapping) and item.get("theme_id") in wanted] if isinstance(raw, list) else []
    if len(themes) != len(wanted):
        raise ValueError("IR-001 active themes are incomplete in intraday_universe.json")
    return themes


def _case_symbols(
    case: Mapping[str, object],
    themes: Iterable[Mapping[str, object]],
    benchmark: str,
) -> tuple[str, ...]:
    symbols = [benchmark]
    holdings = case.get("holdings")
    if isinstance(holdings, list):
        symbols.extend(str(item.get("symbol")) for item in holdings if isinstance(item, Mapping))
    for theme in themes:
        symbols.append(str(theme.get("representative_etf")))
        raw = theme.get("representative_symbols")
        if isinstance(raw, list):
            symbols.extend(str(item) for item in raw)
    return tuple(dict.fromkeys(item.upper() for item in symbols if item))


def _strings(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
