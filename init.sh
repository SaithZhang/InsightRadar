#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  python=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then
  python=.venv/Scripts/python.exe
else
  echo "请先运行 scripts/macos.sh setup（Windows 请按 README 安装环境）。" >&2
  exit 1
fi

echo "=== Harness Initialization ==="

echo "=== project memory check ==="
"$python" scripts/validate_project_memory.py

echo "=== python compile check ==="
"$python" -m compileall -q stock_assist

echo "=== after-close smoke test ==="
"$python" -m stock_assist.cli after-close

echo "Next steps:"
echo "1. Read PROJECT_MEMORY.md and CURRENT_STATE.md"
echo "2. Load only the matching topic, exact feature, and recent matching history"
echo "3. Work on the single next feature from CURRENT_STATE.md"
echo "4. Implement only that feature"
echo "5. Re-run verification before claiming done"
