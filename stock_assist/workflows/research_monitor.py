"""Research-report monitoring workflow."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from stock_assist.data_sources.eastmoney_reports import (
    ResearchReport,
    fetch_recent_report_groups,
    fetch_report_cli_groups,
)
from stock_assist.paths import CONFIG_DIR, DATA_DIR, PROJECT_ROOT
from stock_assist.portfolio import Holding, load_portfolio
from stock_assist.reports import bullet


DEFAULT_CONFIG_PATH = CONFIG_DIR / "research_sources.json"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "research_sources.example.json"


@dataclass(frozen=True)
class SkillCandidate:
    name: str
    slug: str
    reason: str
    url: str


@dataclass(frozen=True)
class ReportExtraction:
    report: ResearchReport
    status: str
    text: str = ""
    note: str = ""


@dataclass(frozen=True)
class ThesisDelta:
    report: ResearchReport
    matched: tuple[str, ...]
    delta: str
    confidence: float
    evidence: str
    source_status: str


SKILLHUB_CANDIDATES = (
    SkillCandidate(
        "研报查询助手",
        "report-ea",
        "直接覆盖行业研报、个股研报、策略报告、宏观研究和券商晨报查询下载。",
        "https://skillhub.cn/skills/report-ea",
    ),
    SkillCandidate(
        "研报观点挖掘",
        "report-analysis",
        "适合把头部券商观点做分歧归纳、来源标注和目标价/评级查询。",
        "https://skillhub.cn/skills/report-analysis",
    ),
    SkillCandidate(
        "金融界资讯研报搜索",
        "jrj-fin-search-skill",
        "资讯与研报摘要合在一起，适合做信息校准和每日/每周复盘。",
        "https://skillhub.cn/skills/jrj-fin-search-skill",
    ),
    SkillCandidate(
        "yanbaoke-research-report-download研报客",
        "yanbaoke-research-report-download",
        "覆盖机构报告库和源文件下载，后续可作为 PDF 正文补全来源。",
        "https://skillhub.cn/skills/yanbaoke-research-report-download",
    ),
)


GITHUB_CANDIDATES = (
    (
        "manymore13/report-cli",
        "查询和下载研究报告的命令行工具，覆盖行业、策略、宏观、晨报、个股研报，并支持 CSV 导出。",
        "https://github.com/manymore13/report-cli",
    ),
    (
        "lzhttn/EastmoneyCrawler",
        "东方财富研报 PDF 批量下载爬虫，覆盖股票、行业、策略研究报告。",
        "https://github.com/lzhttn/EastmoneyCrawler",
    ),
    (
        "qingxuantang/eastmoney_parser",
        "提取东方财富研报汇总数据到本地，可作为后续离线库设计参考。",
        "https://github.com/qingxuantang/eastmoney_parser",
    ),
)


def build_research_monitor_report(config_path: Path | None = None) -> str:
    path = config_path or DEFAULT_CONFIG_PATH
    config, gaps = _load_config(path)
    lookback_days = int(config.get("lookback_days", 7))
    page_size = int(config.get("page_size", 20))
    pdf_extract_limit = int(config.get("pdf_extract_limit", 5))
    delta_path = _resolve_project_path(str(config.get("research_delta_path") or "data/research_deltas.jsonl"))
    watch_keywords = _string_list(config.get("watch_keywords"))

    portfolio = load_portfolio()
    providers = config.get("providers", {})
    if not isinstance(providers, dict):
        providers = {}
    groups, source_gaps, provider_lines = _fetch_report_groups(
        config=config,
        providers=providers,
        portfolio=portfolio,
        lookback_days=lookback_days,
        page_size=page_size,
    )
    gaps.extend(source_gaps)
    if provider_lines:
        gaps.insert(0, f"数据源：{'; '.join(provider_lines)}")
    all_reports = [report for reports in groups.values() for report in reports]
    matched_reports = _match_reports(all_reports, portfolio.holdings, watch_keywords)
    extractions = _extract_report_texts(matched_reports[:pdf_extract_limit])
    deltas = _build_thesis_deltas(matched_reports, extractions, portfolio.holdings, watch_keywords)
    written = _append_research_deltas(delta_path, deltas)

    lines = [
        "# 全网研报监测",
        "",
        "## 数据状态",
        bullet(
            [
                f"配置文件：{path}",
                f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"研报监测窗口：公共源近 {lookback_days} 天，report-cli 持仓源最多回看 90 天，每类最多 {page_size} 条。",
                f"PDF 正文抽取：本次最多尝试 {pdf_extract_limit} 条命中研报；正文不可用时会降级到元数据判断。",
                f"研究变化写入：{delta_path}，本次新增 {written} 条。",
            ]
            + gaps
        ),
        "",
        "## SkillHub/GitHub 可借能力",
        _format_external_capabilities(),
        "",
        "## 研报流概览",
        _format_report_groups(groups),
        "",
        "## 命中持仓/主题",
        _format_matches(matched_reports, portfolio.holdings, watch_keywords),
        "",
        "## PDF 正文抽取",
        _format_extractions(extractions),
        "",
        "## Thesis Delta",
        _format_deltas(deltas),
        "",
        "## 竞品差距与产品改进",
        _format_product_gaps(),
        "",
        "## 下一步",
        bullet(
            [
                "把本报告接入 after-close，让每日盘后报告自动引用最新命中研报。",
                "如果东方财富 PDF 继续返回反爬脚本页，优先接入 report-cli 或 SkillHub 研报查询助手补全文源。",
                "把 `data/research_deltas.jsonl` 中高置信度变化接入 after-close 的持仓研究假设区。",
                "加入提醒规则：新覆盖、评级上调/下调、目标价变化、同业集中发布、宏观策略冲突。",
            ]
        ),
    ]
    return "\n".join(lines)


def _load_config(path: Path) -> tuple[dict[str, Any], list[str]]:
    gaps: list[str] = []
    if not path.exists():
        gaps.append(f"未找到正式配置，已使用示例配置：{EXAMPLE_CONFIG_PATH}")
        path = EXAMPLE_CONFIG_PATH
    if not path.exists():
        gaps.append("示例配置也不存在，使用内置默认关键词。")
        return {
            "watch_keywords": ["AI", "半导体", "储能", "有色", "医药"],
            "lookback_days": 7,
            "pdf_extract_limit": 5,
            "research_delta_path": "data/research_deltas.jsonl",
        }, gaps
    return json.loads(path.read_text(encoding="utf-8")), gaps


def _fetch_report_groups(
    *,
    config: dict[str, Any],
    providers: dict[str, Any],
    portfolio: Any,
    lookback_days: int,
    page_size: int,
) -> tuple[dict[str, list[ResearchReport]], list[str], list[str]]:
    groups: dict[str, list[ResearchReport]] = {}
    gaps: list[str] = []
    provider_lines: list[str] = []

    report_cli_config = providers.get("report_cli", {})
    if not isinstance(report_cli_config, dict):
        report_cli_config = {}
    if report_cli_config.get("enabled", True):
        stock_codes = [holding.code for holding in portfolio.holdings]
        stock_codes.extend(_string_list(report_cli_config.get("watch_stock_codes")))
        include_types = _string_list(report_cli_config.get("include_types")) or ["strategy", "macro", "morning"]
        cli_groups, cli_gaps = fetch_report_cli_groups(
            stock_codes=stock_codes,
            industry_codes=_string_list(report_cli_config.get("industry_codes")),
            include_types=include_types,
            lookback_days=max(lookback_days, int(config.get("report_cli_lookback_days", 90))),
            page_size=page_size,
        )
        _merge_report_groups(groups, cli_groups)
        gaps.extend(cli_gaps)
        provider_lines.append(f"report-cli {sum(len(items) for items in cli_groups.values())} 条")

    public_config = providers.get("eastmoney_public", {})
    if not isinstance(public_config, dict):
        public_config = {}
    if public_config.get("enabled", True):
        public_groups, public_gaps = fetch_recent_report_groups(lookback_days=lookback_days, page_size=page_size)
        _merge_report_groups(groups, public_groups)
        gaps.extend(public_gaps)
        provider_lines.append(f"eastmoney_public {sum(len(items) for items in public_groups.values())} 条")

    return groups, gaps, provider_lines


def _merge_report_groups(target: dict[str, list[ResearchReport]], incoming: dict[str, list[ResearchReport]]) -> None:
    seen = {_report_key(report) for reports in target.values() for report in reports}
    for label, reports in incoming.items():
        bucket = target.setdefault(label, [])
        for report in reports:
            key = _report_key(report)
            if key in seen:
                continue
            seen.add(key)
            bucket.append(report)


def _report_key(report: ResearchReport) -> str:
    return report.info_code or f"{report.title}|{report.org}|{report.publish_date}"


def _format_external_capabilities() -> str:
    skill_lines = [
        f"{item.name}（{item.slug}）：{item.reason} 主页：{item.url}" for item in SKILLHUB_CANDIDATES
    ]
    github_lines = [f"{name}：{reason} 链接：{url}" for name, reason, url in GITHUB_CANDIDATES]
    return "\n".join(["### SkillHub 候选", bullet(skill_lines), "", "### GitHub 候选", bullet(github_lines)])


def _format_report_groups(groups: dict[str, list[ResearchReport]]) -> str:
    parts: list[str] = []
    for label, reports in groups.items():
        parts.append(f"### {label}")
        if not reports:
            parts.append("- 暂无")
            continue
        parts.append(
            bullet(
                [
                    (
                        f"{report.publish_date}｜{report.org}｜{report.title}"
                        f"{_stock_suffix(report)}{_rating_suffix(report)}｜{report.url}"
                    )
                    for report in reports[:10]
                ]
            )
        )
    return "\n".join(parts)


def _format_matches(
    reports: list[ResearchReport],
    holdings: list[Holding],
    watch_keywords: list[str],
) -> str:
    if not reports:
        return "- 暂无研报数据。"
    lines: list[str] = []
    for report in reports[:20]:
        reasons = _match_reasons(report, holdings, watch_keywords)
        if not reasons:
            continue
        lines.append(
            f"{report.publish_date}｜{report.category}｜{report.title}｜命中：{', '.join(reasons)}｜{report.url}"
        )
    if not lines:
        return "- 最近研报未直接命中当前持仓或配置主题，作为行业背景观察。"
    return bullet(lines)


def _format_extractions(extractions: dict[str, ReportExtraction]) -> str:
    if not extractions:
        return "- 暂无命中研报需要抽取。"
    rows = []
    for item in extractions.values():
        snippet = _compact_text(item.text)[:90] if item.text else item.note
        rows.append(f"{item.report.publish_date}｜{item.report.title}｜{item.status}｜{snippet}｜{item.report.pdf_url}")
    return bullet(rows)


def _format_deltas(deltas: list[ThesisDelta]) -> str:
    if not deltas:
        return "- 暂无可写入的观点变化。"
    return bullet(
        [
            (
                f"{item.report.publish_date}｜{item.delta}｜置信度 {item.confidence:.2f}｜"
                f"命中 {', '.join(item.matched)}｜{item.evidence}｜{item.report.url}"
            )
            for item in deltas[:20]
        ]
    )


def _format_product_gaps() -> str:
    return bullet(
        [
            "对标超洞察：它把情报流做了 AI 分级、自动归因和资产详情页；我们目前只有盘后聚合，缺少实时优先级队列。",
            "研报产品化差距：需要报告库、来源可信度、券商/分析师画像、评级/目标价变化、与持仓 thesis 的差异解释。",
            "研究员工作台差距：需要一键看到某持仓最近研报、同业研报密度、策略/宏观冲突、公告与研报是否互相印证。",
            "提醒能力差距：需要新研报命中持仓/行业时触发提醒，而不是等盘后报告人工翻看。",
            "验证闭环差距：需要把研报观点后验到 1/5/20 个交易日价格和基本面事件，给信源打分。",
        ]
    )


def _match_reports(
    reports: list[ResearchReport],
    holdings: list[Holding],
    watch_keywords: list[str],
) -> list[ResearchReport]:
    return [report for report in reports if _match_reasons(report, holdings, watch_keywords)]


def _extract_report_texts(reports: list[ResearchReport]) -> dict[str, ReportExtraction]:
    result: dict[str, ReportExtraction] = {}
    for report in reports:
        result[report.info_code] = _extract_report_text(report)
    return result


def _extract_report_text(report: ResearchReport) -> ReportExtraction:
    if not report.pdf_url:
        return ReportExtraction(report=report, status="no_pdf_url", note="研报元数据未提供 PDF 地址。")
    try:
        data = _download_pdf(report.pdf_url)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return ReportExtraction(report=report, status="download_failed", note=str(exc))
    if not data.startswith(b"%PDF"):
        return ReportExtraction(report=report, status="blocked", note="下载结果不是 PDF，疑似反爬脚本页或阅读限制。")
    try:
        text = _extract_pdf_text(data)
    except Exception as exc:  # pypdf can raise several parser-specific exceptions.
        return ReportExtraction(report=report, status="parse_failed", note=str(exc))
    if not text.strip():
        return ReportExtraction(report=report, status="empty_text", note="PDF 可下载但未抽取到文字。")
    return ReportExtraction(report=report, status="ok", text=text[:3000])


def _download_pdf(url: str) -> bytes:
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=20) as response:
        data = response.read()
    if data.startswith(b"%PDF"):
        return data
    curl_data = _download_pdf_with_curl(url, user_agent)
    return curl_data or data


def _download_pdf_with_curl(url: str, user_agent: str) -> bytes:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
            temp_path = Path(handle.name)
        command = [
            "curl.exe",
            "-L",
            "--silent",
            "--show-error",
            "-A",
            user_agent,
            "-o",
            str(temp_path),
            url,
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if completed.returncode != 0:
            return b""
        data = temp_path.read_bytes()
        return data if data.startswith(b"%PDF") else b""
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return b""
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("缺少 pypdf，无法抽取 PDF 正文。") from exc
    import io

    reader = PdfReader(io.BytesIO(data))
    chunks = []
    for page in reader.pages[:3]:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _build_thesis_deltas(
    reports: list[ResearchReport],
    extractions: dict[str, ReportExtraction],
    holdings: list[Holding],
    watch_keywords: list[str],
) -> list[ThesisDelta]:
    deltas: list[ThesisDelta] = []
    for report in reports:
        matched = tuple(_match_reasons(report, holdings, watch_keywords))
        if not matched:
            continue
        extraction = extractions.get(report.info_code)
        text = extraction.text if extraction else ""
        delta, confidence = _classify_delta(report, text)
        evidence = _evidence_text(report, text)
        deltas.append(
            ThesisDelta(
                report=report,
                matched=matched,
                delta=delta,
                confidence=confidence,
                evidence=evidence,
                source_status=extraction.status if extraction else "metadata_only",
            )
        )
    return deltas


def _classify_delta(report: ResearchReport, text: str) -> tuple[str, float]:
    haystack = f"{report.title} {report.rating} {report.industry} {text[:800]}".lower()
    negative = ["不及预期", "下调", "承压", "领跌", "失守", "走弱", "亏损", "低于预期"]
    positive = ["超预期", "高增", "景气", "看好", "买入", "增持", "推荐", "盈利释放", "需求持续"]
    if any(word in haystack for word in negative):
        return ("反证/削弱", 0.72 if text else 0.56)
    if any(word in haystack for word in positive):
        return ("强化", 0.70 if text else 0.55)
    return ("待验证", 0.48 if text else 0.35)


def _evidence_text(report: ResearchReport, text: str) -> str:
    if text:
        return _compact_text(text)[:160]
    details = [report.title]
    if report.rating:
        details.append(f"评级 {report.rating}")
    if report.industry:
        details.append(f"行业 {report.industry}")
    return "；".join(details)[:160]


def _append_research_deltas(path: Path, deltas: list[ThesisDelta]) -> int:
    if not deltas:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_delta_keys(path)
    rows = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in deltas:
        key = _delta_key(item)
        if key in existing:
            continue
        rows.append(
            {
                "recorded_at": now,
                "key": key,
                "report_date": item.report.publish_date,
                "title": item.report.title,
                "category": item.report.category,
                "org": item.report.org,
                "researcher": item.report.researcher,
                "rating": item.report.rating,
                "stock_code": item.report.stock_code,
                "stock_name": item.report.stock_name,
                "industry": item.report.industry,
                "matched": list(item.matched),
                "delta": item.delta,
                "confidence": item.confidence,
                "evidence": item.evidence,
                "source_status": item.source_status,
                "source": item.report.source,
                "url": item.report.url,
                "pdf_url": item.report.pdf_url,
            }
        )
    if not rows:
        return 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)


def _existing_delta_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("key"):
            keys.add(str(payload["key"]))
    return keys


def _delta_key(item: ThesisDelta) -> str:
    return f"{item.report.info_code}|{','.join(item.matched)}|{item.delta}|{item.source_status}"


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _compact_text(text: str) -> str:
    return " ".join(text.replace("\u3000", " ").split())


def _match_reasons(report: ResearchReport, holdings: list[Holding], watch_keywords: list[str]) -> list[str]:
    haystack = " ".join(
        [report.title, report.stock_code, report.stock_name, report.industry, report.org, report.researcher]
    ).lower()
    reasons: list[str] = []
    for holding in holdings:
        code = holding.code.split(".")[0].lower()
        name = holding.name.lower()
        if code and code in haystack:
            reasons.append(holding.code)
        elif name and name in haystack:
            reasons.append(holding.name)
    for keyword in watch_keywords:
        if keyword.lower() in haystack:
            reasons.append(keyword)
    return list(dict.fromkeys(reasons))


def _stock_suffix(report: ResearchReport) -> str:
    if not report.stock_code and not report.stock_name and not report.industry:
        return ""
    target = report.stock_name or report.industry or report.stock_code
    code = f" {report.stock_code}" if report.stock_code else ""
    return f"｜{target}{code}"


def _rating_suffix(report: ResearchReport) -> str:
    details = []
    if report.rating:
        details.append(f"评级 {report.rating}")
    if report.pages:
        details.append(f"{report.pages}页")
    return f"｜{'，'.join(details)}" if details else ""


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []
