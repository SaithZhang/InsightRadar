"""Loopback-only approved portfolio import UI.

The server binds only to 127.0.0.1 and requires an in-page random token for
state-changing requests.  It never accepts or emits trade orders.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

from stock_assist.after_close_workbench_html import render_after_close_workbench
from stock_assist.data_sources.xysz import AmazingDataClient
from stock_assist.decision_workspace import (
    DAILY_KLINE_REPAIR_REASON_CODES,
    DEFAULT_DAILY_KLINE_REPAIR_STATE,
    append_plan_response,
    load_runtime_state,
    overlay_plan_responses,
    record_daily_kline_repair,
    restage_workspace,
    write_runtime_state,
)
from stock_assist.intraday.execution import (
    append_execution,
    append_reentry_confirmation,
    load_executions,
    load_reentry_confirmations,
    load_reentry_failures,
)
from stock_assist.intraday.network import sanitize_diagnostic_text
from stock_assist.intraday.polling import (
    _shadow_event_mapping,
    load_intraday_runtime,
    persist_execution_guard,
    run_intraday_service,
    stop_intraday_refresh_process,
    stop_intraday_scheduler,
)
from stock_assist.intraday.session import latest_completed_trade_date
from stock_assist.paths import REPORT_DIR
from stock_assist.portfolio import (
    DEFAULT_PORTFOLIO_CONTEXT_PATH,
    Portfolio,
    load_portfolio,
    portfolio_version,
    save_portfolio_management_context,
)
from stock_assist.portfolio_import import (
    apply_portfolio_import,
    preview_portfolio_import,
)
from stock_assist.portfolio_import_web import (
    render_portfolio_import_page as _page,
)
from stock_assist.refresh_jobs import RefreshCoordinator


def serve_portfolio_import(
    *,
    port: int = 8765,
    open_browser: bool = True,
    refresh_coordinator: RefreshCoordinator | None = None,
    intraday_mode: bool = False,
) -> None:
    token = secrets.token_urlsafe(24)
    coordinator = refresh_coordinator or RefreshCoordinator()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html", "/report"}:
                content = _latest_workspace_html(
                    token,
                    refresh_snapshot=coordinator.latest(),
                )
                if content is None:
                    self._send_html(_empty_workspace_page(token))
                    return
                self._send_html(content)
                return
            if self.path == "/portfolio-import":
                self._send_html(_page(token))
                return
            if self.path == "/api/workspace":
                workspace = _latest_workspace(
                    refresh_snapshot=coordinator.latest(),
                )
                if workspace is None:
                    self._send_json({"error": "尚未生成 after-close workspace"}, status=404)
                    return
                self._send_json(overlay_plan_responses(workspace))
                return
            if self.path == "/api/intraday":
                raw_runtime = load_intraday_runtime()
                if not isinstance(raw_runtime, dict):
                    self._send_json({"error": "尚未生成 intraday runtime"}, status=404)
                    return
                self._send_json(_intraday_workspace_views(raw_runtime))
                return
            if self.path == "/api/intraday/runtime":
                raw_runtime = load_intraday_runtime()
                if not isinstance(raw_runtime, dict):
                    self._send_json({"error": "尚未生成 intraday runtime"}, status=404)
                    return
                self._send_json(raw_runtime)
                return
            if self.path == "/api/executions":
                self._send_json(
                    {
                        "executions": [asdict(item) for item in load_executions()],
                        "reentry_confirmations": [
                            asdict(item) for item in load_reentry_confirmations()
                        ],
                        "reentry_failures": [
                            asdict(item) for item in load_reentry_failures()
                        ],
                    }
                )
                return
            if self.path == "/api/refresh/active":
                snapshot = coordinator.active() or coordinator.latest()
                if snapshot is None:
                    self._send_json({"status": "none"})
                    return
                self._send_json(snapshot)
                return
            if self.path.startswith("/api/refresh/"):
                run_id = self.path.removeprefix("/api/refresh/").strip("/")
                snapshot = coordinator.get(run_id)
                if snapshot is None:
                    self._send_json({"error": "refresh run not found"}, status=404)
                    return
                self._send_json(snapshot)
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.headers.get("X-InsightRadar-Token") != token:
                self._send_json({"error": "invalid local session token"}, status=403)
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if self.path == "/api/shutdown":
                    self._send_json({"stopping": True})
                    Thread(target=server.shutdown, daemon=True).start()
                    return
                if self.path == "/api/plan-response":
                    workspace = _latest_workspace(
                        refresh_snapshot=coordinator.latest(),
                    )
                    if workspace is None:
                        raise ValueError("尚未生成 after-close workspace")
                    _require_current_workspace_authority(
                        workspace,
                        load_portfolio(),
                    )
                    plan_id = str(body.get("plan_id") or "")
                    plan_version = str(body.get("plan_version") or "")
                    current_plan = next(
                        (
                            item
                            for item in workspace.get("active_plans", [])
                            if isinstance(item, dict)
                            and item.get("plan_id") == plan_id
                            and item.get("plan_version") == plan_version
                        ),
                        None,
                    )
                    if current_plan is None:
                        raise ValueError("计划不存在或版本已过期，请刷新后重试")
                    record = append_plan_response(
                        plan_id=plan_id,
                        plan_version=plan_version,
                        response=str(body.get("response") or ""),
                        note=str(body.get("note") or ""),
                        plan_status=str(current_plan.get("status") or "blocked"),
                    )
                    coordinator.record_user_response(record)
                    self._send_json(record)
                    return
                if self.path == "/api/portfolio-management":
                    workspace = _latest_workspace()
                    if workspace is None:
                        raise ValueError("尚未生成 after-close workspace")
                    saved = apply_portfolio_management_response(
                        workspace,
                        load_portfolio(),
                        body,
                    )
                    job = coordinator.start(
                        mode="after_close",
                        idempotency_key=str(
                            body.get("request_id")
                            or f"portfolio-management:{saved['code']}:{saved['updated_at']}"
                        ),
                    )
                    self._send_json(
                        {
                            "saved": True,
                            "record": saved,
                            "refresh_job": job,
                        },
                        status=202,
                    )
                    return
                if self.path == "/api/repair-recheck":
                    workspace = _latest_workspace()
                    if workspace is None:
                        raise ValueError("尚未生成 after-close workspace")
                    job = start_repair_recheck(
                        workspace,
                        body,
                        coordinator,
                        repair_state_path=DEFAULT_DAILY_KLINE_REPAIR_STATE,
                    )
                    self._send_json(job, status=202)
                    return
                if self.path == "/api/morning-recheck":
                    workspace = _latest_workspace()
                    if workspace is None:
                        self._send_json({"error": "尚未生成 after-close workspace"}, status=404)
                        return
                    current = datetime.now()
                    refreshed = restage_workspace(
                        overlay_plan_responses(workspace),
                        run_stage="morning_recheck",
                        now=current,
                        latest_completed_trade_date=(
                            _resolve_latest_completed_trade_date(current)
                        ),
                    )
                    write_runtime_state(refreshed)
                    self._send_json(refreshed)
                    return
                if self.path == "/api/refresh":
                    workspace = _latest_workspace() or {}
                    health = workspace.get("data_health")
                    job = coordinator.start(
                        mode=str(body.get("mode") or "stale"),
                        data_health=(
                            item
                            for item in health
                            if isinstance(item, dict)
                        )
                        if isinstance(health, list)
                        else (),
                        idempotency_key=(
                            str(body.get("request_id"))
                            if body.get("request_id")
                            else None
                        ),
                    )
                    self._send_json(job, status=202)
                    return
                if self.path == "/api/execution":
                    record = append_execution(body)
                    result = asdict(record)
                    result["guard"] = persist_execution_guard()
                    self._send_json(result, status=201)
                    return
                if self.path == "/api/reentry-confirmation":
                    record = append_reentry_confirmation(body)
                    self._send_json(asdict(record), status=201)
                    return
                text = str(body.get("text") or "")
                classifications = body.get("classifications") if isinstance(body.get("classifications"), dict) else {}
                preview = preview_portfolio_import(text, classifications=classifications)
                if self.path == "/api/preview":
                    self._send_json(preview)
                    return
                if self.path == "/api/apply":
                    result = apply_portfolio_import(
                        preview,
                        approved=body.get("approved") is True,
                        rerun=False,
                        open_report=False,
                    )
                    fingerprint = hashlib.sha256(
                        json.dumps(
                            preview.get("proposed_portfolio"),
                            ensure_ascii=False,
                            sort_keys=True,
                        ).encode("utf-8")
                    ).hexdigest()[:20]
                    job = coordinator.start(
                        mode="full",
                        idempotency_key=str(
                            body.get("request_id")
                            or f"portfolio-apply:{fingerprint}"
                        ),
                    )
                    result["refresh_job"] = job
                    result["refresh_started"] = True
                    self._send_json(result, status=202)
                    return
                self._send_json({"error": "unknown endpoint"}, status=404)
            except Exception as exc:
                self._send_json({"error": str(exc), "type": type(exc).__name__}, status=400)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, payload: object, *, status: int = 200) -> None:
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _send_html(self, content: str) -> None:
            raw = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    intraday_stop = Event()
    intraday_thread: Thread | None = None
    if intraday_mode:
        def intraday_worker() -> None:
            try:
                run_intraday_service(stop_event=intraday_stop)
            except Exception as exc:
                print(
                    "盘中后台刷新结束："
                    + sanitize_diagnostic_text(type(exc).__name__)
                )

        intraday_thread = Thread(
            target=intraday_worker,
            name="InsightRadarIntradayService",
            daemon=True,
        )
        intraday_thread.start()
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    print(f"InsightRadar local portfolio importer: {url}")
    print("Only this loopback process can save. Use the page's Stop App button or close with Ctrl+C.")
    try:
        server.serve_forever()
    finally:
        if intraday_mode:
            intraday_stop.set()
            stop_intraday_refresh_process()
            if intraday_thread is not None:
                intraday_thread.join(timeout=3.0)
            stop_intraday_scheduler()
        server.server_close()


_PRICE_RULE_MARKERS = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:元|块)|均线|支撑位?|压力位?|价格阈值|MA\d+)",
    re.IGNORECASE,
)


def apply_portfolio_management_response(
    workspace: Mapping[str, object],
    portfolio: Portfolio,
    body: Mapping[str, object],
    *,
    context_path=DEFAULT_PORTFOLIO_CONTEXT_PATH,
    now: datetime | None = None,
) -> dict[str, object]:
    """Validate a local management response and persist the compatible context."""

    code = str(body.get("symbol") or "").strip()
    response = str(body.get("response") or "").strip()
    version = str(body.get("management_plan_version") or "").strip()
    if response not in {"adopt", "modify", "uncertain"}:
        raise ValueError("不支持的方案操作")
    holding = next((item for item in portfolio.holdings if item.code == code), None)
    if holding is None:
        raise ValueError("持仓不存在或已退出，请刷新后重试")
    raw_plans = workspace.get("portfolio_management_plans")
    plans = raw_plans if isinstance(raw_plans, list) else []
    proposal = next(
        (
            item
            for item in plans
            if isinstance(item, Mapping)
            if str(item.get("symbol") or "") == code
            and str(item.get("management_plan_version") or "") == version
        ),
        None,
    )
    if proposal is None:
        raise ValueError("管理方案不存在或版本已过期，请刷新后重试")

    if response == "adopt":
        review_status = str(proposal.get("review_status") or "watch")
        context_status = "user_confirmed"
        context_source = "system_proposal_confirmed"
        user_disposition = "adopted"
    elif response == "uncertain":
        review_status = "uncertain"
        context_status = "system_proposed"
        context_source = "user_uncertain"
        user_disposition = "uncertain"
    else:
        review_status = str(
            body.get("management_choice") or body.get("review_status") or ""
        ).strip()
        if review_status == "uncertain":
            context_status = "system_proposed"
            context_source = "user_uncertain"
            user_disposition = "uncertain"
        else:
            context_status = "user_modified"
            context_source = "user_modified"
            user_disposition = "modified"
    if review_status == "profit_protect" and not (
        holding.pnl_pct is not None and holding.pnl_pct > 0
    ):
        raise ValueError("当前持仓不适用利润保护，请选择继续观察或风险复核")

    fields = {
        "management_name": str(body.get("suggestion_name") or proposal.get("suggestion_name") or "").strip(),
        "management_trigger": str(body.get("trigger_condition") or proposal.get("trigger_condition") or "").strip(),
        "management_persistence": str(body.get("confirmation_window") or proposal.get("confirmation_window") or "").strip(),
        "management_action": str(body.get("triggered_action") or proposal.get("triggered_action") or "").strip(),
        "management_invalidation": str(body.get("invalidation_condition") or proposal.get("invalidation_condition") or "").strip(),
    }
    if proposal.get("data_status") == "data_blocked":
        proposal_fields = {
            "management_trigger": str(proposal.get("trigger_condition") or "").strip(),
            "management_persistence": str(proposal.get("confirmation_window") or "").strip(),
            "management_action": str(proposal.get("triggered_action") or "").strip(),
            "management_invalidation": str(proposal.get("invalidation_condition") or "").strip(),
        }
        changed_text = " ".join(
            value
            for key, value in fields.items()
            if key in proposal_fields and value != proposal_fields[key]
        )
        if changed_text and _PRICE_RULE_MARKERS.search(changed_text):
            raise ValueError("行情异常期间不能新增均线、支撑位或价格阈值规则")
    current_risk_line = (
        f"触发：{fields['management_trigger']}；"
        f"持续：{fields['management_persistence']}；"
        f"动作：{fields['management_action']}；"
        f"失效：{fields['management_invalidation']}"
    )
    saved = save_portfolio_management_context(
        code=code,
        context_status=context_status,
        review_status=review_status,
        current_risk_line=current_risk_line,
        management_plan_version=version,
        context_source=context_source,
        based_on_report=str(proposal.get("based_on_report") or ""),
        management_name=fields["management_name"],
        management_trigger=fields["management_trigger"],
        management_persistence=fields["management_persistence"],
        management_action=fields["management_action"],
        management_invalidation=fields["management_invalidation"],
        next_review_date=str(proposal.get("next_review_time") or ""),
        user_note=str(body.get("note") or ""),
        user_disposition=user_disposition,
        confirmed_at=now,
        path=context_path,
    )
    return {
        **saved,
        "code": code,
        "updated_at": str(saved.get("updated_at") or (now or datetime.now()).isoformat(timespec="seconds")),
    }


def start_repair_recheck(
    workspace: Mapping[str, object],
    body: Mapping[str, object],
    coordinator: RefreshCoordinator,
    *,
    repair_state_path: Path | None = None,
) -> dict[str, object]:
    """Validate one current repair issue before starting its bounded retry."""

    issue_id = str(body.get("issue_id") or "").strip()
    workspace_generated_at = str(body.get("workspace_generated_at") or "").strip()
    if not issue_id:
        raise ValueError("修复问题编号不能为空")
    if workspace_generated_at != str(workspace.get("generated_at") or ""):
        raise ValueError("工作台版本已过期，请刷新后重新检查")
    raw_issues = workspace.get("repair_issues")
    issues = raw_issues if isinstance(raw_issues, list) else []
    issue = next(
        (
            item
            for item in issues
            if isinstance(item, Mapping)
            and str(item.get("issue_id") or "") == issue_id
        ),
        None,
    )
    if issue is None:
        raise ValueError("修复问题已变化或不存在，请刷新后重试")
    if issue.get("repair_allowed") is not True:
        raise ValueError("当前问题不允许从工作台触发修复")
    method = str(issue.get("repair_method") or "")
    if method == "retry_after_close":
        if (
            str(issue.get("reason_code") or "")
            in DAILY_KLINE_REPAIR_REASON_CODES
            and repair_state_path is not None
        ):
            record_daily_kline_repair(
                issue,
                workspace_generated_at=workspace_generated_at,
                path=repair_state_path,
            )
        mode = "after_close"
        data_health: tuple[Mapping[str, object], ...] = ()
    elif method == "refresh_sources":
        mode = "stale"
        raw_health = workspace.get("data_health")
        available_health = tuple(
            item
            for item in (raw_health if isinstance(raw_health, list) else [])
            if isinstance(item, Mapping)
        )
        source = str(issue.get("source") or "")
        data_health = tuple(
            item
            for item in available_health
            if str(item.get("source_name") or item.get("id") or "") == source
        )
        if str(issue.get("field") or "") == "portfolio.risk_reconciliation":
            data_health = ({"source_name": "risk_watch", "status": "blocked"},)
        elif not data_health and source == "after-close":
            data_health = ({"source_name": "after-close", "status": "blocked"},)
        elif not data_health:
            raise ValueError("修复问题对应的数据来源已变化，请刷新后重试")
    elif method == "portfolio_import":
        raise ValueError("该问题需要从持仓导入页重新提供券商字段")
    else:
        raise ValueError("当前修复方式未接入自动重试")
    request_id = str(body.get("request_id") or "").strip()
    return coordinator.start(
        mode=mode,
        data_health=data_health,
        idempotency_key=request_id
        or f"repair-recheck:{issue_id}:{workspace_generated_at}",
    )


def _latest_after_close_html():
    reports = sorted(
        REPORT_DIR.glob("*-after-close.html"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None


def _latest_after_close_json():
    reports = sorted(
        REPORT_DIR.glob("*-after-close.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None


def _latest_workspace(
    *,
    current_portfolio: Portfolio | None = None,
    refresh_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    json_path = _latest_after_close_json()
    if json_path is None:
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    workspace = payload.get("decision_workspace") if isinstance(payload, dict) else None
    if not isinstance(workspace, dict):
        return None
    runtime = load_runtime_state()
    if (
        runtime
        and runtime.get("effective_market_date") == workspace.get("effective_market_date")
        and runtime.get("source_generated_at") == workspace.get("source_generated_at")
    ):
        selected = dict(runtime)
    else:
        selected = dict(workspace)
    intraday = load_intraday_runtime()
    if intraday is not None:
        normalized, historical = _normalize_intraday_overlay(
            intraday,
            expected_trade_date=datetime.now().date().isoformat(),
        )
        views = _intraday_workspace_views(normalized)
        selected.update(views)
        selected["intraday_radar"] = dict(views["selected_session"])
        if historical and not selected.get("intraday_history"):
            selected["intraday_history"] = [dict(normalized)]
    replay = _latest_intraday_replay()
    if replay is not None:
        selected["intraday_replay"] = replay
    return _apply_workspace_validity(
        selected,
        current_portfolio=current_portfolio or load_portfolio(),
        refresh_snapshot=refresh_snapshot,
    )


def _apply_workspace_validity(
    workspace: Mapping[str, object],
    *,
    current_portfolio: Portfolio,
    refresh_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Bind current authority to the exact saved portfolio version."""

    result = deepcopy(dict(workspace))
    current_version = portfolio_version(current_portfolio)
    workspace_version = str(result.get("portfolio_version") or "")
    superseded = workspace_version != current_version
    validity: dict[str, object] = {
        "status": "superseded" if superseded else "current",
        "reason_code": (
            "PORTFOLIO_VERSION_SUPERSEDED" if superseded else None
        ),
        "current_decision_authority": (
            "blocked" if superseded else "current"
        ),
        "current_portfolio_version": current_version,
        "workspace_portfolio_version": workspace_version or None,
        "current_portfolio_as_of": current_portfolio.as_of or None,
        "workspace_effective_market_date": result.get("effective_market_date"),
    }
    refresh = _safe_refresh_summary(refresh_snapshot)
    if refresh is not None:
        validity["latest_refresh"] = refresh
    result["workspace_validity"] = validity
    if not superseded:
        return result

    blocker = "当前持仓版本已变化；该计划仅作为历史快照，不具有当前授权。"
    result["runtime_status"] = "superseded"
    result["view_mode"] = "historical_snapshot"
    result["decision_authority"] = "historical_snapshot_only"
    result["authority_state"] = "blocked"
    result["effective_after_user_confirmation"] = False
    result["trade_authority"] = "none"
    gate = dict(result.get("market_gate")) if isinstance(result.get("market_gate"), Mapping) else {}
    gate.update(
        {
            "status": "blocked",
            "permission": "blocked",
            "reason": blocker,
        }
    )
    result["market_gate"] = gate
    for key in ("plan_changes", "today_plans", "active_plans"):
        rows = result.get(key)
        if not isinstance(rows, list):
            continue
        for plan in rows:
            if not isinstance(plan, dict):
                continue
            plan["status"] = "blocked"
            plan["authority_state"] = "blocked"
            plan["effective_after_user_confirmation"] = False
            reasons = plan.get("blocking_reasons")
            values = [str(item) for item in reasons] if isinstance(reasons, list) else []
            if blocker not in values:
                values.append(blocker)
            plan["blocking_reasons"] = values
            if plan.get("user_response_status") == "accepted":
                plan["user_response_status"] = "pending"
                plan["user_response_note"] = (
                    "当前持仓版本变化已撤销旧 accepted 的当前授权；"
                    "刷新成功并生成新计划后需重新确认。"
                )
                plan["user_response_at"] = None
    positions = result.get("portfolio_positions")
    if isinstance(positions, list):
        for position in positions:
            if isinstance(position, dict):
                position["today_status"] = "blocked"
    return result


def _safe_refresh_summary(
    snapshot: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(snapshot, Mapping):
        return None
    summary = {
        key: snapshot.get(key)
        for key in (
            "status",
            "failed_step",
            "current_step",
            "requested_at",
            "started_at",
            "finished_at",
        )
        if snapshot.get(key) not in (None, "")
    }
    if snapshot.get("error") not in (None, ""):
        error = sanitize_diagnostic_text(str(snapshot.get("error")))
        error = re.sub(r"\b\d{6}\.(?:SH|SZ)\b", "<SYMBOL>", error)
        error = re.sub(r"[A-Za-z]:\\[^\r\n]+", "<LOCAL_PATH>", error)
        summary["error"] = error[:500]
    return summary or None


def _require_current_workspace_authority(
    workspace: Mapping[str, object],
    current_portfolio: Portfolio,
) -> None:
    validity = workspace.get("workspace_validity")
    validity_status = (
        str(validity.get("status") or "")
        if isinstance(validity, Mapping)
        else ""
    )
    current_authority = (
        str(validity.get("current_decision_authority") or "")
        if isinstance(validity, Mapping)
        else ""
    )
    if (
        validity_status != "current"
        or current_authority != "current"
        or str(workspace.get("portfolio_version") or "")
        != portfolio_version(current_portfolio)
    ):
        raise ValueError(
            "当前持仓已更新，这个计划属于旧组合版本。"
            "请完成刷新并生成新计划后重新确认。"
        )


def _resolve_latest_completed_trade_date(current: datetime) -> date | None:
    """Resolve freshness authority from the provider calendar or fail closed."""

    client: AmazingDataClient | None = None
    try:
        client = AmazingDataClient()
        return latest_completed_trade_date(current, client.calendar)
    except Exception:
        return None
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


def _normalize_intraday_overlay(
    runtime: dict[str, object],
    *,
    expected_trade_date: str,
    now: datetime | None = None,
    max_age_seconds: int = 180,
) -> tuple[dict[str, object], bool]:
    """Classify the runtime view without rewriting its recorded authority state."""

    result = dict(runtime)
    for field in ("timeline", "active_alerts"):
        rows = result.get(field)
        if isinstance(rows, list):
            result[field] = [
                _shadow_event_mapping(item)
                for item in rows
                if isinstance(item, Mapping)
            ]
    trade_date = str(result.get("trade_date") or "")
    source_time = _parse_datetime(result.get("source_time"))
    current = now or datetime.now()
    if result.get("session_mode") == "non_trading_day" or result.get("view_mode") == "historical_review":
        result["view_mode"] = "historical_review"
        result["analysis_authority"] = str(
            result.get("analysis_authority") or "historical_shadow"
        )
        result["decision_authority"] = str(
            result.get("decision_authority") or "historical_shadow_only"
        )
        result["trade_authority"] = "none"
        result["realtime_decision_available"] = False
        return result, True
    cross_day = (
        not trade_date
        or trade_date != current.date().isoformat()
    )
    expired = cross_day
    if source_time is None:
        expired = True
    elif source_time.date() == current.date():
        age_seconds = (current - source_time).total_seconds()
        expired = expired or age_seconds < 0 or age_seconds > max_age_seconds
    elif current.date().isoformat() == expected_trade_date:
        expired = True
    if result.get("freshness_status") != "fresh":
        expired = True
    if expired:
        if result.get("status") == "ready":
            result["status"] = "shadow"
        if result.get("decision_authority") == "ready":
            result["decision_authority"] = "shadow_only"
        result["view_mode"] = "historical_stale"
        result["overlay_available"] = False
        result["overlay_freshness_status"] = "expired"
        result["trade_authority"] = "none"
        result["data_status"] = "historical" if cross_day else result.get("data_status", "stale")
        result["next_check_time"] = None
    else:
        result["view_mode"] = str(result.get("view_mode") or "current_session")
        result["overlay_available"] = True
        if result.get("status") == "ready":
            result["status"] = "shadow"
        result["decision_authority"] = str(
            result.get("decision_authority") or "shadow_only"
        )
        result["trade_authority"] = "none"
    return result, cross_day or expired


def _intraday_workspace_views(
    runtime: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    current = now or datetime.now()
    normalized, historical = _normalize_intraday_overlay(
        dict(runtime),
        expected_trade_date=current.date().isoformat(),
        now=current,
    )
    current_session: dict[str, object]
    latest_completed: dict[str, object] | None = None
    history: list[dict[str, object]] = []
    if normalized.get("view_mode") == "historical_review":
        current_session = {
            "calendar_date": str(normalized.get("calendar_date") or current.date().isoformat()),
            "current_exchange_trade_date": normalized.get("current_exchange_trade_date"),
            "session_mode": "non_trading_day",
            "view_mode": "current_session",
            "data_status": "not_applicable_non_trading_day",
            "analysis_authority": "none",
            "decision_authority": "blocked_non_trading_day",
            "trade_authority": "none",
            "realtime_decision_available": False,
        }
        latest_completed = dict(normalized)
        history.append(dict(normalized))
        selected = latest_completed
    else:
        current_session = dict(normalized)
        selected = current_session
        if historical:
            history.append(dict(normalized))
    return {
        "schema_version": "intraday-workspace/v1",
        "view_mode": str(selected.get("view_mode") or "current_session"),
        "current_session": current_session,
        "latest_completed_session": latest_completed,
        "intraday_history": history,
        "selected_session": selected,
    }


def _parse_datetime(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value is not None else None
    except ValueError:
        return None


def _latest_intraday_replay() -> dict[str, object] | None:
    reports = sorted(
        REPORT_DIR.glob("*-intraday-replay.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return None
    try:
        payload = json.loads(reports[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _latest_workspace_html(
    token: str,
    *,
    refresh_snapshot: Mapping[str, object] | None = None,
) -> str | None:
    json_path = _latest_after_close_json()
    if json_path is None:
        latest_html = _latest_after_close_html()
        if latest_html is None:
            return None
        return latest_html.read_text(encoding="utf-8").replace(
            "__LOCAL_SESSION_TOKEN__",
            token,
            1,
        )
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    workspace = _latest_workspace(refresh_snapshot=refresh_snapshot)
    if workspace is not None:
        payload["decision_workspace"] = workspace
    md_path = json_path.with_suffix(".md")
    markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    return render_after_close_workbench(payload, markdown).replace(
        "__LOCAL_SESSION_TOKEN__",
        token,
        1,
    )


def _empty_workspace_page(token: str) -> str:
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>InsightRadar 决策工作台</title>
<style>body{{margin:0;background:#f4f5f7;color:#172033;font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif}}
main{{width:min(720px,calc(100% - 28px));margin:10vh auto;background:#fff;border:1px solid #e1e5eb;border-radius:14px;padding:28px}}
.brand{{color:#b42332;font-weight:900}}a,button{{display:inline-block;border:0;border-radius:8px;padding:9px 13px;margin:8px 8px 0 0;background:#b42332;color:#fff;text-decoration:none;font-weight:800;cursor:pointer}}
.secondary{{background:#edf0f4;color:#172033}}code{{background:#f4f5f7;padding:2px 5px;border-radius:4px}}</style></head>
<body><main><div class="brand">IR · InsightRadar</div><h1>还没有可展示的行动简报</h1>
<p>统一入口已经就绪，但必须先让真实 after-close 流程生成 JSON / Markdown / HTML。系统不会用样例数据填充空白。</p>
<p><code>.venv\\Scripts\\python -m stock_assist.cli after-close</code></p>
<a href="/portfolio-import">先导入 / 更新持仓</a><button class="secondary" id="shutdown">关闭本地应用</button>
<script>const token={json.dumps(token)};document.getElementById("shutdown").onclick=async()=>{{await fetch("/api/shutdown",{{method:"POST",headers:{{"Content-Type":"application/json","X-InsightRadar-Token":token}},body:"{{}}"}});document.body.innerHTML="<main><h1>InsightRadar 已关闭</h1></main>"}}</script>
</main></body></html>"""


def _legacy_inline_page(token: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>InsightRadar 本地应用</title><style>
body{{margin:0;background:#071014;color:#eaf4f1;font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif}}
main{{width:min(960px,calc(100% - 28px));margin:24px auto}}section{{padding:18px;border:1px solid #26383d;border-radius:10px;background:#10191d;margin-bottom:12px}}
h1{{margin:0 0 6px}}p{{color:#91a6a1}}textarea{{width:100%;min-height:190px;box-sizing:border-box;background:#071014;color:#eaf4f1;border:1px solid #344a50;border-radius:8px;padding:10px}}
button,.button,label{{display:inline-block;margin:8px 8px 0 0;padding:9px 13px;border:0;border-radius:7px;background:#62dfa2;color:#062014;font-weight:800;cursor:pointer;text-decoration:none}}button.secondary,.button.secondary{{background:#25353a;color:#eaf4f1}}button.danger{{background:#6b3030;color:#fff}}button[disabled]{{opacity:.45;cursor:not-allowed}}.warn{{color:#f3c269}}.toolbar{{display:flex;flex-wrap:wrap;align-items:center;gap:8px}}.beta-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:12px 0}}.beta-card{{padding:10px;border:1px solid #344a50;border-radius:8px;background:#0a1216}}.beta-card label{{display:block;margin:0;padding:0;background:transparent;color:#eaf4f1;cursor:default}}.beta-card select{{width:100%;margin-top:7px;padding:8px;border-radius:6px;background:#071014;color:#eaf4f1;border:1px solid #456068}}.summary{{padding:10px;border-radius:8px;background:#071014;color:#b8cbc6}}.output{{overflow:auto}}.output table{{width:100%;border-collapse:collapse;min-width:660px}}.output th,.output td{{padding:9px;border-bottom:1px solid #26383d;text-align:left}}.output th{{color:#91a6a1}}.pill{{display:inline-block;padding:2px 7px;border-radius:999px;background:#25353a}}.refresh-panel{{margin-top:14px;padding:12px;border:1px solid #344a50;border-radius:8px;background:#071014}}.refresh-panel[hidden]{{display:none}}.refresh-head{{display:flex;justify-content:space-between;gap:12px}}.refresh-steps{{display:grid;gap:6px;margin-top:10px}}.refresh-step{{display:flex;justify-content:space-between;gap:12px;padding:7px 9px;background:#10191d}}.refresh-step.failed{{color:#ff8b8b}}.refresh-step.completed{{color:#62dfa2}}@media(max-width:640px){{main{{width:min(100% - 18px,960px);margin:9px auto}}section{{padding:13px}}}}
</style></head><body><main><section><div class="toolbar"><a class="button secondary" href="/#portfolio">返回组合风险</a><button class="danger" id="shutdown" type="button">关闭本地应用</button></div><h1>导入或更新持仓</h1><p>把券商持仓表直接粘贴到下方。数据只在本机 127.0.0.1 处理，不上传；必须先预览，再明确批准才会保存。</p>
<input id="file" type="file" accept=".tsv,.txt,.csv"><textarea id="text" placeholder="在这里粘贴包含“证券代码、证券名称、当前持仓、仓位占比”的券商表格"></textarea>
<button id="preview" type="button">1. 解析并预览</button><p class="warn" id="status">尚未预览</p>
<div id="beta-selectors" class="beta-grid"><div class="summary">解析后，在这里逐只选择高 beta、普通或暂不确定。系统不会按代码猜测。</div></div>
<label><input id="approved" type="checkbox"> 2. 我已核对新旧差异并明确批准保存</label><button id="apply" type="button" disabled>3. 保存持仓并启动后台刷新</button>
<div id="refresh-panel" class="refresh-panel" hidden><div class="refresh-head"><strong id="refresh-title">刷新任务</strong><span id="refresh-progress">0%</span></div><div id="refresh-steps" class="refresh-steps"></div></div></section><section><div id="output" class="output"><div class="summary">等待本地解析。</div></div></section></main>
<script>
const token={json.dumps(token)};let last=null;let betaValues={{}};let refreshTimer=null;const $=id=>document.getElementById(id);
const classifications=()=>betaValues;
const post=async(path,approved=false,extra={{}})=>{{const r=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json','X-InsightRadar-Token':token}},body:JSON.stringify({{text:$('text').value,classifications:classifications(),approved,...extra}})}});const data=await r.json();if(!r.ok)throw new Error(data.error||'请求失败');return data}};
const get=async path=>{{const r=await fetch(path,{{headers:{{'X-InsightRadar-Token':token}},cache:'no-store'}});const data=await r.json();if(!r.ok)throw new Error(data.error||'请求失败');return data}};
const requestId=()=>globalThis.crypto?.randomUUID?.()??`refresh-${{Date.now()}}-${{Math.random()}}`;
const renderRefresh=job=>{{if(!job||job.status==='none')return;$('refresh-panel').hidden=false;const done=Number(job.completed_steps??0);const total=Number(job.total_steps??0);const pct=total?Math.round(done/total*100):0;$('refresh-progress').textContent=`${{pct}}%`;$('refresh-title').textContent=job.status==='completed'?'刷新完成':job.status==='failed'?`刷新失败：${{job.failed_step??'unknown'}}`:job.status==='interrupted'?'刷新已中断':'后台串行刷新中';$('refresh-steps').replaceChildren();for(const step of job.steps??[]){{const row=document.createElement('div');row.className=`refresh-step ${{step.status}}`;const name=document.createElement('span');name.textContent=step.workflow;const state=document.createElement('strong');state.textContent=step.status;row.append(name,state);$('refresh-steps').appendChild(row)}}if(job.status==='failed'||job.status==='interrupted'){{$('status').textContent=`刷新未完成：${{job.failed_step??job.current_step??'服务中断'}}。${{job.error??''}} 已保存的持仓不受影响，上一份报告仍保留为旧版本。`}}else if(job.status==='completed'){{$('status').textContent='后台刷新完成，可以返回行动简报。'}}}};
const pollRefresh=async runId=>{{clearTimeout(refreshTimer);try{{const job=await get(`/api/refresh/${{runId}}`);renderRefresh(job);if(['pending','running'].includes(job.status))refreshTimer=setTimeout(()=>pollRefresh(runId),900)}}catch(e){{$('status').textContent='读取刷新进度失败：'+e.message}}}};
const recoverRefresh=async()=>{{try{{const job=await get('/api/refresh/active');if(job.status!=='none'){{renderRefresh(job);if(['pending','running'].includes(job.status))pollRefresh(job.run_id)}}}}catch(e){{console.warn(e)}}}};
const renderBetaSelectors=data=>{{const box=$('beta-selectors');box.replaceChildren();for(const item of data.proposed_portfolio.holdings){{const card=document.createElement('div');card.className='beta-card';const label=document.createElement('label');label.textContent=`${{item.name}} (${{item.code}})`;const select=document.createElement('select');for(const [value,text] of [['unknown','暂不确定'],['high_beta','高 beta'],['normal','普通']]){{const option=document.createElement('option');option.value=value;option.textContent=text;select.appendChild(option)}}select.value=betaValues[item.code]??item.beta_classification??'unknown';betaValues[item.code]=select.value;select.addEventListener('change',()=>{{betaValues[item.code]=select.value;last=null;$('apply').disabled=true;$('status').textContent='beta 分类已修改，请重新解析预览。'}});label.appendChild(select);card.appendChild(label);box.appendChild(card)}}}};
const renderPreview=data=>{{const output=$('output');output.replaceChildren();const risk=document.createElement('div');risk.className='summary';risk.textContent=`持仓 ${{data.proposed_portfolio.holdings.length}} 只｜仓位 ${{data.risk_reconciliation.total_exposure_pct??'未提供'}}%｜风险对账 ${{data.risk_reconciliation.status}}：${{data.risk_reconciliation.reason}}`;output.appendChild(risk);const table=document.createElement('table');const head=document.createElement('tr');for(const text of ['状态','代码','名称','原股数','新股数','新仓位','beta']){{const th=document.createElement('th');th.textContent=text;head.appendChild(th)}}const thead=document.createElement('thead');thead.appendChild(head);table.appendChild(thead);const tbody=document.createElement('tbody');for(const diff of data.differences){{const tr=document.createElement('tr');const values=[diff.status,diff.code,diff.new?.name??diff.old?.name??'',diff.old?.shares??'—',diff.new?.shares??'—',diff.new?.weight_pct??'—',diff.new?.beta_classification??'—'];for(const value of values){{const td=document.createElement('td');td.textContent=String(value);tr.appendChild(td)}}tbody.appendChild(tr)}}table.appendChild(tbody);output.appendChild(table);for(const warning of data.validation.warnings){{const note=document.createElement('p');note.className='warn';note.textContent=warning;output.appendChild(note)}}}};
const runPreview=async()=>{{try{{last=await post('/api/preview');renderBetaSelectors(last);renderPreview(last);const risk=last.risk_reconciliation;$('status').textContent=last.validation.valid?`已识别 ${{last.proposed_portfolio.holdings.length}} 只；风险对账：${{risk.status}}。请核对差异和 beta 分类。`:'校验失败；不得保存';$('apply').disabled=!last.validation.valid||!$('approved').checked}}catch(e){{last=null;$('apply').disabled=true;$('status').textContent='解析失败：'+e.message}}}};
$('file').addEventListener('change',async()=>{{if($('file').files[0]){{$('text').value=await $('file').files[0].text();await runPreview()}}}});
$('preview').addEventListener('click',runPreview);
$('approved').addEventListener('change',()=>{{$('apply').disabled=!(last&&last.validation.valid&&$('approved').checked)}});
$('apply').addEventListener('click',async()=>{{if(!$('approved').checked||!last)return;$('apply').disabled=true;$('status').textContent='正在保存持仓…';try{{const result=await post('/api/apply',true,{{request_id:requestId()}});const output=$('output');output.replaceChildren();const done=document.createElement('div');done.className='summary';done.textContent=`持仓已保存到 ${{result.portfolio_path}}。后台刷新已取得任务号，关闭或刷新页面不会丢失状态。`;const link=document.createElement('a');link.className='button';link.href='/#today';link.textContent='返回行动简报';output.append(done,link);$('status').textContent='持仓已保存；后台正在串行刷新。';renderRefresh(result.refresh_job);pollRefresh(result.refresh_job.run_id)}}catch(e){{$('status').textContent='保存或启动刷新失败：'+e.message;$('apply').disabled=false}}}});
$('shutdown').addEventListener('click',async()=>{{$('shutdown').disabled=true;await post('/api/shutdown');document.body.innerHTML='<main><section><h1>InsightRadar 已关闭</h1><p>可以关闭此页面。</p></section></main>'}});
recoverRefresh();
</script></body></html>"""
