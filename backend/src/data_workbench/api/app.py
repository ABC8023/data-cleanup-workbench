from fastapi import Depends, FastAPI, Header, HTTPException

from data_workbench.api.dependencies import Services
from data_workbench.api.routes.artifacts import router as artifacts_router
from data_workbench.api.routes.edits import router as edits_router
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


def create_app(config: AppConfig, token: str) -> FastAPI:
    app = FastAPI()

    def require_token(x_session_token: str | None = Header(default=None)) -> None:
        if x_session_token != token:
            raise HTTPException(status_code=401, detail="invalid session token")

    services = Services(
        sessions=SessionRepository(config.workspace, config.max_file_bytes),
        adapters=AdapterRegistry(),
        duckdb=DuckDBRuntime(config.memory_limit, config.max_threads),
        profiler=Profiler(),
        findings=FindingRegistry.default(),
        jobs=JobManager(max_heavy_jobs=MAX_HEAVY_JOBS),
    )
    app.state.config = config
    app.state.token_dependency = require_token
    app.state.services = services
    app.state.session_repository = services.sessions
    app.include_router(health_router, dependencies=[Depends(require_token)])
    app.include_router(sessions_router, dependencies=[Depends(require_token)])
    app.include_router(edits_router, dependencies=[Depends(require_token)])
    app.include_router(jobs_router, dependencies=[Depends(require_token)])
    app.include_router(artifacts_router, dependencies=[Depends(require_token)])
    return app
