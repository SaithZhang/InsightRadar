"""Build the share-safe InsightRadar V3.0 Pilot review snapshot.

The generated HTML uses the production renderer and state contract, but all
portfolio names, codes, amounts, and response ledgers are synthetic.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile

from stock_assist.after_close_workbench_html import _document
from stock_assist.decision_workspace import (
    append_plan_response,
    build_decision_workspace,
    record_plan_versions,
)
from stock_assist.portfolio import Holding, Portfolio


OUTPUT = (
    Path(__file__).resolve().parent
    / "artifacts"
    / "InsightRadar-V3.0-Pilot-Scope-Frozen-sanitized.html"
)


def _portfolio() -> Portfolio:
    holdings = [
        Holding(
            code=f"60000{index}.SH",
            name=f"示例持仓{label}",
            shares=None,
            cost=None,
            market_price=None,
            pnl_pct=None,
            market_value=None,
            weight_pct=None,
            beta_classification="unknown",
        )
        for index, label in enumerate(("A", "B", "C", "D"), start=1)
    ]
    return Portfolio(
        cash=None,
        holdings=holdings,
        source=Path("sanitized-review-fixture.json"),
        as_of="2026-07-25",
        risk_reconciliation_status="blocked",
    )


def _payload(*, blocked: bool) -> dict[str, object]:
    plans = [
        {
            "code": f"60000{index}.SH",
            "name": f"示例持仓{label}",
            "position_action": "等待确认，不抢跑",
            "upside_trigger": "连续三根已完成15分钟K线站稳确认位",
            "flat_trigger": "下一交易日收盘前复核",
            "downside_trigger": "跌破风险线则计划失效",
        }
        for index, label in enumerate(("A", "B", "C", "D"), start=1)
    ]
    return {
        "generated_at": "2026-07-25T08:30:00",
        "data_gaps": ["脱敏评审快照：真实行情、成本、权重和账户字段未打包"],
        "unified_decision": {
            "plan_date": "2026-07-25",
            "stance": "等待确认",
            "first_action": "先处理待确认计划",
            "risk_budget": {"risk_level": "yellow", "risk_score": 62},
            "blocked_actions": (
                ["脱敏评审快照不具备真实数据授权，阻断执行"] if blocked else []
            ),
            "source_reports": [
                {
                    "workflow": "risk_watch",
                    "status": "current",
                    "as_of": "2026-07-25",
                    "path": "sanitized-review-evidence",
                }
            ],
            "holding_plans": plans,
        },
        "market_matrix": {"groups": []},
        "reliability": {"decision_ready_holdings": 0, "holding_count": 4},
        "sections": [],
        "signal_outcomes": {},
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        responses = root / "responses.jsonl"
        plans = root / "plans.jsonl"
        baseline = build_decision_workspace(
            _payload(blocked=False),
            _portfolio(),
            generated_at=datetime(2026, 7, 25, 8, 30),
            response_ledger=responses,
            plan_ledger=plans,
        )
        record_plan_versions(baseline, plans)
        first = baseline["active_plans"][0]
        append_plan_response(
            plan_id=str(first["plan_id"]),
            plan_version=str(first["plan_version"]),
            response="deferred",
            plan_status=str(first["status"]),
            note="脱敏示例：稍后处理",
            ledger_path=responses,
            created_at=datetime(2026, 7, 25, 8, 31),
        )
        workspace = build_decision_workspace(
            _payload(blocked=True),
            _portfolio(),
            generated_at=datetime(2026, 7, 25, 8, 32),
            response_ledger=responses,
            plan_ledger=plans,
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        _document(workspace),
        encoding="utf-8",
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
