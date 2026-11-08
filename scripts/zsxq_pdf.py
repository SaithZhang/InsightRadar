#!/usr/bin/env python3
"""Download exactly one authorized PDF using official metadata and logged-in Chrome."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "zsxq-pdf"
MAX_BYTES = 50 * 1024 * 1024
URL_RE = re.compile(r"https://wx\.zsxq\.com/group/([0-9]+)/topic/([0-9]+)/?\Z")


class Failure(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def inputs(url: str, name: str) -> tuple[str, str, str]:
    match = URL_RE.fullmatch(url)
    if not match:
        raise Failure("INVALID_URL", "只接受 https://wx.zsxq.com/group/数字/topic/数字 帖子链接，不含查询参数。")
    if (not name or name != name.strip() or not name.lower().endswith(".pdf")
            or any(c in name for c in "/\\") or any(ord(c) < 32 for c in name)
            or len(name.encode()) > 240):
        raise Failure("INVALID_FILENAME", "请输入单份 PDF 的完整文件名，不含路径、通配符或换行。")
    if any(c in name for c in "*?"):
        raise Failure("INVALID_FILENAME", "附件名必须精确匹配，不支持通配符。")
    return url.rstrip("/"), match[1], match[2]


def metadata(payload: dict, group: str, topic: str, name: str) -> dict:
    if payload.get("success") is not True:
        raise Failure("CLI_ACCESS_FAILED", "官方 CLI 未返回成功；请检查 OAuth 登录和星球会员权限。")
    item = payload.get("topic", {})
    if str(item.get("topic_id")) != topic or str(item.get("group", {}).get("group_id")) != group:
        raise Failure("TOPIC_MISMATCH", "官方响应与输入星球/帖子不匹配，已停止。")
    matches = [f for f in item.get("files", []) if f.get("name") == name]
    if len(matches) != 1:
        raise Failure("ATTACHMENT_NOT_UNIQUE", "未找到唯一的同名附件；请核对完整文件名。")
    f = matches[0]
    if (not isinstance(f.get("size"), int) or not 0 < f["size"] <= MAX_BYTES
            or not re.fullmatch(r"[0-9a-fA-F]{64}", str(f.get("hash", "")))):
        raise Failure("UNVERIFIABLE_ATTACHMENT", "附件超过 50 MB，或缺少可核验的大小/SHA-256；已停止下载。")
    return {k: f[k] for k in ("file_id", "name", "size", "hash")}


def load_metadata(group: str, topic: str, name: str) -> dict:
    try:
        result = subprocess.run(["zsxq-cli", "topic", "+detail", "--topic-id", topic, "--json"],
                                capture_output=True, text=True, timeout=40)
    except FileNotFoundError:
        raise Failure("CLI_MISSING", "请先安装官方 zsxq-cli 并执行 zsxq-cli auth login。") from None
    except subprocess.TimeoutExpired:
        raise Failure("CLI_TIMEOUT", "官方主题读取超时，未触发下载；请稍后重试。") from None
    combined = result.stdout + result.stderr
    if re.search(r"not logged in|HTTP 401|authentication failed|未登录|登录.*失效", combined, re.I):
        raise Failure("CLI_LOGIN_REQUIRED", "官方 OAuth 登录已失效：请运行 zsxq-cli auth login 后重试。")
    if result.returncode:
        raise Failure("CLI_ACCESS_FAILED", "官方 CLI 读取失败；请检查 OAuth 登录、会员权限或限流状态。")
    try:
        return metadata(json.loads(result.stdout), group, topic, name)
    except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
        raise Failure("CLI_RESPONSE_CHANGED", "官方 CLI 返回格式变化，已停止；未打印原始私有响应。") from None


# Only the two visible file/download controls are clicked. No cookies, fetch, private
# APIs, arbitrary navigation, browser preferences, or application state are read.
PAGE_JS = r"""(function (expectedUrl, filename, action) {
  const visible = el => el.getClientRects().length > 0;
  const exact = text => Array.from(document.querySelectorAll('button,a,div,span'))
    .filter(el => visible(el) && el.textContent.trim() === text
      && !Array.from(el.children).some(c => c.textContent.trim() === text));
  if (location.href.replace(/\/$/, '') !== expectedUrl) {
    return JSON.stringify({state: /login|passport/.test(location.href) ? 'LOGIN_REQUIRED' : 'WRONG_PAGE'});
  }
  const login = ['微信扫码登录', '扫码登录', '请登录', '重新登录', '登录已过期'];
  if (login.some(t => exact(t).length)) return JSON.stringify({state:'LOGIN_REQUIRED'});
  if (['安全验证', '请完成验证', '滑动验证'].some(t => exact(t).length))
    return JSON.stringify({state:'VERIFICATION_REQUIRED'});
  if (['无权限访问', '没有访问权限', '加入星球', '续费星球'].some(t => exact(t).length))
    return JSON.stringify({state:'ACCESS_DENIED'});
  const download = exact('下载文件');
  const detail = exact('文件详情');
  if (download.length && detail.length) {
    let panel = download[0].parentElement;
    while (panel && !panel.contains(detail[0])) panel = panel.parentElement;
    if (!panel || panel === document.body || !exact(filename).some(el => panel.contains(el)))
      return JSON.stringify({state:'OTHER_FILE_DIALOG'});
    if (download.length !== 1) return JSON.stringify({state:'AMBIGUOUS_CONTROL'});
    if (action === 'download') {
      download[0].click();
      return JSON.stringify({state:'DOWNLOAD_CLICKED'});
    }
    return JSON.stringify({state:'DETAIL_READY'});
  }
  const files = Array.from(document.querySelectorAll('.file-name'))
    .filter(el => visible(el) && el.textContent.trim() === filename);
  if (files.length > 1) return JSON.stringify({state:'AMBIGUOUS_CONTROL'});
  if (files.length === 1) {
    if (action === 'open') { files[0].click(); return JSON.stringify({state:'OPEN_CLICKED'}); }
    return JSON.stringify({state:'FILE_READY'});
  }
  return JSON.stringify({state:document.readyState === 'complete' ? 'FILE_NOT_VISIBLE' : 'LOADING'});
})"""

APPLESCRIPT = '''on run argv
  set targetURL to item 1 of argv
  set tabID to item 2 of argv
  set pageScript to item 3 of argv
  if application "Google Chrome" is not running then error "CHROME_NOT_RUNNING"
  with timeout of 12 seconds
    tell application "Google Chrome"
      repeat with w in windows
        repeat with t in tabs of w
          if tabID is "" then
            if URL of t is targetURL then return (id of t) as text
          else if (id of t) as text is tabID then
            return execute t javascript pageScript
          end if
        end repeat
      end repeat
      if tabID is not "" then error "TARGET_TAB_CLOSED"
      if (count of windows) is 0 then error "CHROME_WINDOW_REQUIRED"
      set t to make new tab at end of tabs of front window with properties {URL:targetURL}
      return (id of t) as text
    end tell
  end timeout
end run
'''


def chrome(url: str, tab: str = "", source: str = "") -> str:
    try:
        p = subprocess.run(["/usr/bin/osascript", "-", url, tab, source], input=APPLESCRIPT,
                           text=True, capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        raise Failure("BROWSER_TIMEOUT", "Chrome 控制超时；请检查系统自动化授权及浏览器响应，不要连续重试下载。") from None
    if p.returncode:
        if "JavaScript" in p.stderr and ("关闭" in p.stderr or "disabled" in p.stderr):
            raise Failure("BROWSER_SCRIPT_DISABLED", "Chrome 未允许 Apple 事件中的 JavaScript；请在“显示/查看 → 开发者”检查该开关。脚本不会修改设置。")
        if "-1743" in p.stderr:
            raise Failure("BROWSER_PERMISSION_DENIED", "macOS 未允许当前终端控制 Chrome；请检查系统设置 → 隐私与安全性 → 自动化。")
        raise Failure("BROWSER_UNAVAILABLE", "无法控制目标 Chrome 标签页；请确认 Chrome 已打开、系统自动化权限可用。")
    return p.stdout.strip()


def page(url: str, tab: str, name: str, action: str = "state") -> str:
    source = PAGE_JS + "(" + ",".join(json.dumps(x, ensure_ascii=True) for x in (url, name, action)) + ")"
    try:
        state = json.loads(chrome(url, tab, source))["state"]
    except (ValueError, KeyError):
        raise Failure("BROWSER_RESPONSE_CHANGED", "网页控制未返回预期状态；已停止，未重试下载。") from None
    errors = {
        "LOGIN_REQUIRED": "Chrome 的知识星球登录已失效。请在同一 Chrome 窗口登录 wx.zsxq.com 后重试。",
        "VERIFICATION_REQUIRED": "网页要求人工验证；请本人完成验证后重试。",
        "ACCESS_DENIED": "网页提示会员权限不足或需续费，未下载。",
        "WRONG_PAGE": "目标标签页发生跳转；请检查输入链接或登录状态。",
        "OTHER_FILE_DIALOG": "页面显示其他附件的详情；请关闭该弹窗后重试。",
        "AMBIGUOUS_CONTROL": "页面存在多个同名附件或下载按钮，已停止以避免下载错误文件。",
    }
    if state in errors:
        raise Failure(state, errors[state])
    return state


def ready(url: str, tab: str, name: str, target: set[str], seconds: float = 20) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = page(url, tab, name)
        if state in target:
            return state
        time.sleep(.5)
    raise Failure("ATTACHMENT_NOT_VISIBLE", "等待附件/详情超时；请检查登录状态、附件名，或网页结构是否变化。未重复点击。")


def snapshot(folder: Path, name: str) -> dict[str, tuple[int, int]]:
    pattern = re.compile(re.escape(name[:-4]) + r"(?: \(\d+\))?\.pdf\Z", re.I)
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in folder.iterdir()
            if p.is_file() and not p.is_symlink() and pattern.fullmatch(p.name)}


def verified_bytes(path: Path, meta: dict) -> bytes:
    if path.is_symlink() or path.stat().st_size != meta["size"]:
        raise Failure("FILE_MISMATCH", "下载文件大小不符合官方元数据，未读取正文。")
    data = path.read_bytes()
    if not data.startswith(b"%PDF-") or hashlib.sha256(data).hexdigest() != meta["hash"].lower():
        raise Failure("FILE_MISMATCH", "下载文件不是预期 PDF 或 SHA-256 不符，未读取正文。")
    return data


def wait_download(folder: Path, name: str, before: dict, meta: dict, seconds: float) -> Path:
    deadline = time.monotonic() + seconds
    stable: dict = {}
    while time.monotonic() < deadline:
        current = snapshot(folder, name)
        for raw, stat in current.items():
            p = Path(raw)
            if stat == before.get(raw) or stat != stable.get(raw) or Path(raw + '.crdownload').exists():
                continue
            if stat[0] == meta["size"]:
                verified_bytes(p, meta)
                return p
        stable = current
        time.sleep(.5)
    raise Failure("DOWNLOAD_TIMEOUT", "已点击下载一次但未发现校验通过的新文件。请检查 Chrome 下载记录、另存为窗口及 --downloads 路径；不会自动重复点击。")


def extract(path: Path) -> dict:
    source = '''import json, sys
from pypdf import PdfReader
r=PdfReader(sys.argv[1])
if r.is_encrypted or len(r.pages)>200: raise ValueError('encrypted or over 200 pages')
pages=[]
for i,p in enumerate(r.pages):
    t=p.extract_text() or ''
    if len(t)>200000: raise ValueError('page text too large')
    pages.append({'page':i+1,'text':t,'has_images':bool(p.images)})
if not any(p['text'].strip() for p in pages): raise ValueError('no text layer')
print(json.dumps({'pages':pages,'page_count':len(pages),'ocr_performed':False}))
'''
    try:
        p = subprocess.run([sys.executable, "-c", source, str(path)], capture_output=True,
                           text=True, timeout=30, check=True)
        return json.loads(p.stdout)
    except (subprocess.SubprocessError, ValueError):
        raise Failure("PDF_UNREADABLE", "PDF 解析失败：可能加密、无文本层、超过 200 页或解析超时；原文件保留，不自动 OCR。") from None


def save(path: Path, value: bytes) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as f:
        os.chmod(temp, 0o600)
        f.write(value)
    temp.replace(path)


def run(url: str, name: str, downloads: Path, timeout: float = 60) -> dict:
    url, group, topic = inputs(url, name)
    if sys.platform != "darwin":
        raise Failure("MACOS_REQUIRED", "此脚本目前只支持 macOS 上已登录的 Google Chrome。")
    downloads = downloads.expanduser().resolve()
    if not downloads.is_dir():
        raise Failure("DOWNLOADS_MISSING", "下载目录不存在，请用 --downloads 指定 Chrome 实际下载目录。")
    OUTPUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (OUTPUT / ".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Failure("ALREADY_RUNNING", "已有单附件任务运行中，本次不启动。") from None
        meta = load_metadata(group, topic, name)
        tab = chrome(url)
        state = ready(url, tab, name, {"FILE_READY", "DETAIL_READY"})
        key = hashlib.sha256((url + "\n" + name).encode()).hexdigest()[:20]
        folder = OUTPUT / key
        folder.mkdir(exist_ok=True, mode=0o700)
        pdf = folder / "source.pdf"
        cached = pdf.exists()
        if cached:
            verified_bytes(pdf, meta)
        else:
            if state != "DETAIL_READY":
                page(url, tab, name, "open")
                ready(url, tab, name, {"DETAIL_READY"})
            before = snapshot(downloads, name)
            # Never retry a click: an Apple Event timeout may still have acted.
            if page(url, tab, name, "download") != "DOWNLOAD_CLICKED":
                raise Failure("DOWNLOAD_NOT_STARTED", "附件详情已变化，未点击下载。")
            original = wait_download(downloads, name, before, meta, timeout)
            save(pdf, verified_bytes(original, meta))
        parsed = extract(pdf)
        save(folder / "pages.json", (json.dumps(parsed, ensure_ascii=False, indent=2) + "\n").encode())
        text = "\n\n".join(f"--- 第 {p['page']} 页 ---\n{p['text']}" for p in parsed["pages"])
        save(folder / "text.txt", text.encode())
        receipt = {"status": "ok", "cached": cached, "topic_url": url, "attachment": meta,
                   "at": datetime.now(timezone.utc).isoformat(), "page_count": parsed["page_count"],
                   "text_chars": sum(len(p["text"]) for p in parsed["pages"]),
                   "image_pages": [p["page"] for p in parsed["pages"] if p["has_images"]],
                   "ocr_performed": False, "pdf": str(pdf), "text": str(folder / "text.txt"),
                   "pages": str(folder / "pages.json"), "trade_authority": "none"}
        save(folder / "result.json", (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode())
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic_url", help="官方帖子完整链接")
    parser.add_argument("attachment_name", help="单份 PDF 完整文件名，需用引号包住")
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--timeout", type=float, default=60, help="下载等待秒数（5–180）")
    args = parser.parse_args()
    if not 5 <= args.timeout <= 180:
        parser.error("--timeout 必须在 5–180 秒之间")
    try:
        result = run(args.topic_url, args.attachment_name, args.downloads, args.timeout)
    except Failure as e:
        print(json.dumps({"status": "error", "code": e.code, "message": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print(json.dumps({"status": "error", "code": "LOCAL_IO_FAILED", "message": "本地文件读写失败；请检查目录权限和磁盘空间。"}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
