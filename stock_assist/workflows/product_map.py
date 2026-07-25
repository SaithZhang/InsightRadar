"""Render the InsightRadar product module and data map."""

from __future__ import annotations

from datetime import datetime

from stock_assist.branding import PRODUCT_DESCRIPTION, PRODUCT_NAME, PRODUCT_TAGLINE
from stock_assist.product import COMMANDS, FILES, MODULES, module_for
from stock_assist.reports import bullet


def build_product_map_report() -> str:
    lines = [
        f"# {PRODUCT_NAME} Product Map",
        "",
        "## Product Promise",
        bullet(
            [
                PRODUCT_DESCRIPTION,
                PRODUCT_TAGLINE,
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ]
        ),
        "",
        "## Product Modules",
        _format_modules(),
        "",
        "## CLI Surface",
        _format_commands(),
        "",
        "## Configuration And Data Boundaries",
        _format_files(),
        "",
        "## Product-Grade Next Step",
        bullet(
            [
                "Promote this map into lightweight validators for product_config, private_runtime_data, templates, and schemas.",
                "Keep compatibility commands while moving user-facing docs and automations toward `insight-radar`.",
                "Use the module boundaries when adding dashboards, alerts, or future API routes.",
            ]
        ),
    ]
    return "\n".join(lines)


def _format_modules() -> str:
    sections: list[str] = []
    for module in MODULES:
        sections.extend(
            [
                f"### {module.title}",
                bullet(
                    [
                        f"Purpose: {module.purpose}",
                        f"Primary users: {', '.join(module.primary_users)}",
                        f"Outcomes: {', '.join(module.outcomes)}",
                    ]
                ),
            ]
        )
    return "\n".join(sections)


def _format_commands() -> str:
    rows = []
    for command in COMMANDS:
        module = module_for(command.module_key)
        rows.append(
            (
                f"`{command.name}` -> {module.title}: {command.help}. "
                f"Inputs: {', '.join(command.inputs)}. Outputs: {', '.join(command.outputs)}."
            )
        )
    return bullet(rows)


def _format_files() -> str:
    rows = [
        f"`{item.path}` [{item.kind}] -> {module_for(item.module_key).title}: {item.description}"
        for item in FILES
    ]
    return bullet(rows)
