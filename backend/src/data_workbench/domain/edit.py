from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class MoveColumnCommand(BaseEditCommand):
    operation: Literal["move_column"] = "move_column"
    position: Literal["before", "after", "start", "end"]
    reference: str | None = None

    @model_validator(mode="after")
    def reference_matches_position(self) -> MoveColumnCommand:
        relative = self.position in ("before", "after")
        if relative and self.reference is None:
            raise ValueError("move before/after requires a reference column")
        if not relative and self.reference is not None:
            raise ValueError("move to start/end takes no reference column")
        return self


EditCommand = Annotated[
    Union[
        RenameColumnCommand,
        DropColumnCommand,
        ReplaceValueCommand,
        SetCaseCommand,
        TrimWhitespaceCommand,
        MoveColumnCommand,
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
