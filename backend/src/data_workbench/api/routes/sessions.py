import asyncio
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from data_workbench.api.dependencies import Services, get_services
from data_workbench.domain.session import SessionManifest
from data_workbench.ingest.base import MalformedInput, UnsupportedFormat
from data_workbench.jobs.manager import JobContext, JobFailure
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


@router.post("/api/sessions/{session_id}/profile", status_code=202)
async def start_profile(
    session_id: str,
    services: Services = Depends(get_services),
) -> dict[str, str]:
    session = services.sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    async def work(context: JobContext) -> None:
        session_dir = session.source_path.parent

        def run() -> None:
            context.publish("inspect", 0, 4, "Inspecting file")
            try:
                handles = services.adapters.inspect_declared(
                    session.source_path, session.filename, session_dir
                )
            except (MalformedInput, UnsupportedFormat) as error:
                raise JobFailure("invalid_input") from error
            with services.duckdb.connect(session_dir) as connection:
                context.publish("profile", 1, 4, "Profiling dataset")
                profile = services.profiler.profile(
                    connection,
                    handles[0],
                    session.sha256,
                    context.raise_if_cancelled,
                )
                context.publish("findings", 2, 4, "Detecting issues")
                context.raise_if_cancelled()
                findings = services.findings.detect(connection, handles[0], profile)
            context.publish("persist", 3, 4, "Saving results")
            services.sessions.save_profile(session.id, profile, findings)
            context.publish("persist", 4, 4, "Profile complete")

        await asyncio.to_thread(run)

    job = services.jobs.submit("profile", work)
    return {"job_id": job.id}


@router.get("/api/sessions/{session_id}/profile")
def get_profile(
    session_id: str,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, object]:
    saved = repo.load_profile(session_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return saved
