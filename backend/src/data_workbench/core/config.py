from pathlib import Path

from pydantic import BaseModel, ConfigDict


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace: Path
    max_file_bytes: int = 5 * 1024**3
    # Reserve headroom so the full Python/Arrow/FastAPI process stays below 6 GB RSS.
    memory_limit: str = "4GB"
    max_threads: int = 4
    allowed_origin: str = "http://127.0.0.1"
    ai_provider_url: str | None = None
