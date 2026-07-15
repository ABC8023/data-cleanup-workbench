from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from data_workbench.artifacts.manifest import (
    ArtifactBuildError,
    ArtifactService,
    artifact_path,
    load_manifest,
    load_reviewed_descriptions,
    save_reviewed_descriptions,
)
from data_workbench.domain.session import SessionManifest
from data_workbench.storage.session_repository import SessionRepository

router = APIRouter()


class DictionaryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descriptions: dict[str, str]


def get_repo(request: Request) -> SessionRepository:
    return request.app.state.session_repository


def _session_or_404(repo: SessionRepository, session_id: str) -> SessionManifest:
    manifest = repo.get(session_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="session not found")
    return manifest


@router.post("/api/sessions/{session_id}/artifacts")
def build_artifacts(
    session_id: str,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, object]:
    session = _session_or_404(repo, session_id)
    try:
        manifest = ArtifactService().build(
            session.source_path.parent, session.sha256
        )
    except ArtifactBuildError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return manifest.model_dump(mode="json")


@router.get("/api/sessions/{session_id}/artifacts")
def list_artifacts(
    session_id: str,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, object]:
    session = _session_or_404(repo, session_id)
    manifest = load_manifest(session.source_path.parent)
    if manifest is None:
        raise HTTPException(status_code=404, detail="artifacts not built")
    return manifest.model_dump(mode="json")


@router.get("/api/sessions/{session_id}/artifacts/{artifact_id}")
def download_artifact(
    session_id: str,
    artifact_id: str,
    repo: SessionRepository = Depends(get_repo),
) -> FileResponse:
    session = _session_or_404(repo, session_id)
    session_dir = session.source_path.parent
    manifest = load_manifest(session_dir)
    if manifest is None:
        raise HTTPException(status_code=404, detail="artifacts not built")
    record = next(
        (item for item in manifest.artifacts if item.id == artifact_id), None
    )
    if record is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = artifact_path(session_dir, record)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact file missing")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=record.filename,
    )


@router.get("/api/sessions/{session_id}/dictionary")
def get_dictionary_descriptions(
    session_id: str,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, str]:
    session = _session_or_404(repo, session_id)
    return load_reviewed_descriptions(session.source_path.parent)


@router.put("/api/sessions/{session_id}/dictionary")
def update_dictionary_descriptions(
    session_id: str,
    payload: DictionaryUpdateRequest,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, str]:
    session = _session_or_404(repo, session_id)
    save_reviewed_descriptions(session.source_path.parent, payload.descriptions)
    return payload.descriptions
