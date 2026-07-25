"""Validate InsightRadar's bounded project-memory index and routed assets."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "PROJECT_MEMORY.md"
MANIFEST_PATTERN = re.compile(
    r"<!-- project-memory-manifest\s*(\{.*?\})\s*-->",
    re.DOTALL,
)
CURRENT_STATE_PATTERN = re.compile(
    r"<!-- current-state-manifest\s*(\{.*?\})\s*-->",
    re.DOTALL,
)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from stock_assist.workflows.architecture_view import (  # pylint: disable=import-outside-toplevel
        architecture_source_digest,
    )

    errors: list[str] = []
    notes: list[str] = []

    if not INDEX.exists():
        print("FAIL project memory index is missing: PROJECT_MEMORY.md")
        return 1

    raw = INDEX.read_text(encoding="utf-8")
    match = MANIFEST_PATTERN.search(raw)
    if not match:
        print("FAIL PROJECT_MEMORY.md has no project-memory-manifest block")
        return 1

    try:
        manifest = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        print(f"FAIL invalid project-memory manifest JSON: {exc}")
        return 1

    line_count = len(raw.splitlines())
    byte_count = len(raw.encode("utf-8"))
    max_lines = int(manifest.get("max_lines", 200))
    max_bytes = int(manifest.get("max_bytes", 25_600))
    if line_count > max_lines:
        errors.append(f"index has {line_count} lines; cap is {max_lines}")
    if byte_count > max_bytes:
        errors.append(f"index has {byte_count} bytes; cap is {max_bytes}")

    current_state_config = manifest.get("current_state", {})
    current_state_path = ROOT / str(current_state_config.get("path", "CURRENT_STATE.md"))
    current_state_lines = 0
    current_state_bytes = 0
    next_feature_id = "missing"
    if not current_state_path.is_file():
        errors.append(f"current state is missing: {_relative(current_state_path)}")
    else:
        current_state_raw = current_state_path.read_text(encoding="utf-8")
        current_state_lines = len(current_state_raw.splitlines())
        current_state_bytes = len(current_state_raw.encode("utf-8"))
        current_state_max_lines = int(current_state_config.get("max_lines", 120))
        current_state_max_bytes = int(current_state_config.get("max_bytes", 16_384))
        if current_state_lines > current_state_max_lines:
            errors.append(
                f"current state has {current_state_lines} lines; cap is {current_state_max_lines}"
            )
        if current_state_bytes > current_state_max_bytes:
            errors.append(
                f"current state has {current_state_bytes} bytes; cap is {current_state_max_bytes}"
            )

        current_state_match = CURRENT_STATE_PATTERN.search(current_state_raw)
        if not current_state_match:
            errors.append("CURRENT_STATE.md has no current-state-manifest block")
        else:
            try:
                current_state_manifest = json.loads(current_state_match.group(1))
            except json.JSONDecodeError as exc:
                errors.append(f"invalid current-state manifest JSON: {exc}")
            else:
                next_feature_id = str(current_state_manifest.get("next_feature_id", "")).strip()
                for key in ("product_charter", "architecture_source", "decision_index"):
                    target = ROOT / str(current_state_manifest.get(key, ""))
                    if not target.is_file():
                        errors.append(f"current state {key} is missing: {_relative(target)}")

                feature_path = ROOT / "feature_list.json"
                try:
                    feature_payload = json.loads(feature_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    errors.append(f"cannot load feature_list.json: {exc}")
                else:
                    features = feature_payload.get("features", [])
                    feature_by_id: dict[str, dict[str, object]] = {}
                    for feature in features:
                        feature_id = str(feature.get("id", "")).strip()
                        if feature_id in feature_by_id:
                            errors.append(f"duplicate feature id: {feature_id}")
                        feature_by_id[feature_id] = feature
                    if next_feature_id not in feature_by_id:
                        errors.append(f"current state references unknown next feature: {next_feature_id}")
                    else:
                        next_status = str(feature_by_id[next_feature_id].get("status", ""))
                        if next_status not in {"pending", "in_progress"}:
                            errors.append(
                                f"current state next feature {next_feature_id} has invalid status: {next_status}"
                            )

    topic_ids: set[str] = set()
    for topic in manifest.get("topics", []):
        topic_id = str(topic.get("id", "")).strip()
        if not topic_id:
            errors.append("topic without id")
            continue
        if topic_id in topic_ids:
            errors.append(f"duplicate topic id: {topic_id}")
        topic_ids.add(topic_id)

        topic_path = ROOT / str(topic.get("path", ""))
        if not topic_path.is_file():
            errors.append(f"topic file missing: {_relative(topic_path)}")

        for source in topic.get("sources", []):
            source_path = ROOT / str(source)
            if not source_path.exists():
                errors.append(f"source missing for {topic_id}: {_relative(source_path)}")

        for pair in topic.get("generated", []):
            source_path = ROOT / str(pair.get("source", ""))
            output_path = ROOT / str(pair.get("output", ""))
            if not source_path.is_file() or not output_path.is_file():
                errors.append(
                    f"generated pair missing for {topic_id}: "
                    f"{_relative(source_path)} -> {_relative(output_path)}"
                )
            else:
                digest_meta = str(pair.get("digest_meta", "")).strip()
                if digest_meta:
                    expected_digest = architecture_source_digest(source_path.read_bytes())
                    output_text = output_path.read_text(encoding="utf-8")
                    digest_pattern = re.compile(
                        rf'<meta\s+name="{re.escape(digest_meta)}"\s+content="([0-9a-f]{{64}})"\s*/?>'
                    )
                    digest_match = digest_pattern.search(output_text)
                    actual_digest = digest_match.group(1) if digest_match else "missing"
                    if actual_digest != expected_digest:
                        errors.append(
                            f"generated output is stale: {_relative(output_path)} has "
                            f"{digest_meta}={actual_digest}, expected {expected_digest}"
                        )
                elif output_path.stat().st_mtime_ns < source_path.stat().st_mtime_ns:
                    errors.append(
                        f"generated output is stale: {_relative(output_path)} is older than "
                        f"{_relative(source_path)}"
                    )

    from stock_assist.product import COMMANDS  # pylint: disable=import-outside-toplevel

    architecture_path = ROOT / "configs" / "architecture.json"
    architecture = json.loads(architecture_path.read_text(encoding="utf-8"))
    allowed_rings = {"core", "lab", "satellite", "extension", "governance"}
    architecture_rings: set[str] = set()
    for node in architecture.get("nodes", []):
        node_id = str(node.get("id", "missing"))
        ring = str(node.get("ring", "")).strip()
        if ring not in allowed_rings:
            errors.append(f"architecture node {node_id} has invalid product ring: {ring or 'missing'}")
        else:
            architecture_rings.add(ring)
    required_rings = allowed_rings - {"satellite"}
    missing_rings = sorted(required_rings - architecture_rings)
    if missing_rings:
        errors.append("architecture has no nodes for product rings: " + ", ".join(missing_rings))
    covered = {
        str(command)
        for node in architecture.get("nodes", [])
        for command in node.get("commands", [])
    }
    registered = {command.name for command in COMMANDS}
    missing_commands = sorted(registered - covered)
    unknown_commands = sorted(covered - registered)
    if missing_commands:
        errors.append("architecture misses product commands: " + ", ".join(missing_commands))
    if unknown_commands:
        errors.append("architecture references unknown product commands: " + ", ".join(unknown_commands))

    notes.append(f"index={line_count} lines/{byte_count} bytes")
    notes.append(f"current_state={current_state_lines} lines/{current_state_bytes} bytes")
    notes.append(f"next_feature={next_feature_id}")
    notes.append(f"topics={len(topic_ids)}")
    notes.append(
        f"product_rings={len(architecture_rings)}/{len(allowed_rings)} "
        "(satellite optional after external extraction)"
    )
    notes.append(f"architecture_commands={len(covered)}/{len(registered)}")

    if errors:
        print("Project memory validation: FAIL")
        for error in errors:
            print(f"- {error}")
        for note in notes:
            print(f"- {note}")
        return 1

    print("Project memory validation: PASS")
    for note in notes:
        print(f"- {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
