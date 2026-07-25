"""A-share intraday market pulse workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from html import escape
import json
from pathlib import Path

from stock_assist.branding import PRODUCT_NAME
from stock_assist.data_sources.a_share_market import (
    FuturesBasisObservation,
    IntradaySnapshot,
    fetch_amazingdata_snapshots,
    fetch_amazingdata_futures_basis,
    fetch_intraday_snapshot,
    fetch_iwencai_futures_basis,
)
from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.paths import CONFIG_DIR, DATA_DIR
from stock_assist.report_payload import create_report_payload
from stock_assist.reports import bullet
from stock_assist.state_team_watch import build_state_team_etf_proxy


DEFAULT_CONFIG_PATH = CONFIG_DIR / "a_share_pulse.json"
SOURCE_AUDIT_PATH = DATA_DIR / "market_pulse_sources.jsonl"
DEFAULT_INDEX_WATCH = [
    {"code": "000001.SH", "secid": "1.000001", "label": "上证指数", "category": "broad"},
    {"code": "399001.SZ", "secid": "0.399001", "label": "深证成指", "category": "broad"},
    {"code": "399006.SZ", "secid": "0.399006", "label": "创业板指", "category": "growth"},
    {"code": "000300.SH", "secid": "1.000300", "label": "沪深300", "category": "core"},
    {"code": "000905.SH", "secid": "1.000905", "label": "中证500", "category": "mid"},
    {"code": "000852.SH", "secid": "1.000852", "label": "中证1000", "category": "small"},
    {"code": "000688.SH", "secid": "1.000688", "label": "科创50", "category": "growth"},
]
DEFAULT_ETF_WATCH = [
    {"code": "510300.SH", "secid": "1.510300", "label": "沪深300ETF", "category": "core_etf"},
    {"code": "510050.SH", "secid": "1.510050", "label": "上证50ETF", "category": "core_etf"},
    {"code": "510500.SH", "secid": "1.510500", "label": "中证500ETF", "category": "broad_etf"},
    {"code": "588000.SH", "secid": "1.588000", "label": "科创50ETF", "category": "growth_etf"},
    {"code": "159915.SZ", "secid": "0.159915", "label": "创业板ETF", "category": "growth_etf"},
]


@dataclass(frozen=True)
class PulseAnalysis:
    verdict: str
    tone: str
    score: float
    action_bias: str
    strongest: str
    weakest: str
    basis_verdict: str
    basis_tone: str
    basis_action: str


def build_market_pulse_report(config_path: Path | None = None) -> tuple[str, str]:
    _, markdown, html = build_market_pulse_bundle(config_path)
    return markdown, html


def build_market_pulse_bundle(config_path: Path | None = None) -> tuple[dict[str, object], str, str]:
    config, config_gaps = _load_config(config_path)
    index_items = _watch_items(config.get("index_watch", DEFAULT_INDEX_WATCH))
    etf_items = _watch_items(config.get("etf_watch", DEFAULT_ETF_WATCH))
    gaps = list(config_gaps)
    snapshots, source_gaps = _fetch_with_priority(index_items + etf_items)
    gaps.extend(source_gaps)
    indexes = snapshots[: len(index_items)]
    etfs = snapshots[len(index_items) :]
    gaps.extend(_snapshot_gaps(indexes, "指数"))
    gaps.extend(_snapshot_gaps(etfs, "ETF"))
    futures_basis, basis_gaps = _fetch_futures_basis(config)
    gaps.extend(basis_gaps)
    state_team_proxy, state_team_gaps = _fetch_state_team_etf_proxy(config)
    gaps.extend(state_team_gaps)

    analysis = _analyze_pulse(indexes, etfs, futures_basis)
    _write_source_audit(
        analysis,
        indexes,
        etfs,
        futures_basis,
        state_team_proxy,
        gaps,
        config_path or DEFAULT_CONFIG_PATH,
    )
    payload = _build_payload(
        analysis,
        indexes,
        etfs,
        futures_basis,
        state_team_proxy,
        gaps,
        config,
        config_path or DEFAULT_CONFIG_PATH,
    )
    markdown = _render_markdown_from_payload(payload)
    html = _render_html_from_payload(payload)
    return payload, markdown, html


def _build_payload(
    analysis: PulseAnalysis,
    indexes: list[IntradaySnapshot],
    etfs: list[IntradaySnapshot],
    futures_basis: list[FuturesBasisObservation],
    state_team_proxy: dict[str, object],
    gaps: list[str],
    config: dict[str, object],
    config_path: Path,
) -> dict[str, object]:
    state_rows = _proxy_rows(state_team_proxy)
    data_gaps = gaps + _structural_gaps(
        has_futures_basis=bool(_valid_basis(futures_basis)),
        has_futures_positioning=any(item.open_interest is not None for item in futures_basis),
        has_state_team_proxy=bool(state_rows),
    )
    return create_report_payload(
        kind="market_pulse",
        workflow="market-pulse",
        title="A股当日市场脉冲",
        config=str(config_path),
        summary_cards=[
            {
                "id": "direction",
                "label": "Direction",
                "value": analysis.verdict,
                "tone": analysis.tone,
                "note": analysis.action_bias,
            },
            {
                "id": "score",
                "label": "Score",
                "value": f"{analysis.score:+.2f}",
                "tone": analysis.tone,
                "note": "指数 65% + ETF 20% + 基差校正",
            },
            {
                "id": "basis",
                "label": "Basis",
                "value": analysis.basis_verdict,
                "tone": analysis.basis_tone,
                "note": analysis.basis_action,
            },
            {
                "id": "structure",
                "label": "Structure",
                "value": analysis.strongest,
                "tone": "warn",
                "note": f"弱项：{analysis.weakest}",
            },
        ],
        analysis={
            "verdict": analysis.verdict,
            "tone": analysis.tone,
            "score": analysis.score,
            "action_bias": analysis.action_bias,
            "strongest": analysis.strongest,
            "weakest": analysis.weakest,
            "basis_verdict": analysis.basis_verdict,
            "basis_tone": analysis.basis_tone,
            "basis_action": analysis.basis_action,
        },
        components=[
            {"type": "summary_cards", "id": "summary", "items": "summary_cards"},
            {"type": "snapshot_grid", "id": "index_temperature", "title": "指数温度", "items": "indexes"},
            {"type": "snapshot_grid", "id": "etf_support", "title": "ETF护盘观察", "items": "etfs"},
            {"type": "data_table", "id": "state_team_etfs", "title": "国家队ETF份额代理", "items": "state_team_etfs"},
            {"type": "data_table", "id": "futures_basis", "title": "股指期货基差", "items": "futures_basis"},
            {"type": "action_table", "id": "basis_actions", "title": "基差操作建议", "items": "basis_actions"},
            {"type": "data_gaps", "id": "data_gaps", "title": "Data Gaps", "items": "data_gaps"},
        ],
        indexes=[_snapshot_payload(item) for item in indexes],
        etfs=[_snapshot_payload(item) for item in etfs],
        futures_basis=[_basis_payload(item) for item in futures_basis],
        state_team_etf_proxy=state_team_proxy.get("summary") if isinstance(state_team_proxy, dict) else {},
        state_team_etfs=state_rows,
        state_team_methodology=_proxy_list(state_team_proxy, "methodology"),
        basis_actions=[
            {"strategy": strategy, "action": action, "reason": reason}
            for strategy, action, reason in _basis_action_rows(analysis, futures_basis)
        ],
        futures_lines=_futures_lines(futures_basis, config),
        state_etf_lines=_state_etf_lines(etfs, state_team_proxy),
        next_steps=[
            "接入全市场上涨/下跌家数、涨停/跌停、成交额分布、行业涨跌幅，用于判断是指数拉升还是普涨。",
            "补充股指期货持仓量、多空席位和基差历史分位，区分短线反弹和趋势反转。",
            "在已接入的ETF总份额下界上，继续补充日内申赎、溢价率和盘中护盘时段。",
            "等2026年半年报披露完成后，核验2015年证金/汇金直接持股是否同步退出。",
        ],
        data_gaps=data_gaps,
        audit={
            "source_log": str(SOURCE_AUDIT_PATH),
            "source_visibility": "backend_log_only",
        },
    )


def _load_config(path: Path | None) -> tuple[dict[str, object], list[str]]:
    actual_path = path or DEFAULT_CONFIG_PATH
    if not actual_path.exists():
        return {}, [f"未找到市场脉冲配置：{actual_path}，已使用内置指数和ETF观察清单。"]
    try:
        payload = json.loads(actual_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"市场脉冲配置 JSON 解析失败：{actual_path} -> {exc}"]
    if not isinstance(payload, dict):
        return {}, [f"市场脉冲配置不是 JSON object：{actual_path}"]
    return payload, []


def _watch_items(items: object) -> list[dict[str, object]]:
    rows = items if isinstance(items, list) else []
    return [item for item in rows if isinstance(item, dict)]


def _fetch_with_priority(
    items: list[dict[str, object]],
    *,
    now: datetime | None = None,
    public_timeout: int = 4,
) -> tuple[list[IntradaySnapshot], list[str]]:
    gaps: list[str] = []
    if not items:
        return [], ["市场观察清单为空。"]
    if _is_a_share_live_session(now):
        try:
            client = AmazingDataClient()
            try:
                snapshots = fetch_amazingdata_snapshots(client, items)
            finally:
                client.logout()
            if snapshots and not all(item.error for item in snapshots):
                if any(item.error for item in snapshots):
                    gaps.append("Galaxy AmazingData 部分快照缺失；缺失项将显示为 data gap。")
                return snapshots, gaps
            gaps.append("Galaxy AmazingData 快照为空，已尝试公开东方财富分时兜底。")
        except Exception as exc:
            gaps.append(f"Galaxy AmazingData 实时快照不可用，已使用东方财富公开分时兜底：{exc}")
    else:
        gaps.append("当前不在A股连续交易时段，跳过Galaxy实时快照，使用东方财富最近分时收盘数据。")

    snapshots: list[IntradaySnapshot] = []
    for item in items:
        secid = str(item.get("secid") or "")
        if not secid:
            continue
        snapshots.append(
            fetch_intraday_snapshot(
                secid=secid,
                label=str(item.get("label") or secid),
                category=str(item.get("category") or "watch"),
                timeout=public_timeout,
            )
        )
    return snapshots, gaps


def _fetch_futures_basis(
    config: dict[str, object],
    *,
    now: datetime | None = None,
) -> tuple[list[FuturesBasisObservation], list[str]]:
    raw_watch = config.get("futures_basis_watch")
    watch = _watch_items(raw_watch) if isinstance(raw_watch, list) else None
    lookback_minutes = _positive_int(config.get("basis_lookback_minutes"), default=4)
    iwencai_timeout = _positive_int(config.get("iwencai_futures_timeout_seconds"), default=30)
    iwencai_max_age = _positive_int(config.get("iwencai_futures_max_age_days"), default=4)
    live_session = _is_a_share_live_session(now)
    raw_order = config.get("futures_basis_provider_order")
    provider_order = (
        [str(item).strip().lower() for item in raw_order if str(item).strip()]
        if isinstance(raw_order, list)
        else ["iwencai", "amazingdata"]
    )
    gaps: list[str] = []
    for provider in provider_order:
        if provider == "iwencai":
            try:
                rows, provider_gaps = fetch_iwencai_futures_basis(
                    watch,
                    now=now,
                    timeout=iwencai_timeout,
                    max_age_days=iwencai_max_age,
                    require_same_day=live_session,
                )
            except Exception as exc:
                gaps.append(f"同花顺问财股指期货基差不可用：{exc}")
                continue
            gaps.extend(provider_gaps)
            if rows:
                return rows, gaps
            gaps.append("同花顺问财未返回可计算的 IF/IH/IC/IM 基差行。")
            continue
        if provider != "amazingdata":
            gaps.append(f"未知股指期货基差数据源：{provider}")
            continue
        if not live_session:
            gaps.append("当前不在A股连续交易时段，跳过 AmazingData 实时股指期货查询。")
            continue
        client: AmazingDataClient | None = None
        try:
            client = AmazingDataClient()
            rows, provider_gaps = fetch_amazingdata_futures_basis(
                client,
                watch,
                lookback_minutes=lookback_minutes,
            )
            gaps.extend(provider_gaps)
            if rows:
                return rows, gaps
            gaps.append("AmazingData 未返回可计算的 IF/IH/IC/IM 基差行。")
        except Exception as exc:
            gaps.append(f"AmazingData 股指期货基差不可用：{exc}")
        finally:
            if client is not None:
                client.logout()
    return [], gaps or ["股指期货基差暂不可用：未配置有效数据源。"]


def _fetch_state_team_etf_proxy(
    config: dict[str, object],
    *,
    client_cls: type[AmazingDataClient] = AmazingDataClient,
) -> tuple[dict[str, object], list[str]]:
    raw_config = config.get("state_team_etf_proxy")
    proxy_config = raw_config if isinstance(raw_config, dict) else {}
    items = proxy_config.get("items")
    codes = [
        str(item.get("code") or "").upper()
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict) and item.get("code")
    ]
    if not codes:
        return {}, ["未配置国家队ETF份额代理产品。"]
    client: AmazingDataClient | None = None
    try:
        client = client_cls()
        history = client.get_fund_share(codes)
    except Exception as exc:
        return {}, [f"国家队ETF份额代理暂不可用：{exc}"]
    finally:
        if client is not None:
            client.logout()
    raw_history = history if isinstance(history, dict) else {}
    proxy = build_state_team_etf_proxy(raw_history, proxy_config)
    return proxy, [str(item) for item in _proxy_list(proxy, "data_gaps")]


def _is_a_share_live_session(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    return current.weekday() < 5 and time(9, 15) <= current.time() <= time(15, 30)


def _snapshot_gaps(items: list[IntradaySnapshot], label: str) -> list[str]:
    return [f"{label}/{item.label} 实时分时暂不可用：{item.error}" for item in items if item.error]


def _write_source_audit(
    analysis: PulseAnalysis,
    indexes: list[IntradaySnapshot],
    etfs: list[IntradaySnapshot],
    futures_basis: list[FuturesBasisObservation],
    state_team_proxy: dict[str, object],
    gaps: list[str],
    config_path: Path,
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "market-pulse",
        "product": PRODUCT_NAME,
        "config": str(config_path),
        "verdict": analysis.verdict,
        "score": analysis.score,
        "snapshots": [_snapshot_audit(item) for item in [*indexes, *etfs]],
        "futures_basis": [_basis_audit(item) for item in futures_basis],
        "state_team_etf_proxy": state_team_proxy.get("summary") if isinstance(state_team_proxy, dict) else {},
        "data_gaps": gaps,
    }
    with SOURCE_AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _snapshot_audit(item: IntradaySnapshot) -> dict[str, object]:
    return {
        "label": item.label,
        "code": item.code,
        "secid": item.secid,
        "category": item.category,
        "price": item.price,
        "pre_close": item.pre_close,
        "change_pct": item.change_pct,
        "high": item.high,
        "low": item.low,
        "amount": item.amount,
        "update_time": item.update_time,
        "source": item.source,
        "error": item.error,
    }


def _basis_audit(item: FuturesBasisObservation) -> dict[str, object]:
    return {
        "family": item.family,
        "contract": item.contract,
        "underlying_code": item.underlying_code,
        "underlying_label": item.underlying_label,
        "current_time": item.current_time,
        "previous_time": item.previous_time,
        "future_price": item.future_price,
        "spot_price": item.spot_price,
        "future_change": item.future_change,
        "spot_change": item.spot_change,
        "basis": item.basis,
        "previous_basis": item.previous_basis,
        "basis_change": item.basis_change,
        "basis_pct": item.basis_pct,
        "as_of_date": item.as_of_date,
        "volume": item.volume,
        "open_interest": item.open_interest,
        "open_interest_change": item.open_interest_change,
        "quote_kind": item.quote_kind,
        "source": item.source,
        "error": item.error,
    }


def _snapshot_payload(item: IntradaySnapshot) -> dict[str, object]:
    return {
        "label": item.label,
        "code": item.code,
        "category": item.category,
        "price": item.price,
        "change_pct": item.change_pct,
        "high": item.high,
        "low": item.low,
        "amount": item.amount,
        "update_time": item.update_time,
        "error": item.error,
    }


def _basis_payload(item: FuturesBasisObservation) -> dict[str, object]:
    return {
        "family": item.family,
        "contract": item.contract,
        "underlying_code": item.underlying_code,
        "underlying_label": item.underlying_label,
        "current_time": item.current_time,
        "previous_time": item.previous_time,
        "future_price": item.future_price,
        "spot_price": item.spot_price,
        "future_change": item.future_change,
        "spot_change": item.spot_change,
        "basis": item.basis,
        "previous_basis": item.previous_basis,
        "basis_change": item.basis_change,
        "basis_pct": item.basis_pct,
        "as_of_date": item.as_of_date,
        "volume": item.volume,
        "open_interest": item.open_interest,
        "open_interest_change": item.open_interest_change,
        "quote_kind": item.quote_kind,
        "error": item.error,
    }


def _analyze_pulse(
    indexes: list[IntradaySnapshot],
    etfs: list[IntradaySnapshot],
    futures_basis: list[FuturesBasisObservation],
) -> PulseAnalysis:
    valid_indexes = [item for item in indexes if item.change_pct is not None]
    valid_etfs = [item for item in etfs if item.change_pct is not None]
    valid_basis = [item for item in futures_basis if item.basis_change is not None]
    index_score = _average([item.change_pct for item in valid_indexes])
    etf_score = _average([item.change_pct for item in valid_etfs])
    basis_delta = _average([item.basis_change for item in valid_basis])
    basis_score = max(-0.35, min(0.35, (basis_delta or 0) / 20))
    score = (index_score or 0) * 0.65 + (etf_score or 0) * 0.20 + basis_score
    strongest = max(valid_indexes, key=lambda item: item.change_pct or -999, default=None)
    weakest = min(valid_indexes, key=lambda item: item.change_pct or 999, default=None)
    basis_verdict, basis_tone, basis_action = _basis_signal(valid_basis)

    if score >= 0.8:
        verdict = "风险偏好较强"
        tone = "ok"
        action_bias = "可以顺势观察强势方向，但避免盘中追高扩大仓位。"
    elif score >= 0.2:
        verdict = "震荡偏强"
        tone = "ok"
        action_bias = "持仓以确认趋势为主，新增仓位需要成交额和期指基差确认。"
    elif score <= -0.8:
        verdict = "风险偏好转弱"
        tone = "risk"
        action_bias = "先降风险暴露，弱势票优先复核风控线。"
    elif score <= -0.2:
        verdict = "震荡偏弱"
        tone = "warn"
        action_bias = "控制仓位，等待指数、ETF和期指信号重新同向。"
    else:
        verdict = "方向不清"
        tone = "warn"
        action_bias = "不因单一指数波动做大动作，等待广度和衍生品确认。"

    return PulseAnalysis(
        verdict=verdict,
        tone=tone,
        score=score,
        action_bias=action_bias,
        strongest=strongest.label if strongest else "NA",
        weakest=weakest.label if weakest else "NA",
        basis_verdict=basis_verdict,
        basis_tone=basis_tone,
        basis_action=basis_action,
    )


def _render_markdown(
    analysis: PulseAnalysis,
    indexes: list[IntradaySnapshot],
    etfs: list[IntradaySnapshot],
    futures_basis: list[FuturesBasisObservation],
    gaps: list[str],
    config: dict[str, object],
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return "\n".join(
        [
            "# A股当日市场脉冲",
            "",
            "## 结论卡片",
            bullet(
                [
                    f"方向判断：{analysis.verdict}（score={analysis.score:+.2f}）",
                    f"交易含义：{analysis.action_bias}",
                    f"期指基差：{analysis.basis_verdict}；{analysis.basis_action}",
                    f"强弱结构：最强 {analysis.strongest}；最弱 {analysis.weakest}",
                    f"生成时间：{generated_at}",
                ]
            ),
            "",
            "## 指数温度",
            bullet([_snapshot_line(item) for item in indexes]),
            "",
            "## ETF护盘观察",
            bullet([_snapshot_line(item, include_amount=True) for item in etfs]),
            "",
            "## 股指期货与基差",
            bullet(_futures_lines(futures_basis, config)),
            "",
            "## 基差操作建议",
            bullet(_basis_action_lines(analysis, futures_basis)),
            "",
            "## 汇金/国家队ETF观察",
            bullet(_state_etf_lines(etfs)),
            "",
            "## 行业标准下一步",
            bullet(
                [
                    "接入沪深300/上证50/中证500/中证1000股指期货实时价格，计算 IF/IH/IC/IM 当月基差和年化基差。",
                    "接入全市场上涨家数、涨停/跌停、成交额分布、行业涨跌幅，用于判断是指数拉升还是普涨。",
                    "为中央汇金/国家队ETF建立代理指标：核心宽基ETF成交额突增、溢价率、申赎/份额变化和盘中护盘时段。",
                ]
            ),
            "",
            "## 数据缺口",
            bullet(
                gaps
                + _structural_gaps(
                    has_futures_basis=bool(_valid_basis(futures_basis)),
                    has_futures_positioning=any(item.open_interest is not None for item in futures_basis),
                )
            ),
        ]
    )


def _render_markdown_from_payload(payload: dict[str, object]) -> str:
    cards = _cards_by_id(payload)
    generated_at = str(payload.get("generated_at") or "")
    return "\n".join(
        [
            f"# {payload.get('title') or 'A股当日市场脉冲'}",
            "",
            "## 结论卡片",
            bullet(
                [
                    f"方向判断：{_card_value(cards, 'direction')}（score={_card_value(cards, 'score')}）",
                    f"交易含义：{_card_note(cards, 'direction')}",
                    f"期指基差：{_card_value(cards, 'basis')}；{_card_note(cards, 'basis')}",
                    f"强弱结构：最强 {_card_value(cards, 'structure')}；{_card_note(cards, 'structure')}",
                    f"生成时间：{generated_at}",
                ]
            ),
            "",
            "## 指数温度",
            bullet([_snapshot_line_from_payload(item) for item in _payload_list(payload, "indexes")]),
            "",
            "## ETF护盘观察",
            bullet([_snapshot_line_from_payload(item, include_amount=True) for item in _payload_list(payload, "etfs")]),
            "",
            "## 股指期货与基差",
            bullet([str(item) for item in _payload_list(payload, "futures_lines")]),
            "",
            "## 基差操作建议",
            bullet([_basis_action_line_from_payload(item) for item in _payload_list(payload, "basis_actions")]),
            "",
            "## 汇金/国家队ETF观察",
            _state_team_markdown_table(_payload_list(payload, "state_team_etfs")),
            "",
            bullet([str(item) for item in _payload_list(payload, "state_etf_lines")]),
            "",
            "### 口径边界",
            bullet([str(item) for item in _payload_list(payload, "state_team_methodology")]),
            "",
            "## 行业标准下一步",
            bullet([str(item) for item in _payload_list(payload, "next_steps")]),
            "",
            "## 数据缺口",
            bullet([str(item) for item in _payload_list(payload, "data_gaps")]),
        ]
    )


def _render_html_from_payload(payload: dict[str, object]) -> str:
    generated_at = str(payload.get("generated_at") or "")
    summary_cards = "".join(_summary_card_html(item) for item in _payload_list(payload, "summary_cards"))
    index_cards = "".join(_snapshot_card_from_payload(item) for item in _payload_list(payload, "indexes"))
    etf_cards = "".join(_snapshot_card_from_payload(item, include_amount=True) for item in _payload_list(payload, "etfs"))
    basis_rows = _basis_table_html_from_payload(_payload_list(payload, "futures_basis"))
    basis_actions = "".join(_basis_action_row_html(item) for item in _payload_list(payload, "basis_actions"))
    state_rows = _state_team_table_html(_payload_list(payload, "state_team_etfs"))
    futures_items = "".join(f"<li>{escape(str(item))}</li>" for item in _payload_list(payload, "futures_lines"))
    state_items = "".join(f"<li>{escape(str(item))}</li>" for item in _payload_list(payload, "state_etf_lines"))
    state_methodology = "".join(
        f"<li>{escape(str(item))}</li>" for item in _payload_list(payload, "state_team_methodology")
    )
    gap_items = "".join(f"<li>{escape(str(item))}</li>" for item in _payload_list(payload, "data_gaps"))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(str(payload.get("title") or "A股当日市场脉冲"))}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080b0f;
      --panel: #121820;
      --ink: #eef4f1;
      --muted: #91a29e;
      --line: rgba(255,255,255,0.08);
      --ok: #58d68d;
      --warn: #f7bd61;
      --risk: #ff6b7f;
      --accent: #5ee0a0;
      --blue: #74a9ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #080b0f 0%, #0d1218 46%, #080b0f 100%);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    }}
    main {{ width: min(1280px, calc(100% - 32px)); margin: 0 auto; padding: 26px 0 48px; }}
    .topbar {{
      display: flex; justify-content: space-between; align-items: center; min-height: 52px;
      padding: 0 22px; border-bottom: 1px solid var(--line); background: rgba(8, 11, 15, 0.86);
      position: sticky; top: 0; z-index: 5; backdrop-filter: blur(14px);
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; font-weight: 800; }}
    .mark {{
      display: grid; place-items: center; width: 28px; height: 28px; border-radius: 7px;
      background: linear-gradient(135deg, var(--accent), var(--blue)); color: #06100d;
    }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .hero, .card, .panel {{
      border: 1px solid var(--line); border-radius: 8px;
      background: linear-gradient(180deg, rgba(23,31,40,0.96), rgba(12,17,23,0.96));
      box-shadow: 0 18px 48px rgba(0,0,0,0.22);
    }}
    .hero {{ padding: 22px; margin-bottom: 14px; }}
    .eyebrow {{ color: var(--accent); font-size: 12px; font-weight: 900; letter-spacing: 0; }}
    h1 {{ margin: 8px 0 0; font-size: 34px; line-height: 1.2; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; letter-spacing: 0; }}
    .hero-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }}
    .card {{ padding: 16px; min-height: 128px; }}
    .card.primary {{ border-color: rgba(94,224,160,0.30); }}
    .label {{ color: var(--muted); font-size: 12px; font-weight: 800; }}
    .value {{ margin-top: 8px; font-size: 26px; font-weight: 900; line-height: 1.2; }}
    .note {{ margin-top: 8px; color: #c6d2cf; font-size: 13px; line-height: 1.45; }}
    .ok {{ color: var(--ok); }}
    .warn {{ color: var(--warn); }}
    .risk {{ color: var(--risk); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin-bottom: 14px; }}
    .snapshot-name {{ display: flex; justify-content: space-between; gap: 8px; font-size: 14px; font-weight: 900; }}
    .snapshot-price {{ margin-top: 10px; font-size: 22px; font-weight: 900; }}
    .snapshot-meta {{ margin-top: 6px; color: var(--muted); font-size: 12px; line-height: 1.45; }}
    .bar {{ height: 7px; margin-top: 12px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow: hidden; }}
    .fill {{ height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent), var(--blue)); }}
    .fill.risk {{ background: linear-gradient(90deg, var(--risk), var(--warn)); }}
    .panel {{ padding: 18px; margin-bottom: 14px; }}
    .panel-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .table-wrap {{ width: 100%; overflow-x: auto; margin-bottom: 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 12px; border: 1px solid var(--line); text-align: left; white-space: nowrap; }}
    th {{ color: var(--muted); background: rgba(255,255,255,0.04); font-weight: 900; }}
    .basis-table td:nth-child(4), .basis-table td:nth-child(5) {{ font-weight: 900; }}
    .action-table {{ margin-top: 10px; }}
    .action-table td {{ white-space: normal; line-height: 1.45; }}
    ul {{ margin: 0; padding-left: 18px; color: #c9d6d3; font-size: 13px; line-height: 1.55; }}
    li {{ margin: 6px 0; }}
    @media (max-width: 760px) {{
      main {{ width: min(100% - 20px, 1280px); padding-top: 16px; }}
      .topbar {{ padding: 0 14px; }}
      .hero-grid, .panel-grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 25px; }}
      .value {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand"><span class="mark">IR</span><span>{escape(PRODUCT_NAME)}</span></div>
    <div class="meta">{escape(generated_at)}</div>
  </header>
  <main>
    <section class="hero">
      <div class="eyebrow">A-SHARE LIVE PULSE</div>
      <h1>{escape(str(payload.get("title") or "A股当日市场脉冲"))}</h1>
    </section>
    <section class="hero-grid">{summary_cards}</section>
    <section class="panel"><h2>指数温度</h2><div class="grid">{index_cards}</div></section>
    <section class="panel"><h2>ETF护盘观察</h2><div class="grid">{etf_cards}</div></section>
    <section class="panel">
      <h2>国家队ETF份额代理（可证明的退出下界）</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>产品</th><th>当前份额</th><th>近5次</th><th>近20次</th><th>披露持有</th><th>最低退出</th><th>最低退出率</th><th>较2023-03</th><th>较2023-08</th><th>较2023-10</th></tr></thead>
          <tbody>{state_rows}</tbody>
        </table>
      </div>
      <ul>{state_items}</ul>
      <h2 style="margin-top:16px">口径边界</h2><ul>{state_methodology}</ul>
    </section>
    <section class="panel">
      <h2>股指期货基差</h2>
      <div class="table-wrap">
        <table class="basis-table">
          <thead><tr><th>品种</th><th>现货</th><th>期指</th><th>基差</th><th>4分钟变化</th></tr></thead>
          <tbody>{basis_rows}</tbody>
        </table>
      </div>
      <table class="action-table">
        <thead><tr><th>策略</th><th>操作</th><th>理由</th></tr></thead>
        <tbody>{basis_actions}</tbody>
      </table>
    </section>
    <section class="panel-grid">
      <article class="panel"><h2>股指期货与基差</h2><ul>{futures_items}</ul></article>
      <article class="panel"><h2>国家队ETF后续核验</h2><ul><li>补充ETF日内申赎、溢价率与盘中护盘时段。</li><li>半年报披露完成后核验2015年直接持股。</li></ul></article>
      <article class="panel"><h2>Data Gaps</h2><ul>{gap_items}</ul></article>
    </section>
  </main>
</body>
</html>
"""


def _payload_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _proxy_list(proxy: dict[str, object], key: str) -> list[object]:
    value = proxy.get(key) if isinstance(proxy, dict) else None
    return value if isinstance(value, list) else []


def _proxy_rows(proxy: dict[str, object]) -> list[object]:
    return _proxy_list(proxy, "rows")


def _state_team_markdown_table(items: list[object]) -> str:
    if not items:
        return "暂无可用份额历史。"
    lines = [
        "| 产品 | 当前份额 | 近5次 | 近20次 | 披露持有 | 最低退出 | 最低退出率 | 较2023-03 | 较2023-08 | 较2023-10 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| {label} | {current} | {five} | {twenty} | {disclosed} | {exited} | {ratio} | {march} | {august} | {october} |".format(
                label=_markdown_source_label(item),
                current=_yi(item.get("current_yi_shares")),
                five=_recent_change_pct(item, "five_observations"),
                twenty=_recent_change_pct(item, "twenty_observations"),
                disclosed=_yi(item.get("disclosed_state_yi_shares")),
                exited=_yi(item.get("minimum_exited_yi_shares")),
                ratio=_ratio(item.get("minimum_exit_ratio")),
                march=_baseline_pct(item, "pre_buildup"),
                august=_baseline_pct(item, "pre_first_announcement"),
                october=_baseline_pct(item, "pre_rescue_acceleration"),
            )
        )
    return "\n".join(lines)


def _state_team_table_html(items: list[object]) -> str:
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text_label = escape(str(item.get("label") or item.get("code") or "NA"))
        source_url = str(item.get("source_url") or "")
        linked_label = (
            f'<a href="{escape(source_url, quote=True)}" target="_blank" rel="noreferrer">{text_label}</a>'
            if source_url.startswith(("https://", "http://"))
            else text_label
        )
        label = f"{linked_label}<br><span class=\"meta\">{escape(str(item.get('current_date') or ''))}</span>"
        rows.append(
            "<tr>"
            f"<td>{label}</td>"
            f"<td>{escape(_yi(item.get('current_yi_shares')))}</td>"
            f"<td>{escape(_recent_change_pct(item, 'five_observations'))}</td>"
            f"<td>{escape(_recent_change_pct(item, 'twenty_observations'))}</td>"
            f"<td>{escape(_yi(item.get('disclosed_state_yi_shares')))}</td>"
            f"<td>{escape(_yi(item.get('minimum_exited_yi_shares')))}</td>"
            f"<td>{escape(_ratio(item.get('minimum_exit_ratio')))}</td>"
            f"<td>{escape(_baseline_pct(item, 'pre_buildup'))}</td>"
            f"<td>{escape(_baseline_pct(item, 'pre_first_announcement'))}</td>"
            f"<td>{escape(_baseline_pct(item, 'pre_rescue_acceleration'))}</td>"
            "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="10">暂无可用份额历史</td></tr>'


def _baseline_pct(item: dict[str, object], key: str) -> str:
    baselines = item.get("baselines")
    baseline = baselines.get(key) if isinstance(baselines, dict) else None
    value = baseline.get("current_change_pct") if isinstance(baseline, dict) else None
    return _pct_value(value)


def _recent_change_pct(item: dict[str, object], key: str) -> str:
    changes = item.get("recent_changes")
    change = changes.get(key) if isinstance(changes, dict) else None
    value = change.get("change_pct") if isinstance(change, dict) else None
    return _pct_value(value)


def _markdown_source_label(item: dict[str, object]) -> str:
    label = str(item.get("label") or item.get("code") or "NA")
    source_url = str(item.get("source_url") or "")
    return f"[{label}]({source_url})" if source_url.startswith(("https://", "http://")) else label


def _yi(value: object) -> str:
    return f"{float(value):.2f}亿份" if isinstance(value, (int, float)) else "NA"


def _ratio(value: object) -> str:
    return f"{float(value) * 100:.1f}%" if isinstance(value, (int, float)) else "NA"


def _pct_value(value: object) -> str:
    return f"{float(value):+.1f}%" if isinstance(value, (int, float)) else "NA"


def _cards_by_id(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    cards: dict[str, dict[str, object]] = {}
    for item in _payload_list(payload, "summary_cards"):
        if isinstance(item, dict) and item.get("id"):
            cards[str(item["id"])] = item
    return cards


def _card_value(cards: dict[str, dict[str, object]], card_id: str) -> str:
    return str(cards.get(card_id, {}).get("value") or "NA")


def _card_note(cards: dict[str, dict[str, object]], card_id: str) -> str:
    return str(cards.get(card_id, {}).get("note") or "")


def _summary_card_html(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    tone = str(item.get("tone") or "warn")
    primary = " primary" if item.get("id") == "direction" else ""
    return f"""
      <article class="card{primary}">
        <div class="label">{escape(str(item.get("label") or ""))}</div>
        <div class="value {escape(tone)}">{escape(str(item.get("value") or "NA"))}</div>
        <div class="note">{escape(str(item.get("note") or ""))}</div>
      </article>
"""


def _snapshot_line_from_payload(item: object, include_amount: bool = False) -> str:
    if not isinstance(item, dict):
        return "数据缺口"
    if item.get("error"):
        return f"{item.get('label') or 'NA'}：数据缺口，{item.get('error')}"
    amount = f"，成交额 {_amount_yi(_float_payload(item, 'amount'))}" if include_amount else ""
    return (
        f"{item.get('label') or 'NA'}（{item.get('code') or 'NA'}）：{_num(_float_payload(item, 'price'))}"
        f"，涨跌幅 {_pct(_float_payload(item, 'change_pct'))}"
        f"，区间 {_num(_float_payload(item, 'low'))}-{_num(_float_payload(item, 'high'))}{amount}"
        f"，更新时间 {item.get('update_time') or ''}"
    )


def _snapshot_card_from_payload(item: object, include_amount: bool = False) -> str:
    if not isinstance(item, dict):
        return ""
    if item.get("error"):
        return f"""
        <article class="card">
          <div class="snapshot-name"><span>{escape(str(item.get("label") or "NA"))}</span><span class="warn">GAP</span></div>
          <div class="snapshot-meta">{escape(str(item.get("error") or ""))}</div>
        </article>
"""
    change_pct = _float_payload(item, "change_pct")
    tone = _tone(change_pct)
    width = min(100, max(4, abs(change_pct or 0) * 24))
    amount = f"<div class=\"snapshot-meta\">成交额 {_amount_yi(_float_payload(item, 'amount'))}</div>" if include_amount else ""
    return f"""
        <article class="card">
          <div class="snapshot-name"><span>{escape(str(item.get("label") or "NA"))}</span><span class="{tone}">{escape(_pct(change_pct))}</span></div>
          <div class="snapshot-price">{escape(_num(_float_payload(item, "price")))}</div>
          <div class="snapshot-meta">区间 {escape(_num(_float_payload(item, "low")))}-{escape(_num(_float_payload(item, "high")))} · {escape(str(item.get("update_time") or ""))}</div>
          {amount}
          <div class="bar"><div class="fill {tone}" style="width:{width:.1f}%"></div></div>
        </article>
"""


def _basis_action_line_from_payload(item: object) -> str:
    if not isinstance(item, dict):
        return "数据缺口"
    return f"{item.get('strategy') or 'NA'}：{item.get('action') or 'NA'}；{item.get('reason') or ''}"


def _basis_action_row_html(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    return (
        "<tr>"
        f"<td>{escape(str(item.get('strategy') or 'NA'))}</td>"
        f"<td>{escape(str(item.get('action') or 'NA'))}</td>"
        f"<td>{escape(str(item.get('reason') or ''))}</td>"
        "</tr>"
    )


def _basis_table_html_from_payload(items: list[object]) -> str:
    if not items:
        return '<tr><td colspan="5">期指基差数据缺口</td></tr>'
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("error"):
            rows.append(f"<tr><td>{escape(str(item.get('contract') or 'NA'))}</td><td colspan=\"4\">{escape(str(item.get('error') or ''))}</td></tr>")
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('contract') or 'NA'))}</td>"
            f"<td>{escape(str(item.get('underlying_label') or 'NA'))} {_num(_float_payload(item, 'spot_price'))}</td>"
            f"<td>{_num(_float_payload(item, 'future_price'))}<br><small>量 {_quantity(_float_payload(item, 'volume'))} / 持仓 {_quantity(_float_payload(item, 'open_interest'))} / 日增 {_signed_quantity(_float_payload(item, 'open_interest_change'))}</small></td>"
            f"<td>{_signed(_float_payload(item, 'basis'))}<br><small>{_pct(_float_payload(item, 'basis_pct'))}</small></td>"
            f"<td>{escape(_basis_time_text_from_payload(item))}</td>"
            "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="5">期指基差数据缺口</td></tr>'


def _float_payload(item: dict[str, object], key: str) -> float | None:
    value = item.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _basis_time_text_from_payload(item: dict[str, object]) -> str:
    previous_time = str(item.get("previous_time") or "")
    current_time = str(item.get("current_time") or item.get("as_of_date") or "")
    basis_change = _float_payload(item, "basis_change")
    if previous_time and basis_change is not None:
        return f"{previous_time}->{current_time} 变化 {_signed(basis_change)}"
    return f"{current_time} 收盘快照；4分钟变化未提供，仅作诊断"


def _render_html(
    analysis: PulseAnalysis,
    indexes: list[IntradaySnapshot],
    etfs: list[IntradaySnapshot],
    futures_basis: list[FuturesBasisObservation],
    gaps: list[str],
    config: dict[str, object],
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    index_cards = "".join(_snapshot_card(item) for item in indexes)
    etf_cards = "".join(_snapshot_card(item, include_amount=True) for item in etfs)
    valid_futures_basis = _valid_basis(futures_basis)
    gap_items = "".join(
        f"<li>{escape(item)}</li>"
        for item in gaps
        + _structural_gaps(
            has_futures_basis=bool(valid_futures_basis),
            has_futures_positioning=any(item.open_interest is not None for item in futures_basis),
        )
    )
    futures_items = "".join(f"<li>{escape(item)}</li>" for item in _futures_lines(futures_basis, config))
    basis_rows = _basis_table_html(futures_basis)
    basis_actions = "".join(
        f"<tr><td>{escape(item[0])}</td><td>{escape(item[1])}</td><td>{escape(item[2])}</td></tr>"
        for item in _basis_action_rows(analysis, futures_basis)
    )
    state_items = "".join(f"<li>{escape(item)}</li>" for item in _state_etf_lines(etfs))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A股当日市场脉冲</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080b0f;
      --panel: #121820;
      --panel-2: #171f28;
      --ink: #eef4f1;
      --muted: #91a29e;
      --line: rgba(255,255,255,0.08);
      --ok: #58d68d;
      --warn: #f7bd61;
      --risk: #ff6b7f;
      --accent: #5ee0a0;
      --blue: #74a9ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #080b0f 0%, #0d1218 46%, #080b0f 100%);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    }}
    main {{
      width: min(1280px, calc(100% - 32px));
      margin: 0 auto;
      padding: 26px 0 48px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      min-height: 52px;
      padding: 0 22px;
      border-bottom: 1px solid var(--line);
      background: rgba(8, 11, 15, 0.86);
      position: sticky;
      top: 0;
      z-index: 5;
      backdrop-filter: blur(14px);
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; font-weight: 800; }}
    .mark {{
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 7px;
      background: linear-gradient(135deg, var(--accent), var(--blue));
      color: #06100d;
    }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .hero, .card, .panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(180deg, rgba(23,31,40,0.96), rgba(12,17,23,0.96));
      box-shadow: 0 18px 48px rgba(0,0,0,0.22);
    }}
    .hero {{ padding: 22px; margin-bottom: 14px; }}
    .eyebrow {{ color: var(--accent); font-size: 12px; font-weight: 900; letter-spacing: 0; }}
    h1 {{ margin: 8px 0 0; font-size: 34px; line-height: 1.2; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; letter-spacing: 0; }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) repeat(3, minmax(160px, 0.5fr));
      gap: 12px;
      margin-bottom: 14px;
    }}
    .card {{ padding: 16px; min-height: 128px; }}
    .card.primary {{ border-color: rgba(94,224,160,0.30); }}
    .label {{ color: var(--muted); font-size: 12px; font-weight: 800; }}
    .value {{ margin-top: 8px; font-size: 26px; font-weight: 900; line-height: 1.2; }}
    .note {{ margin-top: 8px; color: #c6d2cf; font-size: 13px; line-height: 1.45; }}
    .ok {{ color: var(--ok); }}
    .warn {{ color: var(--warn); }}
    .risk {{ color: var(--risk); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }}
    .snapshot-name {{ display: flex; justify-content: space-between; gap: 8px; font-size: 14px; font-weight: 900; }}
    .snapshot-price {{ margin-top: 10px; font-size: 22px; font-weight: 900; }}
    .snapshot-meta {{ margin-top: 6px; color: var(--muted); font-size: 12px; line-height: 1.45; }}
    .bar {{ height: 7px; margin-top: 12px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow: hidden; }}
    .fill {{ height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent), var(--blue)); }}
    .fill.risk {{ background: linear-gradient(90deg, var(--risk), var(--warn)); }}
    .panel {{ padding: 18px; margin-bottom: 14px; }}
    .panel-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .table-wrap {{ width: 100%; overflow-x: auto; margin-bottom: 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 12px; border: 1px solid var(--line); text-align: left; white-space: nowrap; }}
    th {{ color: var(--muted); background: rgba(255,255,255,0.04); font-weight: 900; }}
    .basis-table td:nth-child(4), .basis-table td:nth-child(5) {{ font-weight: 900; }}
    .action-table {{ margin-top: 10px; }}
    .action-table td {{ white-space: normal; line-height: 1.45; }}
    ul {{ margin: 0; padding-left: 18px; color: #c9d6d3; font-size: 13px; line-height: 1.55; }}
    li {{ margin: 6px 0; }}
    @media (max-width: 760px) {{
      main {{ width: min(100% - 20px, 1280px); padding-top: 16px; }}
      .topbar {{ padding: 0 14px; }}
      .hero-grid, .panel-grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 25px; }}
      .value {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand"><span class="mark">IR</span><span>{escape(PRODUCT_NAME)}</span></div>
    <div class="meta">{escape(generated_at)}</div>
  </header>
  <main>
    <section class="hero">
      <div class="eyebrow">A-SHARE LIVE PULSE</div>
      <h1>A股当日市场脉冲</h1>
    </section>
    <section class="hero-grid">
      <article class="card primary">
        <div class="label">Direction</div>
        <div class="value {analysis.tone}">{escape(analysis.verdict)}</div>
        <div class="note">{escape(analysis.action_bias)}</div>
      </article>
      <article class="card">
        <div class="label">Score</div>
        <div class="value {analysis.tone}">{analysis.score:+.2f}</div>
        <div class="note">指数 65% + ETF 20% + 基差校正</div>
      </article>
      <article class="card">
        <div class="label">Basis</div>
        <div class="value {analysis.basis_tone}">{escape(analysis.basis_verdict)}</div>
        <div class="note">{escape(analysis.basis_action)}</div>
      </article>
      <article class="card">
        <div class="label">Structure</div>
        <div class="value">{escape(analysis.strongest)}</div>
        <div class="note">弱项：{escape(analysis.weakest)}</div>
      </article>
    </section>
    <section class="panel">
      <h2>指数温度</h2>
      <div class="grid">{index_cards}</div>
    </section>
    <section class="panel">
      <h2>ETF护盘观察</h2>
      <div class="grid">{etf_cards}</div>
    </section>
    <section class="panel">
      <h2>股指期货基差</h2>
      <div class="table-wrap">
        <table class="basis-table">
          <thead><tr><th>品种</th><th>现货</th><th>期指</th><th>基差</th><th>4分钟变化</th></tr></thead>
          <tbody>{basis_rows}</tbody>
        </table>
      </div>
      <table class="action-table">
        <thead><tr><th>策略</th><th>操作</th><th>理由</th></tr></thead>
        <tbody>{basis_actions}</tbody>
      </table>
    </section>
    <section class="panel-grid">
      <article class="panel">
        <h2>股指期货与基差</h2>
        <ul>{futures_items}</ul>
      </article>
      <article class="panel">
        <h2>汇金/国家队ETF观察</h2>
        <ul>{state_items}</ul>
      </article>
      <article class="panel">
        <h2>Data Gaps</h2>
        <ul>{gap_items}</ul>
      </article>
    </section>
  </main>
</body>
</html>
"""


def _snapshot_line(item: IntradaySnapshot, include_amount: bool = False) -> str:
    if item.error:
        return f"{item.label}：数据缺口，{item.error}"
    amount = f"，成交额 {_amount_yi(item.amount)}" if include_amount else ""
    return (
        f"{item.label}（{item.code}）：{_num(item.price)}，涨跌幅 {_pct(item.change_pct)}"
        f"，区间 {_num(item.low)}-{_num(item.high)}{amount}，更新时间 {item.update_time}"
    )


def _snapshot_card(item: IntradaySnapshot, include_amount: bool = False) -> str:
    tone = _tone(item.change_pct)
    width = min(100, max(4, abs(item.change_pct or 0) * 24))
    amount = f"<div class=\"snapshot-meta\">成交额 {_amount_yi(item.amount)}</div>" if include_amount else ""
    if item.error:
        return f"""
        <article class="card">
          <div class="snapshot-name"><span>{escape(item.label)}</span><span class="warn">GAP</span></div>
          <div class="snapshot-meta">{escape(item.error)}</div>
        </article>
"""
    return f"""
        <article class="card">
          <div class="snapshot-name"><span>{escape(item.label)}</span><span class="{tone}">{escape(_pct(item.change_pct))}</span></div>
          <div class="snapshot-price">{escape(_num(item.price))}</div>
          <div class="snapshot-meta">区间 {escape(_num(item.low))}-{escape(_num(item.high))} · {escape(item.update_time)}</div>
          {amount}
          <div class="bar"><div class="fill {tone}" style="width:{width:.1f}%"></div></div>
        </article>
"""


def _futures_lines(futures_basis: list[FuturesBasisObservation], config: dict[str, object]) -> list[str]:
    valid = _valid_basis(futures_basis)
    if valid:
        return [_basis_summary_line(item) for item in valid]
    raw = config.get("futures_basis")
    if isinstance(raw, list) and raw:
        lines = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            contract = str(item.get("contract") or "未命名期指")
            basis = item.get("basis")
            status = str(item.get("status") or "manual")
            lines.append(f"{contract}：基差={basis if basis is not None else '待补'}，状态={status}")
        if lines:
            return lines
    return [
        "IF/IH/IC/IM 当月合约实时价格未接入，暂不能计算期指升贴水。",
        "产品口径：基差 = 股指期货价格 - 对应现货指数；正基差偏多，负基差偏谨慎。",
    ]


def _basis_summary_line(item: FuturesBasisObservation) -> str:
    positioning = (
        f"，成交量 {_quantity(item.volume)}，持仓 {_quantity(item.open_interest)}"
        f"，日增仓 {_signed_quantity(item.open_interest_change)}"
        if item.volume is not None or item.open_interest is not None
        else ""
    )
    return (
        f"{item.contract}/{item.underlying_label}：基差 {_signed(item.basis)}，"
        f"基差率 {_pct(item.basis_pct)}{positioning}，{_basis_time_text(item)}"
    )


def _basis_time_text(item: FuturesBasisObservation) -> str:
    if item.previous_time and item.basis_change is not None:
        return f"{item.previous_time}->{item.current_time} 变化 {_signed(item.basis_change)}"
    return f"{item.current_time or item.as_of_date} 收盘快照；4分钟变化未提供，仅作诊断"


def _quantity(value: float | None) -> str:
    return "NA" if value is None else f"{value:,.0f}"


def _signed_quantity(value: float | None) -> str:
    return "NA" if value is None else f"{value:+,.0f}"


def _basis_signal(items: list[FuturesBasisObservation]) -> tuple[str, str, str]:
    valid = _valid_basis(items)
    if not valid:
        return "待确认", "warn", "等期指快照补齐后再判断方向。"
    basis_delta = _average([item.basis_change for item in valid])
    avg_basis_pct = _average([item.basis_pct for item in valid])
    avg_future_change = _average([item.future_change for item in valid])
    avg_spot_change = _average([item.spot_change for item in valid])
    if (basis_delta or 0) >= 3 and (avg_future_change or 0) >= (avg_spot_change or 0):
        return "升水扩张", "ok", "期指强于现货，反弹确认度提高。"
    if (basis_delta or 0) <= -3:
        return "基差收敛", "risk", "期指跟涨不足，不追高，冲高先控风险。"
    if (avg_basis_pct or 0) < -1:
        return "贴水较深", "warn", "期指仍偏谨慎，等量能和基差共振。"
    return "小幅波动", "warn", "基差没有给出强方向，按指数强弱分层处理。"


def _basis_action_lines(analysis: PulseAnalysis, futures_basis: list[FuturesBasisObservation]) -> list[str]:
    return [f"{strategy}：{action}；{reason}" for strategy, action, reason in _basis_action_rows(analysis, futures_basis)]


def _basis_action_rows(
    analysis: PulseAnalysis,
    futures_basis: list[FuturesBasisObservation],
) -> list[tuple[str, str, str]]:
    valid = _valid_basis(futures_basis)
    basis_delta = _average([item.basis_change for item in valid])
    spot_change = _average([item.spot_change for item in valid])
    if not valid:
        return [
            ("不开新仓", "等待", "期指基差数据缺口未补齐"),
            ("已有仓位", "按风险线处理", "只用指数/ETF信号，不放大动作"),
            ("继续盯盘", "补数据", "确认 IF/IH/IC/IM 快照可用"),
        ]
    if all(item.basis_change is None for item in valid):
        return [
            ("不开激进仓", "只作盘后诊断", "收盘基差可用，但缺少4分钟期现变化，不能授权追涨杀跌"),
            ("已有仓位", "结合风险线", "贴水还受分红、资金成本和期限结构影响，不能单独判断方向"),
            ("下一交易时段", "等待实时确认", "观察指数、基差变化、成交量和持仓量是否共振"),
        ]
    if (basis_delta or 0) <= -3 and (spot_change or 0) > 0:
        return [
            ("不追多", "等待回踩确认", "指数反弹但基差收敛，期指跟涨不足"),
            ("冲高控仓", "减风险暴露", "短线反弹质量不够扎实"),
            ("关注量能", "等成交额配合", "缩量反弹容易回落"),
        ]
    if (basis_delta or 0) >= 3 and (spot_change or 0) >= 0:
        return [
            ("顺势观察", "小仓试错", "期指升水扩张，反弹确认度提高"),
            ("不盲目加速", "等回踩或放量", "4分钟反弹过快时容易震荡"),
            ("弱项回避", "避开落后风格", f"当前弱项是 {analysis.weakest}"),
        ]
    return [
        ("不开激进仓", "等下一次共振", "基差变化不够明确"),
        ("已有仓位", "跟随风险线", "指数与期指没有强一致性"),
        ("继续观察", "看 13:00 后变化", "午后量能和基差再定方向"),
    ]


def _basis_table_html(items: list[FuturesBasisObservation]) -> str:
    valid_or_gap = items or []
    if not valid_or_gap:
        return "<tr><td colspan=\"5\">期指基差数据缺口</td></tr>"
    rows = []
    for item in valid_or_gap:
        if item.error:
            rows.append(
                f"<tr><td>{escape(item.contract)}</td><td colspan=\"4\">{escape(item.error)}</td></tr>"
            )
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(item.contract)}</td>"
            f"<td>{escape(item.underlying_label)} {_num(item.spot_price)}</td>"
            f"<td>{_num(item.future_price)}<br><small>量 {_quantity(item.volume)} / 持仓 {_quantity(item.open_interest)} / 日增 {_signed_quantity(item.open_interest_change)}</small></td>"
            f"<td>{_signed(item.basis)}<br><small>{_pct(item.basis_pct)}</small></td>"
            f"<td>{escape(_basis_time_text(item))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _valid_basis(items: list[FuturesBasisObservation]) -> list[FuturesBasisObservation]:
    return [item for item in items if item.basis is not None and not item.error]


def _state_etf_lines(
    etfs: list[IntradaySnapshot],
    proxy: dict[str, object] | None = None,
) -> list[str]:
    summary = proxy.get("summary") if isinstance(proxy, dict) else None
    if isinstance(summary, dict) and summary.get("product_count"):
        lines = [
            f"{summary.get('state') or '待核验'}：4只沪深300ETF当前合计 {_yi(summary.get('current_yi_shares'))}，"
            f"相对2025年末披露汇金持有 {_yi(summary.get('disclosed_state_yi_shares'))}，"
            f"可证明最低退出 {_yi(summary.get('minimum_exited_yi_shares'))}（{_ratio(summary.get('minimum_exit_ratio'))}）。",
            f"最新份额日期 {summary.get('as_of') or 'NA'}；这是ETF份额退出下界，不是现金净卖出，也不能代表2015年证金直接持股。",
        ]
        baselines = summary.get("baselines")
        if isinstance(baselines, dict):
            lines.append(
                "当前合计份额相对2023-03/2023-08/2023-10分别为 "
                f"{_summary_baseline_pct(baselines, 'pre_buildup')} / "
                f"{_summary_baseline_pct(baselines, 'pre_first_announcement')} / "
                f"{_summary_baseline_pct(baselines, 'pre_rescue_acceleration')}。"
            )
        recent_changes = summary.get("recent_changes")
        if isinstance(recent_changes, dict):
            five = recent_changes.get("five_observations")
            twenty = recent_changes.get("twenty_observations")
            lines.append(
                f"短周期代理：{summary.get('change_signal') or '待核验'}；近5次/20次总份额变化 "
                f"{_change_pct(five)} / {_change_pct(twenty)}，"
                f"累计最低退出下界近20次收紧 {_change_tightening(twenty)}。"
            )
            lines.append("短周期收缩只说明ETF总份额下降并收紧累计退出下界，不能证明当期卖方就是国家队。")
        return lines
    valid = sorted(
        [item for item in etfs if item.amount is not None],
        key=lambda item: item.amount or 0,
        reverse=True,
    )
    lines = [
        "中央汇金/国家队实时买卖明细没有公开实时源，当前只能用核心宽基ETF成交额和异动作为代理观察。",
    ]
    for item in valid[:3]:
        lines.append(f"{item.label}：成交额 {_amount_yi(item.amount)}，涨跌幅 {_pct(item.change_pct)}。")
    return lines


def _summary_baseline_pct(baselines: dict[str, object], key: str) -> str:
    item = baselines.get(key)
    value = item.get("current_change_pct") if isinstance(item, dict) else None
    return _pct_value(value)


def _change_pct(item: object) -> str:
    value = item.get("change_pct") if isinstance(item, dict) else None
    return _pct_value(value)


def _change_tightening(item: object) -> str:
    value = item.get("lower_bound_tightening_yi_shares") if isinstance(item, dict) else None
    if not isinstance(value, (int, float)):
        return "NA"
    return f"{float(value):+.2f}亿份"


def _structural_gaps(
    has_futures_basis: bool = False,
    has_futures_positioning: bool = False,
    has_state_team_proxy: bool = False,
) -> list[str]:
    if has_futures_basis and has_futures_positioning:
        futures_gap = "已接入股指期货成交量/持仓量（部分合约有日增仓）；未接入多空席位和基差历史分位。"
    elif has_futures_basis:
        futures_gap = "未接入股指期货持仓量、多空席位和基差历史分位。"
    else:
        futures_gap = "未接入股指期货实时价格、持仓量、多空席位和基差历史分位。"
    state_gap = (
        "已接入ETF总份额历史和汇金披露持仓下界；未接入日内申赎、溢价率及2015年证金直接持股核验。"
        if has_state_team_proxy
        else "未接入ETF份额、申赎、溢价率和中央汇金持仓变化。"
    )
    return [
        "未接入全市场上涨/下跌家数、涨停/跌停、炸板率和行业涨跌幅。",
        futures_gap,
        state_gap,
    ]


def _average(values: list[float | None]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _tone(value: float | None) -> str:
    if value is None:
        return "warn"
    if value > 0:
        return "ok"
    if value < 0:
        return "risk"
    return "warn"


def _pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:+.2f}%"


def _num(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:,.2f}"


def _amount_yi(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value / 100000000:.1f}亿"


def _signed(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:+.2f}"


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
