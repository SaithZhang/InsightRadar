#!/bin/bash
# Foreground local app. No launch agent, global package install, or credential write.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1
export PYTHONUTF8=1
port="${INSIGHTRADAR_PORT:-8765}"
if [[ ! "$port" =~ ^[0-9]+$ ]] || [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
  echo "INSIGHTRADAR_PORT 必须是 1–65535 之间的端口号。" >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "正在创建项目自己的 Python 环境…"
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv --python '>=3.10'
  elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    python3 -m venv .venv
  else
    echo "需要 Python 3.10 或更新版本。安装后重新双击 InsightRadar.command。" >&2
    exit 1
  fi
fi
if [ ! -f .venv/.insightradar-installed ] || [ pyproject.toml -nt .venv/.insightradar-installed ]; then
  echo "正在安装本地工作台依赖（保留现有密钥配置）…"
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python .venv/bin/python -e .
  else
    .venv/bin/python -m pip install -e .
  fi
  touch .venv/.insightradar-installed
fi
case "${1:-start}" in
  setup) echo "Mac 环境已就绪。双击 InsightRadar.command 打开工作台。"; exit 0 ;;
  check) exec ./init.sh ;;
  start) shift "$(( $# > 0 ? 1 : 0 ))" ;;
  --no-open) ;;
  *) echo "用法：scripts/macos.sh [setup|check|start] [--no-open]" >&2; exit 1 ;;
esac
for option in "$@"; do
  if [ "$option" != "--no-open" ]; then
    echo "不支持的启动选项：$option。端口请用 INSIGHTRADAR_PORT 指定。" >&2
    exit 1
  fi
done
# Reuse only this checkout's server; never kill or impersonate a port occupant.
set +e
.venv/bin/python - "$port" "$@" <<'PY'
import hashlib
import json
from pathlib import Path
import socket
import sys
from urllib.request import ProxyHandler, build_opener
import webbrowser

port = int(sys.argv[1])
url = f"http://127.0.0.1:{port}/"
try:
    with socket.create_connection(("127.0.0.1", port), timeout=1):
        pass
except ConnectionRefusedError:
    sys.exit(10)
except OSError:
    print("无法检查本地端口，请稍后重试。", file=sys.stderr)
    sys.exit(1)
try:
    with build_opener(ProxyHandler({})).open(url + "api/health", timeout=2) as response:
        state = json.load(response)
    expected = hashlib.sha256(str(Path.cwd().resolve()).encode()).hexdigest()
    if state.get("application") != "InsightRadar" or state.get("workspace_id") != expected:
        raise ValueError("different application")
except Exception:
    print(f"端口 {port} 已被其他服务占用，未关闭该服务。可用 INSIGHTRADAR_PORT 指定其他端口。", file=sys.stderr)
    sys.exit(1)
print(f"工作台已在运行：{url}")
if "--no-open" not in sys.argv:
    webbrowser.open(url)
PY
probe=$?
set -e
if [ "$probe" -eq 0 ]; then exit 0; fi
if [ "$probe" -ne 10 ]; then exit "$probe"; fi
echo "正在打开 InsightRadar：http://127.0.0.1:$port/"
echo "保持此窗口打开；按 Control-C 或在页面内退出即可停止。"
exec .venv/bin/python -m stock_assist.cli portfolio-import --serve --port "$port" "$@"
