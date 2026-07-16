from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BaseStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    operation_version: Literal[1] = 1
    columns: list[str]
    on_error: Literal["preserve", "set_null", "quarantine"]


class RenameColumnStep(BaseStep):
    operation: Literal["rename_column"] = "rename_column"
    new_name: str = Field(min_length=1)

    @model_validator(mode="after")
    def single_column(self) -> RenameColumnStep:
        if len(self.columns) != 1:
            raise ValueError("rename_column requires exactly one column")
        return self


class NormalizeTextStep(BaseStep):
    operation: Literal["normalize_text"] = "normalize_text"
    trim: bool = True
    case: Literal["preserve", "upper", "lower"] = "preserve"


class ParseDateStep(BaseStep):
    operation: Literal["parse_date"] = "parse_date"
    formats: list[str] = Field(min_length=1)
    output_format: str = Field(default="%Y-%m-%d", min_length=1)


class CastNumberStep(BaseStep):
    operation: Literal["cast_number"] = "cast_number"
    target: Literal["integer", "decimal"]
    decimal_separator: Literal[".", ","] = "."


class ReplaceValueStep(BaseStep):
    operation: Literal["replace_value"] = "replace_value"
    old: str | None
    new: str | None


class DropColumnStep(BaseStep):
    operation: Literal["drop_column"] = "drop_column"


class ExactDeduplicateStep(BaseStep):
    operation: Literal["exact_deduplicate"] = "exact_deduplicate"
    keep: Literal["first", "last"]


class ApplyDuplicateDecisionStep(BaseStep):
    operation: Literal["apply_duplicate_decision"] = "apply_duplicate_decision"
    group_id: str
    action: Literal["keep_separate", "remove_record", "merge_fields"]
    survivor_row_id: str | None = None
    field_survivors: dict[str, str] = Field(default_factory=dict)


RecipeStep = Annotated[
    Union[
        RenameColumnStep,
        NormalizeTextStep,
        ParseDateStep,
        CastNumberStep,
        ReplaceValueStep,
        DropColumnStep,
        ExactDeduplicateStep,
        ApplyDuplicateDecisionStep,
    ],
    Field(discriminator="operation"),
]


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipe_version: Literal[1] = 1
    source_fingerprint: str
    steps: list[RecipeStep]

    @model_validator(mode="after")
    def unique_step_ids(self) -> Recipe:
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("recipe step IDs must be unique")
        return self
