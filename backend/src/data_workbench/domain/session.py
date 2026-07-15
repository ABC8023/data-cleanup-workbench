from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class SessionManifest(BaseModel):
    id: str
    filename: str
    size_bytes: int
    sha256: str
    source_path: Path
    state: Literal["staged", "profiled", "executed"] = "staged"
