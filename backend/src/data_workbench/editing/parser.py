from __future__ import annotations

import re
from typing import Callable, Literal

from data_workbench.domain.edit import (
    DropColumnCommand,
    EditCommand,
    MoveColumnCommand,
    RenameColumnCommand,
    ReplaceValueCommand,
    SetCaseCommand,
    TrimWhitespaceCommand,
)

SUPPORTED_COMMANDS = (
    'rename column <name> to <name>',
    'drop column <name>',
    "replace '<value>' with '<value>' in column <name>",
    "replace null with '<value>' in column <name>",
    "replace '<value>' with null in column <name>",
    "fill nulls in column <name> with '<value>'",
    'uppercase column <name>',
    'lowercase column <name>',
    'trim whitespace in column <name>',
    'move column <name> before <name>',
    'move column <name> after <name>',
    'move column <name> to start',
    'move column <name> to end',
)

_COLUMN = r'("[^"]+"|[^\s\'"]+)'
_VALUE = r"('[^']*'|\"[^\"]*\"|null)"


class UnsupportedCommand(ValueError):
    """Raised when a user command does not match the typed edit grammar."""


def _column(token: str) -> str:
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    return token


def _value(token: str) -> str | None:
    if token.lower() == "null":
        return None
    return token[1:-1]


def _rename(match: re.Match[str]) -> EditCommand:
    return RenameColumnCommand(
        column=_column(match.group(1)), new_name=_column(match.group(2))
    )


def _drop(match: re.Match[str]) -> EditCommand:
    return DropColumnCommand(column=_column(match.group(1)))


def _replace(match: re.Match[str]) -> EditCommand:
    return ReplaceValueCommand(
        column=_column(match.group(3)),
        old=_value(match.group(1)),
        new=_value(match.group(2)),
    )


def _fill_nulls(match: re.Match[str]) -> EditCommand:
    return ReplaceValueCommand(
        column=_column(match.group(1)), old=None, new=_value(match.group(2))
    )


def _set_case(match: re.Match[str]) -> EditCommand:
    case: Literal["upper", "lower"] = (
        "upper" if match.group(1).lower() == "uppercase" else "lower"
    )
    return SetCaseCommand(column=_column(match.group(2)), case=case)


def _trim(match: re.Match[str]) -> EditCommand:
    return TrimWhitespaceCommand(column=_column(match.group(1)))


def _move_relative(match: re.Match[str]) -> EditCommand:
    position: Literal["before", "after"] = (
        "before" if match.group(2).lower() == "before" else "after"
    )
    return MoveColumnCommand(
        column=_column(match.group(1)),
        position=position,
        reference=_column(match.group(3)),
    )


def _move_edge(match: re.Match[str]) -> EditCommand:
    position: Literal["start", "end"] = (
        "start" if match.group(2).lower() == "start" else "end"
    )
    return MoveColumnCommand(column=_column(match.group(1)), position=position)


_GRAMMAR: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], EditCommand]], ...] = (
    (re.compile(rf"^rename column {_COLUMN} to {_COLUMN}$", re.IGNORECASE), _rename),
    (re.compile(rf"^drop column {_COLUMN}$", re.IGNORECASE), _drop),
    (
        re.compile(
            rf"^replace {_VALUE} with {_VALUE} in column {_COLUMN}$", re.IGNORECASE
        ),
        _replace,
    ),
    (
        re.compile(
            rf"^fill nulls in column {_COLUMN} with {_VALUE}$", re.IGNORECASE
        ),
        _fill_nulls,
    ),
    (
        re.compile(rf"^(uppercase|lowercase) column {_COLUMN}$", re.IGNORECASE),
        _set_case,
    ),
    (
        re.compile(rf"^trim(?: whitespace in)? column {_COLUMN}$", re.IGNORECASE),
        _trim,
    ),
    (
        re.compile(
            rf"^move column {_COLUMN} (before|after) {_COLUMN}$", re.IGNORECASE
        ),
        _move_relative,
    ),
    (
        re.compile(rf"^move column {_COLUMN} to (start|end)$", re.IGNORECASE),
        _move_edge,
    ),
)


def parse_command(text: str) -> EditCommand:
    normalized = " ".join(text.split())
    for pattern, build in _GRAMMAR:
        match = pattern.fullmatch(normalized)
        if match is not None:
            return build(match)
    raise UnsupportedCommand(
        "unsupported edit command. Supported commands: "
        + "; ".join(SUPPORTED_COMMANDS)
    )
