from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace: Path
    max_file_bytes: int = 5 * 1024**3
    # Reserve headroom so the full Python/Arrow/FastAPI process stays below 6 GB RSS.
    memory_limit: str = "4GB"
    max_threads: int = 4
    allowed_origin: str = "http://127.0.0.1"
    # "anthropic" uses the built-in Claude provider; ai_provider_url posts the
    # approved payload to a custom HTTPS endpoint instead.
    ai_provider: Literal["anthropic"] | None = None
    ai_provider_url: str | None = None
