from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ColumnProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    inferred_type: str
    null_count: int = Field(ge=0)
    distinct_count: int = Field(ge=0)
    min_value: str | None
    max_value: str | None
    examples: list[str]
    top_values: list[tuple[str, int]]


class DatasetProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_fingerprint: str
    table: str
    row_count: int = Field(ge=0)
    columns: list[ColumnProfile]
    sampled: bool = False
