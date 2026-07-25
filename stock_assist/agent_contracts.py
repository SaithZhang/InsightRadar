"""Validation for project-scoped agent contracts."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from stock_assist.harness_eval.validation import json_tree_error, read_bounded_bytes


EXPECTED_RUNTIME_AGENTS = frozenset(
    {
        "evidence_analyst",
        "market_benchmark_analyst",
        "product_critic",
        "implementation_verifier",
    }
)
ROSTER_SCHEMA_VERSION = "insightradar-agent-roster/v2"
MAX_ROSTER_BYTES = 64 * 1024
ROSTER_FIELDS = frozenset({"schema_version", "operating_model", "agents"})
OPERATING_MODEL_REQUIREMENTS = {
    "lead_role": "lead",
    "max_parallel_task_agents": 3,
    "write_policy": "lead_serializes_workspace_changes",
    "max_active_experiments": 1,
    "max_queued_experiments": 2,
    "product_authority": "human_owner_approves_priority_scope_and_release",
    "trade_authority": "none",
}
EXPECTED_ROSTER_BINDINGS = {
    "owner_reviewer": None,
    "lead": "default",
    **{name: name for name in EXPECTED_RUNTIME_AGENTS},
}
BASE_ROLE_FIELDS = frozenset(
    {"id", "name", "runtime_agent", "engagement", "mission", "authority", "inputs", "outputs"}
)
RUNTIME_ROLE_FIELD_SET = BASE_ROLE_FIELDS | {"failure_result"}
EXPECTED_ENGAGEMENT = {
    "owner_reviewer": "always",
    "lead": "always",
    "evidence_analyst": "on_demand",
    "market_benchmark_analyst": "on_demand",
    "product_critic": "before_experiment_admission",
    "implementation_verifier": "before_completion",
}
OWNER_AUTHORITIES = frozenset(
    {"approve_product_priority", "approve_experiment_start", "approve_release"}
)
LEAD_AUTHORITIES = frozenset(
    {"delegate_read_only_analysis", "integrate_workspace_changes", "propose_experiments"}
)
RUNTIME_ROLE_FIELDS = {
    "mission": str,
    "authority": list,
    "inputs": list,
    "outputs": list,
    "failure_result": str,
}
ALLOWED_RUNTIME_AUTHORITIES = {
    "evidence_analyst": frozenset(
        {"read_workspace", "read_approved_sources", "report_evidence_gaps"}
    ),
    "market_benchmark_analyst": frozenset(
        {"read_workspace", "research_public_sources", "report_benchmark_gaps"}
    ),
    "product_critic": frozenset(
        {"read_workspace", "challenge_experiment", "recommend_rejection"}
    ),
    "implementation_verifier": frozenset(
        {"read_workspace", "run_read_only_verification", "block_completion_claim"}
    ),
}
APPROVED_INSTRUCTION_LINES = {
    "evidence_analyst": (
        "Read AGENTS.md and docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md.",
        "Work only on the bounded evidence question assigned by the lead.",
        "Do not modify the workspace, create commits, or change product state.",
        "Do not spawn subagents.",
        "Separate verified fact, inference, conflict, stale input, and unknown field.",
        "Research evidence has no trade authority. Return source and file references to the lead.",
    ),
    "market_benchmark_analyst": (
        "Read AGENTS.md and docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md.",
        "Work only on the bounded benchmark question assigned by the lead.",
        "Do not modify the workspace, create commits, or change product state.",
        "Do not spawn subagents.",
        "Compare the user problem, workflow, evidence, and outcome measurement.",
        "Return source-linked mechanisms, anti-patterns, and open questions to the lead.",
    ),
    "product_critic": (
        "Read AGENTS.md and docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md.",
        "Review only the experiment assigned by the lead.",
        "Do not modify the workspace, create commits, approve scope, or change product state.",
        "Do not spawn subagents.",
        "Challenge the problem, baseline, metric, smallest experiment, safety boundary, and kill criterion.",
        "Return blocking objections first, then an admit, revise, or reject recommendation.",
    ),
    "implementation_verifier": (
        "Read AGENTS.md and docs/superpowers/specs/2026-07-21-agent-harness-job-readiness-design.md.",
        "Verify only the bounded implementation assigned by the lead.",
        "Do not modify the workspace, create commits, or repair failures.",
        "Do not spawn subagents.",
        "Inspect the diff, focused tests, full tests, real artifacts, explicit gaps, and restart instructions.",
        "Verify that the implementation does not create files.",
        "Return findings by severity, reproduction commands, and a pass or fail verdict.",
    ),
}
CONTRACT_STRING_FIELDS = {"name", "description", "sandbox_mode"}
CONTRACT_ARRAY_FIELDS = {"nickname_candidates"}
CONTRACT_FIELDS = (
    "name",
    "description",
    "sandbox_mode",
    "developer_instructions",
    "nickname_candidates",
)
CONTRACT_FIELD_SET = frozenset(CONTRACT_FIELDS)
STRING_ASSIGNMENT = re.compile(r'^([a-z_]+)\s*=\s*"([^"\n]*)"\s*$')
ARRAY_ASSIGNMENT = re.compile(r"^([a-z_]+)\s*=\s*(\[.*\])\s*$")
STRING_ARRAY = re.compile(r'^\[\s*"[^"\\]+"(?:\s*,\s*"[^"\\]+")*\s*\]$')
REQUIRED_INSTRUCTIONS = (
    "agent-harness-job-readiness-design.md",
    "Do not modify the workspace",
    "Do not spawn subagents",
)


def _has_forbidden_toml_control(value: str, *, allow_newline: bool) -> bool:
    allowed = {"\t"}
    if allow_newline:
        allowed.add("\n")
    return any(
        (ord(character) < 0x20 and character not in allowed)
        or ord(character) == 0x7F
        for character in value
    )


def _normalized_instruction_lines(instructions: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in instructions.splitlines() if line.strip())


def _parse_contract(path: Path) -> tuple[dict[str, str], str, list[str]]:
    """Parse the intentionally limited TOML grammar used by runtime contracts."""
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        return {}, "", [f"{path}: cannot read contract: {error}"]
    if any(
        character == "\r" and (index + 1 == len(text) or text[index + 1] != "\n")
        for index, character in enumerate(text)
    ):
        return {}, "", [f"{path}: bare carriage return is not permitted"]
    lines = text.replace("\r\n", "\n").split("\n")

    errors: list[str] = []
    fields: dict[str, str] = {}
    instructions = ""
    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        stripped = line.strip()
        if not stripped:
            line_index += 1
            continue
        if stripped.startswith("developer_instructions"):
            if stripped != 'developer_instructions = """':
                errors.append(
                    f"{path}: invalid developer_instructions declaration on line {line_index + 1}"
                )
                line_index += 1
                continue
            if "developer_instructions" in fields:
                errors.append(f"{path}: duplicate TOML field developer_instructions")
            fields["developer_instructions"] = ""
            line_index += 1
            instruction_lines: list[str] = []
            while line_index < len(lines) and lines[line_index].strip() != '"""':
                instruction_lines.append(lines[line_index])
                line_index += 1
            if line_index == len(lines):
                errors.append(f"{path}: unterminated developer_instructions block")
                break
            instructions = "\n".join(instruction_lines).strip()
            if "\\" in instructions:
                errors.append(f"{path}: invalid TOML escape in developer_instructions")
            if _has_forbidden_toml_control(instructions, allow_newline=True):
                errors.append(
                    f"{path}: forbidden TOML control character in developer_instructions"
                )
            line_index += 1
            continue

        string_match = STRING_ASSIGNMENT.match(line)
        if string_match:
            field, value = string_match.groups()
            if field not in CONTRACT_STRING_FIELDS:
                errors.append(f"{path}: unrecognized TOML field {field}")
            elif "\\" in value:
                errors.append(f"{path}: invalid TOML escape in {field}")
            elif _has_forbidden_toml_control(value, allow_newline=False):
                errors.append(f"{path}: forbidden TOML control character in {field}")
            elif field in fields:
                errors.append(f"{path}: duplicate TOML field {field}")
            else:
                fields[field] = value
            line_index += 1
            continue

        array_match = ARRAY_ASSIGNMENT.match(line)
        if array_match:
            field, value = array_match.groups()
            if field not in CONTRACT_ARRAY_FIELDS:
                errors.append(f"{path}: unrecognized TOML field {field}")
            elif _has_forbidden_toml_control(value, allow_newline=False):
                errors.append(f"{path}: forbidden TOML control character in {field}")
            elif not STRING_ARRAY.fullmatch(value):
                errors.append(f"{path}: invalid TOML string array for {field}")
            elif field in fields:
                errors.append(f"{path}: duplicate TOML field {field}")
            else:
                fields[field] = value
            line_index += 1
            continue

        field_match = re.match(r"^([a-z_]+)\s*=", stripped)
        if field_match:
            field = field_match.group(1)
            if field in CONTRACT_FIELD_SET:
                errors.append(f"{path}: invalid TOML syntax for {field}")
            else:
                errors.append(f"{path}: unrecognized TOML field {field}")
        else:
            errors.append(f"{path}: invalid or unrecognized TOML syntax on line {line_index + 1}")
        line_index += 1

    return fields, instructions, errors


def _validate_string_list(
    role: dict[str, Any], role_name: str, field: str, errors: list[str]
) -> None:
    value = role.get(field)
    if field not in role:
        errors.append(f"runtime role missing {field}: {role_name}")
    elif not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        errors.append(f"runtime role {field} must be a non-empty string list: {role_name}")


def _validate_runtime_role(role: dict[str, Any], role_name: str, errors: list[str]) -> None:
    for field, expected_type in RUNTIME_ROLE_FIELDS.items():
        if expected_type is list:
            _validate_string_list(role, role_name, field, errors)
            continue
        value = role.get(field)
        if field not in role:
            errors.append(f"runtime role missing {field}: {role_name}")
        elif not isinstance(value, expected_type) or not value.strip():
            errors.append(f"runtime role {field} must be a non-empty string: {role_name}")
    authority = role.get("authority")
    allowed_authorities = ALLOWED_RUNTIME_AUTHORITIES.get(role_name)
    if (
        allowed_authorities is not None
        and isinstance(authority, list)
        and all(isinstance(item, str) for item in authority)
    ):
        if frozenset(authority) != allowed_authorities or len(
            authority
        ) != len(set(authority)):
            errors.append(
                f"runtime role authority must exactly match allowed set: {role_name}"
            )


def _validate_instruction_template(
    role_name: str, instructions: str, path: Path, errors: list[str]
) -> None:
    if not instructions:
        return
    actual_lines = _normalized_instruction_lines(instructions)
    approved_lines = APPROVED_INSTRUCTION_LINES[role_name]
    for line in actual_lines:
        if line not in approved_lines:
            errors.append(f"{path}: unapproved developer_instructions clause: {line}")
    for line in approved_lines:
        if line not in actual_lines:
            errors.append(f"{path}: developer_instructions missing approved clause: {line}")
    if actual_lines != approved_lines:
        errors.append(
            f"{path}: developer_instructions clauses must exactly match approved template"
        )


def _load_roster(roster_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        raw = read_bounded_bytes(roster_path, MAX_ROSTER_BYTES, "agent roster")
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_roster_keys)
    except UnicodeError:
        return None, ["agent roster is not valid UTF-8"]
    except json.JSONDecodeError:
        return None, ["invalid roster JSON"]
    except ValueError as error:
        if str(error) == "duplicate roster JSON key":
            return None, ["duplicate roster JSON key"]
        return None, ["cannot read roster"]
    if not isinstance(payload, dict):
        return None, ["roster root must be a JSON object"]
    bounds_error = json_tree_error(payload, "agent roster")
    if bounds_error:
        return None, [bounds_error]
    return payload, []


def _reject_duplicate_roster_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate roster JSON key")
        result[key] = value
    return result


def _validate_roster(roster: dict[str, Any], errors: list[str]) -> set[str]:
    unknown_root = set(roster) - ROSTER_FIELDS
    if unknown_root:
        errors.append("roster has unknown field")
    missing_root = ROSTER_FIELDS - set(roster)
    if missing_root:
        errors.append("roster is missing required field")
    if roster.get("schema_version") != ROSTER_SCHEMA_VERSION:
        errors.append(f"schema_version must be {ROSTER_SCHEMA_VERSION!r}")

    model = roster.get("operating_model")
    if not isinstance(model, dict):
        errors.append("roster missing operating_model object")
    else:
        if set(model) - set(OPERATING_MODEL_REQUIREMENTS):
            errors.append("operating_model has unknown field")
        for field, expected in OPERATING_MODEL_REQUIREMENTS.items():
            if field not in model:
                errors.append(f"operating_model missing {field}")
            elif model[field] != expected:
                errors.append(f"operating_model {field} must be {expected!r}")

    agents = roster.get("agents")
    if not isinstance(agents, list):
        errors.append("roster missing agents list")
        return set()
    if len(agents) != len(EXPECTED_ROSTER_BINDINGS):
        errors.append("roster must contain exactly 6 roster agents")

    agent_ids: set[str] = set()
    runtime_agents: list[str] = []
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            errors.append(f"roster agent {index} must be an object")
            continue
        agent_id = agent.get("id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            errors.append(f"roster agent {index} missing id")
        elif agent_id in agent_ids:
            errors.append(f"duplicate roster agent id: {agent_id}")
        else:
            agent_ids.add(agent_id)
        if agent_id not in EXPECTED_ROSTER_BINDINGS:
            errors.append("unapproved roster agent identity")
            runtime_agent = agent.get("runtime_agent")
            if runtime_agent == "default":
                errors.append("runtime_agent default is reserved for lead")
            if runtime_agent is None:
                errors.append("null runtime_agent is reserved for owner_reviewer")
            continue

        runtime_agent = agent.get("runtime_agent")
        if "runtime_agent" not in agent:
            errors.append(f"roster agent {index} missing runtime_agent")
            continue
        expected_runtime = EXPECTED_ROSTER_BINDINGS[agent_id]
        if runtime_agent != expected_runtime:
            if agent_id == "lead":
                errors.append("lead roster entry must use runtime_agent default")
            elif agent_id == "owner_reviewer":
                errors.append("owner roster entry must use null runtime_agent")
            else:
                errors.append("runtime role id must match runtime_agent")

        expected_fields = RUNTIME_ROLE_FIELD_SET if agent_id in EXPECTED_RUNTIME_AGENTS else BASE_ROLE_FIELDS
        if set(agent) - expected_fields:
            errors.append("roster agent has unknown field")
        role_label = "lead" if agent_id == "lead" else "owner" if agent_id == "owner_reviewer" else "runtime"
        for field in sorted(expected_fields - set(agent)):
            if role_label == "runtime":
                errors.append(f"runtime role missing {field}: {agent_id}")
            else:
                errors.append(f"{role_label} role missing {field}")
        for field in ("name", "engagement", "mission"):
            value = agent.get(field)
            if field in agent and (not isinstance(value, str) or not value.strip()):
                errors.append(f"{role_label} role {field} must be a non-empty string")
        for field in ("authority", "inputs", "outputs"):
            if field in agent:
                _validate_string_list(agent, str(agent_id), field, errors)
        if agent.get("engagement") != EXPECTED_ENGAGEMENT[agent_id]:
            errors.append(f"{role_label} role engagement is invalid")

        if agent_id == "lead":
            authority = agent.get("authority")
            if not isinstance(authority, list) or len(authority) != len(set(authority)) or frozenset(authority) != LEAD_AUTHORITIES:
                errors.append("lead authority must exactly match allowed set")
            continue
        if agent_id == "owner_reviewer":
            authority = agent.get("authority")
            if not isinstance(authority, list) or len(authority) != len(set(authority)) or frozenset(authority) != OWNER_AUTHORITIES:
                errors.append("owner authority must exactly match allowed set")
            continue
        if not isinstance(runtime_agent, str) or not runtime_agent.strip():
            errors.append(f"roster agent {index} has invalid runtime_agent")
            continue
        if runtime_agent in runtime_agents:
            errors.append(f"duplicate roster runtime agent: {runtime_agent}")
        runtime_agents.append(runtime_agent)
        if runtime_agent not in EXPECTED_RUNTIME_AGENTS:
            errors.append(f"unrecognized roster runtime agent: {runtime_agent}")
        if agent_id != runtime_agent:
            errors.append(
                f"runtime role id must match runtime_agent: {runtime_agent}"
            )
        _validate_runtime_role(agent, runtime_agent, errors)

    for identity in sorted(set(EXPECTED_ROSTER_BINDINGS) - agent_ids):
        errors.append(f"expected roster agent missing: {identity}")
    if len(runtime_agents) != len(EXPECTED_RUNTIME_AGENTS):
        errors.append(
            "expected exactly 4 runtime roster agents, "
            f"found {len(runtime_agents)}"
        )
    runtime_agent_set = set(runtime_agents)
    for name in sorted(EXPECTED_RUNTIME_AGENTS - runtime_agent_set):
        errors.append(f"expected runtime roster agent missing: {name}")
    return runtime_agent_set


def validate_agent_contracts(agent_dir: Path, roster_path: Path) -> list[str]:
    """Return deterministic validation errors for the roster and four TOML contracts."""
    errors: list[str] = []
    roster, roster_errors = _load_roster(roster_path)
    errors.extend(roster_errors)
    runtime_agents = _validate_roster(roster, errors) if roster is not None else set()

    files = sorted(agent_dir.glob("*.toml")) if agent_dir.exists() else []
    if len(files) != len(EXPECTED_RUNTIME_AGENTS):
        errors.append(f"expected exactly 4 agent contracts, found {len(files)}")

    contract_names: list[str] = []
    for path in files:
        fields, instructions, parse_errors = _parse_contract(path)
        errors.extend(parse_errors)
        for field in CONTRACT_FIELDS:
            if field == "developer_instructions":
                if not instructions:
                    errors.append(f"{path}: missing developer_instructions")
            elif not fields.get(field):
                errors.append(f"{path}: missing {field}")
        name = fields.get("name", "")
        if not name:
            continue
        if name in contract_names:
            errors.append(f"{path}: duplicate contract name {name}")
        contract_names.append(name)
        if path.stem != name:
            errors.append(f"{path}: filename stem must match declared name {name}")
        if name not in EXPECTED_RUNTIME_AGENTS:
            errors.append(f"{path}: unrecognized contract name {name}")
        if fields.get("sandbox_mode") != "read-only":
            errors.append(f"{path}: sandbox_mode must be read-only")
        for required in REQUIRED_INSTRUCTIONS:
            if required not in instructions:
                errors.append(f"{path}: developer_instructions missing {required}")
        if name in APPROVED_INSTRUCTION_LINES:
            _validate_instruction_template(name, instructions, path, errors)

    contract_name_set = set(contract_names)
    for name in sorted(EXPECTED_RUNTIME_AGENTS - contract_name_set):
        errors.append(f"expected runtime contract missing: {name}")
    for name in sorted(runtime_agents - contract_name_set):
        errors.append(f"roster runtime agent has no TOML contract: {name}")
    for name in sorted(contract_name_set - runtime_agents):
        errors.append(f"TOML contract is not routed by roster: {name}")
    return errors


def load_validated_agent_roster(agent_dir: Path, roster_path: Path) -> dict[str, Any]:
    """Return a roster only when it and all routed TOML contracts agree."""

    if validate_agent_contracts(agent_dir, roster_path):
        raise ValueError("agent roster validation failed")
    roster, load_errors = _load_roster(roster_path)
    if roster is None or load_errors:
        raise ValueError("agent roster validation failed")
    final_errors: list[str] = []
    _validate_roster(roster, final_errors)
    if final_errors:
        raise ValueError("agent roster validation failed")
    return roster
