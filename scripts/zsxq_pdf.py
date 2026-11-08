#!/usr/bin/env python3
"""Download authorized PDFs in the background; Chrome UI is an explicit fallback."""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "zsxq-pdf"
MAX_BYTES = 50 * 1024 * 1024
COOKIE_FILE = Path.home() / "Library/Application Support/InsightRadar/zsxq-cookie.json"
COOKIE_NAME = "zsxq_access_token"
URL_RE = re.compile(r"https://wx\.zsxq\.com/group/([0-9]+)/topic/([0-9]+)/?\Z")


class Failure(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def inputs(url: str, name: str) -> tuple[str, str, str]:
    match = URL_RE.fullmatch(url) if isinstance(url, str) else None
    if not match:
        raise Failure("INVALID_URL", "只接受 https://wx.zsxq.com/group/数字/topic/数字 帖子链接，不含查询参数。")
    if (not isinstance(name, str) or not name or name != name.strip() or not name.lower().endswith(".pdf")
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


def import_chrome_cookie(destination: Path, profile: str = "Default") -> dict:
    """Explicit one-time import: only this site's auth cookie, never a DB copy."""
    if sys.platform != "darwin":
        raise Failure("MACOS_REQUIRED", "Chrome Cookie 导入目前只支持 macOS。")
    if not re.fullmatch(r"Default|Profile [0-9]+", profile):
        raise Failure("INVALID_PROFILE", "Chrome 配置名只接受 Default 或 Profile 数字。")
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
    except ImportError:
        raise Failure("COOKIE_IMPORT_DEPENDENCY", "仅首次导入需要 cryptography；可安装项目的 zsxq-cookie 可选依赖。") from None
    database = Path.home() / "Library/Application Support/Google/Chrome" / profile / "Cookies"
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
            version = int(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])
            rows = db.execute("SELECT host_key, path, expires_utc, encrypted_value FROM cookies "
                              "WHERE host_key='.zsxq.com' AND name=? AND is_secure=1", (COOKIE_NAME,)).fetchall()
    except (sqlite3.Error, TypeError, ValueError):
        raise Failure("COOKIE_DATABASE_UNAVAILABLE", "无法只读打开该 Chrome Cookie 数据库；请检查配置目录，不会复制或修改数据库。") from None
    if len(rows) != 1:
        raise Failure("COOKIE_LOGIN_REQUIRED", "未找到唯一的知识星球登录 Cookie；请在指定 Chrome 配置登录后重新导入。")
    host, path, expiry, encrypted = rows[0]
    expires = expiry / 1e6 - 11644473600 if expiry else None
    if expires is not None and expires <= time.time():
        raise Failure("COOKIE_LOGIN_REQUIRED", "Chrome 中的 Cookie 已过期；请本人登录后重新导入。")
    if not encrypted.startswith(b"v10"):
        raise Failure("COOKIE_FORMAT_CHANGED", "Chrome Cookie 加密格式变化；停止导入，不尝试绕过。")
    try:
        keychain = subprocess.run(["/usr/bin/security", "-q", "find-generic-password", "-w",
                                   "-a", "Chrome", "-s", "Chrome Safe Storage"],
                                  capture_output=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        raise Failure("KEYCHAIN_ACCESS_REQUIRED", "钥匙串未授权、已锁定或等待确认超时；请本人处理 macOS 提示后重新导入。日常下载不访问钥匙串。") from None
    try:
        key = hashlib.pbkdf2_hmac("sha1", keychain.stdout.strip(), b"saltysalt", 1003, 16)
        decryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
        unpadder = PKCS7(128).unpadder()
        plain = unpadder.update(decryptor.update(encrypted[3:]) + decryptor.finalize()) + unpadder.finalize()
        if version >= 24:
            if plain[:32] != hashlib.sha256(host.encode()).digest():
                raise ValueError("domain integrity")
            plain = plain[32:]
        cookie = {"name": COOKIE_NAME, "value": plain.decode(), "domain": host, "path": path,
                  "expires": expires, "secure": True}
        validate_cookie(cookie)
    except (ValueError, UnicodeError):
        raise Failure("COOKIE_FORMAT_CHANGED", "Cookie 解密或域名完整性校验失败；未保存任何凭据。") from None
    destination = destination.expanduser()
    if destination.resolve().is_relative_to(ROOT):
        raise Failure("COOKIE_PATH_UNSAFE", "Cookie 导入文件必须放在项目目录之外；建议使用默认私有路径。")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    save(destination, (json.dumps(cookie) + "\n").encode())
    return {"status": "ok", "cookie_imported": True, "cookie_file": str(destination),
            "message": "只导入知识星球登录 Cookie；后续下载不调用 Chrome 或钥匙串。"}


def validate_cookie(cookie: dict) -> str:
    if (not isinstance(cookie, dict) or cookie.get("name") != COOKIE_NAME
            or cookie.get("domain") != ".zsxq.com" or cookie.get("path") != "/"
            or cookie.get("secure") is not True
            or not isinstance(cookie.get("value"), str)
            or not 1 <= len(cookie["value"]) <= 4096
            or any(ord(c) < 33 or ord(c) > 126 or c in '\";,\\' for c in cookie["value"])):
        raise Failure("COOKIE_FILE_INVALID", "Cookie 文件格式不符；请用 --import-chrome-cookie 重新导入，不要在聊天或命令行粘贴凭据。")
    expiry = cookie.get("expires")
    if expiry is not None and (not isinstance(expiry, (int, float)) or not time.time() < expiry < 1e12):
        raise Failure("COOKIE_LOGIN_REQUIRED", "Cookie 已过期或有效期异常；请在 Chrome 登录后运行 --import-chrome-cookie。")
    return cookie["value"]


def load_cookie(path: Path) -> str:
    try:
        fd = os.open(path.expanduser(), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r") as f:
            info = os.fstat(f.fileno())
            if info.st_mode & 0o077 or info.st_uid != os.getuid() or info.st_size > 16384:
                raise Failure("COOKIE_FILE_PERMISSIONS", "Cookie 文件须属于当前用户且仅本人可读写（chmod 600）。")
            return validate_cookie(json.load(f))
    except FileNotFoundError:
        raise Failure("COOKIE_FILE_MISSING", "请先运行 --import-chrome-cookie 导入当前知识星球登录态。") from None
    except (OSError, ValueError):
        raise Failure("COOKIE_FILE_INVALID", "无法读取安全的 Cookie 文件；请检查路径或重新导入。") from None


@contextmanager
def http_get(url: str, timeout: float, cookies: dict | None = None):
    # Separate sessions prevent Set-Cookie/netrc credentials reaching the file CDN.
    with requests.Session() as session:
        session.trust_env = False
        session.proxies.update(requests.utils.get_environ_proxies(url))
        try:
            with session.get(url, cookies=cookies or {}, stream=True, allow_redirects=False,
                             headers={"Referer": "https://wx.zsxq.com/", "Origin": "https://wx.zsxq.com",
                                      "User-Agent": "Mozilla/5.0", "X-Version": "2.99.0"},
                             timeout=(min(10, timeout), min(20, timeout))) as response:
                yield response
        except requests.RequestException:
            raise Failure("DOWNLOAD_NETWORK_FAILED", "后台请求失败或超时；未输出 Cookie/签名地址，未自动重试或打开浏览器。") from None


def response_bytes(response, limit: int, deadline: float) -> bytes:
    body = bytearray()
    for block in response.iter_content(65536):
        body.extend(block)
        if len(body) > limit:
            raise Failure("DOWNLOAD_TOO_LARGE", "响应超过预期大小，已停止读取。")
        if time.monotonic() > deadline:
            raise Failure("DOWNLOAD_TIMEOUT", "后台下载超过时限；不会自动重试或打开浏览器。")
    return bytes(body)


def download_cookie(meta: dict, token: str, seconds: float) -> bytes:
    file_id = str(meta["file_id"])
    if not re.fullmatch(r"[0-9]+", file_id):
        raise Failure("UNVERIFIABLE_ATTACHMENT", "官方附件 ID 格式异常，已停止。")
    # Observed in the official wx.zsxq.com web bundle, not an official MCP API.
    endpoint = f"https://api.zsxq.com/v2/files/{file_id}/download_url"
    deadline = time.monotonic() + seconds
    with http_get(endpoint, seconds, {COOKIE_NAME: token}) as response:
        if response.status_code == 401:
            raise Failure("COOKIE_LOGIN_REQUIRED", "网页登录已失效；请在 Chrome 登录后重新导入 Cookie。")
        if response.status_code in (403, 429):
            raise Failure("DOWNLOAD_ACCESS_DENIED", "下载权限不足、需要验证或被限流；停止，不自动重试。")
        if response.status_code != 200:
            raise Failure("DOWNLOAD_API_CHANGED", "下载地址接口响应异常或重定向；未继续请求。")
        try:
            result = json.loads(response_bytes(response, 65536, deadline))
            if result.get("code") == 401:
                raise Failure("COOKIE_LOGIN_REQUIRED", "网页登录已失效；请在 Chrome 登录后重新导入 Cookie。")
            if result.get("succeeded") is not True:
                raise Failure("DOWNLOAD_ACCESS_DENIED", "下载接口拒绝请求；可能是权限、验证、限流或接口变化。停止，不绕过。")
            url = result["resp_data"]["download_url"]
            parts = urlsplit(url)
            if (parts.scheme != "https" or parts.netloc != "files.zsxq.com"
                    or parts.username or parts.password or parts.fragment):
                raise ValueError("unexpected download host")
        except (ValueError, KeyError, TypeError, AttributeError):
            raise Failure("DOWNLOAD_API_CHANGED", "下载地址格式或官方文件域名变化；已停止，未输出签名地址。") from None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Failure("DOWNLOAD_TIMEOUT", "取得地址时已超过时限，未开始文件请求。")
    with http_get(url, remaining) as response:
        if response.status_code != 200:
            raise Failure("DOWNLOAD_FILE_FAILED", "文件地址过期、拒绝访问或重定向；请稍后重新运行，不自动重试。")
        data = response_bytes(response, meta["size"], deadline)
    if (len(data) != meta["size"] or not data.startswith(b"%PDF-")
            or hashlib.sha256(data).hexdigest() != meta["hash"].lower()):
        raise Failure("FILE_MISMATCH", "后台下载文件大小、PDF 标识或 SHA-256 不符；未保存或读取正文。")
    return data


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
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(value)
    temp.replace(path)


def run(url: str, name: str, downloads: Path, timeout: float = 60,
        transport: str = "cookie", cookie_file: Path = COOKIE_FILE) -> dict:
    url, group, topic = inputs(url, name)
    if sys.platform != "darwin":
        raise Failure("MACOS_REQUIRED", "此工具目前在 macOS 验证；其他平台尚未支持。")
    downloads = downloads.expanduser().resolve()
    if transport == "browser" and not downloads.is_dir():
        raise Failure("DOWNLOADS_MISSING", "下载目录不存在，请用 --downloads 指定 Chrome 实际下载目录。")
    OUTPUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (OUTPUT / ".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Failure("ALREADY_RUNNING", "已有单附件任务运行中，本次不启动。") from None
        meta = load_metadata(group, topic, name)
        token = load_cookie(cookie_file) if transport == "cookie" else None
        if transport == "browser":
            tab = chrome(url)
            state = ready(url, tab, name, {"FILE_READY", "DETAIL_READY"})
        key = hashlib.sha256((url + "\n" + name).encode()).hexdigest()[:20]
        folder = OUTPUT / key
        folder.mkdir(exist_ok=True, mode=0o700)
        pdf = folder / "source.pdf"
        cached = pdf.exists()
        if cached:
            verified_bytes(pdf, meta)
        elif transport == "cookie":
            save(pdf, download_cookie(meta, token, timeout))
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
        receipt = {"status": "ok", "cached": cached, "transport": transport, "topic_url": url, "attachment": meta,
                   "at": datetime.now(timezone.utc).isoformat(), "page_count": parsed["page_count"],
                   "text_chars": sum(len(p["text"]) for p in parsed["pages"]),
                   "image_pages": [p["page"] for p in parsed["pages"] if p["has_images"]],
                   "ocr_performed": False, "pdf": str(pdf), "text": str(folder / "text.txt"),
                   "pages": str(folder / "pages.json"), "trade_authority": "none"}
        save(folder / "result.json", (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode())
        return receipt


def run_batch(manifest: Path, downloads: Path, timeout: float, cookie_file: Path) -> dict:
    try:
        if manifest.stat().st_size > 65536:
            raise ValueError("large manifest")
        tasks = json.loads(manifest.read_text())
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 20:
            raise ValueError("batch size")
        seen = set()
        for item in tasks:
            url, _, _ = inputs(item["topic_url"], item["attachment_name"])
            key = (url, item["attachment_name"])
            if key in seen:
                raise ValueError("duplicate")
            seen.add(key)
    except (OSError, ValueError, TypeError, KeyError, Failure):
        raise Failure("INVALID_BATCH", "清单须为 1–20 个不重复的 topic_url/attachment_name 对象；全量校验通过后才开始串行处理。") from None
    results = []
    for index, item in enumerate(tasks):
        if index:
            time.sleep(2)
        try:
            results.append(run(item["topic_url"], item["attachment_name"], downloads, timeout,
                               "cookie", cookie_file))
        except Failure as e:
            return {"status": "error", "completed": results, "failed_index": index,
                    "code": e.code, "message": str(e), "remaining_not_started": len(tasks) - index - 1}
    return {"status": "ok", "completed": results, "count": len(results)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic_url", nargs="?", help="官方帖子完整链接")
    parser.add_argument("attachment_name", nargs="?", help="单份 PDF 完整文件名，需用引号包住")
    parser.add_argument("--transport", choices=["cookie", "browser"], default="cookie")
    parser.add_argument("--cookie-file", type=Path, default=COOKIE_FILE)
    parser.add_argument("--import-chrome-cookie", action="store_true", help="单独导入当前 Chrome 登录 Cookie；可能需要本人确认钥匙串")
    parser.add_argument("--chrome-profile", default="Default", help="仅导入时使用：Default 或 Profile 数字")
    parser.add_argument("--batch", type=Path, help="1–20 个明确指定的附件 JSON 清单，仅支持后台 Cookie 下载")
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--timeout", type=float, default=60, help="下载等待秒数（5–180）")
    args = parser.parse_args()
    if not 5 <= args.timeout <= 180:
        parser.error("--timeout 必须在 5–180 秒之间")
    if args.import_chrome_cookie:
        if args.topic_url or args.attachment_name or args.batch:
            parser.error("Cookie 导入必须单独运行，不同时下载")
    elif args.batch:
        if args.topic_url or args.attachment_name or args.transport != "cookie":
            parser.error("--batch 只接受清单及 Cookie 后台下载，不混用位置参数/浏览器")
    elif not args.topic_url or not args.attachment_name:
        parser.error("请输入帖子链接和附件名，或使用 --batch / --import-chrome-cookie")
    try:
        if args.import_chrome_cookie:
            result = import_chrome_cookie(args.cookie_file, args.chrome_profile)
        elif args.batch:
            result = run_batch(args.batch, args.downloads, args.timeout, args.cookie_file)
        else:
            result = run(args.topic_url, args.attachment_name, args.downloads, args.timeout,
                         args.transport, args.cookie_file)
    except Failure as e:
        print(json.dumps({"status": "error", "code": e.code, "message": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print(json.dumps({"status": "error", "code": "LOCAL_IO_FAILED", "message": "本地文件读写失败；请检查目录权限和磁盘空间。"}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
