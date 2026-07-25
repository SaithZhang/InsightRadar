#!/bin/bash
set -e

echo "=== Harness Initialization ==="

echo "=== project memory check ==="
./.venv/Scripts/python scripts/validate_project_memory.py

echo "=== python compile check ==="
./.venv/Scripts/python -m compileall stock_assist

echo "=== after-close smoke test ==="
./.venv/Scripts/python -m stock_assist.cli after-close

echo "Next steps:"
echo "1. Read PROJECT_MEMORY.md and CURRENT_STATE.md"
echo "2. Load only the matching topic, exact feature, and recent matching history"
echo "3. Work on the single next feature from CURRENT_STATE.md"
echo "4. Implement only that feature"
echo "5. Re-run verification before claiming done"
