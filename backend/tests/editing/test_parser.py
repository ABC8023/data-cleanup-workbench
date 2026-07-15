from __future__ import annotations

import pytest

from data_workbench.domain.edit import (
    DropColumnCommand,
    RenameColumnCommand,
    ReplaceValueCommand,
    SetCaseCommand,
    TrimWhitespaceCommand,
)
from data_workbench.editing.parser import UnsupportedCommand, parse_command


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "rename column customer_id to customer",
            RenameColumnCommand(column="customer_id", new_name="customer"),
        ),
        (
            'rename column "full name" to full_name',
            RenameColumnCommand(column="full name", new_name="full_name"),
        ),
        ("drop column notes", DropColumnCommand(column="notes")),
        ("DROP COLUMN Notes", DropColumnCommand(column="Notes")),
        (
            "replace 'N/A' with null in column amount",
            ReplaceValueCommand(column="amount", old="N/A", new=None),
        ),
        (
            'replace null with "unknown" in column city',
            ReplaceValueCommand(column="city", old=None, new="unknown"),
        ),
        (
            "replace '' with null in column city",
            ReplaceValueCommand(column="city", old="", new=None),
        ),
        (
            "fill nulls in column city with 'unknown'",
            ReplaceValueCommand(column="city", old=None, new="unknown"),
        ),
        ("uppercase column code", SetCaseCommand(column="code", case="upper")),
        ("Lowercase Column Code", SetCaseCommand(column="Code", case="lower")),
        ("trim column name", TrimWhitespaceCommand(column="name")),
        (
            "  trim   whitespace in column name ",
            TrimWhitespaceCommand(column="name"),
        ),
    ],
)
def test_parse_supported_commands(text: str, expected: object) -> None:
    assert parse_command(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "delete everything",
        "drop column",
        "rename column a b",
        "replace x with y in column c",
        "update table set a = 1",
        "drop column a; drop column b",
        "uppercase column a where a = 'x'",
    ],
)
def test_parse_rejects_unsupported_commands(text: str) -> None:
    with pytest.raises(UnsupportedCommand, match="Supported commands"):
        parse_command(text)
