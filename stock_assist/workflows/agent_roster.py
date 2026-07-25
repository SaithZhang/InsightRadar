"""Agent operating-model reporting."""

from __future__ import annotations

from pathlib import Path

from stock_assist.agent_contracts import load_validated_agent_roster
from stock_assist.paths import CONFIG_DIR, PROJECT_ROOT


DEFAULT_AGENTS_PATH = CONFIG_DIR / "agents.json"
DEFAULT_AGENT_DIR = PROJECT_ROOT / ".codex" / "agents"


def _joined(field: str, values: object) -> str:
    if values is None:
        return "未填写"
    if not isinstance(values, list):
        value = json.dumps(values, ensure_ascii=False, sort_keys=True)
        return f"配置错误：{field} 必须是列表，收到 {type(values).__name__}：{value}"
    return ", ".join(str(value) for value in values) or "未填写"


def build_agent_roster_report(
    config_path: Path = DEFAULT_AGENTS_PATH,
    agent_dir: Path = DEFAULT_AGENT_DIR,
) -> str:
    payload = load_validated_agent_roster(agent_dir, config_path)
    operating_model = payload.get("operating_model", {})
    lines = [
        "# Agent 分工表",
        "",
        "## 运行模型",
        f"- 主角色：{operating_model.get('lead_role', '未填写')}",
        f"- 最多并行任务 Agent：{operating_model.get('max_parallel_task_agents', '未填写')}",
        f"- 写入策略：{operating_model.get('write_policy', '未填写')}",
        (
            f"- 活跃实验上限：{operating_model.get('max_active_experiments', '未填写')}；"
            f"排队实验上限：{operating_model.get('max_queued_experiments', '未填写')}"
        ),
        f"- 产品权限：{operating_model.get('product_authority', '未填写')}",
        f"- 交易权限：{operating_model.get('trade_authority', '未填写')}",
        "",
    ]
    for agent in payload.get("agents", []):
        lines.extend(
            [
                f"## {agent.get('name', '未命名')} ({agent.get('id', 'missing-id')})",
                f"- 运行时角色：{agent.get('runtime_agent') or '人工角色'}",
                f"- 介入时点：{agent.get('engagement', '未填写')}",
                f"- 任务：{agent.get('mission', '未填写')}",
                f"- 权限边界：{_joined('authority', agent.get('authority'))}",
                f"- 输入：{_joined('inputs', agent.get('inputs'))}",
                f"- 输出：{_joined('outputs', agent.get('outputs'))}",
                f"- 失败边界：{agent.get('failure_result') or '未填写（缺少 failure_result）'}",
                "",
            ]
        )
    return "\n".join(lines)
