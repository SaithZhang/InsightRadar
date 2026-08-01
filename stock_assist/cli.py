"""Command-line entry points for product workflows."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import sys

from stock_assist.branding import PRODUCT_NAME, PRODUCT_TAGLINE
from stock_assist.after_close_workbench_html import render_after_close_workbench
from stock_assist.collectors.twitter_cli import collect_user_posts
from stock_assist.collectors.twitter_observations import sync_observations_from_twitter_raw
from stock_assist.data_sources.nga import clear_cookie, default_cookie_path, load_cookie, save_cookie
from stock_assist.decision_workspace import record_plan_versions
from stock_assist.harness_eval.smoke import run_contract_smoke
from stock_assist.intraday.polling import poll_intraday
from stock_assist.llm import clear_api_key, default_api_key_path, load_api_key, save_api_key
from stock_assist.reports import write_payload_report_triplet, write_report
from stock_assist.product import command_failure_advice, command_for, product_cli_epilog
from stock_assist.portfolio_import import apply_portfolio_import, parse_classifications, preview_portfolio_import
from stock_assist.portfolio_import_server import serve_portfolio_import
from stock_assist.workflows.after_close import build_after_close_bundle
from stock_assist.workflows.ai_capex_watch import build_ai_capex_watch_bundle
from stock_assist.workflows.agent_roster import build_agent_roster_report
from stock_assist.workflows.architecture_view import build_architecture_view
from stock_assist.workflows.crypto_monitor import build_crypto_monitor_report
from stock_assist.workflows.factor_lab import build_factor_lab_bundle
from stock_assist.workflows.factor_pipeline import build_factor_pipeline_bundle
from stock_assist.workflows.factor_universe import build_factor_universe_bundle
from stock_assist.workflows.evolution import build_evolution_report
from stock_assist.workflows.industry_research import build_industry_pool_report
from stock_assist.workflows.intraday_replay import build_intraday_replay_bundle
from stock_assist.workflows.influencer_sentiment import build_influencer_sentiment_report
from stock_assist.workflows.influencer_skills import build_influencer_skills_report
from stock_assist.workflows.market_pulse import build_market_pulse_bundle
from stock_assist.workflows.market_levels import build_market_levels_bundle
from stock_assist.workflows.nga_monitor import build_nga_monitor_report
from stock_assist.workflows.nga_daily import build_nga_daily_bundle
from stock_assist.workflows.product_map import build_product_map_report
from stock_assist.workflows.research_monitor import build_research_monitor_report
from stock_assist.workflows.risk_watch import build_risk_watch_bundle
from stock_assist.workflows.style_rotation import build_style_rotation_bundle


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"{PRODUCT_NAME} - {PRODUCT_TAGLINE}",
        epilog=product_cli_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("after-close", help=command_for("after-close").help)
    intraday_replay = subparsers.add_parser("intraday-replay", help=command_for("intraday-replay").help)
    intraday_replay.add_argument("--case", type=Path, default=None, help="private IR-001 case JSON; defaults to data/intraday/cases/IR-001.json")
    intraday_replay.add_argument("--refresh-archive", action="store_true", help="refresh and archive point-in-time minute data before replay")
    intraday_replay.add_argument("--no-fallback", action="store_true", help="do not use the per-symbol Eastmoney fallback")
    intraday_poll = subparsers.add_parser("intraday-poll", help=command_for("intraday-poll").help)
    intraday_poll.add_argument("--iterations", type=int, default=1, help="bounded poll count; default is one")
    intraday_poll.add_argument("--interval", type=int, default=60, help="seconds between polls, 5-60")
    intraday_poll.add_argument("--no-fallback", action="store_true", help="do not use the per-symbol Eastmoney fallback")
    portfolio_import = subparsers.add_parser("portfolio-import", help=command_for("portfolio-import").help)
    portfolio_import.add_argument("--file", type=Path, default=None, help="local broker TSV path")
    portfolio_import.add_argument("--classification", action="append", default=[], help="explicit CODE=high_beta|normal|unknown; repeatable")
    portfolio_import.add_argument("--approve", action="store_true", help="explicitly approve atomic save and risk-profile synchronization")
    portfolio_import.add_argument("--no-rerun", action="store_true", help="save only; do not rerun workflows")
    portfolio_import.add_argument("--no-open", action="store_true", help="do not open the latest report after a successful rerun")
    portfolio_import.add_argument("--serve", action="store_true", help="start the token-protected loopback import UI")
    portfolio_import.add_argument("--port", type=int, default=8765, help="loopback UI port")

    industry = subparsers.add_parser("industry-pool", help=command_for("industry-pool").help)
    industry.add_argument("industry", help="industry name configured in configs/industries.json")

    subparsers.add_parser("influencer-skills", help=command_for("influencer-skills").help)
    subparsers.add_parser("influencer-sentiment", help=command_for("influencer-sentiment").help)
    nga_auth = subparsers.add_parser("nga-auth", help=command_for("nga-auth").help)
    nga_auth.add_argument("action", choices=("set", "status", "clear"), help="manage the local NGA cookie")
    nga_monitor = subparsers.add_parser("nga-monitor", help=command_for("nga-monitor").help)
    nga_monitor.add_argument("--config", type=Path, default=None, help="optional NGA monitor json path")
    llm_auth = subparsers.add_parser("llm-auth", help=command_for("llm-auth").help)
    llm_auth.add_argument("action", choices=("set", "status", "clear"), help="manage the local AI API key")
    nga_daily = subparsers.add_parser("nga-daily", help=command_for("nga-daily").help)
    nga_daily.add_argument("--config", type=Path, default=None, help="optional NGA monitor json path")
    nga_daily.add_argument("--date", default=None, help="target date in YYYY-MM-DD")
    nga_daily.add_argument("--window", choices=("morning", "day"), default="day", help="morning or full trading-day evidence window")
    nga_daily.add_argument("--llm", action="store_true", help="use one AI call for semantic clustering and synthesis")
    nga_daily.add_argument("--model", default=None, help="optional OpenAI-compatible model override")
    x_posts = subparsers.add_parser("x-user-posts", help=command_for("x-user-posts").help)
    x_posts.add_argument("handle", help="X/Twitter handle, with or without @")
    x_posts.add_argument("-n", "--max", type=int, default=5, help="maximum number of posts")
    x_sync = subparsers.add_parser("x-sync-observations", help=command_for("x-sync-observations").help)
    x_sync.add_argument("--raw", type=Path, default=None, help="optional raw twitter json file")
    subparsers.add_parser("agents", help=command_for("agents").help)
    harness_smoke = subparsers.add_parser("harness-smoke", help=command_for("harness-smoke").help)
    harness_smoke.add_argument("--manifest", type=Path, default=None, help="optional Harness task manifest")
    harness_smoke.add_argument("--output-dir", type=Path, default=None, help="optional runtime artifact directory")
    subparsers.add_parser("architecture-view", help=command_for("architecture-view").help)
    subparsers.add_parser("evolve", help=command_for("evolve").help)
    crypto = subparsers.add_parser("crypto-monitor", help=command_for("crypto-monitor").help)
    crypto.add_argument("--config", type=Path, default=None, help="optional crypto watchlist json path")
    market = subparsers.add_parser("market-pulse", help=command_for("market-pulse").help)
    market.add_argument("--config", type=Path, default=None, help="optional A-share pulse json path")
    levels = subparsers.add_parser("market-levels", help=command_for("market-levels").help)
    levels.add_argument("--config", type=Path, default=None, help="optional market levels json path")
    style_rotation = subparsers.add_parser("style-rotation", help=command_for("style-rotation").help)
    style_rotation.add_argument("--config", type=Path, default=None, help="optional style rotation json path")
    style_rotation.add_argument("--as-of", default=None, help="optional analysis date YYYY-MM-DD")
    risk_watch = subparsers.add_parser("risk-watch", help=command_for("risk-watch").help)
    risk_watch.add_argument("--config", type=Path, default=None, help="optional risk-watch json path")
    risk_watch.add_argument("--profile", type=Path, default=None, help="optional private portfolio risk profile")
    risk_watch.add_argument("--as-of", default=None, help="optional replay end date YYYY-MM-DD")
    risk_watch.add_argument("--replay-start", default=None, help="optional replay start date YYYY-MM-DD")
    ai_capex = subparsers.add_parser("ai-capex-watch", help=command_for("ai-capex-watch").help)
    ai_capex.add_argument("--config", type=Path, default=None, help="optional AI capex watch json path")
    ai_capex.add_argument("--as-of", default=None, help="optional scoring date YYYY-MM-DD")
    factors = subparsers.add_parser("factor-lab", help=command_for("factor-lab").help)
    factors.add_argument("--config", type=Path, default=None, help="optional factor lab json path")
    pipeline = subparsers.add_parser("factor-pipeline", help=command_for("factor-pipeline").help)
    pipeline.add_argument("--config", type=Path, default=None, help="optional factor pipeline json path")
    universe = subparsers.add_parser("factor-universe-sync", help=command_for("factor-universe-sync").help)
    universe.add_argument("--index-code", default="000852.SH", help="index code, defaults to CSI 1000")
    universe.add_argument("--output", type=Path, default=None, help="membership CSV output path")
    research = subparsers.add_parser("research-monitor", help=command_for("research-monitor").help)
    research.add_argument("--config", type=Path, default=None, help="optional research sources json path")
    subparsers.add_parser("product-map", help=command_for("product-map").help)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "after-close":
            payload, md_content, html_content = build_after_close_bundle()
            workspace = payload.get("decision_workspace")
            if isinstance(workspace, dict):
                workspace["plan_version_history"] = record_plan_versions(workspace)
                html_content = render_after_close_workbench(payload, md_content)
            json_path, md_path, html_path = write_payload_report_triplet("after-close", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "intraday-replay":
            payload, md_content, html_content = build_intraday_replay_bundle(
                args.case,
                refresh_archive=args.refresh_archive,
                allow_fallback=not args.no_fallback,
            )
            json_path, md_path, html_path = write_payload_report_triplet("intraday-replay", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "intraday-poll":
            payload = poll_intraday(
                iterations=args.iterations,
                interval_seconds=args.interval,
                allow_fallback=not args.no_fallback,
            )
            path = json.dumps(payload, ensure_ascii=False, indent=2)
        elif args.command == "portfolio-import":
            if args.serve:
                serve_portfolio_import(port=args.port, open_browser=not args.no_open)
                path = f"portfolio importer stopped: http://127.0.0.1:{args.port}/"
            else:
                if args.file is None:
                    raise ValueError("请提供 --file，或使用 --serve 启动本地导入UI。")
                preview = preview_portfolio_import(
                    args.file.read_text(encoding="utf-8-sig"),
                    classifications=parse_classifications(args.classification),
                )
                if args.approve:
                    result = apply_portfolio_import(
                        preview,
                        approved=True,
                        rerun=not args.no_rerun,
                        open_report=not args.no_open,
                    )
                    path = json.dumps(result, ensure_ascii=False, indent=2)
                else:
                    path = json.dumps(preview, ensure_ascii=False, indent=2)
        elif args.command == "industry-pool":
            path = write_report("industry-pool", build_industry_pool_report(args.industry))
        elif args.command == "influencer-skills":
            path = write_report("influencer-skills", build_influencer_skills_report())
        elif args.command == "influencer-sentiment":
            path = write_report("influencer-sentiment", build_influencer_sentiment_report())
        elif args.command == "nga-auth":
            cookie_path = default_cookie_path()
            if args.action == "set":
                cookie = getpass.getpass("NGA Cookie（输入隐藏，不会写入仓库）: ")
                path = save_cookie(cookie, cookie_path)
            elif args.action == "status":
                try:
                    load_cookie(cookie_path)
                    state = "configured"
                except Exception:
                    state = "missing"
                path = f"{state}: {cookie_path}"
            else:
                removed = clear_cookie(cookie_path)
                path = f"{'removed' if removed else 'already missing'}: {cookie_path}"
        elif args.command == "nga-monitor":
            path = write_report("nga-monitor", build_nga_monitor_report(args.config))
        elif args.command == "llm-auth":
            key_path = default_api_key_path()
            if args.action == "set":
                api_key = getpass.getpass("AI API key（输入隐藏，不会写入仓库）: ")
                path = save_api_key(api_key, key_path)
            elif args.action == "status":
                try:
                    load_api_key(key_path)
                    state = "configured"
                except Exception:
                    state = "missing"
                path = f"{state}: {key_path}"
            else:
                removed = clear_api_key(key_path)
                path = f"{'removed' if removed else 'already missing'}: {key_path}"
        elif args.command == "nga-daily":
            payload, md_content, html_content = build_nga_daily_bundle(
                args.config,
                target_date=args.date,
                window=args.window,
                use_llm=args.llm,
                model=args.model,
            )
            report_name = "nga-morning" if args.window == "morning" else "nga-daily"
            json_path, md_path, html_path = write_payload_report_triplet(report_name, payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "x-user-posts":
            path = collect_user_posts(args.handle, args.max)
        elif args.command == "x-sync-observations":
            path = sync_observations_from_twitter_raw(args.raw)
        elif args.command == "agents":
            path = write_report("agents", build_agent_roster_report())
        elif args.command == "harness-smoke":
            result = run_contract_smoke(args.manifest, args.output_dir)
            report_path = write_report("harness-smoke", result.markdown)
            path = f"{result.trace_path}\n{result.checkpoint_path}\n{report_path}"
        elif args.command == "architecture-view":
            path = build_architecture_view()
        elif args.command == "evolve":
            path = write_report("evolution", build_evolution_report())
        elif args.command == "crypto-monitor":
            path = write_report("crypto-monitor", build_crypto_monitor_report(args.config))
        elif args.command == "market-pulse":
            payload, md_content, html_content = build_market_pulse_bundle(args.config)
            json_path, md_path, html_path = write_payload_report_triplet("market-pulse", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "market-levels":
            payload, md_content, html_content = build_market_levels_bundle(args.config)
            json_path, md_path, html_path = write_payload_report_triplet("market-levels", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "style-rotation":
            payload, md_content, html_content = build_style_rotation_bundle(args.config, as_of=args.as_of)
            json_path, md_path, html_path = write_payload_report_triplet("style-rotation", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "risk-watch":
            payload, md_content, html_content = build_risk_watch_bundle(
                args.config,
                args.profile,
                as_of=args.as_of,
                replay_start=args.replay_start,
            )
            json_path, md_path, html_path = write_payload_report_triplet("risk-watch", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "ai-capex-watch":
            payload, md_content, html_content = build_ai_capex_watch_bundle(args.config, as_of=args.as_of)
            json_path, md_path, html_path = write_payload_report_triplet("ai-capex-watch", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "factor-lab":
            payload, md_content, html_content = build_factor_lab_bundle(args.config)
            json_path, md_path, html_path = write_payload_report_triplet("factor-lab", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "factor-pipeline":
            payload, md_content, html_content = build_factor_pipeline_bundle(args.config)
            json_path, md_path, html_path = write_payload_report_triplet("factor-pipeline", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "factor-universe-sync":
            payload, md_content, html_content = build_factor_universe_bundle(args.index_code, args.output)
            json_path, md_path, html_path = write_payload_report_triplet("factor-universe", payload, md_content, html_content)
            path = f"{json_path}\n{md_path}\n{html_path}"
        elif args.command == "research-monitor":
            path = write_report("research-monitor", build_research_monitor_report(args.config))
        elif args.command == "product-map":
            path = write_report("product-map", build_product_map_report())
        else:
            raise ValueError(f"Unsupported command: {args.command}")
    except Exception as exc:
        print(f"{PRODUCT_NAME} command failed: {args.command}", file=sys.stderr)
        print(f"Error: {exc}", file=sys.stderr)
        try:
            print(command_failure_advice(args.command), file=sys.stderr)
        except KeyError:
            print("Suggested fix: rerun with `insight-radar --help` and check the command inputs.", file=sys.stderr)
        return 1

    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
