from pathlib import Path
from typing import Awaitable, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from data_workbench.ai.gateway import AiGateway, PreviewStore, utc_now
from data_workbench.ai.providers import (
    AiProvider,
    AnthropicDictionaryProvider,
    DisabledProvider,
    HttpDictionaryProvider,
)
from data_workbench.api.dependencies import Services
from data_workbench.api.routes.ai import router as ai_router
from data_workbench.api.routes.artifacts import router as artifacts_router
from data_workbench.api.routes.edits import router as edits_router
from data_workbench.artifacts.dictionary import build_dictionary
from data_workbench.api.routes.health import router as health_router
from data_workbench.api.routes.jobs import router as jobs_router
from data_workbench.api.routes.sessions import router as sessions_router
from data_workbench.core.config import AppConfig
from data_workbench.engine.duckdb_runtime import DuckDBRuntime
from data_workbench.findings.registry import FindingRegistry
from data_workbench.ingest.registry import AdapterRegistry
from data_workbench.jobs.manager import JobManager
from data_workbench.profiling.profiler import Profiler
from data_workbench.storage.session_repository import SessionRepository

MAX_HEAVY_JOBS = 1
DEFAULT_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(
    config: AppConfig,
    token: str,
    static_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI()

    def require_token(x_session_token: str | None = Header(default=None)) -> None:
        if x_session_token != token:
            raise HTTPException(status_code=401, detail="invalid session token")

    @app.middleware("http")
    async def enforce_origin(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        origin = request.headers.get("origin")
        if origin is not None and origin != config.allowed_origin:
            return JSONResponse(
                status_code=403, content={"detail": "origin not allowed"}
            )
        return await call_next(request)

    services = Services(
        sessions=SessionRepository(config.workspace, config.max_file_bytes),
        adapters=AdapterRegistry(),
        duckdb=DuckDBRuntime(config.memory_limit, config.max_threads),
        profiler=Profiler(),
        findings=FindingRegistry.default(),
        jobs=JobManager(max_heavy_jobs=MAX_HEAVY_JOBS),
    )
    provider: AiProvider
    if config.ai_provider == "anthropic":
        provider = AnthropicDictionaryProvider()
    elif config.ai_provider_url:
        provider = HttpDictionaryProvider(config.ai_provider_url)
    else:
        provider = DisabledProvider()
    app.state.config = config
    app.state.token_dependency = require_token
    app.state.services = services
    app.state.session_repository = services.sessions
    app.state.ai_gateway = AiGateway(
        provider,
        PreviewStore(),
        clock=utc_now,
        deterministic_dictionary=lambda profile: build_dictionary(profile, {}),
    )
    app.include_router(health_router, dependencies=[Depends(require_token)])
    app.include_router(sessions_router, dependencies=[Depends(require_token)])
    app.include_router(edits_router, dependencies=[Depends(require_token)])
    app.include_router(jobs_router, dependencies=[Depends(require_token)])
    app.include_router(artifacts_router, dependencies=[Depends(require_token)])
    app.include_router(ai_router, dependencies=[Depends(require_token)])
    resolved_static = static_dir if static_dir is not None else DEFAULT_STATIC_DIR
    if resolved_static.is_dir():
        app.mount(
            "/", StaticFiles(directory=resolved_static, html=True), name="ui"
        )
    return app
