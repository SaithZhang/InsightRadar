from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from stock_assist.agent_contracts import validate_agent_contracts


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AgentContractTests(unittest.TestCase):
    def copy_contract_inputs(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        root = Path(temporary_directory.name)
        agent_dir = root / "agents"
        agent_dir.mkdir()
        for source in (PROJECT_ROOT / ".codex" / "agents").glob("*.toml"):
            target = agent_dir / source.name
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        roster_path = root / "agents.json"
        roster_path.write_text(
            (PROJECT_ROOT / "configs" / "agents.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return temporary_directory, agent_dir, roster_path

    def read_roster(self, roster_path: Path) -> dict[str, object]:
        return json.loads(roster_path.read_text(encoding="utf-8"))

    def write_roster(self, roster_path: Path, payload: dict[str, object]) -> None:
        roster_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def test_project_contracts_match_roster(self) -> None:
        errors = validate_agent_contracts(
            PROJECT_ROOT / ".codex" / "agents",
            PROJECT_ROOT / "configs" / "agents.json",
        )
        self.assertEqual(errors, [])

    def test_operating_model_caps_parallelism_and_serializes_writes(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "configs" / "agents.json").read_text(encoding="utf-8")
        )
        model = payload["operating_model"]
        self.assertEqual(model["max_parallel_task_agents"], 3)
        self.assertEqual(model["write_policy"], "lead_serializes_workspace_changes")
        self.assertEqual(model["max_active_experiments"], 1)
        self.assertEqual(model["max_queued_experiments"], 2)
        self.assertEqual(model["trade_authority"], "none")

    def test_exactly_four_runtime_contracts_are_read_only_and_non_recursive(self) -> None:
        paths = sorted((PROJECT_ROOT / ".codex" / "agents").glob("*.toml"))
        self.assertEqual(len(paths), 4)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn('sandbox_mode = "read-only"', text)
            self.assertIn("agent-harness-job-readiness-design.md", text)
            self.assertIn("Do not modify the workspace", text)
            self.assertIn("Do not spawn subagents", text)

    def test_rejects_malformed_or_unrecognized_contract_toml(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            contract_path = agent_dir / "evidence_analyst.toml"
            contract_path.write_text(
                contract_path.read_text(encoding="utf-8")
                + "unexpected = true\n"
                + "nickname_candidates = [unquoted]\n",
                encoding="utf-8",
            )
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(
            any("unrecognized TOML field unexpected" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("invalid TOML string array" in error for error in errors), errors
        )

    def test_rejects_invalid_toml_escapes_in_fields_and_instructions(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            contract_path = agent_dir / "evidence_analyst.toml"
            contract_path.write_text(
                contract_path.read_text(encoding="utf-8")
                .replace(
                    'description = "Read-only analyst for provenance, point-in-time facts, entity mapping, and explicit gaps."',
                    'description = "invalid TOML escape: \\q"',
                )
                .replace(
                    "Do not spawn subagents.\n",
                    "Do not spawn subagents.\\q\n",
                ),
                encoding="utf-8",
            )
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(
            any("invalid TOML escape in description" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("invalid TOML escape in developer_instructions" in error for error in errors),
            errors,
        )

    def test_rejects_toml_forbidden_controls_in_all_contract_values(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            contract_path = agent_dir / "evidence_analyst.toml"
            contract_path.write_text(
                contract_path.read_text(encoding="utf-8")
                .replace(
                    'description = "Read-only analyst for provenance, point-in-time facts, entity mapping, and explicit gaps."',
                    'description = "bad\u0001\u007f"',
                )
                .replace(
                    'nickname_candidates = ["Ledger", "Beacon", "Trace"]',
                    'nickname_candidates = ["Ledger\u0001", "Beacon\u007f", "Trace"]',
                )
                .replace(
                    "Do not spawn subagents.\n",
                    "Do not spawn subagents.\u0001\u007f\n",
                ),
                encoding="utf-8",
            )
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(
            any("forbidden TOML control character in description" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("forbidden TOML control character in nickname_candidates" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any(
                "forbidden TOML control character in developer_instructions" in error
                for error in errors
            ),
            errors,
        )

    def test_rejects_bare_carriage_returns_in_contract_bytes(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            contract_path = agent_dir / "evidence_analyst.toml"
            contract_path.write_bytes(
                contract_path.read_bytes()
                .replace(b"\r\n", b"\n")
                .replace(b"\n", b"\r")
            )
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(
            any("bare carriage return is not permitted" in error for error in errors),
            errors,
        )

    def test_accepts_crlf_contract_bytes(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            contract_path = agent_dir / "evidence_analyst.toml"
            contract_path.write_bytes(
                contract_path.read_bytes()
                .replace(b"\r\n", b"\n")
                .replace(b"\n", b"\r\n")
            )
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertEqual(errors, [])

    def test_instruction_template_rejects_same_line_permission_contradictions(self) -> None:
        write_variants = (
            "Do not modify the workspace, but you may create a file.",
            "Do not modify the workspace except when writing a file.",
            "Do not modify the workspace; you may edit a file.",
        )
        for instruction in write_variants:
            temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
            with temporary_directory:
                contract_path = agent_dir / "evidence_analyst.toml"
                contract_path.write_text(
                    contract_path.read_text(encoding="utf-8").replace(
                        "Do not modify the workspace, create commits, or change product state.",
                        instruction,
                    ),
                    encoding="utf-8",
                )
                errors = validate_agent_contracts(agent_dir, roster_path)
            self.assertTrue(
                any("unapproved developer_instructions clause" in error for error in errors),
                (instruction, errors),
            )

        delegation_variants = (
            "Do not spawn subagents, but ask another agent to inspect it.",
            "Do not spawn subagents except for verification.",
            "Do not spawn subagents; delegate analysis to another agent.",
        )
        for instruction in delegation_variants:
            temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
            with temporary_directory:
                contract_path = agent_dir / "evidence_analyst.toml"
                contract_path.write_text(
                    contract_path.read_text(encoding="utf-8").replace(
                        "Do not spawn subagents.", instruction
                    ),
                    encoding="utf-8",
                )
                errors = validate_agent_contracts(agent_dir, roster_path)
            self.assertTrue(
                any("unapproved developer_instructions clause" in error for error in errors),
                (instruction, errors),
            )

    def test_accepts_approved_safe_negated_analysis_clause(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            contract_path = agent_dir / "implementation_verifier.toml"
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertEqual(errors, [])

    def test_instruction_template_rejects_extra_approved_clause(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            contract_path = agent_dir / "implementation_verifier.toml"
            contract_path.write_text(
                contract_path.read_text(encoding="utf-8").replace(
                    "Verify that the implementation does not create files.\n",
                    "Verify that the implementation does not create files.\n"
                    "Verify that the implementation does not create files.\n",
                ),
                encoding="utf-8",
            )
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(
            any("clauses must exactly match approved template" in error for error in errors),
            errors,
        )

    def test_rejects_filesystem_and_delegation_instruction_bypasses(self) -> None:
        write_variants = (
            "You may create a file in the workspace.",
            "You may delete a file in the workspace.",
            "You may remove a file in the workspace.",
            "You may move a file in the workspace.",
            "You may rename a file in the workspace.",
            "You may edit a file in the workspace.",
            "You may append to a file in the workspace.",
            "You may overwrite a file in the workspace.",
        )
        for instruction in write_variants:
            temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
            with temporary_directory:
                contract_path = agent_dir / "evidence_analyst.toml"
                contract_path.write_text(
                    contract_path.read_text(encoding="utf-8").replace(
                        "Do not spawn subagents.\n",
                        f"Do not spawn subagents.\n{instruction}\n",
                    ),
                    encoding="utf-8",
                )
                errors = validate_agent_contracts(agent_dir, roster_path)
            self.assertTrue(
                any("unapproved developer_instructions clause" in error for error in errors),
                (instruction, errors),
            )

        for instruction in (
            "You may delegate analysis to another agent.",
            "You may launch a subagent for verification.",
            "You may ask another agent to inspect the workspace.",
        ):
            temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
            with temporary_directory:
                contract_path = agent_dir / "evidence_analyst.toml"
                contract_path.write_text(
                    contract_path.read_text(encoding="utf-8").replace(
                        "Do not spawn subagents.\n",
                        f"Do not spawn subagents.\n{instruction}\n",
                    ),
                    encoding="utf-8",
                )
                errors = validate_agent_contracts(agent_dir, roster_path)
            self.assertTrue(
                any("unapproved developer_instructions clause" in error for error in errors),
                (instruction, errors),
            )

    def test_rejects_malformed_roster_json_as_validation_error(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            roster_path.write_text("{not valid json", encoding="utf-8")
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("invalid roster JSON" in error for error in errors), errors)

    def test_returns_errors_for_roster_shape_and_missing_runtime_agent(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            roster_path.write_text("[]", encoding="utf-8")
            shape_errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(
            any("roster root must be a JSON object" in error for error in shape_errors),
            shape_errors,
        )

        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            payload = self.read_roster(roster_path)
            agents = payload["agents"]
            self.assertIsInstance(agents, list)
            del agents[2]["runtime_agent"]
            self.write_roster(roster_path, payload)
            key_errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(
            any("missing runtime_agent" in error for error in key_errors), key_errors
        )

    def test_rejects_writable_and_conflicting_contract_instructions(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            contract_path = agent_dir / "evidence_analyst.toml"
            contract_path.write_text(
                contract_path.read_text(encoding="utf-8")
                .replace('sandbox_mode = "read-only"', 'sandbox_mode = "workspace-write"')
                .replace(
                    "Do not spawn subagents.\n",
                    "Do not spawn subagents.\n"
                    "You may modify the workspace.\n"
                    "You may spawn subagents.\n",
                ),
                encoding="utf-8",
            )
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("sandbox_mode must be read-only" in error for error in errors), errors)
        self.assertTrue(
            any("unapproved developer_instructions clause: You may modify" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("unapproved developer_instructions clause: You may spawn" in error for error in errors),
            errors,
        )

    def test_rejects_contract_count_drift_and_roster_desynchronization(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            (agent_dir / "implementation_verifier.toml").unlink()
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("expected exactly 4 agent contracts" in error for error in errors), errors)
        self.assertTrue(
            any("roster runtime agent has no TOML contract" in error for error in errors),
            errors,
        )

    def test_rejects_duplicate_roster_and_contract_identities(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            payload = self.read_roster(roster_path)
            agents = payload["agents"]
            self.assertIsInstance(agents, list)
            agents[3]["runtime_agent"] = "evidence_analyst"
            self.write_roster(roster_path, payload)
            contract_path = agent_dir / "market_benchmark_analyst.toml"
            contract_path.write_text(
                contract_path.read_text(encoding="utf-8").replace(
                    'name = "market_benchmark_analyst"',
                    'name = "evidence_analyst"',
                ),
                encoding="utf-8",
            )
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("duplicate roster runtime agent" in error for error in errors), errors)
        self.assertTrue(any("duplicate contract name" in error for error in errors), errors)

    def test_rejects_rogue_default_writer_and_unapproved_null_role(self) -> None:
        for rogue in (
            {
                "id": "rogue_writer",
                "name": "Rogue writer",
                "runtime_agent": "default",
                "engagement": "always",
                "mission": "Write workspace changes independently",
                "authority": ["integrate_workspace_changes"],
                "inputs": ["workspace"],
                "outputs": ["changes"],
            },
            {
                "id": "extra_human",
                "name": "Extra human",
                "runtime_agent": None,
                "engagement": "always",
                "mission": "Approve independently",
                "authority": ["approve_release"],
                "inputs": ["review"],
                "outputs": ["approval"],
            },
        ):
            temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
            with temporary_directory:
                payload = self.read_roster(roster_path)
                payload["agents"].append(rogue)
                self.write_roster(roster_path, payload)
                errors = validate_agent_contracts(agent_dir, roster_path)
            self.assertTrue(any("exactly 6 roster agents" in error for error in errors), errors)
            self.assertTrue(any("unapproved roster agent identity" in error for error in errors), errors)

    def test_rejects_roster_unknown_fields_and_lead_owner_authority_drift(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            payload = self.read_roster(roster_path)
            payload["unexpected_root"] = "fail"
            payload["operating_model"]["unexpected_model"] = "fail"
            owner = payload["agents"][0]
            lead = payload["agents"][1]
            owner["unexpected_agent"] = "fail"
            owner["authority"] = ["integrate_workspace_changes"]
            lead["authority"] = ["approve_release"]
            lead.pop("outputs")
            self.write_roster(roster_path, payload)
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("roster has unknown field" in error for error in errors), errors)
        self.assertTrue(any("operating_model has unknown field" in error for error in errors), errors)
        self.assertTrue(any("roster agent has unknown field" in error for error in errors), errors)
        self.assertTrue(any("owner authority must exactly match allowed set" in error for error in errors), errors)
        self.assertTrue(any("lead authority must exactly match allowed set" in error for error in errors), errors)
        self.assertTrue(any("lead role missing outputs" in error for error in errors), errors)

    def test_rejects_duplicate_roster_json_keys_without_echo(self) -> None:
        marker = "PRIVATE-MARKER-DUPLICATE-9981"
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            text = roster_path.read_text(encoding="utf-8").replace(
                '"schema_version": "insightradar-agent-roster/v2"',
                f'"{marker}": 1, "{marker}": 2, "schema_version": "insightradar-agent-roster/v2"',
            )
            roster_path.write_text(text, encoding="utf-8")
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("duplicate roster JSON key" in error for error in errors), errors)
        self.assertNotIn(marker, "\n".join(errors))

    def test_rejects_contract_filename_name_mismatch(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            (agent_dir / "evidence_analyst.toml").rename(agent_dir / "renamed.toml")
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("filename stem must match declared name" in error for error in errors), errors)

    def test_rejects_missing_operating_model_governance(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            payload = self.read_roster(roster_path)
            model = payload["operating_model"]
            self.assertIsInstance(model, dict)
            del model["lead_role"]
            del model["write_policy"]
            del model["trade_authority"]
            self.write_roster(roster_path, payload)
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("operating_model missing lead_role" in error for error in errors), errors)
        self.assertTrue(any("operating_model missing write_policy" in error for error in errors), errors)
        self.assertTrue(any("operating_model missing trade_authority" in error for error in errors), errors)

    def test_rejects_wrong_roster_schema_version(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            payload = self.read_roster(roster_path)
            payload["schema_version"] = "insightradar-agent-roster/v1"
            self.write_roster(roster_path, payload)
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("schema_version must be" in error for error in errors), errors)

    def test_rejects_runtime_role_missing_schema_fields(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            payload = self.read_roster(roster_path)
            agents = payload["agents"]
            self.assertIsInstance(agents, list)
            role = agents[2]
            self.assertIsInstance(role, dict)
            for field in ("mission", "authority", "inputs", "outputs", "failure_result"):
                role.pop(field, None)
            self.write_roster(roster_path, payload)
            errors = validate_agent_contracts(agent_dir, roster_path)
        self.assertTrue(any("runtime role missing mission" in error for error in errors), errors)
        self.assertTrue(any("runtime role missing authority" in error for error in errors), errors)
        self.assertTrue(any("runtime role missing inputs" in error for error in errors), errors)
        self.assertTrue(any("runtime role missing outputs" in error for error in errors), errors)
        self.assertTrue(any("runtime role missing failure_result" in error for error in errors), errors)

    def test_rejects_runtime_role_authorities_outside_identity_allowlist(self) -> None:
        forbidden_authorities = (
            "write_workspace",
            "execute_trade",
            "spawn_subagent",
            "approve_product_priority",
            "approve_release",
            "read_private_data",
            "read_secret",
        )
        for authority in forbidden_authorities:
            temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
            with temporary_directory:
                payload = self.read_roster(roster_path)
                agents = payload["agents"]
                self.assertIsInstance(agents, list)
                role = agents[2]
                self.assertIsInstance(role, dict)
                role["authority"] = ["read_workspace", authority]
                self.write_roster(roster_path, payload)
                errors = validate_agent_contracts(agent_dir, roster_path)
            self.assertTrue(
                any("authority must exactly match allowed set" in error for error in errors),
                (authority, errors),
            )

    def test_missing_contract_fields_have_deterministic_error_order(self) -> None:
        temporary_directory, agent_dir, roster_path = self.copy_contract_inputs()
        with temporary_directory:
            contract_path = agent_dir / "evidence_analyst.toml"
            contract_path.write_text('name = "evidence_analyst"\n', encoding="utf-8")
            errors = validate_agent_contracts(agent_dir, roster_path)
        contract_errors = [
            error for error in errors if error.startswith(f"{contract_path}:")
        ]
        self.assertEqual(
            contract_errors,
            [
                f"{contract_path}: missing description",
                f"{contract_path}: missing sandbox_mode",
                f"{contract_path}: missing developer_instructions",
                f"{contract_path}: missing nickname_candidates",
                f"{contract_path}: sandbox_mode must be read-only",
                f"{contract_path}: developer_instructions missing agent-harness-job-readiness-design.md",
                f"{contract_path}: developer_instructions missing Do not modify the workspace",
                f"{contract_path}: developer_instructions missing Do not spawn subagents",
            ],
        )


if __name__ == "__main__":
    unittest.main()
