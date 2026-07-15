from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ArtifactKind = Literal[
    "cleaned",
    "recipe",
    "report_html",
    "report_json",
    "dictionary_md",
    "dictionary_json",
    "quarantine",
]


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: ArtifactKind
    filename: str
    sha256: str
    size_bytes: int = Field(ge=0)


class OutputManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_fingerprint: str
    recipe_hash: str
    app_version: str
    operation_versions: dict[str, int]
    row_reconciliation: dict[str, int]
    artifacts: list[ArtifactRecord]
    state: Literal["complete"] = "complete"
