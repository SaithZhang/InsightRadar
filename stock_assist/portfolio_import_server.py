"""Loopback-only approved portfolio import UI.

The server binds only to 127.0.0.1 and requires an in-page random token for
state-changing requests.  It never accepts or emits trade orders.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import secrets
from threading import Thread

from stock_assist.after_close_workbench_html import render_after_close_workbench
from stock_assist.decision_workspace import (
    append_plan_response,
    load_runtime_state,
    overlay_plan_responses,
    restage_workspace,
    write_runtime_state,
)
from stock_assist.paths import REPORT_DIR
from stock_assist.portfolio_import import apply_portfolio_import, preview_portfolio_import
from stock_assist.portfolio_import_web import (
    render_portfolio_import_page as _page,
)
from stock_assist.refresh_jobs import RefreshCoordinator


def serve_portfolio_import(
    *,
    port: int = 8765,
    open_browser: bool = True,
    refresh_coordinator: RefreshCoordinator | None = None,
) -> None:
    token = secrets.token_urlsafe(24)
    coordinator = refresh_coordinator or RefreshCoordinator()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html", "/report"}:
                content = _latest_workspace_html(token)
                if content is None:
                    self._send_html(_empty_workspace_page(token))
                    return
                self._send_html(content)
                return
            if self.path == "/portfolio-import":
                self._send_html(_page(token))
                return
            if self.path == "/api/workspace":
                workspace = _latest_workspace()
                if workspace is None:
                    self._send_json({"error": "尚未生成 after-close workspace"}, status=404)
                    return
                self._send_json(overlay_plan_responses(workspace))
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
                    workspace = _latest_workspace()
                    if workspace is None:
                        raise ValueError("尚未生成 after-close workspace")
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
                if self.path == "/api/morning-recheck":
                    workspace = _latest_workspace()
                    if workspace is None:
                        self._send_json({"error": "尚未生成 after-close workspace"}, status=404)
                        return
                    refreshed = restage_workspace(
                        overlay_plan_responses(workspace),
                        run_stage="morning_recheck",
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
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    print(f"InsightRadar local portfolio importer: {url}")
    print("Only this loopback process can save. Use the page's Stop App button or close with Ctrl+C.")
    try:
        server.serve_forever()
    finally:
        server.server_close()


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


def _latest_workspace() -> dict[str, object] | None:
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
        return runtime
    return workspace


def _latest_workspace_html(token: str) -> str | None:
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
    workspace = _latest_workspace()
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
