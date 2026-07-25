"""Approved local broker import, risk reconciliation, and safe rerun flow."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable, Iterable

from stock_assist.paths import DATA_DIR, REPORT_DIR
from stock_assist.portfolio import BROKER_HEADER_ALIASES, load_portfolio, parse_galaxy_position_table


DEFAULT_PORTFOLIO_PATH = DATA_DIR / "portfolio.json"
DEFAULT_RISK_PROFILE_PATH = DATA_DIR / "risk_watch_profile.json"
VALID_BETA_CLASSES = {"high_beta", "normal", "unknown"}
REQUIRED_RERUN_WORKFLOWS = ("market-levels", "risk-watch", "market-pulse", "style-rotation", "after-close")


def preview_portfolio_import(
    text: str,
    *,
    classifications: dict[str, str] | None = None,
    portfolio_path: Path = DEFAULT_PORTFOLIO_PATH,
    risk_profile_path: Path = DEFAULT_RISK_PROFILE_PATH,
    as_of: str | None = None,
) -> dict[str, object]:
    classification_map = {str(key): str(value) for key, value in (classifications or {}).items()}
    rows = parse_galaxy_position_table(text)
    errors: list[str] = []
    warnings: list[str] = []
    holdings: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        raw_code = _cell(row, "code")
        name = _cell(row, "name")
        market = _cell(row, "market")
        code = _normalize_code(raw_code, market)
        shares = _number(_cell(row, "shares"))
        if shares is None:
            shares = _number(_cell(row, "shares_fallback"))
        if shares is None or shares <= 0:
            continue
        if not code:
            errors.append(f"第{index}行缺少证券代码。")
            continue
        if not name:
            errors.append(f"{code}缺少证券名称。")
        classification = classification_map.get(code, "unknown")
        if classification not in VALID_BETA_CLASSES:
            errors.append(f"{code}的beta分类{classification!r}无效。")
            classification = "unknown"
        market_price = _number(_cell(row, "market_price"))
        market_value = _number(_cell(row, "market_value"))
        weight_pct = _number(_cell(row, "weight_pct"))
        if weight_pct is not None and weight_pct <= 0:
            weight_pct = None
        if market_value is None and market_price is not None:
            market_value = shares * market_price
        holdings.append(
            {
                "code": code,
                "name": name,
                "shares": shares,
                "available": _number(_cell(row, "available")),
                "cost": _number(_cell(row, "cost")),
                "market_price": market_price,
                "pnl": _number(_cell(row, "pnl")),
                "pnl_pct": _number(_cell(row, "pnl_pct")),
                "day_pnl": _number(_cell(row, "day_pnl")),
                "day_pnl_pct": _number(_cell(row, "day_pnl_pct")),
                "market_value": market_value,
                "weight_pct": weight_pct,
                "market": market,
                "beta_classification": classification,
                "thesis": "券商持仓导入，待补买入逻辑。",
                "risk_line": "按原始风险线、市场状态和组合预算复核。",
                "review_status": "needs_context",
            }
        )
    if not rows:
        errors.append("未找到可解析的券商TSV表头和数据行。")
    if not holdings:
        errors.append("未找到当前持仓大于0的记录。")
    if any(item["beta_classification"] == "unknown" for item in holdings):
        warnings.append("存在unknown beta分类；系统没有根据股票代码静默推断高β。")

    old = load_portfolio(portfolio_path)
    old_rows = {
        holding.code: {
            "code": holding.code,
            "name": holding.name,
            "shares": holding.shares,
            "available": holding.available,
            "weight_pct": holding.weight_pct,
            "beta_classification": holding.beta_classification,
        }
        for holding in old.holdings
    }
    new_rows = {str(item["code"]): item for item in holdings}
    differences = _diff_holdings(old_rows, new_rows)
    profile = _load_json_object(risk_profile_path)
    reconciliation = _reconcile_risk(holdings, profile)
    portfolio_payload = {
        "schema_version": "insightradar-portfolio/v2",
        "as_of": as_of or datetime.now().date().isoformat(),
        "cash": None,
        "source_note": "本地券商TSV经用户批准导入；未上传。",
        "risk_reconciliation": reconciliation,
        "holdings": holdings,
    }
    risk_payload = _risk_profile_payload(profile, holdings, reconciliation, portfolio_payload["as_of"])
    return {
        "validation": {"valid": not errors, "errors": errors, "warnings": warnings},
        "old_portfolio_status": "readable" if not old.missing else "missing_or_invalid",
        "differences": differences,
        "proposed_portfolio": portfolio_payload,
        "proposed_risk_profile": risk_payload,
        "risk_reconciliation": reconciliation,
        "approval_required": True,
        "privacy": "local_only_no_upload",
    }


def apply_portfolio_import(
    preview: dict[str, object],
    *,
    approved: bool,
    portfolio_path: Path = DEFAULT_PORTFOLIO_PATH,
    risk_profile_path: Path = DEFAULT_RISK_PROFILE_PATH,
    rerun: bool = True,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
    open_report: bool = True,
) -> dict[str, object]:
    if not approved:
        raise PermissionError("未获得用户明确批准，不写入持仓或风险画像。")
    validation = preview.get("validation") if isinstance(preview.get("validation"), dict) else {}
    if not validation.get("valid"):
        raise ValueError("字段校验未通过，不允许保存。")
    portfolio_payload = preview.get("proposed_portfolio")
    risk_payload = preview.get("proposed_risk_profile")
    if not isinstance(portfolio_payload, dict) or not isinstance(risk_payload, dict):
        raise ValueError("预览缺少待保存payload。")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    portfolio_backup = _backup_path(portfolio_path, timestamp)
    risk_backup = _backup_path(risk_profile_path, timestamp)
    portfolio_temp = _write_temp_json(portfolio_path, portfolio_payload)
    risk_temp = _write_temp_json(risk_profile_path, risk_payload)
    try:
        if portfolio_path.exists():
            shutil.copy2(portfolio_path, portfolio_backup)
        if risk_profile_path.exists():
            shutil.copy2(risk_profile_path, risk_backup)
        os.replace(portfolio_temp, portfolio_path)
        os.replace(risk_temp, risk_profile_path)
    except Exception:
        if portfolio_backup.exists():
            shutil.copy2(portfolio_backup, portfolio_path)
        if risk_backup.exists():
            shutil.copy2(risk_backup, risk_profile_path)
        raise
    finally:
        portfolio_temp.unlink(missing_ok=True)
        risk_temp.unlink(missing_ok=True)

    runs = rerun_required_workflows(runner=runner) if rerun else []
    latest = _latest_after_close_report()
    opened = False
    if open_report and latest is not None:
        import webbrowser

        opened = bool(webbrowser.open(latest.as_uri()))
    return {
        "saved": True,
        "portfolio_path": str(portfolio_path),
        "risk_profile_path": str(risk_profile_path),
        "portfolio_backup": str(portfolio_backup) if portfolio_backup.exists() else None,
        "risk_profile_backup": str(risk_backup) if risk_backup.exists() else None,
        "risk_reconciliation": preview.get("risk_reconciliation"),
        "reruns": runs,
        "latest_report": str(latest) if latest else None,
        "report_opened": opened,
        "authority": "no_trade_execution",
    }


def rerun_required_workflows(
    *,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
    workflows: Iterable[str] = REQUIRED_RERUN_WORKFLOWS,
) -> list[dict[str, object]]:
    active_runner = runner or _default_runner
    results: list[dict[str, object]] = []
    for workflow in workflows:
        command = [sys.executable, "-m", "stock_assist.cli", workflow]
        completed = active_runner(command)
        result = {
            "workflow": workflow,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip()[-2000:],
            "stderr": completed.stderr.strip()[-2000:],
        }
        results.append(result)
        if completed.returncode != 0:
            raise RuntimeError(f"{workflow}重跑失败：{completed.stderr.strip() or completed.stdout.strip()}")
    return results


def parse_classifications(values: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"分类必须使用 CODE=high_beta|normal|unknown：{value}")
        code, classification = value.split("=", 1)
        normalized = _normalize_code(code.strip(), "")
        classification = classification.strip()
        if classification not in VALID_BETA_CLASSES:
            raise ValueError(f"无效beta分类：{classification}")
        result[normalized] = classification
    return result


def _risk_profile_payload(
    existing: dict[str, object],
    holdings: list[dict[str, object]],
    reconciliation: dict[str, object],
    effective_from: object,
) -> dict[str, object]:
    payload = dict(existing)
    weights = [item.get("weight_pct") for item in holdings]
    reconciled = reconciliation.get("status") == "reconciled"
    payload.update(
        {
            "total_exposure_pct": round(sum(float(value) for value in weights), 4) if all(isinstance(value, (int, float)) for value in weights) else None,
            "holding_weights_pct": [float(value) for value in weights if isinstance(value, (int, float))],
            "high_beta_exposure_pct": (
                round(sum(float(item["weight_pct"]) for item in holdings if item.get("beta_classification") == "high_beta"), 4)
                if reconciled
                else None
            ),
            "portfolio_effective_from": effective_from,
            "position_classifications": {str(item["code"]): item.get("beta_classification") for item in holdings},
            "reconciliation_status": reconciliation.get("status"),
            "reconciliation_reason": reconciliation.get("reason"),
        }
    )
    return payload


def _reconcile_risk(holdings: list[dict[str, object]], existing: dict[str, object]) -> dict[str, object]:
    weights_complete = bool(holdings) and all(isinstance(item.get("weight_pct"), (int, float)) for item in holdings)
    classifications_complete = bool(holdings) and all(item.get("beta_classification") in {"high_beta", "normal"} for item in holdings)
    total = sum(float(item["weight_pct"]) for item in holdings) if weights_complete else None
    if total is not None and not (0 <= total <= 100.0001):
        return {"status": "blocked", "reason": "持仓权重合计不在0%-100%范围。", "weight_coverage": 1.0, "classification_coverage": 1.0 if classifications_complete else 0.0}
    if not weights_complete:
        reason = "仓位占比字段不完整，portfolio与risk profile无法对账。"
    elif not classifications_complete:
        reason = "存在unknown beta分类，高β敞口无法对账。"
    else:
        reason = "持仓权重和显式beta分类已与risk profile同步。"
    return {
        "status": "reconciled" if weights_complete and classifications_complete else "blocked",
        "reason": reason,
        "total_exposure_pct": round(total, 4) if total is not None else None,
        "weight_coverage": 1.0 if weights_complete else sum(isinstance(item.get("weight_pct"), (int, float)) for item in holdings) / len(holdings) if holdings else 0.0,
        "classification_coverage": sum(item.get("beta_classification") in {"high_beta", "normal"} for item in holdings) / len(holdings) if holdings else 0.0,
        "existing_profile_status": existing.get("reconciliation_status") or "legacy_unverified",
    }


def _diff_holdings(old: dict[str, dict[str, object]], new: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for code in sorted(set(old) | set(new)):
        if code not in old:
            status = "added"
        elif code not in new:
            status = "removed"
        else:
            fields = ("shares", "available", "weight_pct", "beta_classification")
            status = "changed" if any(old[code].get(field) != new[code].get(field) for field in fields) else "unchanged"
        rows.append({"code": code, "status": status, "old": old.get(code), "new": new.get(code)})
    return rows


def _cell(row: dict[str, str], key: str) -> str:
    for heading in BROKER_HEADER_ALIASES[key]:
        value = row.get(heading)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").replace("％", ""))
    except ValueError:
        return None


def _normalize_code(code: str, market: str) -> str:
    clean = code.strip().upper()
    if "." in clean:
        return clean
    if market.startswith("沪") or clean.startswith(("6", "9")):
        return f"{clean}.SH"
    if market.startswith("深") or clean.startswith(("0", "2", "3")):
        return f"{clean}.SZ"
    return clean


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_temp_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return temporary


def _backup_path(path: Path, timestamp: str) -> Path:
    return path.with_name(f"{path.name}.backup-{timestamp}")


def _latest_after_close_report() -> Path | None:
    paths = sorted(REPORT_DIR.glob("*-after-close.html"), reverse=True)
    return paths[0].resolve() if paths else None


def _default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
