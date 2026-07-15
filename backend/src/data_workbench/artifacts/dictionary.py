from __future__ import annotations

import json
from typing import Any


def build_dictionary(
    profile: dict[str, Any], reviewed_descriptions: dict[str, str]
) -> dict[str, Any]:
    columns = sorted(
        (
            {
                "name": column["name"],
                "inferred_type": column["inferred_type"],
                "null_count": column["null_count"],
                "distinct_count": column["distinct_count"],
                "examples": list(column["examples"]),
                "description": reviewed_descriptions.get(str(column["name"]), ""),
            }
            for column in profile["columns"]
        ),
        key=lambda column: str(column["name"]),
    )
    return {
        "source_fingerprint": profile["source_fingerprint"],
        "table": profile["table"],
        "row_count": profile["row_count"],
        "columns": columns,
    }


def render_dictionary_json(dictionary: dict[str, Any]) -> str:
    return json.dumps(dictionary, indent=2, sort_keys=True) + "\n"


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_dictionary_markdown(dictionary: dict[str, Any]) -> str:
    lines = [
        "# Data Dictionary",
        "",
        f"Table `{dictionary['table']}` — {dictionary['row_count']} rows,"
        f" source `{dictionary['source_fingerprint']}`.",
        "",
        "| Column | Type | Nulls | Distinct | Examples | Description |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for column in dictionary["columns"]:
        examples = ", ".join(str(example) for example in column["examples"][:3])
        lines.append(
            f"| {_cell(column['name'])} | {_cell(column['inferred_type'])}"
            f" | {column['null_count']} | {column['distinct_count']}"
            f" | {_cell(examples)} | {_cell(column['description'])} |"
        )
    return "\n".join(lines) + "\n"
