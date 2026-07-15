import asyncio
import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from data_workbench.api.dependencies import Services, get_services
from data_workbench.api.routes.edits import _base_handle
from data_workbench.domain.duplicates import DuplicateConfig
from data_workbench.domain.recipe import Recipe
from data_workbench.duplicates.engine import (
    DuplicateEngine,
    InvalidDuplicateConfig,
)
from data_workbench.domain.session import SessionManifest
from data_workbench.editing.engine import resolve_handle
from data_workbench.ingest.base import (
    MalformedInput,
    TableHandle,
    UnsupportedFormat,
)
from data_workbench.jobs.manager import JobContext, JobFailure
from data_workbench.recipes.executor import ExecutionError, RecipeExecutor
from data_workbench.storage.session_repository import SessionRepository

router = APIRouter()


class RecipePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe: Recipe
    table: str | None = None


class RecipeExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe: Recipe
    table: str | None = None
    output_format: Literal["csv", "parquet"] = "parquet"
    approved: bool = False


def _recipe_session(
    services: Services, session_id: str, recipe: Recipe, table: str | None
) -> tuple[SessionManifest, TableHandle]:
    manifest = services.sessions.get(session_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="session not found")
    if recipe.source_fingerprint != manifest.sha256:
        raise HTTPException(
            status_code=409,
            detail="recipe fingerprint does not match the session source",
        )
    base = _base_handle(manifest, table)
    return manifest, resolve_handle(manifest.source_path.parent, base)


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


@router.post("/api/sessions/{session_id}/recipe/preview")
def preview_recipe(
    session_id: str,
    payload: RecipePreviewRequest,
    services: Services = Depends(get_services),
) -> dict[str, object]:
    manifest, handle = _recipe_session(
        services, session_id, payload.recipe, payload.table
    )
    with services.duckdb.connect(manifest.source_path.parent) as connection:
        preview = RecipeExecutor().preview(connection, handle, payload.recipe)
    return preview.model_dump(mode="json")


@router.post("/api/sessions/{session_id}/recipe/execute", status_code=202)
async def execute_recipe(
    session_id: str,
    payload: RecipeExecuteRequest,
    services: Services = Depends(get_services),
) -> dict[str, str]:
    if not payload.approved:
        raise HTTPException(
            status_code=400,
            detail="execution changes data and requires approved=true"
            " after reviewing a preview",
        )
    manifest, handle = _recipe_session(
        services, session_id, payload.recipe, payload.table
    )
    session_dir = manifest.source_path.parent

    async def work(context: JobContext) -> None:
        def run() -> None:
            context.publish("execute", 0, 2, "Executing recipe")
            with services.duckdb.connect(session_dir) as connection:
                try:
                    result = RecipeExecutor().execute(
                        connection,
                        handle,
                        payload.recipe,
                        session_dir / "outputs",
                        payload.output_format,
                        context,
                    )
                except ExecutionError as error:
                    raise JobFailure("execution_failed") from error
            context.publish("persist", 1, 2, "Saving execution result")
            services.sessions.save_execution(
                manifest.id, result.model_dump(mode="json")
            )
            context.publish("persist", 2, 2, "Execution complete")

        await asyncio.to_thread(run)

    job = services.jobs.submit("execute", work)
    return {"job_id": job.id}


class FuzzyDuplicatesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: DuplicateConfig
    table: str | None = None
    max_candidates: int = 1000


class ExactDuplicatesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str]
    table: str | None = None


def _duplicate_handle(
    services: Services, session_id: str, table: str | None
) -> tuple[SessionManifest, TableHandle]:
    manifest = services.sessions.get(session_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="session not found")
    base = _base_handle(manifest, table)
    return manifest, resolve_handle(manifest.source_path.parent, base)


@router.post("/api/sessions/{session_id}/duplicates/fuzzy")
def find_fuzzy_duplicates(
    session_id: str,
    payload: FuzzyDuplicatesRequest,
    services: Services = Depends(get_services),
) -> list[dict[str, object]]:
    manifest, handle = _duplicate_handle(services, session_id, payload.table)
    with services.duckdb.connect(manifest.source_path.parent) as connection:
        try:
            groups = DuplicateEngine().find_fuzzy(
                connection, handle, payload.config, payload.max_candidates
            )
        except InvalidDuplicateConfig as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return [group.model_dump(mode="json") for group in groups]


@router.post("/api/sessions/{session_id}/duplicates/exact")
def find_exact_duplicates(
    session_id: str,
    payload: ExactDuplicatesRequest,
    services: Services = Depends(get_services),
) -> list[dict[str, object]]:
    manifest, handle = _duplicate_handle(services, session_id, payload.table)
    with services.duckdb.connect(manifest.source_path.parent) as connection:
        try:
            groups = DuplicateEngine().find_exact(
                connection, handle, payload.columns
            )
        except InvalidDuplicateConfig as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return [group.model_dump(mode="json") for group in groups]


@router.get("/api/sessions/{session_id}/execution")
def get_execution(
    session_id: str,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, object]:
    saved = repo.load_execution(session_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="execution not found")
    return saved
