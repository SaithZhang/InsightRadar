from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_assist.agent_contracts import validate_agent_contracts


def main() -> int:
    errors = validate_agent_contracts(
        PROJECT_ROOT / ".codex" / "agents",
        PROJECT_ROOT / "configs" / "agents.json",
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Agent contracts valid: roster and read-only runtime roles are aligned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
