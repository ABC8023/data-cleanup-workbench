from __future__ import annotations

from enum import IntEnum
from typing import Literal, Protocol

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from data_workbench.domain.profile import DatasetProfile
from data_workbench.ingest.base import TableHandle


class Severity(IntEnum):
    info = 1
    warning = 2
    error = 3


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    rule_id: str
    rule_version: int = Field(ge=1)
    category: str
    severity: Severity
    table: str
    columns: list[str]
    affected_row_count: int = Field(ge=0)
    affected_ratio: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, str | int | float]
    examples: list[dict[str, str]]
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_operation: dict[str, object] | None
    risk_level: Literal["safe", "review_required", "informational"]
    provenance: dict[str, str]


class Detector(Protocol):
    @property
    def rule_id(self) -> str: ...

    @property
    def rule_version(self) -> int: ...

    def detect(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        profile: DatasetProfile,
    ) -> list[Finding]: ...
