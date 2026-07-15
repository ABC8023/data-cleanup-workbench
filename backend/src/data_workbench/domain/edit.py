from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class BaseEditCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str


class RenameColumnCommand(BaseEditCommand):
    operation: Literal["rename_column"] = "rename_column"
    new_name: str


class DropColumnCommand(BaseEditCommand):
    operation: Literal["drop_column"] = "drop_column"


class ReplaceValueCommand(BaseEditCommand):
    operation: Literal["replace_value"] = "replace_value"
    old: str | None
    new: str | None


class SetCaseCommand(BaseEditCommand):
    operation: Literal["set_case"] = "set_case"
    case: Literal["upper", "lower"]


class TrimWhitespaceCommand(BaseEditCommand):
    operation: Literal["trim_whitespace"] = "trim_whitespace"


EditCommand = Annotated[
    Union[
        RenameColumnCommand,
        DropColumnCommand,
        ReplaceValueCommand,
        SetCaseCommand,
        TrimWhitespaceCommand,
    ],
    Field(discriminator="operation"),
]


class EditSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    before: str | None
    after: str | None


class EditPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    command: EditCommand
    table: str
    columns_before: list[str]
    columns_after: list[str]
    affected_row_count: int = Field(ge=0)
    samples: list[EditSample]


class AppliedEdit(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int = Field(ge=1)
    table: str
    command: EditCommand
    staged_filename: str
    row_count: int = Field(ge=0)
