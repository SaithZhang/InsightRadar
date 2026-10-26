"""Presentation-only assets for the local portfolio import workflow.

HTTP routing, portfolio writes, and refresh execution live outside this
module.  The page speaks only to the documented loopback JSON endpoints.
"""

from __future__ import annotations

import json


def render_portfolio_import_page(token: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>InsightRadar 本地持仓导入</title>
  <style>{_styles()}</style>
</head>
<body>
  <main>
    <section>
      <div class="toolbar">
        <a class="button secondary" href="/#portfolio">返回组合风险</a>
        <button class="danger" id="shutdown" type="button">关闭本地应用</button>
      </div>
      <div class="import-kicker">InsightRadar · 组合设置</div>
      <h1>把你的持仓带进工作台</h1>
      <p>从券商复制持仓表，先预览、核对，再确认保存。导入内容保存在本机；保存后会自动刷新分析。</p>
      <div class="import-steps"><span class="current">01 选择文件或粘贴</span><span>02 预览并核对</span><span>03 确认保存</span></div>
      <label class="file-label" for="file">选择持仓文件 <small>TSV / TXT / CSV</small></label>
      <input id="file" type="file" accept=".tsv,.txt,.csv">
      <label class="paste-label" for="text">或直接粘贴券商表格</label>
      <textarea id="text" placeholder="在这里粘贴包含证券代码、证券名称、当前持仓和仓位占比的券商表格"></textarea>
      <button id="preview" type="button">1. 解析并预览</button>
      <p class="warn" id="status">尚未预览</p>
      <div id="beta-status" class="summary">市场敏感度（Beta）会在保存后自动计算。缺少行情或样本不足时显示待核实。</div>
      <label class="approval">
        <input id="approved" type="checkbox">
        2. 我已核对新旧差异并明确批准保存
      </label>
      <button id="apply" type="button" disabled>3. 保存持仓并启动后台刷新</button>
      <div id="refresh-panel" class="refresh-panel" hidden>
        <div class="refresh-head">
          <strong id="refresh-title">刷新任务</strong>
          <span id="refresh-progress">0%</span>
        </div>
        <p class="sub">页面重载只恢复任务状态；若本地服务进程重启，未完成任务会标记为中断，不会自动续跑。</p>
        <div id="refresh-steps" class="refresh-steps"></div>
        <button class="secondary" id="retry-refresh" type="button" hidden>重试全量刷新</button>
      </div>
    </section>
    <section>
      <div id="output" class="output">
        <div class="summary">等待本地解析。</div>
      </div>
    </section>
  </main>
  <script>{_script(token)}</script>
</body>
</html>"""


def _styles() -> str:
    return """
:root{color-scheme:dark;--bg:#071014;--panel:#10191d;--line:#344a50;--text:#eaf4f1;--muted:#91a6a1;--good:#62dfa2;--warn:#f3c269;--bad:#ff8b8b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
main{width:min(960px,calc(100% - 28px));margin:24px auto}section{padding:18px;border:1px solid #26383d;border-radius:10px;background:var(--panel);margin-bottom:12px}
h1{margin:12px 0 6px}p{color:var(--muted)}textarea{width:100%;min-height:190px;margin-top:10px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);resize:vertical}
button,.button{display:inline-flex;align-items:center;justify-content:center;margin:8px 8px 0 0;padding:9px 13px;border:0;border-radius:7px;background:var(--good);color:#062014;font-weight:800;cursor:pointer;text-decoration:none}
button.secondary,.button.secondary{background:#25353a;color:var(--text)}button.danger{background:#6b3030;color:#fff}button[disabled]{opacity:.45;cursor:not-allowed}.warn{color:var(--warn)}
.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.approval{display:inline-block;margin:10px 8px 0 0;padding:9px 12px;border:1px solid var(--line);border-radius:7px}
.summary{padding:10px;border-radius:8px;background:var(--bg);color:#b8cbc6}.output{overflow:auto}.output table{width:100%;min-width:660px;border-collapse:collapse}.output th,.output td{padding:9px;border-bottom:1px solid #26383d;text-align:left}.output th{color:var(--muted)}
.refresh-panel{margin-top:14px;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--bg)}.refresh-panel[hidden]{display:none}.refresh-head,.refresh-step{display:flex;justify-content:space-between;gap:12px}.refresh-steps{display:grid;gap:6px;margin-top:10px}.refresh-step{padding:7px 9px;background:var(--panel)}.refresh-step.failed,.refresh-step.interrupted{color:var(--bad)}.refresh-step.completed{color:var(--good)}
@media(max-width:640px){main{width:min(100% - 18px,960px);margin:9px auto}section{padding:13px}}
body{background:#071522;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#f3f0e8}
main{width:min(1020px,calc(100% - 32px));margin:30px auto}section{padding:30px;border-color:#294251;border-radius:15px;background:#0b1e2c}.toolbar{justify-content:space-between;margin-bottom:28px}.toolbar .danger{background:transparent;color:#9ab0bb;font-size:12px}.toolbar .secondary{background:#162e3d}
.import-kicker{font-size:11px;letter-spacing:.09em;color:#a7cdbd}h1{font-size:30px;letter-spacing:-.035em;font-weight:600;margin-top:12px}p{color:#99afbc;line-height:1.8}.import-steps{display:flex;gap:28px;border-bottom:1px solid #294251;margin:26px 0 24px;color:#7893a2;font-size:12px}.import-steps span{padding-bottom:13px}.import-steps .current{color:#bddfcd;border-bottom:2px solid #bddfcd}
.file-label,.paste-label{display:block;color:#b2c7d1;font-size:13px;margin-bottom:9px}.file-label small{color:#7c99a8;margin-left:10px}input[type=file]{max-width:100%;color:#8ba4b2;font-size:12px}input[type=file]::file-selector-button{border:1px solid #375363;border-radius:7px;background:#152e3c;color:#c1d7df;padding:9px 13px;margin-right:10px;cursor:pointer}.paste-label{margin-top:22px}textarea{padding:16px;border:1px solid #314d5d;background:#071824;line-height:1.7;font-size:13px}textarea:focus{outline:2px solid #8abbaa;outline-offset:2px}button,.button{background:#bddfcd;color:#142a2c;font-weight:600;padding:11px 16px}.summary{background:#102735;color:#9cb8c6;padding:13px;font-size:12px}.approval{display:flex;align-items:center;gap:8px;border:0;padding:10px 0}.approval input{accent-color:#bddfcd}.output:empty{display:none}
@media(max-width:620px){section{padding:20px}h1{font-size:25px}.import-steps{gap:15px;font-size:10px}.toolbar{gap:4px;margin-bottom:24px}.toolbar .button{padding:8px 10px;font-size:12px}}

"""


def _script(token: str) -> str:
    safe_token = json.dumps(token)
    return f"""
const token={safe_token};
let previewState=null;
let refreshTimer=null;
const $=id=>document.getElementById(id);
const requestId=()=>globalThis.crypto?.randomUUID?.()??`refresh-${{Date.now()}}-${{Math.random()}}`;

async function post(path, approved=false, extra={{}}) {{
  const response=await fetch(path,{{
    method:"POST",
    headers:{{"Content-Type":"application/json","X-InsightRadar-Token":token}},
    body:JSON.stringify({{
      text:$("text").value,
      approved,
      ...extra,
    }}),
  }});
  const result=await response.json();
  if(!response.ok) throw new Error(result.error||"请求失败");
  return result;
}}

async function getJson(path) {{
  const response=await fetch(path,{{
    headers:{{"X-InsightRadar-Token":token}},
    cache:"no-store",
  }});
  const result=await response.json();
  if(!response.ok) throw new Error(result.error||"读取状态失败");
  return result;
}}

function renderPreview(data) {{
  const output=$("output");
  output.replaceChildren();
  const risk=document.createElement("div");
  risk.className="summary";
  risk.textContent=`持仓 ${{data.proposed_portfolio.holdings.length}} 只｜仓位 ${{data.risk_reconciliation.total_exposure_pct??"未提供"}}%｜风险对账 ${{data.risk_reconciliation.status}}：${{data.risk_reconciliation.reason}}`;
  output.appendChild(risk);
  const table=document.createElement("table");
  const thead=document.createElement("thead");
  const head=document.createElement("tr");
  for(const text of ["状态","代码","名称","原股数","新股数","新仓位","beta"]) {{
    const th=document.createElement("th");
    th.textContent=text;
    head.appendChild(th);
  }}
  thead.appendChild(head);
  table.appendChild(thead);
  const tbody=document.createElement("tbody");
  for(const diff of data.differences) {{
    const tr=document.createElement("tr");
    const values=[
      diff.status,
      diff.code,
      diff.new?.name??diff.old?.name??"",
      diff.old?.shares??"—",
      diff.new?.shares??"—",
      diff.new?.weight_pct??"—",
      diff.new?"后台自动计算":"—",
    ];
    for(const value of values) {{
      const td=document.createElement("td");
      td.textContent=String(value);
      tr.appendChild(td);
    }}
    tbody.appendChild(tr);
  }}
  table.appendChild(tbody);
  output.appendChild(table);
  for(const warning of data.validation.warnings) {{
    const note=document.createElement("p");
    note.className="warn";
    note.textContent=warning;
    output.appendChild(note);
  }}
}}

function renderRefresh(job) {{
  if(!job||job.status==="none") return;
  $("refresh-panel").hidden=false;
  const terminalFailure=["failed","interrupted"].includes(job.status);
  const restartRequired=String(job.error??"").includes("重新启动 InsightRadar");
  $("retry-refresh").hidden=!terminalFailure||restartRequired;
  const done=Number(job.completed_steps??0);
  const total=Number(job.total_steps??0);
  $("refresh-progress").textContent=`${{total?Math.round(done/total*100):0}}%`;
  $("refresh-title").textContent=
    job.status==="completed"?"刷新完成":
    job.status==="failed"?`刷新失败：${{job.failed_step??"unknown"}}`:
    job.status==="interrupted"?"刷新已中断":"后台串行刷新中";
  $("refresh-steps").replaceChildren();
  for(const step of job.steps??[]) {{
    const row=document.createElement("div");
    row.className=`refresh-step ${{step.status}}`;
    const name=document.createElement("span");
    name.textContent=step.workflow;
    const state=document.createElement("strong");
    state.textContent=step.status;
    row.append(name,state);
    $("refresh-steps").appendChild(row);
  }}
  if(terminalFailure) {{
    $("status").textContent=restartRequired
      ?`${{job.error}} 请点击右上角“关闭本地应用”，再双击 InsightRadar.cmd。`
      :`刷新未完成：${{job.failed_step??job.current_step??"服务中断"}}。${{job.error??""}} 已保存的持仓不受影响，上一份报告仍保留为旧版本。`;
  }} else if(job.status==="completed") {{
    $("status").textContent="后台刷新完成，可以返回行动简报。";
  }}
}}

async function pollRefresh(runId) {{
  clearTimeout(refreshTimer);
  try {{
    const job=await getJson(`/api/refresh/${{runId}}`);
    renderRefresh(job);
    if(["pending","running"].includes(job.status)) {{
      refreshTimer=setTimeout(()=>pollRefresh(runId),900);
    }}
  }} catch(error) {{
    $("status").textContent="读取刷新进度失败："+error.message;
  }}
}}

async function recoverRefresh() {{
  try {{
    const job=await getJson("/api/refresh/active");
    if(job.status!=="none") {{
      renderRefresh(job);
      if(["pending","running"].includes(job.status)) pollRefresh(job.run_id);
    }}
  }} catch(error) {{
    console.warn(error);
  }}
}}

$("retry-refresh").addEventListener("click",async()=>{{
  $("retry-refresh").hidden=true;
  $("status").textContent="正在重新发起全量刷新…";
  try {{
    const job=await post("/api/refresh",false,{{mode:"full",request_id:requestId()}});
    renderRefresh(job);
    pollRefresh(job.run_id);
  }} catch(error) {{
    $("status").textContent="无法重新发起刷新："+error.message;
    $("retry-refresh").hidden=false;
  }}
}});

async function runPreview() {{
  try {{
    previewState=await post("/api/preview");
    renderPreview(previewState);
    const risk=previewState.risk_reconciliation;
    $("status").textContent=previewState.validation.valid
      ?`已识别 ${{previewState.proposed_portfolio.holdings.length}} 只；请核对差异。保存后先自动计算 beta，再进行风险对账。`
      :"校验失败；不得保存";
    $("apply").disabled=!previewState.validation.valid||!$("approved").checked;
  }} catch(error) {{
    previewState=null;
    $("apply").disabled=true;
    $("status").textContent="解析失败："+error.message;
  }}
}}

$("file").addEventListener("change",async()=>{{
  if($("file").files[0]) {{
    $("text").value=await $("file").files[0].text();
    await runPreview();
  }}
}});
$("preview").addEventListener("click",runPreview);
$("approved").addEventListener("change",()=>{{
  $("apply").disabled=!(previewState&&previewState.validation.valid&&$("approved").checked);
}});
$("apply").addEventListener("click",async()=>{{
  if(!$("approved").checked||!previewState) return;
  $("apply").disabled=true;
  $("status").textContent="正在保存持仓…";
  try {{
    const result=await post("/api/apply",true,{{request_id:requestId()}});
    const output=$("output");
    output.replaceChildren();
    const done=document.createElement("div");
    done.className="summary";
    done.textContent=`持仓已保存到 ${{result.portfolio_path}}。后台刷新已取得任务号，关闭或刷新页面不会丢失状态。`;
    const link=document.createElement("a");
    link.className="button";
    link.href="/#today";
    link.textContent="返回行动简报";
    output.append(done,link);
    $("status").textContent="持仓已保存；后台正在串行刷新。";
    renderRefresh(result.refresh_job);
    pollRefresh(result.refresh_job.run_id);
  }} catch(error) {{
    $("status").textContent="保存或启动刷新失败："+error.message;
    $("apply").disabled=false;
  }}
}});
$("shutdown").addEventListener("click",async()=>{{
  $("shutdown").disabled=true;
  await post("/api/shutdown");
  document.body.innerHTML="<main><section><h1>InsightRadar 已关闭</h1><p>可以关闭此页面。</p></section></main>";
}});
recoverRefresh();
"""
