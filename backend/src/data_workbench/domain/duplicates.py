from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DuplicateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    blocking_columns: list[str]
    comparison_weights: dict[str, float]
    threshold: float = Field(ge=0.0, le=1.0)


class DuplicateCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    left_row_id: str
    right_row_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, float]


class DuplicateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["keep_separate", "remove_record", "merge_fields"]
    survivor_row_id: str | None = None
    field_survivors: dict[str, str] = Field(default_factory=dict)


class DuplicateGroup(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    row_ids: list[str]
    candidates: list[DuplicateCandidate]
    display_values: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, float]
    decision: DuplicateDecision | None = None
