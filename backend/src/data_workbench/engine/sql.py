from __future__ import annotations

from pathlib import Path


def quote_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
