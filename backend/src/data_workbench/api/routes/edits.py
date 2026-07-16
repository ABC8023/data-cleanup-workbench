from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from data_workbench.domain.edit import EditCommand
from data_workbench.domain.session import SessionManifest
from data_workbench.editing.engine import (
    EditEngine,
    InvalidEdit,
    UnknownColumn,
    load_edits,
    resolve_handle,
    table_columns,
)
from data_workbench.editing.parser import UnsupportedCommand, parse_command
from data_workbench.engine.duckdb_runtime import DuckDBRuntime
from data_workbench.engine.sql import quote_identifier
from data_workbench.ingest.base import (
    MalformedInput,
    TableHandle,
    UnsupportedFormat,
)
from data_workbench.ingest.registry import AdapterRegistry
from data_workbench.storage.session_repository import SessionRepository

router = APIRouter()

MAX_PREVIEW_ROWS = 200


class EditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    table: str | None = None
    approved: bool = False


def get_repo(request: Request) -> SessionRepository:
    return request.app.state.session_repository


def _load_session(session_id: str, repo: SessionRepository) -> SessionManifest:
    manifest = repo.get(session_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="session not found")
    return manifest


def _base_handle(manifest: SessionManifest, table: str | None) -> TableHandle:
    session_dir = manifest.source_path.parent
    try:
        handles = AdapterRegistry().inspect_declared(
            manifest.source_path, manifest.filename, session_dir
        )
    except UnsupportedFormat as error:
        raise HTTPException(
            status_code=400, detail=f"unsupported source format '{error}'"
        ) from error
    except MalformedInput as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if table is None:
        return handles[0]
    for handle in handles:
        if handle.name == table:
            return handle
    raise HTTPException(status_code=404, detail=f"table {table!r} not found")


def _prepare(
    request: Request,
    session_id: str,
    payload: EditRequest,
    repo: SessionRepository,
) -> tuple[SessionManifest, TableHandle, EditCommand, DuckDBRuntime]:
    manifest = _load_session(session_id, repo)
    try:
        command = parse_command(payload.command)
    except UnsupportedCommand as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    base = _base_handle(manifest, payload.table)
    handle = resolve_handle(manifest.source_path.parent, base)
    config = request.app.state.config
    runtime = DuckDBRuntime(config.memory_limit, config.max_threads)
    return manifest, handle, command, runtime


@router.post("/api/sessions/{session_id}/edits/preview")
def preview_edit(
    request: Request,
    session_id: str,
    payload: EditRequest,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, object]:
    manifest, handle, command, runtime = _prepare(request, session_id, payload, repo)
    session_dir = manifest.source_path.parent
    with runtime.connect(session_dir) as connection:
        try:
            preview = EditEngine().preview(connection, handle, command)
        except (UnknownColumn, InvalidEdit) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return preview.model_dump(mode="json")


@router.post("/api/sessions/{session_id}/edits")
def apply_edit(
    request: Request,
    session_id: str,
    payload: EditRequest,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, object]:
    if not payload.approved:
        raise HTTPException(
            status_code=400,
            detail="edits change data and require approved=true after preview",
        )
    manifest, handle, command, runtime = _prepare(request, session_id, payload, repo)
    session_dir = manifest.source_path.parent
    with runtime.connect(session_dir) as connection:
        try:
            applied = EditEngine().apply(connection, session_dir, handle, command)
        except (UnknownColumn, InvalidEdit) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return applied.model_dump(mode="json")


@router.get("/api/sessions/{session_id}/rows")
def preview_rows(
    request: Request,
    session_id: str,
    limit: int = 50,
    table: str | None = None,
    repo: SessionRepository = Depends(get_repo),
) -> dict[str, object]:
    manifest = _load_session(session_id, repo)
    base = _base_handle(manifest, table)
    session_dir = manifest.source_path.parent
    handle = resolve_handle(session_dir, base)
    capped = max(1, min(limit, MAX_PREVIEW_ROWS))
    config = request.app.state.config
    runtime = DuckDBRuntime(config.memory_limit, config.max_threads)
    with runtime.connect(session_dir) as connection:
        columns = table_columns(connection, handle)
        select = ", ".join(quote_identifier(name) for name in columns)
        fetched = connection.sql(
            f"SELECT {select} FROM ({handle.scan_sql}) LIMIT {capped}"
        ).fetchall()
        counted = connection.sql(
            f"SELECT count(*) FROM ({handle.scan_sql})"
        ).fetchone()
    return {
        "table": handle.name,
        "columns": columns,
        "total_rows": int(counted[0]) if counted is not None else 0,
        "rows": [
            [None if value is None else str(value) for value in row]
            for row in fetched
        ],
    }


@router.get("/api/sessions/{session_id}/edits")
def list_edits(
    session_id: str,
    repo: SessionRepository = Depends(get_repo),
) -> list[dict[str, object]]:
    manifest = _load_session(session_id, repo)
    return [
        edit.model_dump(mode="json")
        for edit in load_edits(manifest.source_path.parent)
    ]
