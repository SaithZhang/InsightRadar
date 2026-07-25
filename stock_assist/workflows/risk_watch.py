"""Daily cross-market risk temperature and no-lookahead replay workflow."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
import json
from pathlib import Path

from stock_assist.branding import PRODUCT_NAME
from stock_assist.data_sources.a_share_klines import fetch_public_klines
from stock_assist.data_sources.global_markets import fetch_yahoo_history
from stock_assist.data_sources.iwencai_market import (
    fetch_a_share_anchor_records,
    fetch_a_share_crowding,
    fetch_ths_all_a,
)
from stock_assist.market_structure import build_anchor_structure
from stock_assist.macro_transmission import (
    VerifiedMacroEvent,
    calibrate_macro_transmission,
    evaluate_macro_transmission,
    replay_macro_transmission,
)
from stock_assist.paths import CONFIG_DIR, DATA_DIR
from stock_assist.report_payload import create_report_payload
from stock_assist.risk_watch import (
    DailyPoint,
    DailySeries,
    LEVEL_LABELS,
    PortfolioRiskProfile,
    RISK_BUDGETS,
    RiskSnapshot,
    replay_risk,
)


DEFAULT_CONFIG_PATH = CONFIG_DIR / "risk_watch.json"
DEFAULT_MACRO_CONFIG_PATH = CONFIG_DIR / "macro_transmission.json"
DEFAULT_PROFILE_PATH = DATA_DIR / "risk_watch_profile.json"
A_SHARE_TARGETS = {
    "shanghai": ("上证指数", "1.000001", "sh000001"),
    "chinext": ("创业板指", "0.399006", "sz399006"),
    "star50": ("科创50", "1.000688", "sh000688"),
    "csi1000": ("中证1000", "1.000852", "sh000852"),
}
GLOBAL_TARGETS = {
    "sp500": ("标普500", "^GSPC"),
    "qqq": ("QQQ", "QQQ"),
    "sox": ("费城半导体", "^SOX"),
    "kospi": ("韩国KOSPI", "^KS11"),
    "kosdaq": ("韩国KOSDAQ", "^KQ11"),
    "nikkei": ("日经225", "^N225"),
}


def build_risk_watch_bundle(
    config_path: Path | None = None,
    profile_path: Path | None = None,
    *,
    as_of: str | None = None,
    replay_start: str | None = None,
) -> tuple[dict[str, object], str, str]:
    config, gaps = _load_json(config_path or DEFAULT_CONFIG_PATH, optional=True)
    profile, profile_gaps = _load_profile(profile_path or DEFAULT_PROFILE_PATH)
    gaps.extend(profile_gaps)
    end = _parse_date(as_of) if as_of else date.today()
    history_days = _positive_int(config.get("history_days"), 360)
    start = _parse_date(replay_start) if replay_start else _default_replay_start(config, end)
    fetch_start = min(start - timedelta(days=120), end - timedelta(days=history_days))
    series, source_gaps = _fetch_series(fetch_start, end, history_days)
    gaps.extend(source_gaps)
    replay = replay_risk(series, profile, start=start, end=end)
    if not replay:
        raise RuntimeError(f"{start.isoformat()}至{end.isoformat()}没有可评分交易日")
    latest = replay[-1]
    macro_shadow = _load_macro_shadow(latest.day)
    crowding_snapshot: dict[str, object] | None = None
    try:
        snapshot, snapshot_source = fetch_a_share_crowding(latest.day)
        crowding_snapshot = {
            "date": snapshot.day.isoformat(),
            "source": snapshot_source,
            "total_amount": snapshot.total_amount,
            "top1_amount_share": snapshot.top1_amount_share,
            "top10_amount_share": snapshot.top10_amount_share,
            "top20_amount_share": snapshot.top20_amount_share,
            "top50_amount_share": snapshot.top50_amount_share,
            "top50_hhi_partial": snapshot.top50_hhi_partial,
            "top1_turnover_free_float": snapshot.top1_turnover_free_float,
            "top1_code": snapshot.top1_code,
            "top1_name": snapshot.top1_name,
            "universe_count": snapshot.universe_count,
            "scoring_status": "diagnostic_until_20_daily_snapshots",
        }
    except Exception as exc:
        gaps.append(f"A股成交集中度快照不可用：{exc}")
    anchor_structure: dict[str, object] | None = None
    anchor_config = config.get("anchor_structure")
    if isinstance(anchor_config, dict) and bool(anchor_config.get("enabled", False)):
        try:
            anchor_structure = _fetch_anchor_structure(anchor_config, latest)
        except Exception as exc:
            gaps.append(f"A股锚点宽度不可用：{exc}")
    latest.data_gaps.extend(gap for gap in gaps if gap not in latest.data_gaps)
    alerts = _alert_summary(replay, series.get("all_a"))
    event_alerts = _event_alert_summary(replay)
    actions = _conditional_actions(latest, profile)
    payload = create_report_payload(
        kind="risk_watch",
        workflow="risk-watch",
        title="每日市场与组合风险温度计",
        as_of=latest.day.isoformat(),
        config=str(config_path or DEFAULT_CONFIG_PATH),
        profile={
            "source": profile.source,
            "portfolio_effective_from": profile.portfolio_effective_from.isoformat() if profile.portfolio_effective_from else None,
            "behavior_effective_from": profile.behavior_effective_from.isoformat() if profile.behavior_effective_from else None,
            "total_exposure_pct": profile.total_exposure_pct,
            "holding_weights_pct": list(profile.holding_weights_pct),
            "high_beta_exposure_pct": profile.high_beta_exposure_pct,
            "manual_flags": {
                "fomo": profile.fomo_flag,
                "long_horizon_pricing": profile.long_horizon_pricing_flag,
                "retail_euphoria": profile.retail_euphoria_flag,
            },
        },
        latest=latest.to_dict(),
        crowding_snapshot=crowding_snapshot,
        anchor_structure=anchor_structure,
        macro_transmission=macro_shadow,
        alerts=alerts,
        event_alerts=event_alerts,
        actions=actions,
        replay={
            "start": start.isoformat(),
            "end": latest.day.isoformat(),
            "trading_days": len(replay),
            "rows": [snapshot.to_dict() for snapshot in replay],
        },
        sources=[
            {"key": item.key, "name": item.name, "source": item.source, "bars": len(item.points)}
            for item in series.values()
        ],
        methodology=[
            "只使用评分日及以前的日线；MA20、MA60、回撤、波动率与成交分位均无未来函数。",
            "五个家族分别为等权广度、A股内部结构、海外科技/亚洲、拥挤行为、组合脆弱度；单一家族不能确认红灯。",
            "橙/红灯通常要求三日内至少两次确认；极端下跌日只有在此前已经橙灯时才允许直接升级。",
            "仓位上限是风险预算，不是自动交易指令；低仓位遇红灯不要求开盘恐慌卖出。",
            "韩国熔断事件闸门由价格序列触发：KOSPI单日跌幅达到8%后锁定10个韩国交易日；20个交易日内第二次达到该阈值时升级，若期间再次出现超过4%的大跌，则维持冻结加仓。",
            "锚点宽度固定比较2024-09-24以前已上市股票的前复权区间收益；覆盖不足时不报告‘3900只’结论。",
        ],
        data_gaps=latest.data_gaps,
        disclaimer="风险温度计降低尾部回撤概率，但不能保证完全躲过跳空、突发事件或个股暴雷；不构成投资建议。",
    )
    return payload, _render_markdown(payload), _render_html(payload)


def _fetch_anchor_structure(config: dict[str, object], latest: RiskSnapshot) -> dict[str, object]:
    anchor = _parse_date(str(config.get("anchor_date") or "2024-09-24"))
    benchmark_anchor = float(config.get("benchmark_anchor_close") or 2863.13)
    page_size = _positive_int(config.get("page_size"), 500)
    max_pages = _positive_int(config.get("max_pages"), 20)
    records, source, query = fetch_a_share_anchor_records(
        anchor,
        latest.day,
        page_size=page_size,
        max_pages=max_pages,
    )
    shanghai = latest.metrics.get("shanghai", {})
    current_close = _optional_float(shanghai.get("close")) if isinstance(shanghai, dict) else None
    industries = config.get("technology_industries")
    technology_industries = (
        [str(item) for item in industries]
        if isinstance(industries, list)
        else ["电子", "通信", "计算机"]
    )
    return build_anchor_structure(
        records,
        anchor_date=anchor,
        as_of=latest.day,
        benchmark_anchor_close=benchmark_anchor,
        benchmark_current_close=current_close,
        min_rows=_positive_int(config.get("min_rows"), 4000),
        min_coverage=float(config.get("min_coverage") or 0.90),
        technology_industries=technology_industries,
        source=source,
        query=query,
    )


def _fetch_series(start: date, end: date, history_days: int) -> tuple[dict[str, DailySeries], list[str]]:
    series: dict[str, DailySeries] = {}
    gaps: list[str] = []
    try:
        bars, source = fetch_ths_all_a(start, end)
        series["all_a"] = DailySeries(
            "all_a",
            "同花顺全A(沪深京)",
            source,
            tuple(DailyPoint(item.day, item.close, item.amount) for item in bars),
        )
    except Exception as exc:
        gaps.append(f"同花顺全A不可用：{exc}")
    for key, (name, secid, tencent_code) in A_SHARE_TARGETS.items():
        try:
            candles, source = fetch_public_klines(
                secid=secid,
                tencent_code=tencent_code,
                interval="day",
                limit=min(1000, max(120, history_days)),
            )
            points = tuple(
                DailyPoint(item.time.date(), item.close, item.amount if item.amount > 0 else None)
                for item in candles
                if start <= item.time.date() <= end
            )
            series[key] = DailySeries(key, name, source, points)
        except Exception as exc:
            gaps.append(f"{name}日线不可用：{exc}")
    for key, (name, symbol) in GLOBAL_TARGETS.items():
        try:
            bars = fetch_yahoo_history(symbol, range_name="1y")
            points = tuple(DailyPoint(item.day, item.close) for item in bars if start <= item.day <= end)
            series[key] = DailySeries(key, name, "Yahoo Finance chart", points)
        except Exception as exc:
            gaps.append(f"{name}日线不可用：{exc}")
    return series, gaps


def _load_profile(path: Path) -> tuple[PortfolioRiskProfile, list[str]]:
    payload, gaps = _load_json(path, optional=True)
    if not payload:
        return PortfolioRiskProfile(source=str(path)), gaps + [f"未找到风险画像 {path}"]
    weights = payload.get("holding_weights_pct", [])
    if not isinstance(weights, list):
        weights = []
        gaps.append("holding_weights_pct不是数组，已忽略")
    return (
        PortfolioRiskProfile(
            total_exposure_pct=_optional_float(payload.get("total_exposure_pct")),
            holding_weights_pct=tuple(float(value) for value in weights if _optional_float(value) is not None),
            high_beta_exposure_pct=_optional_float(payload.get("high_beta_exposure_pct")),
            fomo_flag=bool(payload.get("fomo_flag", False)),
            long_horizon_pricing_flag=bool(payload.get("long_horizon_pricing_flag", False)),
            retail_euphoria_flag=bool(payload.get("retail_euphoria_flag", False)),
            portfolio_effective_from=_parse_date(str(payload["portfolio_effective_from"])) if payload.get("portfolio_effective_from") else None,
            behavior_effective_from=_parse_date(str(payload["behavior_effective_from"])) if payload.get("behavior_effective_from") else None,
            source=str(path),
        ),
        gaps,
    )


def _load_json(path: Path, *, optional: bool) -> tuple[dict[str, object], list[str]]:
    if not path.exists():
        return {}, ([] if optional else [f"未找到 {path}"])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {}, [f"读取{path}失败：{exc}"]
    if not isinstance(payload, dict):
        return {}, [f"{path}不是JSON object"]
    return payload, []


def _parse_macro_events(
    raw_events: object,
) -> tuple[tuple[VerifiedMacroEvent, ...], list[str]]:
    if not isinstance(raw_events, list):
        return (), ["宏观事件配置不是数组，已忽略。"]
    events: list[VerifiedMacroEvent] = []
    gaps: list[str] = []
    seen_ids: set[str] = set()
    allowed_types = {
        "supply_disruption",
        "sanction",
        "producer_policy",
        "ceasefire",
        "supply_normalization",
    }
    allowed_statuses = {"official", "conflicting", "unavailable"}
    for index, item in enumerate(raw_events):
        event_id = (
            str(item.get("event_id") or "").strip()
            if isinstance(item, dict)
            else f"index-{index}"
        )
        label = event_id or f"index-{index}"
        try:
            if not isinstance(item, dict):
                raise ValueError("record is not an object")
            if not event_id:
                raise ValueError("event_id is required")
            if event_id in seen_ids:
                raise ValueError("event_id is duplicated")
            event_type = str(item.get("event_type") or "").strip()
            if event_type not in allowed_types:
                raise ValueError(f"unsupported event_type: {event_type}")
            published_at = str(item.get("published_at") or "").strip()
            confirmed_at = str(item.get("confirmed_at") or "").strip()
            published = _parse_aware_datetime(published_at)
            confirmed = _parse_aware_datetime(confirmed_at)
            if confirmed < published:
                raise ValueError("confirmed_at precedes published_at")
            active_from = _parse_date(str(item.get("active_from") or ""))
            active_until = (
                _parse_date(str(item["active_until"]))
                if item.get("active_until")
                else None
            )
            if active_until is not None and active_until < active_from:
                raise ValueError("active_until precedes active_from")
            verification_status = str(
                item.get("verification_status") or ""
            ).strip()
            if verification_status not in allowed_statuses:
                raise ValueError(
                    f"unsupported verification_status: {verification_status}"
                )
            source_url = str(item.get("source_url") or "").strip()
            if not source_url.startswith("https://"):
                raise ValueError("source_url must use HTTPS")
            events.append(
                VerifiedMacroEvent(
                    event_id=event_id,
                    event_type=event_type,
                    published_at=published_at,
                    confirmed_at=confirmed_at,
                    active_from=active_from,
                    active_until=active_until,
                    verification_status=verification_status,
                    source_url=source_url,
                )
            )
            seen_ids.add(event_id)
        except (TypeError, ValueError) as exc:
            gaps.append(f"宏观事件 {label} 无效：{exc}")
    return tuple(events), gaps


def _load_macro_shadow(as_of: date) -> dict[str, object]:
    config, gaps = _load_json(DEFAULT_MACRO_CONFIG_PATH, optional=False)
    events, event_gaps = _parse_macro_events(config.get("events", []))
    gaps.extend(event_gaps)
    symbols = config.get("symbols")
    if not isinstance(symbols, dict):
        symbols = {}
        gaps.append("宏观传导 symbols 配置缺失或无效。")
    history_range = str(config.get("history_range") or "10y")
    series: dict[str, DailySeries] = {}
    for key in (
        "brent",
        "wti",
        "us10y",
        "sp500",
        "qqq",
        "sox",
        "kospi",
    ):
        symbol = str(symbols.get(key) or "").strip()
        if not symbol:
            gaps.append(f"宏观序列 {key} 未配置 symbol。")
            continue
        try:
            bars = fetch_yahoo_history(symbol, range_name=history_range)
            points = tuple(
                DailyPoint(item.day, item.close, item.volume)
                for item in bars
                if item.day <= as_of and item.close > 0
            )
            if not points:
                raise RuntimeError(f"{symbol} 在 {as_of.isoformat()} 前无可用收盘")
            series[key] = DailySeries(
                key,
                key,
                f"https://finance.yahoo.com/quote/{symbol}/history",
                points,
            )
        except Exception as exc:
            gaps.append(f"宏观序列 {key}（{symbol}）不可用：{exc}")
    if not series:
        observation = evaluate_macro_transmission({}, as_of, config, events)
        result = observation.to_dict()
        result.update(
            {
                "calibration_status": "unavailable",
                "independent_event_count": 0,
                "calibration": {
                    "calibration_status": "unavailable",
                    "independent_event_count": 0,
                    "in_sample_event_count": 0,
                    "out_of_sample_event_count": 0,
                    "outcomes": [],
                    "threshold_sensitivity": [],
                    "authority": "diagnostic_only",
                },
                "series_30d": {},
                "data_gaps": gaps or ["宏观序列全部不可用。"],
            }
        )
        return result
    start = min(
        point.day
        for item in series.values()
        for point in item.points
    )
    observations = replay_macro_transmission(
        series,
        start,
        as_of,
        config,
        events,
    )
    latest = (
        observations[-1]
        if observations
        else evaluate_macro_transmission(series, as_of, config, events)
    )
    calibration = calibrate_macro_transmission(
        observations,
        series,
        config,
    )
    result = latest.to_dict()
    result.update(
        {
            "calibration_status": calibration.calibration_status,
            "independent_event_count": calibration.independent_event_count,
            "calibration": calibration.to_dict(),
            "series_30d": _bounded_series_payload(series),
            "data_gaps": gaps,
        }
    )
    return result


def _bounded_series_payload(
    series: dict[str, DailySeries],
    *,
    limit: int = 30,
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in series.items():
        points = item.points[-limit:]
        if not points:
            continue
        result[key] = {
            "source": item.source,
            "as_of": points[-1].day.isoformat(),
            "points": [
                {
                    "date": point.day.isoformat(),
                    "close": point.close,
                }
                for point in points
            ],
        }
    return result


def _parse_aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed


def _default_replay_start(config: dict[str, object], end: date) -> date:
    configured = config.get("default_replay_start")
    if configured:
        return _parse_date(str(configured))
    return end - timedelta(days=90)


def _alert_summary(replay: list[RiskSnapshot], all_a: DailySeries | None) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    final_day = replay[-1].day
    final_close = _close_as_of(all_a, final_day) if all_a else None
    for level in ("yellow", "orange", "red"):
        first = next((item for item in replay if item.level == level), None)
        if first is None:
            continue
        alert_close = _close_as_of(all_a, first.day) if all_a else None
        forward_change = (
            final_close / alert_close - 1
            if final_close is not None and alert_close not in (None, 0)
            else None
        )
        alerts.append(
            {
                "level": level,
                "label": LEVEL_LABELS[level],
                "first_date": first.day.isoformat(),
                "score": first.score,
                "all_a_change_to_end": forward_change,
            }
        )
    return alerts


def _conditional_actions(snapshot: RiskSnapshot, profile: PortfolioRiskProfile) -> list[str]:
    budget = RISK_BUDGETS[snapshot.budget_level]
    actions = [
        f"{LEVEL_LABELS[snapshot.budget_level]}风险预算：总仓位上限{budget['total_exposure_cap_pct']}%，高β仓位上限{budget['high_beta_cap_pct']}%。"
    ]
    if snapshot.budget_level != snapshot.level:
        actions.append(
            f"市场温度已回落到{LEVEL_LABELS[snapshot.level]}，但此前红灯预算仍锁定；连续3个绿灯后才恢复加仓权限。"
        )
    if profile.total_exposure_pct is None:
        actions.append("组合仓位未知：先更新data/risk_watch_profile.json，再决定是否需要降仓。")
    elif profile.total_exposure_pct > budget["total_exposure_cap_pct"]:
        actions.append(
            f"当前总仓位{profile.total_exposure_pct:.1f}%超预算；在下一次流动性和反弹窗口分批降至上限，不用开盘市价追砍。"
        )
    else:
        actions.append(f"当前总仓位{profile.total_exposure_pct:.1f}%未超预算，不因灯色机械清仓。")
    if profile.high_beta_exposure_pct is not None and profile.high_beta_exposure_pct > budget["high_beta_cap_pct"]:
        actions.append(
            f"高β仓位{profile.high_beta_exposure_pct:.1f}%高于预算；优先削减单票/同主题集中，而不是卖掉低相关防守仓。"
        )
    if snapshot.level in {"orange", "red"} or snapshot.budget_level == "red":
        actions.append("暂停新增高β和追涨；只有重新站回MA20且海外弱势市场少于2个，才允许逐级恢复风险预算。")
    return actions


def _event_alert_summary(replay: list[RiskSnapshot]) -> list[dict[str, object]]:
    event_keys = tuple(
        sorted(
            {
                signal.key
                for snapshot in replay
                for signal in snapshot.signals
                if "shock" in signal.key or signal.key == "korea_circuit_breaker_window"
            }
        )
    )
    result: list[dict[str, object]] = []
    for key in event_keys:
        was_active = False
        for snapshot in replay:
            signal = next((item for item in snapshot.signals if item.key == key), None)
            is_active = signal is not None
            if is_active and not was_active and signal is not None:
                result.append(
                    {"key": key, "first_date": snapshot.day.isoformat(), "points": signal.points, "detail": signal.detail}
                )
            was_active = is_active
    return result


def _render_markdown(payload: dict[str, object]) -> str:
    latest = payload["latest"]
    assert isinstance(latest, dict)
    lines = [
        "# 每日市场与组合风险温度计",
        "",
        f"> 截至 {latest.get('date')}；{latest.get('level_label')}，风险分 {latest.get('score')}/100，数据覆盖 {float(latest.get('coverage_ratio') or 0):.0%}。",
        "",
        "## 结论",
        "",
        f"- **当前：{latest.get('level_label')}；执行预算：{latest.get('budget_level_label')}。** 原始等级 {LEVEL_LABELS.get(str(latest.get('raw_level')), latest.get('raw_level'))}；独立信号家族 {latest.get('active_families')} 个。",
    ]
    lines.extend(f"- {item}" for item in payload.get("actions", []))
    crowding = payload.get("crowding_snapshot")
    if isinstance(crowding, dict):
        lines.extend(
            [
                "",
                "## 成交拥挤度快照",
                "",
                f"- 全A成交额：{float(crowding.get('total_amount') or 0) / 1e8:.0f}亿元。",
                f"- 前10/20/50成交占比：{_pct(crowding.get('top10_amount_share'))} / {_pct(crowding.get('top20_amount_share'))} / {_pct(crowding.get('top50_amount_share'))}。",
                f"- 成交第一名：{crowding.get('top1_name')}（{crowding.get('top1_code')}），占全A {_pct(crowding.get('top1_amount_share'))}，成交额/自由流通市值 {_pct(crowding.get('top1_turnover_free_float'))}。",
                "- 当前只作诊断展示；累计至少20个每日快照后才计算历史分位并参与风险计分。",
            ]
        )
    structure = payload.get("anchor_structure")
    if isinstance(structure, dict):
        lines.extend(
            [
                "",
                "## 9·24锚点宽度与指数失真",
                "",
                f"- 锚点累计宽度：{structure.get('health_score', 'NA')}/100（{structure.get('health_label') or '待确认'}）；状态 {structure.get('status') or 'unavailable'}，不代表当前短线趋势。",
                f"- 低于锚点：{structure.get('below_anchor_count', 'NA')}/{structure.get('valid_count', 'NA')}，占 {_pct(structure.get('below_anchor_ratio'))}；覆盖率 {_pct(structure.get('coverage_ratio'))}。",
                f"- 股票池：返回 {structure.get('returned_unique_count', 'NA')}，锚点后上市剔除 {structure.get('post_anchor_listing_count', 'NA')}，上市日期缺失 {structure.get('missing_listing_date_count', 'NA')}。",
                f"- 等权等效上证：{_point(structure.get('equal_weight_equivalent_point'))}；中位数股票等效：{_point(structure.get('median_equivalent_point'))}；官方上证：{_point(structure.get('benchmark_current_close'))}。",
                f"- 上证实际收益 {_pct(structure.get('benchmark_return'))}，固定股票池等权收益 {_pct(structure.get('equal_weight_return'))}，偏离 {_pct(structure.get('benchmark_equal_weight_gap'))}。",
                f"- 科技口径：{','.join(str(item) for item in structure.get('technology_definition', [])) or '待确认'}；当前自由流通市值占比代理 {_pct(structure.get('technology_current_free_float_share'))}，不能冒充历史指数点位贡献。",
                f"- ‘3900只低于9·24’审计：{_claim_status(structure.get('claim_3900_status'))}。",
            ]
        )
    lines.extend(["", "## 触发信号", "", "| 家族 | 分值 | 证据 |", "|---|---:|---|"])
    for signal in latest.get("signals", []):
        if isinstance(signal, dict):
            lines.append(f"| {signal.get('family')} | +{signal.get('points')} | {signal.get('detail')} |")
    lines.extend(["", "## 本轮预警回放", "", "| 灯色 | 首次确认 | 分数 | 此后全A至期末 |", "|---|---|---:|---:|"])
    for alert in payload.get("alerts", []):
        if isinstance(alert, dict):
            change = alert.get("all_a_change_to_end")
            change_text = f"{float(change):.1%}" if isinstance(change, (int, float)) else "NA"
            lines.append(f"| {alert.get('label')} | {alert.get('first_date')} | {alert.get('score')} | {change_text} |")
    event_alerts = payload.get("event_alerts", [])
    if event_alerts:
        lines.extend(["", "## 跨市场冲击闸门", ""])
        lines.extend(
            f"- {item.get('first_date')}：{item.get('detail')}（+{item.get('points')}）"
            for item in event_alerts
            if isinstance(item, dict)
        )
    lines.extend(_macro_markdown_lines(payload.get("macro_transmission")))
    lines.extend(["", "## 数据源与缺口", ""])
    lines.extend(f"- {item.get('name')}：{item.get('source')}，{item.get('bars')}根。" for item in payload.get("sources", []) if isinstance(item, dict))
    for gap in payload.get("data_gaps", []):
        lines.append(f"- 数据缺口：{gap}")
    lines.extend(["", "## 方法与边界", ""])
    lines.extend(f"- {item}" for item in payload.get("methodology", []))
    lines.extend(["", f"> {payload.get('disclaimer', '')}", ""])
    return "\n".join(lines)


def _render_html(payload: dict[str, object]) -> str:
    latest = payload["latest"]
    assert isinstance(latest, dict)
    level = str(latest.get("level", "yellow"))
    signals = "".join(
        f"<tr><td>{escape(str(item.get('family','')))}</td><td>+{item.get('points')}</td><td>{escape(str(item.get('detail','')))}</td></tr>"
        for item in latest.get("signals", []) if isinstance(item, dict)
    )
    alerts = "".join(
        f"<tr><td>{escape(str(item.get('label','')))}</td><td>{escape(str(item.get('first_date','')))}</td><td>{item.get('score')}</td><td>{_pct(item.get('all_a_change_to_end'))}</td></tr>"
        for item in payload.get("alerts", []) if isinstance(item, dict)
    )
    actions = "".join(f"<li>{escape(str(item))}</li>" for item in payload.get("actions", []))
    macro_html = _macro_shadow_html(payload.get("macro_transmission"))
    crowding = payload.get("crowding_snapshot")
    crowding_html = ""
    if isinstance(crowding, dict):
        crowding_html = (
            '<section class="panel"><h2>成交拥挤度快照</h2><div class="cards">'
            f'<article class="card"><span>前20成交占比</span><b>{_pct(crowding.get("top20_amount_share"))}</b></article>'
            f'<article class="card"><span>前50成交占比</span><b>{_pct(crowding.get("top50_amount_share"))}</b></article>'
            f'<article class="card"><span>成交第一名</span><b>{escape(str(crowding.get("top1_name", "")))}</b></article>'
            '</div><p class="muted">当前只作诊断展示；累计至少20个每日快照后才计算历史分位并参与计分。</p></section>'
        )
    structure = payload.get("anchor_structure")
    structure_html = ""
    if isinstance(structure, dict):
        structure_html = (
            '<section class="panel"><h2>9·24锚点宽度与指数失真</h2><div class="cards">'
            f'<article class="card"><span>低于锚点</span><b>{_pct(structure.get("below_anchor_ratio"))}</b><small>{structure.get("below_anchor_count", "NA")}/{structure.get("valid_count", "NA")} · 覆盖 {_pct(structure.get("coverage_ratio"))}</small></article>'
            f'<article class="card"><span>等权等效上证</span><b>{_point(structure.get("equal_weight_equivalent_point"))}</b><small>官方 {_point(structure.get("benchmark_current_close"))}</small></article>'
            f'<article class="card"><span>锚点累计宽度</span><b>{structure.get("health_score", "NA")}/100</b><small>{escape(str(structure.get("health_label") or "待确认"))} · 非短线趋势</small></article>'
            '</div>'
            f'<p>“3900只”审计：{escape(_claim_status(structure.get("claim_3900_status")))}。'
            f'固定股票池等权收益 {_pct(structure.get("equal_weight_return"))}，中位数股票等效上证 {_point(structure.get("median_equivalent_point"))}。</p>'
            '<p class="muted">个股收益采用问财前复权区间涨跌幅；等效点位不是官方指数，当前自由流通权重不冒充历史指数贡献。</p></section>'
        )
    gaps = "".join(f"<li>{escape(str(item))}</li>" for item in payload.get("data_gaps", [])) or "<li>本次未识别到阻断性缺口。</li>"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>每日风险温度计</title>
<style>:root{{--bg:#091015;--panel:#121d24;--line:#2a3a44;--text:#edf4f4;--muted:#9aabb1;--green:#53d39a;--yellow:#f1ca62;--orange:#ff9b55;--red:#ff6666}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif}}main{{width:min(1050px,calc(100% - 28px));margin:auto;padding:28px 0}}h1{{font-size:30px;margin:4px 0}}.muted{{color:var(--muted)}}.hero,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;margin:16px 0}}.hero{{border-color:var(--{level})}}.hero strong{{display:block;font-size:38px;color:var(--{level})}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card{{background:#0d171d;border:1px solid var(--line);border-radius:12px;padding:14px}}.card b{{display:block;font-size:24px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left}}ul{{padding-left:20px}}@media(max-width:700px){{.cards{{grid-template-columns:1fr}}.table{{overflow-x:auto}}h1{{font-size:24px}}}}</style></head><body><main>
<div class="muted">{escape(PRODUCT_NAME)} · RISK WATCH · {escape(str(payload.get('generated_at','')))}</div><h1>每日市场与组合风险温度计</h1>
<section class="hero"><span>截至 {escape(str(latest.get('date','')))}</span><strong>{escape(str(latest.get('level_label','')))} · {latest.get('score')}/100</strong><span>执行预算 {escape(str(latest.get('budget_level_label','')))} · 数据覆盖 {float(latest.get('coverage_ratio') or 0):.0%} · {latest.get('active_families')}个独立信号家族</span></section>
<section class="cards"><article class="card"><span>总仓位上限</span><b>{latest.get('risk_budget',{}).get('total_exposure_cap_pct')}%</b></article><article class="card"><span>高β仓位上限</span><b>{latest.get('risk_budget',{}).get('high_beta_cap_pct')}%</b></article><article class="card"><span>回放交易日</span><b>{payload.get('replay',{}).get('trading_days')}</b></article></section>
<section class="panel"><h2>执行预案</h2><ul>{actions}</ul></section><section class="panel"><h2>触发信号</h2><div class="table"><table><thead><tr><th>家族</th><th>分值</th><th>证据</th></tr></thead><tbody>{signals}</tbody></table></div></section>
<section class="panel"><h2>本轮无未来函数回放</h2><div class="table"><table><thead><tr><th>灯色</th><th>首次确认</th><th>分数</th><th>此后全A至期末</th></tr></thead><tbody>{alerts}</tbody></table></div></section>{macro_html}<details class="panel"><summary>数据缺口</summary><ul>{gaps}</ul></details><p class="muted">{escape(str(payload.get('disclaimer','')))}</p>
{crowding_html}{structure_html}</main></body></html>"""


def _macro_markdown_lines(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    lines = ["", "## 能源—科技宏观传导（影子）", ""]
    for key, title in (
        ("energy_supply_shock", "能源供给冲击"),
        ("duration_pressure", "利率/久期压力"),
        ("korea_import_stress", "韩国进口成本压力"),
    ):
        state = value.get(key)
        if not isinstance(state, dict):
            lines.append(f"- **{title}**：不可用；缺少结构化状态。")
            continue
        lines.append(
            f"- **{title}**：{_macro_state_label(state.get('status'))}；"
            f"下一观察条件：{state.get('next_review_condition') or '等待下一次已完成收盘。'}"
        )
        counter = state.get("counter_evidence")
        if isinstance(counter, list) and counter:
            lines.append(
                f"  - 反证/替代解释：{'；'.join(str(item) for item in counter)}"
            )
        state_gaps = state.get("gaps")
        if isinstance(state_gaps, list) and state_gaps:
            lines.append(
                f"  - 状态缺口：{'；'.join(str(item) for item in state_gaps)}"
            )
    lines.append(
        f"- 校准：{value.get('calibration_status') or 'unavailable'}；"
        f"独立事件数：{value.get('independent_event_count', 0)}。"
    )
    sources = value.get("sources")
    if isinstance(sources, list) and sources:
        linked_sources = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            key = str(source.get("key") or "source")
            url = str(source.get("url") or "")
            as_of = str(source.get("as_of") or "unknown")
            if url.startswith("https://"):
                linked_sources.append(f"[{key}]({url})（截至 {as_of}）")
            else:
                linked_sources.append(f"{key}（截至 {as_of}）")
        if linked_sources:
            lines.append(f"- 来源：{'；'.join(linked_sources)}。")
    data_gaps = value.get("data_gaps")
    if isinstance(data_gaps, list):
        lines.extend(f"- 宏观数据缺口：{gap}" for gap in data_gaps)
    lines.append("- 权限：仅诊断；本状态不改变风险灯、仓位上限或交易计划。")
    return lines


def _macro_shadow_html(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    cards: list[str] = []
    details: list[str] = []
    for key, title in (
        ("energy_supply_shock", "能源供给冲击"),
        ("duration_pressure", "利率/久期压力"),
        ("korea_import_stress", "韩国进口成本压力"),
    ):
        state = value.get(key)
        state = state if isinstance(state, dict) else {}
        cards.append(
            '<article class="card">'
            f"<span>{escape(title)}</span>"
            f"<b>{escape(_macro_state_label(state.get('status')))}</b>"
            f"<small>{escape(str(state.get('next_review_condition') or '等待下一次已完成收盘。'))}</small>"
            "</article>"
        )
        counter = state.get("counter_evidence")
        if isinstance(counter, list):
            details.extend(
                f"<li>{escape(title)}反证：{escape(str(item))}</li>"
                for item in counter
            )
        state_gaps = state.get("gaps")
        if isinstance(state_gaps, list):
            details.extend(
                f"<li>{escape(title)}缺口：{escape(str(item))}</li>"
                for item in state_gaps
            )
    sources: list[str] = []
    raw_sources = value.get("sources")
    if isinstance(raw_sources, list):
        for source in raw_sources:
            if not isinstance(source, dict):
                continue
            key = escape(str(source.get("key") or "source"))
            url = str(source.get("url") or "")
            as_of = escape(str(source.get("as_of") or "unknown"))
            if url.startswith("https://"):
                sources.append(
                    f'<a href="{escape(url, quote=True)}" rel="noopener">{key}</a>'
                    f"（截至 {as_of}）"
                )
            else:
                sources.append(f"{key}（截至 {as_of}）")
    data_gaps = value.get("data_gaps")
    if isinstance(data_gaps, list):
        details.extend(
            f"<li>宏观数据缺口：{escape(str(item))}</li>"
            for item in data_gaps
        )
    detail_html = (
        f"<ul>{''.join(details)}</ul>"
        if details
        else '<p class="muted">本次没有新增宏观数据缺口。</p>'
    )
    source_html = (
        f"<p>来源：{'；'.join(sources)}。</p>"
        if sources
        else '<p class="muted">来源链接当前不可用。</p>'
    )
    return (
        '<section class="panel" id="macro-transmission-shadow">'
        "<h2>能源—科技宏观传导（影子）</h2>"
        f'<div class="cards">{"".join(cards)}</div>'
        f"<p>校准：{escape(str(value.get('calibration_status') or 'unavailable'))}；"
        f"独立事件数：{escape(str(value.get('independent_event_count', 0)))}。</p>"
        f"{source_html}{detail_html}"
        '<p class="muted">权限：仅诊断；本状态不改变风险灯、仓位上限或交易计划。</p>'
        "</section>"
    )


def _macro_state_label(value: object) -> str:
    return {
        "unavailable": "不可用",
        "observe": "观察",
        "confirmed": "确认",
        "invalidated": "失效",
    }.get(str(value), "不可用")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _optional_float(value: object) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _close_as_of(series: DailySeries | None, day: date) -> float | None:
    if series is None:
        return None
    values = [point.close for point in series.points if point.day <= day]
    return values[-1] if values else None


def _pct(value: object) -> str:
    return f"{float(value):.1%}" if isinstance(value, (int, float)) else "NA"


def _point(value: object) -> str:
    return f"{float(value):.2f}点" if isinstance(value, (int, float)) else "NA"


def _claim_status(value: object) -> str:
    return {
        "supported": "同口径结果支持至少3900只低于锚点",
        "not_supported": "同口径结果不支持3900只",
        "unverified": "覆盖或样本不足，暂不下结论",
    }.get(str(value), "暂不下结论")
