"""Local research cards. Revisions are research records, never trading authority."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from stock_assist.paths import DATA_DIR, PROJECT_ROOT

BOARD_PATH = DATA_DIR / "research-board.json"
PILOT_ROOT = PROJECT_ROOT.parent / "InsightRadar-Control"
_LOCK = threading.RLock()
_RUNNING: set[str] = set()
FIELDS = ("title", "question", "keyword", "symbols", "thesis", "entry", "invalidation",
          "exit", "holding_relation", "related_symbols", "as_of", "valid_until")
KINDS = {"fact", "inference", "rumor", "sentiment", "unknown"}
OUTCOMES = {"未触发", "缺证据未行动", "触发未执行", "人工执行待核对", "退出过早", "假设失效", "继续观察"}


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _text(value: object, maximum: int = 4000) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("文字格式不正确或超过长度限制")
    return value.strip()


def _date(value: str) -> str:
    date.fromisoformat(value)
    return value


def _url(value: object) -> str:
    value = _text(value, 2000)
    if value and (urlparse(value).scheme not in {"http", "https"} or not urlparse(value).netloc):
        raise ValueError("来源链接仅支持 http 或 https")
    return value


def _symbols(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 12:
        raise ValueError("最多关联12个证券代码")
    if any(not isinstance(s, str) or not re.fullmatch(r"\d{6}", s) for s in value):
        raise ValueError("证券代码须为6位数字")
    return list(dict.fromkeys(value))


def _read(path: Path) -> dict:
    if not path.exists():
        return {"schema": 1, "revision": 0, "cards": [], "events": [], "holdings_snapshot": None}
    board = json.loads(path.read_text(encoding="utf-8"))
    if board.get("schema") != 1 or not isinstance(board.get("cards"), list):
        raise ValueError("研究数据格式异常；已保留原文件")
    return board


def _write(path: Path, board: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".research-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(board, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _record(board: dict, card: dict, action: str, note: str) -> None:
    card["version"] = card.get("version", 0) + 1
    card["updated_at"] = now()
    snapshot = deepcopy({k: v for k, v in card.items() if k != "history"})
    card.setdefault("history", []).append({"version": card["version"], "at": now(),
                                        "action": action, "note": note, "snapshot": snapshot})
    board["events"].append({"id": uuid.uuid4().hex, "card_id": card["id"], "title": card["title"],
                            "version": card["version"], "action": action, "note": note, "at": now()})
    board["revision"] += 1


def _find(board: dict, ident: object) -> dict:
    card = next((c for c in board["cards"] if c["id"] == ident), None)
    if card is None:
        raise ValueError("研究卡不存在，请刷新")
    return card


def read_board(path: Path = BOARD_PATH) -> dict:
    with _LOCK:
        board = _read(path)
        today = now()[:10]
        changed = False
        discovery = board.get("discovery") or {}
        if discovery.get("status") == "running" and "discovery" not in _RUNNING:
            discovery.update(status="interrupted", message="上次发现任务中断，结果未知；不会自动重发")
            board["revision"] += 1
            changed = True
        for card in board["cards"]:
            job = card.get("job") or {}
            if job.get("status") == "running" and card["id"] not in _RUNNING:
                job.update(status="interrupted", message="上次研究中断，远端结果未知；不会自动重发", finished_at=now())
                _record(board, card, "研究中断", job["message"])
                changed = True
        if changed:
            _write(path, board)
        result = deepcopy(board)
        for card in result["cards"]:
            card["expired"] = bool(card.get("valid_until") and card["valid_until"] < today)
            card["open_gaps"] = sum(not g.get("resolved_by") for g in card["gaps"])
            card["trade_authority"] = "none"
        result["today"] = today
        result["pilot_available"] = (PILOT_ROOT / "radar").is_file()
        return result


def mutate(body: dict, path: Path = BOARD_PATH) -> dict:
    with _LOCK:
        board = _read(path)
        if type(body.get("revision")) is not int or body["revision"] != board["revision"]:
            raise ValueError("页面已有新版本，请刷新后再保存；你的输入尚未覆盖旧记录")
        action = body.get("action")
        if action == "create":
            question = _text(body.get("question", ""), 2000)
            title = _text(body.get("title", ""), 100) or question[:40]
            if not question or not title:
                raise ValueError("请输入要研究的问题")
            card = {key: "" for key in FIELDS}
            card.update(id=uuid.uuid4().hex, title=title, question=question,
                        keyword=_text(body.get("keyword", ""), 40), symbols=_symbols(body.get("symbols", [])),
                        related_symbols=[], as_of=now()[:10], valid_until=_date(body["valid_until"]),
                        status="watch", evidence=[], gaps=[], reviews=[], history=[], version=0, job=None)
            for label in ("需核验支持与反对证据", "当前行情、入场和退出条件待核验", "可用现金与融资余额待对账"):
                card["gaps"].append({"id": uuid.uuid4().hex, "text": label, "resolved_by": None})
            board["cards"].insert(0, card)
            note = "已建立研究卡；尚未形成交易信号"
        else:
            card = _find(board, body.get("card_id"))
            if (card.get("job") or {}).get("status") == "running":
                raise ValueError("研究正在运行，请等待完成后再修改这张卡")
            note = _text(body.get("note", ""), 2000)
            if action == "revise":
                for field in FIELDS:
                    if field not in body:
                        continue
                    value = body[field]
                    if field in {"symbols", "related_symbols"}:
                        value = _symbols(value)
                    else:
                        value = _text(value, 100 if field == "title" else 40 if field == "keyword" else 4000)
                        if field in {"as_of", "valid_until"}:
                            value = _date(value)
                    card[field] = value
                if not card["title"] or not card["question"] or not note:
                    raise ValueError("标题、研究问题和修改原因不能为空")
            elif action == "evidence":
                kind = body.get("kind")
                title = _text(body.get("title", ""), 200)
                content = _text(body.get("text", ""), 5000)
                as_of = _date(body.get("as_of", ""))
                if not title or not content or kind not in KINDS or as_of > now()[:10]:
                    raise ValueError("请填写来源标题、材料内容、有效类型及不晚于今天的材料日期")
                stance = body.get("stance", "context")
                if stance not in {"supports", "opposes", "context"}:
                    raise ValueError("证据方向不正确")
                evidence = {"id": uuid.uuid4().hex, "title": title, "text": content, "kind": kind,
                            "stance": stance, "url": _url(body.get("url", "")), "as_of": as_of,
                            "added_at": now(), "origin": "user_material"}
                card["evidence"].append(evidence)
                gap_id = body.get("gap_id")
                if gap_id:
                    gap = next((g for g in card["gaps"] if g["id"] == gap_id), None)
                    if gap is None or gap.get("resolved_by"):
                        raise ValueError("缺口不存在或已被处理")
                    if kind != "fact" or not evidence["url"]:
                        raise ValueError("处理缺口需提供事实类型和可追溯来源；观点可保留为线索")
                    gap.update(resolved_by=evidence["id"], resolved_at=now())
                note = "追加材料：" + title + ("；用户标记对应缺口已补证，仍需复核" if gap_id else "")
            elif action == "gap":
                text = _text(body.get("text", ""), 500)
                if not text:
                    raise ValueError("请填写缺少的证据")
                card["gaps"].append({"id": uuid.uuid4().hex, "text": text, "resolved_by": None})
                note = text
            elif action == "freeze":
                note = note or "冻结观察版本；缺口仍保留，未授予交易权限"
                card["last_frozen_at"] = now()
            elif action == "status":
                status = body.get("status")
                if status not in {"watch", "paused", "invalidated", "closed"} or not note:
                    raise ValueError("请选择状态并填写原因")
                card["status"] = status
            elif action == "review":
                outcome = body.get("outcome")
                if outcome not in OUTCOMES or not note:
                    raise ValueError("请选择复盘结果并填写当时发生了什么")
                card["reviews"].append({"outcome": outcome, "note": note, "at": now(), "plan_version": card["version"]})
                note = outcome + "：" + note
            else:
                raise ValueError("不支持的研究操作")
        _record(board, card, str(action), note)
        _write(path, board)
        return {"saved": True, "card_id": card["id"], "revision": board["revision"]}


def start_research(body: dict, path: Path = BOARD_PATH) -> dict:
    """Reuse the bounded Pilot CLI in a child process; no arbitrary command/path input."""
    with _LOCK:
        board = _read(path)
        card = _find(board, body.get("card_id"))
        if body.get("revision") != board["revision"]:
            raise ValueError("页面已有新版本，请刷新后重试")
        if (card.get("job") or {}).get("status") == "running":
            return {"started": False, "card_id": card["id"]}
        if _RUNNING:
            raise ValueError("已有研究正在运行，请完成后再发起下一条")
        if not (PILOT_ROOT / "radar").is_file():
            raise ValueError("未找到现有 Research Pilot，仍可手动补充证据")
        mode = body.get("mode", "offline")
        if mode not in {"offline", "ai"}:
            raise ValueError("研究模式不正确")
        if not card["keyword"] or len(card["symbols"]) > 3:
            raise ValueError("归档研究需检索关键词，最多3个证券代码；方向研究可以暂不填代码")
        card["job"] = {"status": "running", "mode": mode, "started_at": now(),
                       "message": "检索本地证据" if mode == "offline" else "调用既有研究 Agent；不自动重试"}
        _RUNNING.add(card["id"])
        _record(board, card, "发起研究", card["job"]["message"])
        _write(path, board)
        thread = threading.Thread(target=_run_research, args=(deepcopy(card), path), daemon=True)
        thread.start()
        return {"started": True, "card_id": card["id"]}


def _run_research(card: dict, path: Path) -> None:
    symbols = [("SH" if s[0] in "569" else "BJ" if s[0] in "48" else "SZ") + s for s in card["symbols"]]
    # Run the existing bounded engine on the child main thread (its deadline uses signals).
    script = """import json,sys
from pilot.core import config
from pilot.runner import Run
task=json.loads(sys.stdin.read())
offline=task.pop('offline')
cfg=config()
run=Run(cfg,task)
if offline:
    run.execute(offline=True)
else:
    try:
        from pilot.model import DeepSeek
        model=DeepSeek(cfg)
    except Exception:
        run.state.update(status='FAILED',error='MODEL_UNAVAILABLE')
        run.finish()
    else:
        run.execute(model=model)
print('运行编号：'+run.folder.name)
"""
    command = [sys.executable, "-c", script]
    task = {"question": card["question"], "keyword": card["keyword"], "symbols": symbols,
            "as_of": now(), "offline": card["job"]["mode"] == "offline"}
    evidence, draft, run_id = [], None, None
    status, message = "failed", "研究未完成；保留原卡与缺口"
    try:
        completed = subprocess.run(command, cwd=PILOT_ROOT, input=json.dumps(task, ensure_ascii=False),
                                   capture_output=True, text=True, timeout=135)
        match = re.search(r"运行编号：(\d{8}-\d{6}-[0-9a-f]{8})", completed.stdout)
        if match:
            run_id = match.group(1)
            folder = PILOT_ROOT / "runtime" / "runs" / run_id
            state = json.loads((folder / "state.json").read_text())
            for file in sorted((folder / "evidence").glob("*.json")):
                item = json.loads(file.read_text())
                result = item["result"]
                if item["tool"] != "search_archive" or not result.get("items"):
                    compact = {k: v for k, v in result.items() if k not in {"snapshot", "source_path", "missing_files"}}
                    evidence.append({"id": uuid.uuid4().hex,
                        "title": {"market_bars": "行情回执", "quant_report": "量化研究回执", "search_archive": "归档检索回执"}.get(item["tool"], "研究回执"),
                        "text": json.dumps(compact, ensure_ascii=False, indent=2)[:5000],
                        "kind": "unknown", "stance": "context", "url": "", "as_of": state.get("created_at", "日期未知"),
                        "added_at": now(), "origin": "pilot_receipt", "source_ref": item.get("evidence_id", ""),
                        "source_id": run_id + ":" + item.get("evidence_id", ""), "run_id": run_id})
                if item["tool"] == "search_archive":
                    for row in result.get("items", []):
                        evidence.append({"id": uuid.uuid4().hex, "title": row.get("title") or f"{result['source']} · {row.get('author') or '作者待核'}",
                            "text": row.get("excerpt", ""), "kind": "unknown", "stance": "context",
                            "url": _url(row.get("url") or ""), "as_of": row.get("published_at", ""),
                            "first_seen_at": row.get("first_seen_at"), "added_at": now(), "origin": "pilot_archive",
                            "source_id": row.get("source_id"), "source_ref": item.get("evidence_id", ""), "run_id": run_id})
            answer = json.loads((folder / "answer.json").read_text())
            if answer:
                draft = {"answer": answer, "run_id": run_id, "at": now(),
                         "note": "AI草稿待核验；引用存在不等于语义正确，不自动修改价格条件或解除缺口"}
            status = "completed" if state["status"] in {"COMPLETED", "EVIDENCE_ONLY"} else "partial"
            message = f"已保存 {len(evidence)} 条材料与回执；覆盖有限。行情回执缺失时仍需补证。"
            if status == "partial":
                message = "研究未完整完成；已保留可用证据。不会自动重试。"
        elif completed.returncode:
            message = "研究入口未完成；未更改条件，可检查原 Pilot 运行记录"
    except subprocess.TimeoutExpired:
        status, message = "interrupted", "研究超时；远端结果可能已产生，不会自动重发"
    except (OSError, ValueError, KeyError, TypeError):
        status, message = "failed", "研究结果无法读取；保留原卡与缺口"
    finally:
        with _LOCK:
            try:
                board = _read(path)
                latest = _find(board, card["id"])
                existing = {(e.get("source_id"), e.get("text")) for e in latest["evidence"]}
                latest["evidence"].extend(e for e in evidence if (e.get("source_id"), e.get("text")) not in existing)
                if draft:
                    latest["ai_draft"] = draft
                latest["job"].update(status=status, message=message, finished_at=now(), run_id=run_id)
                _record(board, latest, "研究返回", message)
                _write(path, board)
            finally:
                _RUNNING.discard(card["id"])


def start_discovery(body: dict, path: Path = BOARD_PATH) -> dict:
    with _LOCK:
        board = _read(path)
        if body.get("revision") != board["revision"]:
            raise ValueError("页面已有新版本，请刷新后重试")
        if _RUNNING:
            raise ValueError("已有研究正在运行，请等待完成")
        if not (PILOT_ROOT / "radar").is_file():
            raise ValueError("现有研究模型入口不可用")
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        board["discovery"] = {"status": "running", "run_id": run_id, "started_at": now(),
                              "message": "确认交易日窗口，读取隔夜归档并核对来源覆盖；未指定方向或标的"}
        board["revision"] += 1
        _write(path, board)
        _RUNNING.add("discovery")
        threading.Thread(target=_run_discovery, args=(run_id, path), daemon=True).start()
        return {"started": True, "run_id": run_id}


def _run_discovery(run_id: str, path: Path) -> None:
    output = path.parent / "research-discovery" / (run_id + ".json")
    result = {"status": "failed", "message": "发现任务未完成，原有研究保持不变"}
    try:
        subprocess.run([sys.executable, "-m", "stock_assist.research_discovery", str(output)],
                       cwd=PROJECT_ROOT, capture_output=True, timeout=90, check=False)
        if output.exists():
            result = json.loads(output.read_text())
        if result["status"] in {"collecting", "running"}:
            result.update(status="interrupted", message="发现任务未正常完成；不会自动重发")
    except subprocess.TimeoutExpired:
        result = {"status": "interrupted", "message": "发现超时，远端结果未知；不会自动重发"}
    except (OSError, ValueError, KeyError):
        pass
    finally:
        with _LOCK:
            try:
                board = _read(path)
                packet = result.get("packet", {})
                board["discovery"].update(status=result["status"], message=result.get("message", ""),
                    finished_at=now(), coverage=packet.get("coverage", []), cutoff=packet.get("cutoff"),
                    window_start=packet.get("window_start"), evidence_count=len(packet.get("items", [])),
                    window_status=packet.get("window_status"), sampling=packet.get("sampling", ""),
                    boundary=packet.get("boundary", ""), calendar=packet.get("calendar", {}),
                    packet_schema=packet.get("schema", 1),
                    summary=result.get("answer", {}).get("summary", ""), model_calls=result.get("model_calls", 0),
                    estimated_usd=result.get("estimated_usd"), http_status=result.get("http_status"),
                    mapping_warnings=result.get("mapping_warnings", []))
                if result["status"] == "completed":
                    _import_discoveries(board, result, run_id)
                board["discovery"]["card_ids"] = [c["id"] for c in board["cards"]
                    if c.get("discovery_run") == run_id or c.get("discovery_update", {}).get("run_id") == run_id]
                board["revision"] += 1
                _write(path, board)
            finally:
                _RUNNING.discard("discovery")


def _import_discoveries(board: dict, result: dict, run_id: str) -> None:
    known = {r["id"]: r for r in result["packet"]["items"]}
    for kind in ("opportunities", "risks"):
        for row in result["answer"][kind]:
            keyword = row["keyword"].split()[0]
            signature = (keyword, kind)
            previous = next((c for c in board["cards"] if c.get("origin") == "discovery"
                             and (c["keyword"], c.get("discovery_kind")) == signature
                             and c["status"] not in {"closed", "invalidated"}), None)
            evidence = []
            for ref in dict.fromkeys(row["evidence_ids"] + row["counter_evidence_ids"]):
                item = known[ref]
                evidence.append({"id": uuid.uuid4().hex, "title": item["title"] or f"{item['source']} · {item['author']}",
                    "text": item["text"], "url": _url(item["url"] or ""), "as_of": item["published_at"],
                    "first_seen_at": item["first_seen_at"], "added_at": now(), "kind": "unknown",
                    "period": item.get("period"), "truncated": item.get("truncated", False),
                    "quoted_text_removed": item.get("quoted_text_removed", False),
                    "stance": "opposes" if ref in row["counter_evidence_ids"] else "supports",
                    "origin": "autonomous_discovery", "run_id": run_id, "source_id": item["source_id"], "source_ref": ref})
            if previous:
                # Continue the existing candidate, never overwrite the user's plan or past thesis.
                # D001 is local to a run. Keeping only source_id/text loses later
                # citation aliases and can point a new draft at old, unrelated D001.
                prior_keys = {(e.get("run_id"), e.get("source_ref"), e.get("source_id")) for e in previous["evidence"]}
                added = [e for e in evidence if (e["run_id"], e["source_ref"], e["source_id"]) not in prior_keys]
                if not added and (previous.get("discovery_run") == run_id or previous.get("discovery_update", {}).get("run_id") == run_id):
                    continue
                previous["evidence"].extend(added)
                previous["discovery_update"] = {"title": row["title"], "reason": row["reason"], "next_check": row["next_check"], "run_id": run_id}
                _record(board, previous, "自主发现更新", "新材料已追加；原预案和原判断未自动改写")
                continue
            card = {key: "" for key in FIELDS}
            excerpts = "\n".join(e["text"] for e in evidence)
            related = [h for h in (board.get("holdings_snapshot") or {}).get("holdings", [])
                       if h["code"] in row["symbols"] or (h.get("name") and h["name"] in excerpts)]
            gaps = [row["next_check"], "最新行情与机械入场、失效、退出条件待核验", "现金与期末融资待对账；不生成新仓数量"]
            gaps.append("发现仅覆盖本次归档抽样；新闻转述和KOL观点需回到原始证据核验")
            if not row["symbols"]:
                gaps.insert(0, "原文未明确对应证券代码；需核验可交易标的映射")
            card.update(id=uuid.uuid4().hex, title=row["title"], question="这个新发现是否足以改变我的观察或持仓？",
                keyword=keyword, symbols=row["symbols"], thesis=row["reason"],
                related_symbols=[h["code"] for h in related],
                holding_relation=("归档直接提及持仓：" + "、".join(h["name"] for h in related) + "。这是名称关联，传导及风险敞口仍需核验；未调整持仓。" if related else "未发现与已有持仓的直接同名关联；行业重叠风险仍需核验。未调整持仓。"),
                as_of=result["packet"]["cutoff"][:10], valid_until=(date.fromisoformat(now()[:10])+timedelta(days=7)).isoformat(),
                status="watch", origin="discovery", discovery_kind=kind, discovery_run=run_id,
                evidence=evidence, gaps=[{"id": uuid.uuid4().hex, "text": g, "resolved_by": None} for g in gaps],
                reviews=[], history=[], version=0, job=None)
            board["cards"].append(card)
            _record(board, card, "自主发现", "从近期归档生成待核验候选；未指定方向或价格，不构成交易信号")
