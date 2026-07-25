"""Self-evolution workflow for converting report gaps into backlog."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from stock_assist.paths import CONFIG_DIR, DATA_DIR, PROJECT_ROOT, REPORT_DIR
from stock_assist.product_governance import (
    DEFAULT_GOVERNANCE_PATH,
    GovernanceSnapshot,
    governance_markdown_lines,
    load_governance_snapshot,
)
from stock_assist.reports import bullet
from stock_assist.signal_outcomes import load_outcome_snapshot, outcome_markdown_lines


KEYWORDS = {
    "portfolio": ["未找到持仓", "暂无持仓", "portfolio.manual.tsv", "portfolio.json"],
    "portfolio_context": ["未找到组合上下文", "needs_context", "买入逻辑=券商持仓导入"],
    "data_source": ["AmazingData 不可用", "Missing required", "查询失败", "数据不可用"],
    "industry": ["未配置产业", "候选股票池"],
    "influencer": ["大V", "influencer", "外部观点观察"],
    "unverified_views": ["待验证观点", "需复核", "二手转述"],
    "report_integration": ["未命中当前持仓", "暂无持仓，先作为观察池线索"],
    "crypto": ["加密资产监控", "Hyperliquid", "清算风险"],
}


FEATURE_PATH = PROJECT_ROOT / "feature_list.json"


def build_evolution_report(
    report_dir: Path = REPORT_DIR,
    feature_path: Path = FEATURE_PATH,
    governance_path: Path = DEFAULT_GOVERNANCE_PATH,
) -> str:
    features = _load_features(feature_path)
    feature_status = _feature_status(features)
    governance = load_governance_snapshot(governance_path, feature_path)
    local_state = _local_data_state()
    gaps: dict[str, int] = {key: 0 for key in KEYWORDS}
    files = (
        [path for path in sorted(report_dir.glob("*.md")) if not path.name.endswith("-evolution.md")]
        if report_dir.exists()
        else []
    )
    for path in files[-30:]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for key, words in KEYWORDS.items():
            if any(word in text for word in words):
                gaps[key] += 1
    backlog = _bound_backlog(_build_backlog(gaps, feature_status, local_state), governance)
    outcome_snapshot = load_outcome_snapshot()
    return "\n".join(
        [
            "# \u81ea\u6211\u8fdb\u5316\u62a5\u544a", "",
            "## \u6700\u8fd1\u62a5\u544a\u626b\u63cf", bullet([f"{key}: {value}" for key, value in gaps.items()]), "",
            "## \u5f53\u524d\u80fd\u529b\u72b6\u6001", bullet(_feature_lines(features)), "",
            "## \u4ea7\u54c1\u5b9e\u9a8c\u6cbb\u7406", bullet(governance_markdown_lines(governance)), "",
            "## \u672c\u5730\u6570\u636e\u7f3a\u53e3", bullet(_local_state_lines(local_state)), "",
            "## \u4fe1\u53f7\u540e\u9a8c\u8bc4\u5206", bullet(outcome_markdown_lines(outcome_snapshot)), "",
            "## \u4e0b\u4e00\u8f6e backlog", bullet(backlog),
        ]
    )


def _load_features(path: Path = FEATURE_PATH) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    raw_features = payload.get("features", []) if isinstance(payload, dict) else []
    return [item for item in raw_features if isinstance(item, dict) and item.get("id")]


def _feature_status(features: list[dict[str, object]]) -> dict[str, str]:
    return {str(item["id"]): str(item.get("status", "unknown")) for item in features}


def _feature_number(item: dict[str, object]) -> int:
    try:
        return int(str(item["id"]).split("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def _local_data_state() -> dict[str, bool]:
    return {
        "portfolio_input": (
            (DATA_DIR / "portfolio.manual.tsv").exists()
            or (DATA_DIR / "portfolio.json").exists()
            or (DATA_DIR / "portfolio.galaxy.tsv").exists()
        ),
        "portfolio_context": (DATA_DIR / "portfolio_context.json").exists(),
        "amazingdata_env": (PROJECT_ROOT / ".env").exists(),
        "crypto_watchlist": (CONFIG_DIR / "crypto_watchlist.json").exists(),
        "crypto_watchlist_example": (CONFIG_DIR / "crypto_watchlist.example.json").exists(),
        "research_sources": (CONFIG_DIR / "research_sources.json").exists(),
        "influencer_observations": (DATA_DIR / "influencer_observations.jsonl").exists(),
        "signal_outcomes": (DATA_DIR / "signal_outcomes.jsonl").exists(),
    }


def _feature_lines(features: list[dict[str, object]]) -> list[str]:
    counts = Counter(str(item.get("status", "unknown")) for item in features)
    lines = [
        "\u72b6\u6001\u6c47\u603b：" + ", ".join(
            f"{status}={counts[status]}" for status in sorted(counts)
        )
    ]
    unfinished = [item for item in features if str(item.get("status")) != "pass"]
    latest_pass = sorted(
        [item for item in features if str(item.get("status")) == "pass"],
        key=_feature_number,
    )[-8:]
    visible = sorted(unfinished, key=_feature_number) + latest_pass
    lines.extend(
        f"{item['id']} {item.get('name', 'Unnamed feature')}: "
        f"{item.get('status', 'unknown')}"
        for item in visible
    )
    return lines


def _bound_backlog(backlog: list[str], snapshot: GovernanceSnapshot) -> list[str]:
    if snapshot.remaining_queue_slots == 0:
        return ["\u5b9e\u9a8c\u961f\u5217\u5df2\u6ee1；\u5148\u5b8c\u6210\u3001\u7ec8\u6b62\u6216\u79fb\u51fa\u65e2\u6709\u5b9e\u9a8c，\u4e0d\u65b0\u589e\u529f\u80fd\u3002"]
    if not backlog:
        return ["\u6682\u65e0\u8db3\u591f\u8bc1\u636e\u5f62\u6210\u65b0\u5b9e\u9a8c；\u4fdd\u7559\u961f\u5217\u5bb9\u91cf，\u4e0d\u4e3a\u586b\u6ee1 backlog \u800c\u9020\u529f\u80fd\u3002"]
    return [f"\u5019\u9009（\u5c1a\u672a\u83b7\u51c6）：{item}" for item in backlog[: snapshot.remaining_queue_slots]]


def _local_state_lines(local_state: dict[str, bool]) -> list[str]:
    lines = []
    if not local_state["portfolio_input"]:
        lines.append("缺少真实持仓输入：data/portfolio.manual.tsv、data/portfolio.json 或 data/portfolio.galaxy.tsv。")
    if not local_state["portfolio_context"]:
        lines.append("缺少组合研究记忆：data/portfolio_context.json，报告只能显示 needs_context。")
    if not local_state["amazingdata_env"]:
        lines.append("缺少 .env，AmazingData doctor/盘后行情可能无法登录。")
    if not local_state["crypto_watchlist"] and local_state["crypto_watchlist_example"]:
        lines.append("缺少正式加密监控配置：configs/crypto_watchlist.json，目前只能回退示例。")
    if not local_state["research_sources"]:
        lines.append("缺少正式研报监测配置：configs/research_sources.json。")
    if not local_state["influencer_observations"]:
        lines.append("缺少大V观点流水：data/influencer_observations.jsonl。")
    if not local_state["signal_outcomes"]:
        lines.append("缺少信号后验账本：先运行 after-close 生成 data/signal_outcomes.jsonl。")
    return lines or ["关键本地输入已就绪。"]


def _build_backlog(
    gaps: dict[str, int],
    feature_status: dict[str, str],
    local_state: dict[str, bool],
) -> list[str]:
    backlog: list[str] = []
    if not local_state["portfolio_context"] and feature_status.get("feat-003") == "pass":
        backlog.append("P0：按 data/portfolio_context.example.json 补真实 portfolio_context，让持仓从 needs_context 进入可复盘状态。")
    elif not local_state["portfolio_input"]:
        backlog.append("P0：补 data/portfolio.manual.tsv、data/portfolio.json 或 data/portfolio.galaxy.tsv，让盘后指引有稳定真实对象。")

    if feature_status.get("feat-004") != "pass":
        backlog.append("P0：完成 evolve 的能力状态读取和本地数据缺口识别，避免重复旧 backlog。")

    if not local_state["crypto_watchlist"] and feature_status.get("feat-009") == "pass":
        backlog.append("P1：把 configs/crypto_watchlist.example.json 复制成正式配置，并按真实观察地址/阈值维护。")

    if feature_status.get("feat-006") == "planned":
        backlog.append("P1：实现研究假设 tracker：催化剂、反证条件、观察窗口、下次复盘日期。")
    if feature_status.get("feat-007") == "planned":
        backlog.append("P1：增加同业比较证据层，把持仓估值、业绩和板块承接放到同一张判断表。")
    if feature_status.get("feat-008") == "planned":
        backlog.append("P1：增加事件日历和公告 watchlist，区分事件风险和普通价格波动。")

    if feature_status.get("feat-012") == "planned":
        backlog.append("P1：接入全网研报监测，把券商/行业/宏观研报命中持仓和主题后写入每日研究流。")

    if feature_status.get("feat-027") != "pass":
        backlog.append("P1：建立信号后验账本，按 1/5/20 个交易日记录收益、命中率和最大有利/不利波动。")

    if feature_status.get("feat-011") != "pass" and (gaps["unverified_views"] or gaps["report_integration"]):
        backlog.append("P2：为外部观点补一手链接、命中持仓/产业池映射和价格后验，降低二手摘要权重。")
    if gaps["data_source"]:
        backlog.append("P2：保留 AmazingData/CNInfo 失败样本，给报告开头的数据可用性增加更具体诊断。")
    return backlog
