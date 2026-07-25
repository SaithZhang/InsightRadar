"""Read-only Twitter/X collection through the local twitter-cli package."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from stock_assist.paths import DATA_DIR, ensure_runtime_dirs


TWITTER_RAW_DIR = DATA_DIR / "twitter_raw"


class TwitterCliError(RuntimeError):
    """Raised when twitter-cli cannot fetch data."""


def collect_user_posts(handle: str, max_posts: int = 5) -> Path:
    ensure_runtime_dirs()
    TWITTER_RAW_DIR.mkdir(exist_ok=True)
    payload = _run_twitter(["user-posts", handle.lstrip("@"), "--json", "-n", str(max_posts)])
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = TWITTER_RAW_DIR / f"{stamp}-{handle.lstrip('@')}-posts.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_twitter(args: list[str]) -> dict[str, Any]:
    env = _twitter_env()
    exe = Path(sys.executable).with_name("twitter.exe")
    command = [str(exe if exe.exists() else "twitter"), *args]
    result = subprocess.run(
        command,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        detail = output or result.stderr.strip()
        raise TwitterCliError(detail)
    payload = json.loads(output)
    if not payload.get("ok"):
        raise TwitterCliError(json.dumps(payload, ensure_ascii=False))
    return payload


def _twitter_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if os.name == "nt":
        for name in ("TWITTER_AUTH_TOKEN", "TWITTER_CT0"):
            if not env.get(name):
                value = _read_windows_user_env(name)
                if value:
                    env[name] = value
    return env


def _read_windows_user_env(name: str) -> str:
    try:
        import winreg
    except ImportError:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return ""
