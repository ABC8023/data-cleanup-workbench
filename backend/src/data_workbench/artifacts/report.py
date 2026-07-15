from __future__ import annotations

import json
from typing import Any

from jinja2 import Environment, select_autoescape

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Data Quality Report</title></head>
<body>
<h1>Data Quality Report</h1>
<p>Source fingerprint: <code>{{ report.source_fingerprint }}</code></p>
<p>Table <code>{{ report.table }}</code> with {{ report.row_count }} rows and
{{ report.columns | length }} columns.</p>
<h2>Columns</h2>
<table border="1">
<tr><th>Name</th><th>Type</th><th>Nulls</th><th>Distinct</th></tr>
{% for column in report.columns %}
<tr><td>{{ column.name }}</td><td>{{ column.inferred_type }}</td>
<td>{{ column.null_count }}</td><td>{{ column.distinct_count }}</td></tr>
{% endfor %}
</table>
<h2>Findings</h2>
<table border="1">
<tr><th>Rule</th><th>Severity</th><th>Columns</th><th>Affected rows</th>
<th>Examples</th></tr>
{% for finding in report.findings %}
<tr><td>{{ finding.rule_id }}</td><td>{{ finding.severity }}</td>
<td>{{ finding.columns | join(', ') }}</td>
<td>{{ finding.affected_row_count }}</td>
<td>{{ finding.example_values | join(', ') }}</td></tr>
{% endfor %}
</table>
</body>
</html>
"""


def build_report(
    profile: dict[str, Any], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    columns = sorted(
        (
            {
                "name": column["name"],
                "inferred_type": column["inferred_type"],
                "null_count": column["null_count"],
                "distinct_count": column["distinct_count"],
            }
            for column in profile["columns"]
        ),
        key=lambda column: str(column["name"]),
    )
    summarized = sorted(
        (
            {
                "rule_id": finding["rule_id"],
                "severity": int(finding["severity"]),
                "columns": finding["columns"],
                "affected_row_count": finding["affected_row_count"],
                "affected_ratio": finding["affected_ratio"],
                "risk_level": finding["risk_level"],
                "example_values": [
                    str(example.get("value", ""))
                    for example in finding["examples"]
                ],
            }
            for finding in findings
        ),
        key=lambda finding: (
            -int(finding["severity"]),
            str(finding["rule_id"]),
            tuple(finding["columns"]),
        ),
    )
    return {
        "source_fingerprint": profile["source_fingerprint"],
        "table": profile["table"],
        "row_count": profile["row_count"],
        "columns": columns,
        "findings": summarized,
    }


def render_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_report_html(report: dict[str, Any]) -> str:
    environment = Environment(autoescape=select_autoescape(default=True))
    return environment.from_string(_HTML_TEMPLATE).render(report=report)
