"""Markdown report helpers."""

from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
import re

from stock_assist.branding import PRODUCT_NAME, PRODUCT_SLUG
from stock_assist.paths import REPORT_DIR, ensure_runtime_dirs


def write_report(name: str, content: str) -> Path:
    ensure_runtime_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"{stamp}-{name}.md"
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def write_report_pair(name: str, content: str) -> tuple[Path, Path]:
    """Write matching Markdown and HTML reports with the same timestamp."""

    ensure_runtime_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_path = REPORT_DIR / f"{stamp}-{name}.md"
    html_path = REPORT_DIR / f"{stamp}-{name}.html"
    md_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    html_path.write_text(markdown_report_to_html(content), encoding="utf-8")
    return md_path, html_path


def write_custom_html_report_pair(name: str, content: str, html: str) -> tuple[Path, Path]:
    """Write matching Markdown and caller-rendered HTML reports with the same timestamp."""

    ensure_runtime_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_path = REPORT_DIR / f"{stamp}-{name}.md"
    html_path = REPORT_DIR / f"{stamp}-{name}.html"
    md_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return md_path, html_path


def write_payload_report_triplet(
    name: str,
    payload: dict[str, object],
    content: str,
    html: str,
) -> tuple[Path, Path, Path]:
    """Write matching JSON payload, Markdown, and caller-rendered HTML reports."""

    ensure_runtime_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = REPORT_DIR / f"{stamp}-{name}.json"
    md_path = REPORT_DIR / f"{stamp}-{name}.md"
    html_path = REPORT_DIR / f"{stamp}-{name}.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return json_path, md_path, html_path


def bullet(items: list[str]) -> str:
    if not items:
        return "- 暂无"
    return "\n".join(f"- {item}" for item in items)


def markdown_report_to_html(content: str) -> str:
    """Render the project's compact Markdown reports as a readable HTML page."""

    title = _extract_title(content)
    subtitle = (
        "先看多空、情绪阶段、板块温度与大V变化；完整帖子证据按需展开。"
        if "## 情绪仪表盘" in content and "## 大V观点与转向" in content
        else "跨市场环境、组合风险、同业锚和事件线索集中在一个盘后工作台。"
    )
    dashboard = _build_dashboard(content)
    body = _markdown_body_to_html(content)
    portfolio_import_enabled = title == "盘后持仓操作指引" or "## 核心可靠性" in content
    portfolio_button = _portfolio_import_button() if portfolio_import_enabled else ""
    portfolio_modal = _portfolio_import_modal() if portfolio_import_enabled else ""
    portfolio_script = _portfolio_import_script() if portfolio_import_enabled else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070a0d;
      --panel: #10161a;
      --panel-2: #141c22;
      --ink: #ecf3f2;
      --muted: #8fa19d;
      --line: #26333a;
      --accent: #5ee0a0;
      --accent-2: #74a9ff;
      --gold: #f0c35b;
      --risk: #ff6b7f;
      --ok: #58d68d;
      --warn: #f7bd61;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 18% 0%, rgba(94, 224, 160, 0.13), transparent 32%),
        radial-gradient(circle at 82% 12%, rgba(116, 169, 255, 0.10), transparent 34%),
        linear-gradient(180deg, #070a0d 0%, #0a0e12 42%, #070a0d 100%);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      line-height: 1.55;
      overflow-x: hidden;
      overflow-wrap: anywhere;
    }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 54px;
      padding: 0 24px;
      border-bottom: 1px solid rgba(255,255,255,0.07);
      background: rgba(7, 10, 13, 0.82);
      backdrop-filter: blur(16px);
    }}
    .brand {{
      display: flex;
      gap: 10px;
      align-items: center;
      font-weight: 700;
    }}
    .mark {{
      width: 28px;
      height: 28px;
      display: grid;
      place-items: center;
      border-radius: 7px;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #06100d;
      font-weight: 900;
    }}
    .top-meta {{
      color: var(--muted);
      font-size: 13px;
    }}
    .top-actions {{ display: flex; align-items: center; gap: 12px; }}
    .ui-button {{
      appearance: none;
      border: 1px solid rgba(94, 224, 160, 0.38);
      border-radius: 8px;
      padding: 8px 13px;
      color: #07110d;
      background: linear-gradient(135deg, var(--accent), #8aebba);
      font: inherit;
      font-size: 13px;
      font-weight: 800;
      cursor: pointer;
    }}
    .ui-button.secondary {{ color: var(--ink); background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.14); }}
    .ui-button:hover {{ filter: brightness(1.06); text-decoration: none; }}
    main {{
      width: min(1360px, calc(100% - 32px));
      margin: 0 auto;
      padding: 14px 0 52px;
    }}
    .report-title {{
      margin: 0 0 3px;
      font-size: 22px;
      line-height: 1.25;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .dashboard {{
      display: grid;
      gap: 12px;
      margin-bottom: 18px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(360px, 0.75fr);
      gap: 16px;
    }}
    .hero-panel, .metric-card, .chart-panel, .market-card {{
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(20, 28, 34, 0.92), rgba(12, 17, 21, 0.92));
      border-radius: 8px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.22);
    }}
    .hero-panel {{
      padding: 11px 16px;
      min-height: 0;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      margin-bottom: 6px;
      padding: 4px 10px;
      border: 1px solid rgba(94, 224, 160, 0.28);
      border-radius: 999px;
      color: var(--accent);
      background: rgba(94, 224, 160, 0.08);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .hero-copy {{
      margin: 0;
      max-width: 760px;
      color: #b8c7c4;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .metric-card {{
      padding: 15px;
    }}
    .brief-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) repeat(3, minmax(180px, 0.55fr));
      gap: 12px;
    }}
    .brief-card, .decision-card {{
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(20, 28, 34, 0.92), rgba(12, 17, 21, 0.92));
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 18px 48px rgba(0,0,0,0.20);
    }}
    .brief-card.primary {{
      border-color: rgba(94, 224, 160, 0.24);
    }}
    .brief-label, .decision-label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .brief-value {{
      margin-top: 8px;
      font-size: 26px;
      font-weight: 900;
      line-height: 1.2;
    }}
    .brief-note {{
      margin-top: 8px;
      color: #b8c7c4;
      font-size: 13px;
    }}
    .operator-strip {{
      display: grid;
      grid-template-columns: repeat(10, minmax(0, 1fr));
      gap: 7px;
      padding: 9px;
      border: 1px solid rgba(94,224,160,0.22);
      border-radius: 10px;
      background: linear-gradient(90deg, rgba(94,224,160,0.08), rgba(116,169,255,0.06));
    }}
    .operator-cell {{ min-width: 0; padding: 7px 8px; border-right: 1px solid rgba(255,255,255,0.07); }}
    .operator-cell:last-child {{ border-right: 0; }}
    .operator-cell span {{ display: block; color: var(--muted); font-size: 10px; font-weight: 800; }}
    .operator-cell b {{ display: block; margin-top: 2px; font-size: 13px; line-height: 1.25; overflow-wrap: anywhere; }}
    .operator-cell.action {{ grid-column: span 2; }}
    .battle-timeline {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }}
    .timeline-card {{
      min-width: 0;
      padding: 10px 11px;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      background: rgba(14,20,24,0.94);
    }}
    .timeline-time {{ color: var(--accent-2); font-size: 11px; font-weight: 900; }}
    .timeline-observe {{ margin-top: 4px; color: #dbe7e4; font-size: 12px; line-height: 1.35; overflow-wrap: anywhere; }}
    .timeline-state {{ margin-top: 5px; color: var(--warn); font-size: 11px; font-weight: 800; }}
    .timeline-action {{ margin-top: 4px; color: var(--muted); font-size: 11px; line-height: 1.35; overflow-wrap: anywhere; }}
    .regime-panel {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .gauge-card, .level-panel, .structure-panel {{
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 10px;
      background: linear-gradient(160deg, rgba(23, 33, 39, 0.96), rgba(10, 15, 19, 0.96));
      box-shadow: 0 18px 48px rgba(0,0,0,0.22);
    }}
    .gauge-card {{ padding: 16px; text-align: center; }}
    .gauge-ring {{
      --score: 0;
      --gauge-color: var(--risk);
      position: relative;
      width: 128px;
      height: 128px;
      margin: 12px auto 8px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: conic-gradient(var(--gauge-color) calc(var(--score) * 1%), rgba(255,255,255,0.07) 0);
    }}
    .gauge-ring::before {{
      content: '';
      position: absolute;
      inset: 11px;
      border-radius: 50%;
      background: #0d1317;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);
    }}
    .gauge-number {{ position: relative; z-index: 1; font-size: 29px; font-weight: 900; line-height: 1; }}
    .gauge-number small {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    .gauge-label {{ font-size: 15px; font-weight: 900; }}
    .gauge-note {{ min-height: 34px; margin-top: 5px; color: var(--muted); font-size: 11px; line-height: 1.4; }}
    .level-panel, .structure-panel {{ grid-column: span 2; padding: 16px; }}
    .level-heading {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 12px; }}
    .level-heading span {{ color: var(--muted); font-size: 11px; }}
    .level-ladder {{ display: grid; gap: 8px; }}
    .level-row {{
      display: grid;
      grid-template-columns: 82px minmax(88px, auto) 1fr;
      gap: 10px;
      align-items: center;
      padding: 8px 10px;
      border-radius: 7px;
      background: rgba(255,255,255,0.035);
      font-size: 12px;
    }}
    .level-row b {{ font: 900 14px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .level-row span:last-child {{ color: var(--muted); }}
    .level-row.support {{ border-left: 3px solid var(--risk); }}
    .level-row.confirm {{ border-left: 3px solid var(--warn); }}
    .level-row.resistance {{ border-left: 3px solid var(--accent-2); }}
    .level-row.repair {{ border-left: 3px solid var(--accent); }}
    .structure-metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; }}
    .structure-metric {{ padding: 10px; border-radius: 7px; background: rgba(255,255,255,0.035); }}
    .structure-metric span {{ display: block; color: var(--muted); font-size: 11px; }}
    .structure-metric b {{ display: block; margin-top: 3px; font: 900 18px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .structure-callout {{ margin-top: 8px; padding: 9px 10px; border-left: 3px solid var(--warn); border-radius: 6px; color: #d8e1df; background: rgba(247,189,97,0.08); font-size: 12px; }}
    .decision-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 12px;
    }}
    .decision-card {{
      min-height: 176px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .decision-card.risk {{ border-color: rgba(255, 107, 127, 0.36); }}
    .decision-card.warn {{ border-color: rgba(247, 189, 97, 0.30); }}
    .decision-card.ok {{ border-color: rgba(88, 214, 141, 0.28); }}
    .decision-top {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
    }}
    .decision-name {{
      font-size: 16px;
      font-weight: 900;
      line-height: 1.25;
    }}
    .action-tag {{
      flex: 0 0 auto;
      max-width: 116px;
      padding: 4px 8px;
      border-radius: 999px;
      background: rgba(255,255,255,0.07);
      font-size: 12px;
      font-weight: 800;
      text-align: center;
    }}
    .action-tag.risk {{ color: var(--risk); background: rgba(255, 107, 127, 0.11); }}
    .action-tag.warn {{ color: var(--warn); background: rgba(247, 189, 97, 0.11); }}
    .action-tag.ok {{ color: var(--ok); background: rgba(88, 214, 141, 0.10); }}
    .decision-reason {{
      color: #dce8e5;
      font-size: 13px;
      line-height: 1.45;
    }}
    .decision-risk {{
      margin-top: auto;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    .decision-metrics {{
      display: flex;
      gap: 12px;
      color: var(--muted);
      font-size: 12px;
    }}
    .priority-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .priority-card {{
      min-height: 144px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 16px;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      background: linear-gradient(180deg, rgba(20, 28, 34, 0.92), rgba(12, 17, 21, 0.92));
      box-shadow: 0 18px 48px rgba(0,0,0,0.18);
    }}
    .priority-card.risk {{ border-color: rgba(255, 107, 127, 0.34); }}
    .priority-card.warn {{ border-color: rgba(247, 189, 97, 0.30); }}
    .priority-card.ok {{ border-color: rgba(88, 214, 141, 0.25); }}
    .priority-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}
    .priority-rank {{
      display: grid;
      place-items: center;
      width: 26px;
      height: 26px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      color: var(--ink);
      font-size: 12px;
      font-weight: 900;
    }}
    .priority-source {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }}
    .priority-title {{
      font-size: 15px;
      font-weight: 900;
      line-height: 1.3;
    }}
    .priority-body {{
      color: #c9d6d3;
      font-size: 13px;
      line-height: 1.45;
    }}
    .priority-meta {{
      margin-top: auto;
      color: var(--muted);
      font-size: 12px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 12px;
    }}
    .metric-value {{
      margin-top: 8px;
      font-size: 24px;
      font-weight: 800;
    }}
    .metric-note {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }}
    .market-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .market-card {{
      padding: 14px;
    }}
    .market-region {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 12px;
    }}
    .market-row {{
      display: grid;
      grid-template-columns: minmax(74px, 1fr) auto;
      gap: 8px;
      align-items: center;
      padding: 7px 0;
      border-top: 1px solid rgba(255,255,255,0.06);
      font-size: 13px;
    }}
    .pos {{ color: var(--ok); }}
    .neg {{ color: var(--risk); }}
    .flat {{ color: var(--muted); }}
    .chart-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .intel-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(300px, 0.9fr) minmax(300px, 0.9fr);
      gap: 16px;
    }}
    .chart-panel {{
      padding: 18px;
    }}
    .signal-panel {{
      display: grid;
      gap: 12px;
    }}
    .chart-title {{
      margin: 0 0 14px;
      font-size: 15px;
      color: #dce8e5;
    }}
    .signal-row {{
      display: grid;
      grid-template-columns: 84px minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      padding: 10px 0;
      border-top: 1px solid rgba(255,255,255,0.06);
      font-size: 12px;
    }}
    .signal-pill {{
      display: inline-flex;
      justify-content: center;
      min-width: 64px;
      padding: 3px 8px;
      border-radius: 999px;
      background: rgba(255,255,255,0.06);
      color: var(--muted);
      font-weight: 800;
    }}
    .donut-wrap {{
      display: grid;
      grid-template-columns: 112px minmax(0, 1fr);
      gap: 16px;
      align-items: center;
    }}
    .donut {{
      width: 112px;
      aspect-ratio: 1;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: conic-gradient(var(--risk) 0 var(--risk-angle), var(--ok) var(--risk-angle) var(--ok-angle), var(--warn) var(--ok-angle) 360deg);
      box-shadow: inset 0 0 0 18px rgba(7, 10, 13, 0.92);
    }}
    .donut-value {{
      font-size: 22px;
      font-weight: 900;
    }}
    .legend {{
      display: grid;
      gap: 8px;
      font-size: 12px;
      color: var(--muted);
    }}
    .legend-dot {{
      width: 9px;
      height: 9px;
      display: inline-block;
      margin-right: 7px;
      border-radius: 50%;
      background: var(--muted);
    }}
    .legend-dot.risk {{ background: var(--risk); }}
    .legend-dot.ok {{ background: var(--ok); }}
    .legend-dot.warn {{ background: var(--warn); }}
    .heatmap-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
    }}
    .heat-tile {{
      min-height: 118px;
      padding: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      background: linear-gradient(180deg, rgba(255,255,255,0.055), rgba(255,255,255,0.025));
    }}
    .heat-tile.risk {{ border-color: rgba(255, 107, 127, 0.38); background: linear-gradient(180deg, rgba(255, 107, 127, 0.16), rgba(255,255,255,0.025)); }}
    .heat-tile.ok {{ border-color: rgba(88, 214, 141, 0.34); background: linear-gradient(180deg, rgba(88, 214, 141, 0.13), rgba(255,255,255,0.025)); }}
    .heat-tile.warn {{ border-color: rgba(247, 189, 97, 0.34); background: linear-gradient(180deg, rgba(247, 189, 97, 0.13), rgba(255,255,255,0.025)); }}
    .heat-name {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-size: 13px;
      font-weight: 800;
    }}
    .heat-meta {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
    .spark-track {{
      height: 7px;
      margin-top: 11px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      overflow: hidden;
    }}
    .spark-fill {{
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 86px minmax(0, 1fr) 68px;
      gap: 10px;
      align-items: center;
      margin: 10px 0;
      font-size: 12px;
    }}
    .bar-track {{
      height: 9px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
    }}
    .bar-fill {{
      display: block;
      height: 100%;
      min-width: 2px;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
    }}
    .bar-fill.risk {{
      background: linear-gradient(90deg, var(--risk), var(--warn));
    }}
    .bar-fill.ok {{
      background: linear-gradient(90deg, var(--accent), var(--ok));
    }}
    .chart-note {{
      min-height: 40px;
      margin: -5px 0 16px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }}
    .sentiment-stack {{
      display: flex;
      width: 100%;
      height: 34px;
      overflow: hidden;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      background: rgba(255,255,255,0.05);
    }}
    .sentiment-segment {{
      display: grid;
      min-width: 34px;
      place-items: center;
      color: #07100d;
      font-size: 12px;
      font-weight: 900;
    }}
    .sentiment-segment.bull {{ background: var(--ok); }}
    .sentiment-segment.neutral {{ background: var(--warn); }}
    .sentiment-segment.bear {{ background: var(--risk); }}
    .sentiment-legend {{
      grid-template-columns: repeat(3, auto);
      justify-content: start;
      margin-top: 14px;
    }}
    .kol-list {{ display: grid; gap: 8px; }}
    .kol-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 4px 12px;
      padding: 9px 0;
      border-top: 1px solid rgba(255,255,255,0.06);
    }}
    .kol-row:first-child {{ border-top: 0; }}
    .kol-row div {{ display: flex; gap: 8px; align-items: baseline; }}
    .kol-row div span, .kol-row b {{ color: var(--muted); font-size: 11px; }}
    .kol-row p {{ grid-column: 1 / -1; margin: 0; color: #c9d6d3; font-size: 12px; }}
    .conclusion-panel {{
      padding: 18px;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      background: linear-gradient(180deg, rgba(20, 28, 34, 0.92), rgba(12, 17, 21, 0.92));
    }}
    .conclusion-heading {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: end;
      margin-bottom: 14px;
    }}
    .conclusion-heading h2 {{ margin-top: 4px; }}
    .conclusion-heading p {{ max-width: 420px; color: var(--muted); font-size: 12px; text-align: right; }}
    .topic-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
    }}
    .topic-card {{
      min-height: 168px;
      padding: 14px;
      border: 1px solid rgba(255,255,255,0.07);
      border-radius: 8px;
      background: rgba(255,255,255,0.035);
    }}
    .topic-card > span {{ color: var(--accent); font: 800 11px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .topic-card h3 {{ margin: 9px 0; font-size: 14px; }}
    .topic-card p {{ color: var(--muted); font-size: 12px; line-height: 1.45; }}
    .content-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 16px;
    }}
    .report-section {{
      margin: 0;
      padding: 18px 20px;
      background: rgba(16, 22, 26, 0.92);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      box-shadow: 0 12px 34px rgba(0,0,0,0.20);
    }}
    details.report-section {{
      padding: 0;
      overflow: hidden;
    }}
    details.report-section > summary {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 54px;
      padding: 0 20px;
      cursor: pointer;
      list-style: none;
    }}
    details.report-section > summary::-webkit-details-marker {{ display: none; }}
    details.report-section > summary::after {{
      content: '+';
      color: var(--muted);
      font-size: 20px;
      font-weight: 300;
    }}
    details.report-section[open] > summary::after {{ content: '-'; }}
    .section-body {{
      padding: 0 20px 18px;
      border-top: 1px solid rgba(255,255,255,0.06);
    }}
    h2 {{
      margin: 0;
      font-size: 20px;
      line-height: 1.35;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 0 0 8px;
      font-size: 16px;
      line-height: 1.35;
      letter-spacing: 0;
    }}
    .sub-card {{
      margin-top: 12px;
      padding: 14px 16px;
      border: 1px solid rgba(255,255,255,0.08);
      border-left: 3px solid var(--accent);
      border-radius: 8px;
      background: rgba(255,255,255,0.03);
    }}
    ul {{
      margin: 0;
      padding-left: 20px;
    }}
    li {{
      margin: 6px 0;
      padding-left: 2px;
      color: #c9d6d3;
    }}
    li.risk {{ color: var(--risk); }}
    li.ok {{ color: var(--ok); }}
    li.warn {{ color: var(--warn); }}
    p {{
      margin: 8px 0;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
      overflow-wrap: anywhere;
    }}
    a:hover {{ text-decoration: underline; }}
    .generated {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
      text-align: right;
    }}
    .import-modal {{
      width: min(900px, calc(100% - 28px));
      max-height: calc(100vh - 36px);
      padding: 0;
      border: 1px solid rgba(255,255,255,0.14);
      border-radius: 12px;
      color: var(--ink);
      background: #0d1317;
      box-shadow: 0 30px 100px rgba(0,0,0,0.72);
    }}
    .import-modal::backdrop {{ background: rgba(0,0,0,0.72); backdrop-filter: blur(5px); }}
    .import-shell {{ padding: 20px; }}
    .import-head {{ display: flex; justify-content: space-between; gap: 18px; align-items: start; }}
    .import-head h2 {{ margin: 0 0 4px; }}
    .import-head p, .import-hint {{ color: var(--muted); font-size: 12px; }}
    .import-close {{ border: 0; color: var(--muted); background: transparent; font-size: 26px; cursor: pointer; }}
    .import-input {{
      width: 100%; min-height: 210px; margin-top: 12px; padding: 12px;
      resize: vertical; border: 1px solid rgba(255,255,255,0.13); border-radius: 8px;
      color: var(--ink); background: #070b0e; font: 12px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
    }}
    .import-toolbar {{ display: flex; flex-wrap: wrap; gap: 9px; margin: 12px 0; align-items: center; }}
    .import-status {{ margin-left: auto; color: var(--muted); font-size: 12px; }}
    .import-preview {{ max-height: 230px; overflow: auto; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; }}
    .import-preview table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    .import-preview th, .import-preview td {{ padding: 8px 9px; border-bottom: 1px solid rgba(255,255,255,0.07); text-align: left; white-space: nowrap; }}
    .import-preview th {{ position: sticky; top: 0; color: var(--muted); background: #121a1f; }}
    @media (max-width: 720px) {{
      .topbar {{ padding: 0 14px; }}
      main {{
        width: min(calc(100% - 20px), 1180px);
        padding-top: 16px;
      }}
      .hero-panel, .dashboard, .operator-strip, .battle-timeline, .content-grid {{ min-width: 0; max-width: 100%; }}
      .hero-grid, .chart-grid, .market-grid, .metric-grid, .intel-grid, .brief-grid, .decision-grid, .priority-grid, .donut-wrap, .topic-grid, .regime-panel {{
        grid-template-columns: 1fr;
      }}
      .operator-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .operator-cell {{ border-right: 0; border-bottom: 1px solid rgba(255,255,255,0.07); }}
      .operator-cell.action {{ grid-column: span 2; }}
      .battle-timeline {{ grid-template-columns: 1fr; }}
      .top-meta {{ display: none; }}
      .level-row {{ grid-template-columns: 74px 92px 1fr; }}
      .gauge-card, .level-panel, .structure-panel {{ grid-column: auto; }}
      .structure-metrics {{ grid-template-columns: 1fr; }}
      .conclusion-heading {{ display: block; }}
      .conclusion-heading p {{ max-width: none; text-align: left; }}
      .report-title {{ font-size: 24px; }}
      .report-section {{ padding: 14px; }}
      .sub-card {{ padding: 12px; }}
      .bar-row {{ grid-template-columns: 76px minmax(0, 1fr) 58px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand"><span class="mark">IR</span><span>{escape(PRODUCT_NAME)}</span></div>
    <div class="top-actions"><div class="top-meta">Research console · A股 / 美股 / 韩国</div>{portfolio_button}</div>
  </header>
  <main>
    <section class="hero-panel">
      <span class="badge">DAILY RESEARCH BRIEF</span>
      <h1 class="report-title">{escape(title)}</h1>
      <p class="subtitle">{escape(subtitle)}</p>
    </section>
{dashboard}
    <div class="content-grid">
{body}
    </div>
    <div class="generated">Generated by {escape(PRODUCT_NAME)}</div>
  </main>
{portfolio_modal}
{portfolio_script}
</body>
</html>
"""


def _build_dashboard(content: str) -> str:
    if "## 情绪仪表盘" in content and "## 大V观点与转向" in content:
        return _build_nga_dashboard(content)
    holdings = _parse_broker_holdings(content)
    markets = _parse_market_snapshots(content)
    actions = _parse_actions(content)
    action_cards = _parse_action_details(content)
    unified = _parse_unified_brief(content)
    market_values = [float(item["market_value"]) for item in holdings if isinstance(item.get("market_value"), float)]
    total_value = sum(market_values) if market_values else None
    risk_actions = sum(1 for action in actions if any(word in action for word in ["减仓", "退出", "降低"]))
    avg_day = _average([item["day_pnl_pct"] for item in holdings])
    avg_total = _average([item["pnl_pct"] for item in holdings])
    gap_count = _count_meaningful_lines(_section_lines(content, "数据缺口"))
    research_count = _count_meaningful_lines(_section_lines(content, "研报观点变化"))
    event_count = _count_meaningful_lines(_section_lines(content, "事件日历与公告 watchlist"))
    external_count = _count_meaningful_lines(_section_lines(content, "外部观点观察"))

    return f"""
    <section class="dashboard">
      {_operator_strip(content, unified, gap_count)}
      {_battle_timeline(content)}
      {_executive_brief(content, holdings, actions, action_cards, gap_count, research_count, event_count)}
      {_regime_gauges(unified)}
      {_priority_cards(content, action_cards, gap_count)}
      {_decision_cards(holdings, action_cards)}
      <div class="intel-grid">
        {_signal_panel(gap_count, risk_actions, research_count, event_count, external_count, unified.get("risk_label", ""))}
        {_action_donut(actions)}
        {_market_breadth_panel(markets)}
      </div>
      <div class="hero-grid">
        <div class="metric-grid">
          {_metric_card("持仓数量", f"{len(holdings)}", "来自券商持仓快照")}
          {_metric_card("组合市值", _money_text(total_value), "股票持仓合计")}
          {_metric_card("风险动作", f"{risk_actions}", "减仓/退出/降低仓位")}
          {_metric_card("日内均值", _pct_text(avg_day), f"总盈亏均值 {_pct_text(avg_total)}", _sentiment_class(avg_day))}
        </div>
        {_position_chart("仓位分布", holdings, "weight_pct")}
      </div>
      <div class="market-grid">
        {''.join(_market_card(region, items) for region, items in markets.items())}
      </div>
      <div class="chart-grid">
        {_position_chart("单票总盈亏", holdings, "pnl_pct")}
        {_position_chart("单票当日表现", holdings, "day_pnl_pct")}
      </div>
      {_holding_heatmap(holdings, action_cards)}
    </section>
"""


def _build_nga_dashboard(content: str) -> str:
    metrics = _parse_nga_metrics(content)
    bull, neutral, bear = _parse_nga_sentiment_mix(metrics.get("看多 / 中性 / 看空", ""))
    sectors = _parse_nga_sector_temperature(content)
    influencers = _parse_nga_influencers(content)
    conclusions = _parse_nga_conclusions(content)
    direction = metrics.get("整体方向", "数据不足")
    stage = metrics.get("情绪阶段", "待标定")
    risk_appetite = _metric_score(metrics.get("风险偏好", ""))
    panic = _metric_score(metrics.get("恐慌强度", ""))
    euphoria = _metric_score(metrics.get("亢奋强度", ""))
    disagreement = _metric_score(metrics.get("多空分歧", ""))
    return f"""
    <section class="dashboard nga-dashboard">
      <section class="brief-grid">
        <article class="brief-card primary">
          <div class="brief-label">今日结论</div>
          <div class="brief-value neg">{escape(direction)}</div>
          <div class="brief-note">看空占 {bear:.0f}%，风险偏好仅 {risk_appetite}/100；反弹先看持续性，不把单日修复当反转。</div>
        </article>
        <article class="brief-card">
          <div class="brief-label">情绪阶段</div>
          <div class="brief-value">{escape(stage)}</div>
          <div class="brief-note">历史样本不足20日，只能标记候选。</div>
        </article>
        <article class="brief-card">
          <div class="brief-label">最强分歧</div>
          <div class="brief-value">{disagreement}</div>
          <div class="brief-note">科技长期逻辑与短期筹码风险冲突。</div>
        </article>
        <article class="brief-card">
          <div class="brief-label">板块切换</div>
          <div class="brief-value">科技 ↓</div>
          <div class="brief-note">创新药升温；红利消费偏防御承接。</div>
        </article>
      </section>
      <div class="chart-grid">
        {_nga_sentiment_chart(bull, neutral, bear)}
        {_nga_intensity_chart(risk_appetite, panic, euphoria, disagreement)}
      </div>
      <div class="chart-grid">
        {_nga_sector_panel(sectors)}
        {_nga_influencer_panel(influencers)}
      </div>
      {_nga_conclusion_cards(conclusions)}
    </section>
"""


def _parse_nga_metrics(content: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in _section_lines(content, "情绪仪表盘"):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in {"指标", "---"} or set(cells[0]) == {"-"}:
            continue
        result[cells[0]] = cells[1]
    return result


def _parse_nga_sentiment_mix(value: str) -> tuple[float, float, float]:
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value)[:3]]
    if len(numbers) != 3:
        return 0.0, 0.0, 0.0
    return numbers[0], numbers[1], numbers[2]


def _metric_score(value: str) -> int:
    match = re.search(r"\d+", value)
    return min(100, max(0, int(match.group(0)))) if match else 0


def _parse_nga_sector_temperature(content: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    active = False
    for raw in content.splitlines():
        line = raw.strip()
        if line == "### 板块温度":
            active = True
            continue
        if active and line.startswith("## "):
            break
        if not active or not line.startswith("- ") or "：" not in line:
            continue
        name, detail = line[2:].split("：", 1)
        rows.append((name.strip(), detail.strip()))
    return rows[:6]


def _parse_nga_influencers(content: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in _section_lines(content, "大V观点与转向"):
        if not line.startswith("- **"):
            continue
        match = re.match(r"- \*\*([^*]+)\*\*：(.*)", line)
        if not match:
            continue
        heading, detail = match.groups()
        name = heading.split("（", 1)[0].strip()
        stance = heading.split("｜", 1)[1].strip() if "｜" in heading else "观察"
        count_match = re.search(r"补回\s*(\d+)\s*条", detail)
        rows.append(
            {
                "name": name,
                "stance": stance,
                "count": int(count_match.group(1)) if count_match else 0,
                "summary": _short_text(re.sub(r"\[[^\]]+\]\([^\)]+\)", "", detail), 70),
            }
        )
    return rows[:5]


def _parse_nga_conclusions(content: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    lines = content.splitlines()
    for index, raw in enumerate(lines):
        heading = raw.strip()
        match = re.match(r"##\s+(\d+)\.\s+(.+)", heading)
        if not match:
            continue
        paragraph = ""
        for candidate in lines[index + 1 :]:
            candidate = candidate.strip()
            if candidate.startswith("## "):
                break
            if candidate and not candidate.startswith(("#", "-", "|", ">")):
                paragraph = candidate
                break
        rows.append({"rank": match.group(1), "title": match.group(2), "summary": _short_text(paragraph, 86)})
    return rows[:5]


def _nga_sentiment_chart(bull: float, neutral: float, bear: float) -> str:
    return f"""
        <article class="chart-panel">
          <h3 class="chart-title">大众多空构成</h3>
          <p class="chart-note">看空表达占主导；大V观点已从大众样本中剔除，避免重复计权。</p>
          <div class="sentiment-stack" role="img" aria-label="看多 {bull:.0f}%，中性 {neutral:.0f}%，看空 {bear:.0f}%">
            <span class="sentiment-segment bull" style="width:{bull:.2f}%">{bull:.0f}%</span>
            <span class="sentiment-segment neutral" style="width:{neutral:.2f}%">{neutral:.0f}%</span>
            <span class="sentiment-segment bear" style="width:{bear:.2f}%">{bear:.0f}%</span>
          </div>
          <div class="legend sentiment-legend"><span><i class="legend-dot ok"></i>看多</span><span><i class="legend-dot warn"></i>中性</span><span><i class="legend-dot risk"></i>看空</span></div>
        </article>
"""


def _nga_intensity_chart(risk: int, panic: int, euphoria: int, disagreement: int) -> str:
    rows = [
        ("风险偏好", risk, "ok"),
        ("恐慌强度", panic, "risk"),
        ("亢奋强度", euphoria, "warn"),
        ("多空分歧", disagreement, "risk"),
    ]
    bars = "".join(
        f'<div class="bar-row"><span>{escape(name)}</span><span class="bar-track"><i class="bar-fill {tone}" style="width:{value}%"></i></span><b>{value}</b></div>'
        for name, value, tone in rows
    )
    return f"""
        <article class="chart-panel">
          <h3 class="chart-title">情绪强度</h3>
          <p class="chart-note">恐慌与分歧同时偏高，说明市场更接近“有承接但未形成共识”的冰点候选。</p>
          {bars}
        </article>
"""


def _nga_sector_panel(sectors: list[tuple[str, str]]) -> str:
    tiles = []
    for name, detail in sectors:
        tone = "risk" if any(word in detail for word in ["看空", "恐慌", "偏空"]) else "ok" if any(word in detail for word in ["偏多", "升温"]) else "warn"
        label = "降温" if tone == "risk" else "升温" if tone == "ok" else "观察"
        tiles.append(
            f'<div class="heat-tile {tone}"><div class="heat-name"><span>{escape(name)}</span><span>{label}</span></div><div class="heat-meta">{escape(_short_text(detail, 66))}</div></div>'
        )
    return f"""
        <article class="chart-panel">
          <h3 class="chart-title">板块温度</h3>
          <p class="chart-note">科技是主要风险源；创新药承接资金，但拥挤度已进入需要警惕的区域。</p>
          <div class="heatmap-grid">{''.join(tiles)}</div>
        </article>
"""


def _nga_influencer_panel(rows: list[dict[str, object]]) -> str:
    cards = []
    for row in rows:
        count = int(row["count"])
        activity = f"{count}条回复" if count else "主题/观察"
        cards.append(
            f'<div class="kol-row"><div><strong>{escape(str(row["name"]))}</strong><span>{escape(str(row["stance"]))}</span></div><b>{activity}</b><p>{escape(str(row["summary"]))}</p></div>'
        )
    return f"""
        <article class="chart-panel">
          <h3 class="chart-title">大V信号</h3>
          <p class="chart-note">三位活跃作者共同指向：科技中期逻辑未破，但短线仍需出清、去弱留强。</p>
          <div class="kol-list">{''.join(cards)}</div>
        </article>
"""


def _nga_conclusion_cards(rows: list[dict[str, str]]) -> str:
    cards = "".join(
        f'<article class="topic-card"><span>0{escape(row["rank"])}</span><h3>{escape(row["title"])}</h3><p>{escape(row["summary"])}</p></article>'
        for row in rows
    )
    return f"""
      <section class="conclusion-panel">
        <div class="conclusion-heading"><div><span class="brief-label">五个结论</span><h2>先读判断，再展开证据</h2></div><p>下方长文默认折叠，需要核验时再查看帖子与高赞回复。</p></div>
        <div class="topic-grid">{cards}</div>
      </section>
"""


def _signal_panel(
    gaps: int,
    risks: int,
    research: int,
    events: int,
    external: int,
    unified_risk_label: str = "",
) -> str:
    data_state = "OK" if gaps == 0 else "GAP"
    data_class = "ok" if gaps == 0 else "warn"
    if unified_risk_label:
        risk_state = unified_risk_label
        risk_class = "risk" if any(word in unified_risk_label for word in ["红", "橙"]) else "warn"
        risk_note = "统一风险预算"
    else:
        risk_state = "HIGH" if risks >= 2 else ("WATCH" if risks else "CALM")
        risk_class = "risk" if risks >= 2 else ("warn" if risks else "ok")
        risk_note = f"{risks} actions"
    return f"""
        <article class="chart-panel signal-panel">
          <h3 class="chart-title">Intelligence Signals</h3>
          {_signal_row("Data", data_state, f"{gaps} gaps", data_class)}
          {_signal_row("Risk", risk_state, risk_note, risk_class)}
          {_signal_row("Research", "LIVE", f"{research} deltas", "ok" if research else "flat")}
          {_signal_row("Events", "WATCH", f"{events} items", "warn" if events else "flat")}
          {_signal_row("Views", "FLOW", f"{external} items", "ok" if external else "flat")}
        </article>
"""


def _operator_strip(content: str, unified: dict[str, str], gap_count: int) -> str:
    if not unified:
        return ""
    readiness = re.search(r"严格决策就绪\s+(\d+/\d+)", content)
    score = unified.get("formal_score") or unified.get("bear_bull", "待确认").split("（", 1)[0]
    cells = [
        ("当前熊牛分", score, ""),
        ("今日姿态", unified.get("stance", "等待确认"), ""),
        ("生死支撑", unified.get("support_zone", "待确认"), ""),
        ("第一确认", unified.get("confirmation_zone", "待确认"), ""),
        ("强压力", unified.get("strong_resistance", "待确认"), ""),
        ("失效条件", unified.get("invalidation", "等待15分钟确认"), ""),
        ("第一动作", unified.get("first_action", "不新增仓位"), "action"),
        ("数据时点", unified.get("regime_as_of", "待确认"), ""),
        ("决策就绪度", readiness.group(1) if readiness else f"缺口{gap_count}", ""),
    ]
    return '<section class="operator-strip" aria-label="首屏操盘条">' + "".join(
        f'<div class="operator-cell {tone}"><span>{escape(label)}</span><b>{escape(_short_text(value, 74))}</b></div>'
        for label, value, tone in cells
    ) + "</section>"


def _battle_timeline(content: str) -> str:
    rows: list[dict[str, str]] = []
    capture = False
    timeline_lines: list[str] = []
    for raw in content.splitlines():
        stripped = raw.strip()
        if stripped in {"## 四时点作战时间轴", "### 四时点作战时间轴"}:
            capture = True
            continue
        if capture and stripped.startswith(("## ", "### ")):
            break
        if capture and stripped:
            timeline_lines.append(stripped)
    for raw in timeline_lines:
        line = raw.strip()
        if not line.startswith("- ") or "｜观察：" not in line:
            continue
        parts = line[2:].split("｜")
        row = {"time": parts[0].strip(), "observe": "待确认", "state": "等待观察", "action": "保持原计划"}
        for part in parts[1:]:
            if part.startswith("观察："):
                row["observe"] = part.split("：", 1)[1].strip()
            elif part.startswith("当前："):
                row["state"] = part.split("：", 1)[1].strip()
            elif part.startswith("动作："):
                row["action"] = part.split("：", 1)[1].strip()
        rows.append(row)
    if not rows:
        return ""
    return '<section class="battle-timeline" aria-label="四时点作战时间轴">' + "".join(
        '<article class="timeline-card">'
        f'<div class="timeline-time">{escape(row["time"])}</div>'
        f'<div class="timeline-observe">观察：{escape(_short_text(row["observe"], 96))}</div>'
        f'<div class="timeline-state">当前：{escape(row["state"])}</div>'
        f'<div class="timeline-action">动作：{escape(_short_text(row["action"], 112))}</div>'
        '</article>'
        for row in rows[:4]
    ) + "</section>"


def _executive_brief(
    content: str,
    holdings: list[dict[str, float | str]],
    actions: list[str],
    action_cards: dict[str, dict[str, str]],
    gaps: int,
    research: int,
    events: int,
) -> str:
    unified = _parse_unified_brief(content)
    if unified:
        return f"""
      <section class="brief-grid">
        <article class="brief-card primary">
          <div class="brief-label">明日总体姿态</div>
          <div class="brief-value">{escape(unified.get('stance', '等待确认'))}</div>
          <div class="brief-note">{escape(unified.get('first_action', '补齐数据前不新增仓位。'))}</div>
        </article>
        <article class="brief-card">
          <div class="brief-label">低开 / 走弱</div>
          <div class="brief-value"><span class="risk">执行纪律</span></div>
          <div class="brief-note">{escape(unified.get('downside', '触发原风险线后复核减仓。'))}</div>
        </article>
        <article class="brief-card">
          <div class="brief-label">平开 / 震荡</div>
          <div class="brief-value">保持不动</div>
          <div class="brief-note">{escape(unified.get('flat', '上下条件均未触发时等待确认。'))}</div>
        </article>
        <article class="brief-card">
          <div class="brief-label">允许加仓前</div>
          <div class="brief-value">条件解锁</div>
          <div class="brief-note">{escape(unified.get('unlock', '风险、趋势与基本面至少两类证据同时改善。'))}</div>
        </article>
      </section>
"""
    risk_names = [
        name
        for name, item in action_cards.items()
        if any(word in item.get("action", "") for word in ["减仓", "退出", "降低"])
    ]
    hold_count = sum(1 for action in actions if any(word in action for word in ["持有", "等待", "观察"]))
    risk_count = len(risk_names)
    conclusion = "先处理风险持仓" if risk_count else "维持观察"
    note = "、".join(risk_names[:3]) if risk_names else "无强制动作；等待新增证据。"
    market_values = [float(item["market_value"]) for item in holdings if isinstance(item.get("market_value"), float)]
    total_value = sum(market_values) if market_values else None
    avg_day = _average([item["day_pnl_pct"] for item in holdings])
    data_state = "完整" if gaps == 0 else f"{gaps} 个缺口"
    return f"""
      <section class="brief-grid">
        <article class="brief-card primary">
          <div class="brief-label">Today Conclusion</div>
          <div class="brief-value">{escape(conclusion)}</div>
          <div class="brief-note">风险优先：{escape(note)}</div>
        </article>
        <article class="brief-card">
          <div class="brief-label">Action</div>
          <div class="brief-value"><span class="risk">{risk_count}</span> / {len(actions)}</div>
          <div class="brief-note">风险复核 {risk_count}，持有观察 {hold_count}</div>
        </article>
        <article class="brief-card">
          <div class="brief-label">Portfolio</div>
          <div class="brief-value">{escape(_money_text(total_value))}</div>
          <div class="brief-note">日内均值 <span class="{_sentiment_class(avg_day)}">{escape(_pct_text(avg_day))}</span></div>
        </article>
        <article class="brief-card">
          <div class="brief-label">Evidence</div>
          <div class="brief-value">{research + events}</div>
          <div class="brief-note">研报 {research}，事件 {events}，数据 {data_state}</div>
        </article>
      </section>
"""


def _parse_unified_brief(content: str) -> dict[str, str]:
    lines = _section_lines(content, "明日统一指引")
    if not lines:
        return {}
    result: dict[str, str] = {}
    unlock_section = False
    for raw in lines:
        line = raw.strip()
        text = line[2:].strip() if line.startswith("- ") else line
        if text.startswith("总体姿态："):
            result["stance"] = text.split("：", 1)[1].split("（", 1)[0].strip()
        elif text.startswith("第一动作："):
            result["first_action"] = text.split("：", 1)[1].strip()
        elif text.startswith("风险预算："):
            result["risk_label"] = text.split("：", 1)[1].split("；", 1)[0].strip()
        elif text.startswith("评分截至："):
            result["regime_as_of"] = text.split("：", 1)[1].split("；", 1)[0].strip()
        elif text.startswith("熊牛评分："):
            result["bear_bull"] = text.split("：", 1)[1].strip()
        elif text.startswith("评分变化："):
            score_text = text.split("：", 1)[1]
            formal = re.search(r"当前正式分\s+(-?\d+(?:\.\d+)?)", score_text)
            candidate = re.search(r"盘中候选分\s+(-?\d+(?:\.\d+)?)", score_text)
            if formal:
                result["formal_score"] = formal.group(1) + "/10"
            if candidate:
                result["candidate_score"] = candidate.group(1) + "/10"
        elif text.startswith("恐慌贪婪："):
            result["fear_greed"] = text.split("：", 1)[1].strip()
        elif text.startswith("拥挤度："):
            result["crowding"] = text.split("：", 1)[1].strip()
        elif text.startswith("锚点累计宽度："):
            result["structure_health"] = text.split("：", 1)[1].strip()
        elif text.startswith("低于锚点："):
            result["below_anchor"] = text.split("：", 1)[1].strip()
        elif text.startswith("等权等效上证："):
            values = text.split("：", 1)[1]
            result["equal_weight_equivalent"] = values.split("；", 1)[0].strip()
            if "中位数股票等效：" in values:
                result["median_equivalent"] = values.split("中位数股票等效：", 1)[1].split("；", 1)[0].strip()
            if "官方上证：" in values:
                result["official_index"] = values.split("官方上证：", 1)[1].rstrip("。").strip()
        elif text.startswith("指数偏离："):
            result["index_divergence"] = text.split("：", 1)[1].strip()
        elif text.startswith("3900只审计："):
            result["claim_3900"] = text.split("：", 1)[1].split("；", 1)[0].strip()
        elif text.startswith("当前点位："):
            result["market_latest"] = text.split("：", 1)[1].split("；", 1)[0].strip()
            state_match = re.search(r"market_level_state：([^；。]+)", text)
            if state_match:
                result["market_level_state"] = state_match.group(1).strip()
        elif text.startswith("生死支撑："):
            result["support_zone"] = text.split("：", 1)[1].split("；", 1)[0].strip()
        elif text.startswith("第一确认："):
            result["confirmation_zone"] = text.split("：", 1)[1].split("；", 1)[0].strip()
        elif text.startswith("较强压力："):
            result["strong_resistance"] = text.split("：", 1)[1].split("；", 1)[0].rstrip("。").strip()
        elif text.startswith("日线修复："):
            result["daily_repair"] = text.split("：", 1)[1].split("；", 1)[0].strip()
        elif text.startswith("失效预案："):
            result["invalidation"] = text.split("：", 1)[1].strip()
        elif "低开或走弱｜" in text and "｜动作：" in text:
            result["downside"] = text.split("｜动作：", 1)[1].strip()
        elif "平开或震荡｜" in text and "｜动作：" in text:
            result["flat"] = text.split("｜动作：", 1)[1].strip()
        elif text.startswith("### 允许提高风险前必须满足"):
            unlock_section = True
        elif text.startswith("### "):
            unlock_section = False
        elif unlock_section and line.startswith("- ") and "unlock" not in result:
            result["unlock"] = text
    return result


def _regime_gauges(unified: dict[str, str]) -> str:
    if not unified.get("bear_bull"):
        return ""
    bear_value = _score_from_text(unified.get("bear_bull", ""), 10.0)
    fear_value = _score_from_text(unified.get("fear_greed", ""), 100.0)
    crowd_value = _score_from_text(unified.get("crowding", ""), 100.0)
    structure_value = _score_from_text(unified.get("structure_health", ""), 100.0)
    cards = [
        _gauge_card("熊牛温度", unified.get("bear_bull", "待确认"), bear_value, 10, "0=熊 / 10=牛；低分是风险状态，不是抄底信号", "#ff6b7f"),
        _gauge_card("恐慌贪婪", unified.get("fear_greed", "待确认"), fear_value, 100, "动量、趋势、回撤、波动与宽度合成", "#f0c35b"),
        _gauge_card("交易拥挤度", unified.get("crowding", "待确认"), crowd_value, 100, "绝对阈值；少于20个每日样本，尚非历史分位", "#74a9ff"),
        _gauge_card("9·24累计宽度", unified.get("structure_health", "待确认"), structure_value, 100, "只回答相对锚点的累计位置；不代表当前短线趋势", "#7ad7c4"),
    ]
    levels = _market_level_panel(unified)
    structure = _market_structure_panel(unified)
    return f'<section class="regime-panel">{"".join(cards)}{levels}{structure}</section>'


def _score_from_text(value: str, maximum: float) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None
    return min(maximum, max(0.0, float(match.group(0))))


def _gauge_card(
    title: str,
    raw_value: str,
    value: float | None,
    maximum: int,
    note: str,
    color: str,
) -> str:
    score_pct = 0.0 if value is None else value / maximum * 100.0
    score_text = "NA" if value is None else f"{value:.1f}".rstrip("0").rstrip(".")
    label_match = re.search(r"[（(]([^；;)）]+)", raw_value)
    label = label_match.group(1).strip() if label_match else "待确认"
    return f"""
        <article class="gauge-card">
          <div class="brief-label">{escape(title)}</div>
          <div class="gauge-ring" style="--score:{score_pct:.1f};--gauge-color:{color}" role="img" aria-label="{escape(title)} {score_text}/{maximum}">
            <div class="gauge-number">{score_text}<small>/{maximum}</small></div>
          </div>
          <div class="gauge-label">{escape(label)}</div>
          <div class="gauge-note">{escape(note)}</div>
        </article>
"""


def _market_level_panel(unified: dict[str, str]) -> str:
    as_of = unified.get("regime_as_of", "待确认")
    latest = unified.get("market_latest", "待确认")
    rows = [
        ("生死支撑", unified.get("support_zone", "待确认"), "跌破且15分钟不能收回，继续防守", "support"),
        ("第一确认", unified.get("confirmation_zone", "待确认"), "站稳后才把行情上调为有效反弹", "confirm"),
        ("较强压力", unified.get("strong_resistance", "待确认"), "周线级压力，不追涨", "resistance"),
        ("日线修复", unified.get("daily_repair", "待确认"), "配合宽度改善才考虑趋势修复", "repair"),
    ]
    rendered = "".join(
        f'<div class="level-row {tone}"><span>{escape(name)}</span><b>{escape(value)}</b><span>{escape(note)}</span></div>'
        for name, value, note, tone in rows
    )
    return f"""
        <article class="level-panel">
          <div class="level-heading"><div><div class="brief-label">上证状态切换阶梯</div><h3>现价 {escape(latest)}</h3></div><span>截至 {escape(as_of)}</span></div>
          <div class="level-ladder">{rendered}</div>
        </article>
"""


def _market_structure_panel(unified: dict[str, str]) -> str:
    below = unified.get("below_anchor", "待确认")
    below_ratio = re.search(r"[（(](\d+(?:\.\d+)?%)", below)
    ratio_text = below_ratio.group(1) if below_ratio else "NA"
    coverage = re.search(r"覆盖率\s+(\d+(?:\.\d+)?%)", below)
    coverage_text = coverage.group(1) if coverage else "NA"
    return f"""
        <article class="structure-panel">
          <div class="level-heading"><div><div class="brief-label">市场宽度与指数失真</div><h3>9·24固定锚点</h3></div><span>覆盖 {escape(coverage_text)}</span></div>
          <div class="structure-metrics">
            <div class="structure-metric"><span>低于锚点</span><b>{escape(ratio_text)}</b></div>
            <div class="structure-metric"><span>等权等效上证</span><b>{escape(unified.get('equal_weight_equivalent', 'NA'))}</b></div>
            <div class="structure-metric"><span>中位数股票等效</span><b>{escape(unified.get('median_equivalent', 'NA'))}</b></div>
          </div>
          <div class="structure-callout">3900只审计：{escape(unified.get('claim_3900', '覆盖不足，暂不验证'))}</div>
          <div class="gauge-note">官方上证 {escape(unified.get('official_index', 'NA'))}；{escape(unified.get('index_divergence', '指数偏离待确认'))}</div>
        </article>
"""


def portfolio_import_html_parts() -> tuple[str, str, str]:
    """Return the existing local-only portfolio import button, modal, and script."""

    return (
        _portfolio_import_button(),
        _portfolio_import_modal(),
        _portfolio_import_script(),
    )


def _portfolio_import_button() -> str:
    return '<button class="ui-button" id="portfolio-import-open" type="button">导入持仓</button>'


def _portfolio_import_modal() -> str:
    return """
  <dialog class="import-modal" id="portfolio-import-modal">
    <div class="import-shell">
      <div class="import-head">
        <div><h2>导入券商持仓</h2><p>数据只在本机浏览器中解析，不会上传。支持直接粘贴银河等券商的制表符表格。</p></div>
        <button class="import-close" id="portfolio-import-close" type="button" aria-label="关闭">×</button>
      </div>
      <textarea class="import-input" id="portfolio-import-text" placeholder="从券商持仓页复制后粘贴：必须包含证券代码、证券名称，优先读取当前持仓，缺失时读取股票余额。"></textarea>
      <div class="import-toolbar">
        <label class="ui-button secondary">选择 TSV 文件<input id="portfolio-import-file" type="file" accept=".tsv,.txt,.csv" hidden></label>
        <button class="ui-button secondary" id="portfolio-import-parse" type="button">解析预览</button>
        <button class="ui-button" id="portfolio-import-save" type="button">打开 InsightRadar 导入页</button>
        <button class="ui-button secondary" id="portfolio-import-copy" type="button">复制应用入口名称</button>
        <span class="import-status" id="portfolio-import-status">尚未解析</span>
      </div>
      <div class="import-preview" id="portfolio-import-preview"><div class="import-hint" style="padding:16px">这里可先做无写入预览；完整保存必须进入127.0.0.1安全服务，核对新旧差异并明确批准。</div></div>
      <p class="import-hint">先双击 <b>InsightRadar.cmd</b> 启动本地应用并保持其窗口运行，再点“打开 InsightRadar 导入页”。若这里已经粘贴了持仓，按钮会尝试复制到剪贴板，到导入页后按 Ctrl+V 即可。应用会预览新旧差异、逐只选择 beta、原子保存并刷新报告；不会上传持仓，也不会下单。</p>
    </div>
  </dialog>
"""


def _portfolio_import_script() -> str:
    return r"""
  <script>
  (() => {
    const modal = document.getElementById('portfolio-import-modal');
    const open = document.getElementById('portfolio-import-open');
    const close = document.getElementById('portfolio-import-close');
    const input = document.getElementById('portfolio-import-text');
    const file = document.getElementById('portfolio-import-file');
    const parseButton = document.getElementById('portfolio-import-parse');
    const saveButton = document.getElementById('portfolio-import-save');
    const copyButton = document.getElementById('portfolio-import-copy');
    const status = document.getElementById('portfolio-import-status');
    const preview = document.getElementById('portfolio-import-preview');
    let payload = null;
    const aliases = {
      shares: ['当前持仓', '当前股份', '股票余额'], available: ['股份可用', '自有股份可用'],
      code: ['证券代码'], name: ['证券名称'], cost: ['成本价'], market_price: ['市价'],
      pnl: ['盈亏'], pnl_pct: ['盈亏比例(%)'], day_pnl: ['当日盈亏'],
      day_pnl_pct: ['当日盈亏比(%)', '当日盈亏比例(%)'], market_value: ['市值'],
      weight_pct: ['仓位占比(%)'], market: ['交易市场']
    };
    const cell = (row, key) => {
      for (const heading of aliases[key]) if ((row[heading] ?? '') !== '') return String(row[heading]).trim();
      return '';
    };
    const number = value => {
      const cleaned = String(value ?? '').replaceAll(',', '').replace('%', '').trim();
      if (!cleaned) return null;
      const parsed = Number(cleaned);
      return Number.isFinite(parsed) ? parsed : null;
    };
    const code = (value, market) => {
      const clean = String(value).trim();
      if (clean.includes('.')) return clean;
      if (String(market).startsWith('沪') || /^[69]/.test(clean)) return `${clean}.SH`;
      if (String(market).startsWith('深') || /^[023]/.test(clean)) return `${clean}.SZ`;
      return clean;
    };
    const parse = text => {
      const lines = text.split(/\r?\n/).filter(line => line.trim());
      const headerIndex = lines.findIndex(line => line.includes('证券代码'));
      if (headerIndex < 0) throw new Error('没有找到“证券代码”表头');
      const headers = lines[headerIndex].split('\t').map(value => value.trim());
      const rows = lines.slice(headerIndex + 1).map(line => {
        const values = line.split('\t').map(value => value.trim());
        return Object.fromEntries(headers.map((heading, index) => [heading, values[index] ?? '']));
      }).filter(row => cell(row, 'code'));
      const holdings = rows.map(row => {
        const market = cell(row, 'market');
        const shares = number(cell(row, 'shares'));
        const marketPrice = number(cell(row, 'market_price'));
        const suppliedValue = number(cell(row, 'market_value'));
        return {
          code: code(cell(row, 'code'), market), name: cell(row, 'name'), shares,
          cost: number(cell(row, 'cost')), market_price: marketPrice,
          pnl: number(cell(row, 'pnl')), pnl_pct: number(cell(row, 'pnl_pct')),
          day_pnl: number(cell(row, 'day_pnl')), day_pnl_pct: number(cell(row, 'day_pnl_pct')),
          market_value: suppliedValue ?? (shares !== null && marketPrice !== null ? shares * marketPrice : null),
          weight_pct: number(cell(row, 'weight_pct')), available: number(cell(row, 'available')),
          market, thesis: '券商持仓导入，待补买入逻辑。',
          risk_line: '按成本回撤、单日跌幅、仓位集中度和原始买入逻辑复核。',
          review_status: 'needs_context'
        };
      }).filter(item => item.shares !== null && item.shares > 0);
      if (!holdings.length) throw new Error('没有找到当前持仓大于0的记录');
      return {as_of: new Date().toISOString().slice(0, 10), cash: null, source_note: '本地券商TSV经InsightRadar报告导入', holdings};
    };
    const render = data => {
      preview.replaceChildren();
      const table = document.createElement('table');
      const headings = ['代码', '名称', '股数', '成本', '市价', '盈亏%', '仓位%'];
      const keys = ['code', 'name', 'shares', 'cost', 'market_price', 'pnl_pct', 'weight_pct'];
      const head = document.createElement('thead'); const hr = document.createElement('tr');
      headings.forEach(value => { const th = document.createElement('th'); th.textContent = value; hr.appendChild(th); });
      head.appendChild(hr); table.appendChild(head);
      const body = document.createElement('tbody');
      data.holdings.forEach(item => { const row = document.createElement('tr'); keys.forEach(key => { const td = document.createElement('td'); td.textContent = item[key] ?? '未提供'; row.appendChild(td); }); body.appendChild(row); });
      table.appendChild(body); preview.appendChild(table);
    };
    const doParse = () => {
      try { payload = parse(input.value); render(payload); status.textContent = `已解析 ${payload.holdings.length} 只持仓；进入安全服务后核对新旧差异`; }
      catch (error) { payload = null; preview.textContent = error.message; status.textContent = '解析失败'; }
    };
    const save = async () => {
      try { if (input.value.trim()) await navigator.clipboard.writeText(input.value); } catch (_error) {}
      window.open('http://127.0.0.1:8765/', '_blank', 'noopener');
      status.textContent = '已打开本地导入页；若页面无法访问，请先双击 InsightRadar.cmd。已粘贴内容可在导入页按 Ctrl+V。';
    };
    open.addEventListener('click', () => modal.showModal()); close.addEventListener('click', () => modal.close());
    modal.addEventListener('click', event => { if (event.target === modal) modal.close(); });
    parseButton.addEventListener('click', doParse); saveButton.addEventListener('click', save);
    file.addEventListener('change', async () => { if (file.files[0]) { input.value = await file.files[0].text(); doParse(); } });
    copyButton.addEventListener('click', async () => { await navigator.clipboard.writeText('InsightRadar.cmd'); status.textContent = '已复制应用入口名称：InsightRadar.cmd'; });
  })();
  </script>
"""


def _decision_cards(
    holdings: list[dict[str, float | str]],
    action_cards: dict[str, dict[str, str]],
) -> str:
    if not holdings:
        return ""
    cards = "".join(_decision_card(item, action_cards.get(str(item["name"]), {})) for item in holdings)
    return f"""
      <section class="decision-grid">
        {cards}
      </section>
"""


def _decision_card(item: dict[str, float | str], detail: dict[str, str]) -> str:
    name = str(item["name"])
    action = detail.get("action", "待观察")
    reason = _short_text(detail.get("reason", "等待新增证据。"), 68)
    risk_line = _short_text(detail.get("risk", "按风险线复核。"), 72)
    pnl = float(item["pnl_pct"]) if isinstance(item["pnl_pct"], float) else None
    day = float(item["day_pnl_pct"]) if isinstance(item["day_pnl_pct"], float) else None
    weight = float(item["weight_pct"]) if isinstance(item["weight_pct"], float) else None
    weight_text = f"{weight:.1f}%" if weight is not None else "NA"
    tone = _action_tone(action)
    return f"""
        <article class="decision-card {tone}">
          <div class="decision-top">
            <div>
              <div class="decision-label">Decision</div>
              <div class="decision-name">{escape(name)}</div>
            </div>
            <span class="action-tag {tone}">{escape(action)}</span>
          </div>
          <div class="decision-reason">{escape(reason)}</div>
          <div class="decision-metrics">
            <span class="{_sentiment_class(pnl)}">总 {_pct_text(pnl)}</span>
            <span class="{_sentiment_class(day)}">日 {_pct_text(day)}</span>
            <span>仓 {weight_text}</span>
          </div>
          <div class="decision-risk">{escape(risk_line)}</div>
        </article>
"""


def _priority_cards(content: str, action_cards: dict[str, dict[str, str]], gap_count: int) -> str:
    signals = _collect_priority_signals(content, action_cards, gap_count)[:3]
    if not signals:
        signals = [
            {
                "score": 10,
                "source": "Radar",
                "title": "No urgent signal",
                "body": "Keep the current plan and wait for stronger evidence.",
                "meta": "All long-form evidence remains available below.",
                "tone": "ok",
            }
        ]
    cards = "".join(_priority_card(index + 1, signal) for index, signal in enumerate(signals))
    return f"""
      <section class="priority-grid">
        {cards}
      </section>
"""


def _priority_card(index: int, signal: dict[str, object]) -> str:
    tone = str(signal.get("tone") or "warn")
    return f"""
        <article class="priority-card {tone}">
          <div class="priority-top">
            <span class="priority-rank">{index}</span>
            <span class="priority-source">{escape(str(signal.get("source") or "Signal"))}</span>
          </div>
          <div class="priority-title">{escape(str(signal.get("title") or "Untitled signal"))}</div>
          <div class="priority-body">{escape(_short_text(str(signal.get("body") or ""), 92))}</div>
          <div class="priority-meta">{escape(str(signal.get("meta") or ""))}</div>
        </article>
"""


def _collect_priority_signals(
    content: str,
    action_cards: dict[str, dict[str, str]],
    gap_count: int,
) -> list[dict[str, object]]:
    signals: list[dict[str, object]] = []

    for name, detail in action_cards.items():
        action = detail.get("action", "")
        tone = _action_tone(action)
        score = {"risk": 100, "warn": 78, "ok": 52}.get(tone, 60)
        signals.append(
            {
                "score": score,
                "source": "Portfolio",
                "title": f"{name}: {action or 'watch'}",
                "body": detail.get("reason") or detail.get("risk") or "Wait for stronger evidence.",
                "meta": detail.get("risk") or "Risk line unavailable.",
                "tone": tone,
            }
        )

    if gap_count:
        for line in _top_lines_from_sections(content, ["数据缺口", "鏁版嵁缂哄彛"], 2):
            signals.append(
                {
                    "score": 88,
                    "source": "Data Gap",
                    "title": "Input missing",
                    "body": line,
                    "meta": "Fix the data before trusting this signal.",
                    "tone": "warn",
                }
            )

    for line in _top_lines_from_sections(content, ["研报观点变化", "鐮旀姤瑙傜偣鍙樺寲"], 3):
        confidence = _extract_confidence(line)
        signals.append(
            {
                "score": 66 + int(confidence * 22),
                "source": "Research",
                "title": "Research delta",
                "body": line,
                "meta": f"confidence {confidence:.2f}",
                "tone": "ok" if confidence >= 0.7 else "warn",
            }
        )

    for line in _top_lines_from_sections(content, ["事件日历与公告", "浜嬩欢鏃ュ巻涓庡叕鍛"], 2):
        near_term = bool(re.search(r"T\+[0-3]\b|D\+[0-3]\b", line))
        signals.append(
            {
                "score": 76 if near_term else 62,
                "source": "Event",
                "title": "Event watch",
                "body": line,
                "meta": "near term" if near_term else "calendar",
                "tone": "warn",
            }
        )

    for line in _top_lines_from_sections(content, ["外部观点观察", "澶栭儴瑙傜偣瑙傚療"], 2):
        confidence = _extract_confidence(line)
        signals.append(
            {
                "score": 54 + int(confidence * 18),
                "source": "Viewpoint",
                "title": "External view",
                "body": line,
                "meta": f"confidence {confidence:.2f}",
                "tone": "warn",
            }
        )

    signals.sort(key=lambda item: int(item.get("score", 0)), reverse=True)
    return signals


def _top_lines_from_sections(content: str, headings: list[str], limit: int) -> list[str]:
    lines: list[str] = []
    for heading in headings:
        for line in _section_lines_fuzzy(content, heading):
            if not line.startswith("- "):
                continue
            text = line[2:].strip()
            if not text or "暂无" in text or "鏆傛棤" in text:
                continue
            if text not in lines:
                lines.append(text)
            if len(lines) >= limit:
                return lines
    return lines


def _section_lines_fuzzy(content: str, heading_fragment: str) -> list[str]:
    lines = content.splitlines()
    capture = False
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if capture:
                break
            capture = heading_fragment in stripped[3:].strip()
            continue
        if capture and stripped:
            result.append(stripped)
    return result


def _extract_confidence(text: str) -> float:
    patterns = [
        r"(?:置信度|confidence|score)\s*[=:：]?\s*([01](?:\.\d+)?)",
        r"score=([01](?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return max(0.0, min(1.0, float(match.group(1))))
    return 0.5


def _action_tone(action: str) -> str:
    if any(word in action for word in ["减仓", "退出", "降低"]):
        return "risk"
    if any(word in action for word in ["复核", "观察"]):
        return "warn"
    return "ok"


def _signal_row(label: str, state: str, note: str, value_class: str) -> str:
    return f"""
          <div class="signal-row">
            <span>{escape(label)}</span>
            <span class="signal-pill {value_class}">{escape(state)}</span>
            <span class="{value_class}">{escape(note)}</span>
          </div>
"""


def _action_donut(actions: list[str]) -> str:
    total = max(1, len(actions))
    risk = sum(1 for action in actions if any(word in action for word in ["减仓", "退出", "降低"]))
    ok = sum(1 for action in actions if any(word in action for word in ["持有", "等待", "观察"]))
    warn = max(0, len(actions) - risk - ok)
    risk_angle = risk / total * 360
    ok_angle = (risk + ok) / total * 360
    return f"""
        <article class="chart-panel">
          <h3 class="chart-title">Action Mix</h3>
          <div class="donut-wrap" style="--risk-angle:{risk_angle:.1f}deg; --ok-angle:{ok_angle:.1f}deg">
            <div class="donut"><span class="donut-value">{risk}/{len(actions)}</span></div>
            <div class="legend">
              <div><span class="legend-dot risk"></span>Risk review: {risk}</div>
              <div><span class="legend-dot ok"></span>Hold / wait: {ok}</div>
              <div><span class="legend-dot warn"></span>Other watch: {warn}</div>
            </div>
          </div>
        </article>
"""


def _market_breadth_panel(markets: dict[str, list[dict[str, object]]]) -> str:
    rows = []
    for region, items in markets.items():
        values = [float(item["change_pct"]) for item in items if isinstance(item.get("change_pct"), float)]
        positive = sum(1 for value in values if value > 0)
        negative = sum(1 for value in values if value < 0)
        avg = sum(values) / len(values) if values else None
        tone_class = _sentiment_class(avg)
        rows.append(_signal_row(region, _pct_text(avg), f"{positive}+ / {negative}-", tone_class))
    if not rows:
        rows.append(_signal_row("Market", "NA", "no snapshots", "flat"))
    return f"""
        <article class="chart-panel signal-panel">
          <h3 class="chart-title">Market Breadth</h3>
          {''.join(rows)}
        </article>
"""


def _holding_heatmap(
    holdings: list[dict[str, float | str]],
    action_cards: dict[str, dict[str, str]],
) -> str:
    if not holdings:
        tiles = '<article class="heat-tile"><div class="heat-name"><span>暂无</span><span>NA</span></div></article>'
    else:
        max_weight = max([float(item["weight_pct"]) for item in holdings if isinstance(item["weight_pct"], float)] or [1])
        tiles = "".join(_heat_tile(item, action_cards, max_weight) for item in holdings)
    return f"""
      <article class="chart-panel">
        <h3 class="chart-title">Position Heatmap</h3>
        <div class="heatmap-grid">{tiles}</div>
      </article>
"""


def _heat_tile(
    item: dict[str, float | str],
    action_cards: dict[str, str],
    max_weight: float,
) -> str:
    name = str(item["name"])
    action = action_cards.get(name, {}).get("action", "待观察")
    tone = _action_tone(action)
    weight = float(item["weight_pct"]) if isinstance(item["weight_pct"], float) else None
    pnl = float(item["pnl_pct"]) if isinstance(item["pnl_pct"], float) else None
    day = float(item["day_pnl_pct"]) if isinstance(item["day_pnl_pct"], float) else None
    width = min(100, max(4, weight / max_weight * 100)) if weight is not None and max_weight else 4
    weight_text = f"{weight:.1f}%" if weight is not None else "NA"
    return f"""
          <article class="heat-tile {tone}">
            <div class="heat-name"><span>{escape(name)}</span><span class="{_sentiment_class(pnl)}">{_pct_text(pnl)}</span></div>
            <div class="heat-meta">{escape(action)} · day <span class="{_sentiment_class(day)}">{_pct_text(day)}</span> · weight {weight_text}</div>
            <div class="spark-track"><div class="spark-fill" style="width:{width:.1f}%"></div></div>
          </article>
"""


def _metric_card(label: str, value: str, note: str, value_class: str = "") -> str:
    return f"""
          <article class="metric-card">
            <div class="metric-label">{escape(label)}</div>
            <div class="metric-value {value_class}">{escape(value)}</div>
            <div class="metric-note">{escape(note)}</div>
          </article>
"""


def _market_card(region: str, items: list[dict[str, object]]) -> str:
    if not items:
        rows = '<div class="market-row"><span>暂无</span><span class="flat">NA</span></div>'
        tone = "数据不足"
    else:
        valid = [item["change_pct"] for item in items if isinstance(item["change_pct"], float)]
        tone = _market_tone(valid)
        rows = "".join(
            f"""<div class="market-row">
              <span>{escape(str(item["name"]))}</span>
              <span class="{_sentiment_class(item["change_pct"])}">{escape(_pct_text(item["change_pct"]))}</span>
            </div>"""
            for item in items
        )
    return f"""
        <article class="market-card">
          <div class="market-region"><strong>{escape(region)}</strong><span>{escape(tone)}</span></div>
          {rows}
        </article>
"""


def _position_chart(title: str, holdings: list[dict[str, float | str]], field: str) -> str:
    if not holdings:
        rows = '<div class="bar-row"><span>暂无</span><div class="bar-track"></div><span>NA</span></div>'
    else:
        values = [abs(float(item[field])) for item in holdings if isinstance(item[field], float)]
        max_value = max(values) if values else 1
        rows = "".join(_bar_row(item, field, max_value) for item in holdings)
    return f"""
        <article class="chart-panel">
          <h3 class="chart-title">{escape(title)}</h3>
          {rows}
        </article>
"""


def _bar_row(item: dict[str, float | str], field: str, max_value: float) -> str:
    value = float(item[field]) if isinstance(item[field], float) else None
    width = min(100, max(2, abs(value) / max_value * 100)) if value is not None and max_value else 2
    bar_class = "ok" if value is not None and value >= 0 else ("risk" if value is not None else "")
    shown = (f"{value:.1f}%" if field != "market_value" else _money_text(value)) if value is not None else "NA"
    return f"""
          <div class="bar-row">
            <span>{escape(str(item["name"]))}</span>
            <div class="bar-track"><div class="bar-fill {bar_class}" style="width:{width:.1f}%"></div></div>
            <span class="{_sentiment_class(value)}">{escape(shown)}</span>
          </div>
"""


def _parse_broker_holdings(content: str) -> list[dict[str, float | str]]:
    section = _section_lines(content, "券商持仓快照")
    holdings = []
    number_or_missing = r"(?:-?\d+(?:\.\d+)?|未提供)"
    pattern = re.compile(
        rf"^- (?P<name>[^：]+)：仓位 (?P<weight>{number_or_missing})[％%]，成本 .*?，市价 .*?，"
        rf"总盈亏 (?P<pnl>{number_or_missing})(?:[％%])?，当日 (?P<day>{number_or_missing})(?:[％%])?，"
        rf"市值 (?P<value>{number_or_missing})。"
    )
    for line in section:
        match = pattern.match(line)
        if not match:
            continue
        holdings.append(
            {
                "name": match.group("name"),
                "weight_pct": _optional_number(match.group("weight")),
                "pnl_pct": _optional_number(match.group("pnl")),
                "day_pnl_pct": _optional_number(match.group("day")),
                "market_value": _optional_number(match.group("value")),
            }
        )
    return holdings


def _optional_number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _parse_market_snapshots(content: str) -> dict[str, list[dict[str, object]]]:
    section = _section_lines(content, "跨市场宏观温度")
    groups: dict[str, list[dict[str, object]]] = {}
    region = ""
    pattern = re.compile(r"^- (?P<name>[^（]+)（(?P<symbol>[^）]+)）：(?P<price>[\d,.]+)，涨跌 (?P<change>[+-]?\d+(?:\.\d+)?)%")
    for line in section:
        if line.startswith("### "):
            region = line[4:].strip()
            groups.setdefault(region, [])
            continue
        match = pattern.match(line)
        if match and region:
            groups.setdefault(region, []).append(
                {
                    "name": match.group("name"),
                    "symbol": match.group("symbol"),
                    "price": float(match.group("price").replace(",", "")),
                    "change_pct": float(match.group("change")),
                }
            )
    return groups


def _parse_actions(content: str) -> list[str]:
    actions = []
    for line in content.splitlines():
        if line.startswith("- 建议动作："):
            actions.append(line.split("：", 1)[1].strip())
    return actions


def _parse_action_details(content: str) -> dict[str, dict[str, str]]:
    section = _section_lines(content, "持仓动作")
    current = ""
    result: dict[str, dict[str, str]] = {}
    for line in section:
        if line.startswith("### "):
            current = line[4:].split("（", 1)[0].strip()
            result.setdefault(current, {})
            continue
        if current and line.startswith("- 建议动作："):
            result.setdefault(current, {})["action"] = line.split("：", 1)[1].strip()
        elif current and line.startswith("- 核心理由："):
            result.setdefault(current, {})["reason"] = line.split("：", 1)[1].strip()
        elif current and line.startswith("- 风险线："):
            result.setdefault(current, {})["risk"] = line.split("：", 1)[1].strip()
    return result


def _count_meaningful_lines(lines: list[str]) -> int:
    return sum(1 for line in lines if line.startswith("- ") and "暂无" not in line)


def _section_lines(content: str, heading: str) -> list[str]:
    lines = content.splitlines()
    capture = False
    result: list[str] = []
    for line in lines:
        if line == f"## {heading}":
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture and line.strip():
            result.append(line.strip())
    return result


def _average(values: list[float | str]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, float)]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _money_text(value: float | None) -> str:
    if value is None:
        return "NA"
    if abs(value) >= 10000:
        return f"{value / 10000:.1f}万"
    return f"{value:.0f}"


def _pct_text(value: object) -> str:
    if not isinstance(value, (float, int)):
        return "NA"
    return f"{value:+.1f}%"


def _sentiment_class(value: object) -> str:
    if not isinstance(value, (float, int)):
        return "flat"
    if value > 0:
        return "pos"
    if value < 0:
        return "neg"
    return "flat"


def _market_tone(values: list[object]) -> str:
    numeric = [float(value) for value in values if isinstance(value, (float, int))]
    if not numeric:
        return "数据不足"
    avg = sum(numeric) / len(numeric)
    if avg >= 1:
        return "风险偏好较强"
    if avg <= -1:
        return "风险偏好偏弱"
    if avg >= 0:
        return "震荡偏强"
    return "震荡偏弱"


def _short_text(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"


def _extract_title(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return f"{PRODUCT_SLUG} report"


def _markdown_body_to_html(content: str) -> str:
    lines: list[str] = []
    in_ul = False
    in_section = False
    in_card = False
    section_heading = ""

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            lines.append("      </ul>")
            in_ul = False

    def close_card() -> None:
        nonlocal in_card
        close_ul()
        if in_card:
            lines.append("    </article>")
            in_card = False

    def close_section() -> None:
        nonlocal in_section, section_heading
        close_card()
        if in_section:
            lines.append("    </div>")
            lines.append("  </details>")
            in_section = False
            section_heading = ""

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            close_ul()
            continue
        if line.startswith("# "):
            close_section()
            continue
        if line.startswith("## "):
            close_section()
            section_heading = line[3:].strip()
            open_attr = ""
            lines.append(f"  <details class=\"report-section\"{open_attr}>")
            lines.append(f"    <summary><h2>{_inline_html(section_heading)}</h2></summary>")
            lines.append("    <div class=\"section-body\">")
            in_section = True
            continue
        if line.startswith("### "):
            close_card()
            if not in_section:
                lines.append("  <details class=\"report-section\">")
                lines.append("    <summary><h2>Evidence</h2></summary>")
                lines.append("    <div class=\"section-body\">")
                in_section = True
            lines.append("    <article class=\"sub-card\">")
            lines.append(f"      <h3>{_inline_html(line[4:].strip())}</h3>")
            in_card = True
            continue
        if line.startswith("- "):
            if not in_ul:
                lines.append("      <ul>")
                in_ul = True
            item = line[2:].strip()
            lines.append(f"        <li class=\"{_item_class(item)}\">{_inline_html(item)}</li>")
            continue
        close_ul()
        lines.append(f"    <p>{_inline_html(line)}</p>")

    close_section()
    return "\n".join(lines)


def _inline_html(text: str) -> str:
    escaped = escape(text)
    placeholders: dict[str, str] = {}
    markdown_link_re = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
    for index, match in enumerate(markdown_link_re.finditer(text)):
        token = f"@@INSIGHT_LINK_{index}@@"
        source = escape(match.group(0))
        href = escape(match.group(2), quote=True)
        label = escape(match.group(1))
        placeholders[token] = f'<a href="{href}" target="_blank" rel="noreferrer">{label}</a>'
        escaped = escaped.replace(source, token, 1)
    url_re = re.compile(r"(https?://[^\s，。；、）)]+)")
    escaped = url_re.sub(r'<a href="\1" target="_blank" rel="noreferrer">\1</a>', escaped)
    for token, link in placeholders.items():
        escaped = escaped.replace(token, link)
    return escaped


def _item_class(text: str) -> str:
    if any(word in text for word in ["减仓", "退出", "不可用", "失败", "风险", "回撤", "跌停"]):
        return "risk"
    if any(word in text for word in ["暂无", "已披露", "持有/等待", "持有观察"]):
        return "ok"
    if any(word in text for word in ["待补", "复核", "未命中", "需复核", "数据缺口"]):
        return "warn"
    return ""
