import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from data_workbench.domain.session import SessionManifest
from data_workbench.storage.session_repository import SessionRepository

router = APIRouter()


def get_repo(request: Request) -> SessionRepository:
    return request.app.state.session_repository


@router.post("/api/sessions")
async def create_session(
    request: Request,
    filename: str,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, object]:
    raw_length = request.headers.get("content-length")
    if raw_length is None or not raw_length.isdigit():
        raise HTTPException(status_code=411, detail="Content-Length is required")
    size = int(raw_length)
    config = request.app.state.config
    if size > config.max_file_bytes:
        raise HTTPException(status_code=413, detail="file exceeds 5 GB limit")
    if shutil.disk_usage(config.workspace).free < size * 2:
        raise HTTPException(status_code=507, detail="insufficient local disk space")
    display_filename = Path(filename.replace("\\", "/")).name
    try:
        manifest = await repo.stage(display_filename, size, request.stream())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return manifest.model_dump(mode="json")


@router.get("/api/sessions/{session_id}")
def get_session(
    session_id: str,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, object]:
    manifest: SessionManifest | None = repo.get(session_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="session not found")
    return manifest.model_dump(mode="json")
