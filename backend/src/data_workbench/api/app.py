from fastapi import Depends, FastAPI, Header, HTTPException

from data_workbench.api.routes.health import router as health_router
from data_workbench.core.config import AppConfig


def create_app(config: AppConfig, token: str) -> FastAPI:
    app = FastAPI()

    def require_token(x_session_token: str | None = Header(default=None)) -> None:
        if x_session_token != token:
            raise HTTPException(status_code=401, detail="invalid session token")

    app.include_router(health_router, dependencies=[Depends(require_token)])
    app.state.config = config
    app.state.token_dependency = require_token
    return app
