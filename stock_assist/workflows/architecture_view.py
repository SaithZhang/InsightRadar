"""Generate the interactive InsightRadar workflow architecture view."""

from __future__ import annotations

import html
import hashlib
import json
from pathlib import Path

from stock_assist.branding import PRODUCT_NAME, PRODUCT_SLUG, PRODUCT_TAGLINE
from stock_assist.paths import CONFIG_DIR, PROJECT_ROOT, ensure_runtime_dirs


DEFAULT_ARCHITECTURE_PATH = CONFIG_DIR / "architecture.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "docs" / "architecture.html"


def architecture_source_digest(source_bytes: bytes) -> str:
    """Hash architecture JSON independently of checkout line endings."""
    normalized = source_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def build_architecture_view(
    config_path: Path = DEFAULT_ARCHITECTURE_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    ensure_runtime_dirs()
    output_path.parent.mkdir(exist_ok=True)
    source_bytes = config_path.read_bytes()
    payload = json.loads(source_bytes.decode("utf-8"))
    source_digest = architecture_source_digest(source_bytes)
    output_path.write_bytes(_render_html(payload, source_digest).encode("utf-8"))
    return output_path


def _render_html(payload: dict[str, object], source_digest: str) -> str:
    state = json.dumps(payload, ensure_ascii=False)
    escaped_state = html.escape(state, quote=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="architecture-source-sha256" content="{source_digest}">
  <title>{PRODUCT_NAME} 架构拓扑</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d8dee8;
      --accent: #0f766e;
      --accent-soft: #dff5f1;
      --blue: #2563eb;
      --warn: #b45309;
      --purple: #7c3aed;
      --shadow: 0 12px 30px rgba(24, 39, 75, 0.09);
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; min-height: 100%; }}
    body {{
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    button {{ font: inherit; }}
    .app {{ display: grid; grid-template-columns: 270px minmax(720px, 1fr) 330px; min-height: 100vh; }}
    .sidebar, .inspector {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      background: var(--panel);
      padding: 18px;
      border-right: 1px solid var(--line);
    }}
    .inspector {{ border-right: 0; border-left: 1px solid var(--line); }}
    .brand {{ display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }}
    .brand-mark {{
      width: 36px;
      height: 36px;
      border-radius: 10px;
      display: grid;
      place-items: center;
      color: #fff;
      background: var(--accent);
      font-weight: 800;
    }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ margin-bottom: 3px; font-size: 21px; }}
    h2 {{ margin-bottom: 10px; color: var(--muted); font-size: 13px; text-transform: uppercase; }}
    h3 {{ margin-bottom: 8px; font-size: 15px; }}
    .subtle {{ color: var(--muted); font-size: 13px; line-height: 1.55; }}
    .memory-note {{
      margin: 0 0 16px;
      border: 1px solid #b9e6dc;
      border-radius: 10px;
      padding: 10px;
      color: #0b625c;
      background: #edfdf9;
      font-size: 12px;
      line-height: 1.5;
    }}
    .module-list, .ideas {{ display: grid; gap: 8px; }}
    .module-row {{
      width: 100%;
      text-align: left;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      color: var(--ink);
      background: #fff;
      cursor: pointer;
    }}
    .module-row.active {{ border-color: var(--accent); background: var(--accent-soft); }}
    .module-title {{ margin-bottom: 5px; font-size: 14px; font-weight: 750; }}
    .tag {{
      display: inline-flex;
      align-items: center;
      min-height: 21px;
      margin: 3px 4px 0 0;
      border-radius: 999px;
      padding: 0 7px;
      color: #344054;
      background: #eef2f7;
      font-size: 11px;
    }}
    .tag.active, .tag.wired, .tag.source_of_truth {{ color: var(--accent); background: var(--accent-soft); }}
    .tag.research_only, .tag.evidence_mvp {{ color: var(--blue); background: #e8f0ff; }}
    .tag.gated {{ color: var(--warn); background: #fff2d6; }}
    .tag.resident {{ color: var(--purple); background: #f1eafe; }}
    .detail-section {{ margin-top: 15px; border-top: 1px solid var(--line); padding-top: 14px; }}
    .idea {{ border: 1px solid var(--line); border-radius: 10px; padding: 10px; background: #fff; }}
    .idea strong {{ font-size: 13px; }}
    .idea p {{ margin: 6px 0 0; }}
    .canvas-wrap {{ min-width: 0; overflow: auto; padding: 18px; }}
    .canvas-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 14px; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .toolbar button {{
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 11px;
      color: var(--ink);
      background: #fff;
      cursor: pointer;
    }}
    .toolbar .primary {{ border-color: var(--accent); color: #fff; background: var(--accent); }}
    .canvas {{
      position: relative;
      min-width: 1480px;
      min-height: 900px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 12px;
      background:
        linear-gradient(90deg, rgba(15, 118, 110, 0.05) 1px, transparent 1px),
        linear-gradient(rgba(15, 118, 110, 0.05) 1px, transparent 1px),
        #fff;
      background-size: 28px 28px;
      box-shadow: var(--shadow);
    }}
    .lane {{ position: absolute; top: 0; bottom: 0; border-right: 1px solid var(--line); padding: 13px; pointer-events: none; }}
    .lane:last-child {{ border-right: 0; }}
    .lane-title {{ font-size: 13px; font-weight: 800; }}
    .lane-desc {{ margin-top: 4px; max-width: 240px; color: var(--muted); font-size: 11px; line-height: 1.35; }}
    svg.edges {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }}
    .node {{
      position: absolute;
      min-height: 112px;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 11px;
      background: #fff;
      box-shadow: 0 8px 20px rgba(20, 24, 31, 0.08);
      cursor: grab;
      user-select: none;
    }}
    .node.active {{ outline: 3px solid rgba(15, 118, 110, 0.18); border-color: var(--accent); }}
    .node-top {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 6px; margin-bottom: 7px; }}
    .node-name {{ font-size: 14px; font-weight: 800; line-height: 1.3; }}
    .node-summary {{ color: var(--muted); font-size: 11px; line-height: 1.42; }}
    code {{ display: block; white-space: normal; word-break: break-word; border: 1px solid var(--line); border-radius: 8px; padding: 9px; background: #f8fafc; font-size: 12px; line-height: 1.5; }}
    ul {{ margin: 8px 0 0; padding-left: 18px; color: #344054; font-size: 13px; line-height: 1.6; }}
    @media (max-width: 1180px) {{ .app {{ grid-template-columns: 230px minmax(720px, 1fr); }} .inspector {{ display: none; }} }}
    @media (max-width: 760px) {{ .app {{ display: block; }} .sidebar, .inspector {{ position: static; width: auto; height: auto; border: 0; }} .sidebar {{ display: none; }} .canvas-wrap {{ padding: 12px; }} .canvas-head {{ display: block; }} .toolbar {{ margin-top: 10px; }} }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">IR</div>
        <div><h1>{PRODUCT_NAME}</h1><div class="subtle">{PRODUCT_TAGLINE}</div></div>
      </div>
      <div class="memory-note">长期入口：<strong>PROJECT_MEMORY.md</strong><br>图源：<strong>configs/architecture.json</strong></div>
      <h2>模块</h2>
      <div id="moduleList" class="module-list"></div>
      <div class="detail-section"><h2>当前演进原则</h2><div id="ideas" class="ideas"></div></div>
    </aside>
    <main class="canvas-wrap">
      <div class="canvas-head">
        <div><h1>InsightRadar 架构拓扑</h1><p class="subtle">数据 → 研究/市场 → 组合决策 → 后验反馈。拖动节点只保存本机布局，不改写配置。</p></div>
        <div class="toolbar"><button id="resetLayout">重置布局</button><button id="fitView" class="primary">自动排列</button></div>
      </div>
      <section id="canvas" class="canvas"><svg id="edges" class="edges"></svg></section>
    </main>
    <aside class="inspector"><h2>节点详情</h2><div id="inspector"></div></aside>
  </div>
  <script id="architecture-data" type="application/json">{escaped_state}</script>
  <script>
    const graph = JSON.parse(document.getElementById('architecture-data').textContent);
    const canvas = document.getElementById('canvas');
    const edgesSvg = document.getElementById('edges');
    const list = document.getElementById('moduleList');
    const inspector = document.getElementById('inspector');
    const ringLabels = {{ core: '核心', lab: '实验室', satellite: '卫星应用', extension: '可选扩展', governance: '治理' }};
    function ringLabel(node) {{ return ringLabels[node.ring] || node.ring || '未分类'; }}
    const ideas = document.getElementById('ideas');
    const layoutKey = '{PRODUCT_SLUG}-architecture-layout-v2';
    let activeId = graph.nodes[0]?.id;
    let saved = JSON.parse(localStorage.getItem(layoutKey) || '{{}}');

    function laneWidth() {{ return canvas.clientWidth / graph.lanes.length; }}
    function laneCount(laneId) {{ return graph.nodes.filter(node => node.lane === laneId).length; }}
    function ensureCanvasHeight() {{
      const maxCount = Math.max(1, ...graph.lanes.map(lane => laneCount(lane.id)));
      canvas.style.height = `${{Math.max(900, 112 + maxCount * 148)}}px`;
    }}
    function defaultPosition(node) {{
      const laneIndex = Math.max(0, graph.lanes.findIndex(lane => lane.id === node.lane));
      const order = graph.nodes.filter(item => item.lane === node.lane).findIndex(item => item.id === node.id);
      return {{ x: laneIndex * laneWidth() + 22, y: 84 + order * 148 }};
    }}
    function positionFor(node) {{ return saved[node.id] || defaultPosition(node); }}
    function selectNode(id) {{ activeId = id; render(); }}

    function render() {{
      ensureCanvasHeight();
      canvas.querySelectorAll('.lane,.node').forEach(item => item.remove());
      renderLanes();
      renderNodes();
      renderList();
      renderIdeas();
      renderInspector();
      requestAnimationFrame(renderEdges);
    }}
    function renderLanes() {{
      const width = laneWidth();
      graph.lanes.forEach((lane, index) => {{
        const el = document.createElement('div');
        el.className = 'lane';
        el.style.left = `${{index * width}}px`;
        el.style.width = `${{width}}px`;
        el.innerHTML = `<div class="lane-title">${{lane.title}}</div><div class="lane-desc">${{lane.description}}</div>`;
        canvas.appendChild(el);
      }});
    }}
    function renderNodes() {{
      const width = laneWidth();
      graph.nodes.forEach(node => {{
        const pos = positionFor(node);
        const el = document.createElement('article');
        el.className = `node ${{node.id === activeId ? 'active' : ''}}`;
        el.dataset.id = node.id;
        el.style.left = `${{pos.x}}px`;
        el.style.top = `${{pos.y}}px`;
        el.style.width = `${{Math.min(252, width - 44)}}px`;
        el.innerHTML = `<div class="node-top"><div class="node-name">${{node.title}}</div><span class="tag ${{node.status}}">${{node.status}}</span></div><div class="node-summary">${{node.summary}}</div><span class="tag">${{ringLabel(node)}}</span><span class="tag">${{node.type}}</span>`;
        el.addEventListener('pointerdown', startDrag);
        el.addEventListener('click', () => selectNode(node.id));
        canvas.appendChild(el);
      }});
    }}
    function renderList() {{
      list.innerHTML = '';
      graph.nodes.forEach(node => {{
        const row = document.createElement('button');
        row.className = `module-row ${{node.id === activeId ? 'active' : ''}}`;
        row.innerHTML = `<div class="module-title">${{node.title}}</div><span class="tag ${{node.status}}">${{node.status}}</span><span class="tag">${{ringLabel(node)}}</span><span class="tag">${{node.lane}}</span>`;
        row.addEventListener('click', () => selectNode(node.id));
        list.appendChild(row);
      }});
    }}
    function renderIdeas() {{
      ideas.innerHTML = graph.ideas.map(idea => `<div class="idea"><strong>${{idea.priority}} · ${{idea.title}}</strong><p class="subtle">${{idea.detail}}</p></div>`).join('');
    }}
    function renderInspector() {{
      const node = graph.nodes.find(item => item.id === activeId);
      if (!node) {{ inspector.innerHTML = '<p class="subtle">请选择一个节点。</p>'; return; }}
      inspector.innerHTML = `
        <h1>${{node.title}}</h1><p class="subtle">${{node.summary}}</p>
        <span class="tag ${{node.status}}">${{node.status}}</span><span class="tag">${{ringLabel(node)}}</span><span class="tag">${{node.type}}</span>
        <div class="detail-section"><h3>运行/位置</h3><code>${{node.command}}</code></div>
        <div class="detail-section"><h3>输入</h3><ul>${{node.inputs.map(item => `<li>${{item}}</li>`).join('')}}</ul></div>
        <div class="detail-section"><h3>输出</h3><ul>${{node.outputs.map(item => `<li>${{item}}</li>`).join('')}}</ul></div>
        <div class="detail-section"><h3>下一步</h3><ul>${{node.next.map(item => `<li>${{item}}</li>`).join('')}}</ul></div>`;
    }}
    function renderEdges() {{
      edgesSvg.innerHTML = '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#98a2b3"></path></marker></defs>';
      const rect = canvas.getBoundingClientRect();
      graph.edges.forEach(edge => {{
        const from = canvas.querySelector(`[data-id="${{edge.from}}"]`);
        const to = canvas.querySelector(`[data-id="${{edge.to}}"]`);
        if (!from || !to) return;
        const a = from.getBoundingClientRect();
        const b = to.getBoundingClientRect();
        const x1 = a.left - rect.left + a.width;
        const y1 = a.top - rect.top + a.height / 2;
        const x2 = b.left - rect.left;
        const y2 = b.top - rect.top + b.height / 2;
        const bend = Math.max(35, Math.abs(x2 - x1) / 2);
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', `M ${{x1}} ${{y1}} C ${{x1 + bend}} ${{y1}}, ${{x2 - bend}} ${{y2}}, ${{x2}} ${{y2}}`);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#98a2b3');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('marker-end', 'url(#arrow)');
        edgesSvg.appendChild(path);
      }});
    }}
    function startDrag(event) {{
      const nodeEl = event.currentTarget;
      const id = nodeEl.dataset.id;
      activeId = id;
      const startX = event.clientX;
      const startY = event.clientY;
      const initial = {{ x: parseFloat(nodeEl.style.left), y: parseFloat(nodeEl.style.top) }};
      nodeEl.setPointerCapture(event.pointerId);
      function move(moveEvent) {{
        const x = Math.max(8, initial.x + moveEvent.clientX - startX);
        const y = Math.max(70, initial.y + moveEvent.clientY - startY);
        saved[id] = {{ x, y }};
        nodeEl.style.left = `${{x}}px`;
        nodeEl.style.top = `${{y}}px`;
        renderEdges();
      }}
      function up() {{
        localStorage.setItem(layoutKey, JSON.stringify(saved));
        nodeEl.removeEventListener('pointermove', move);
        nodeEl.removeEventListener('pointerup', up);
        render();
      }}
      nodeEl.addEventListener('pointermove', move);
      nodeEl.addEventListener('pointerup', up);
    }}
    document.getElementById('resetLayout').addEventListener('click', () => {{ saved = {{}}; localStorage.removeItem(layoutKey); render(); }});
    document.getElementById('fitView').addEventListener('click', () => {{ saved = {{}}; graph.nodes.forEach(node => saved[node.id] = defaultPosition(node)); localStorage.setItem(layoutKey, JSON.stringify(saved)); render(); }});
    window.addEventListener('resize', () => {{ if (Object.keys(saved).length === 0) render(); else renderEdges(); }});
    render();
  </script>
</body>
</html>
"""
