from __future__ import annotations

import argparse
import socket
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote

import uvicorn

from data_workbench.api.app import create_app
from data_workbench.core.config import AppConfig
from data_workbench.core.security import new_session_token, validate_loopback_host

BROWSER_DELAY_SECONDS = 0.5


def reserve_ephemeral_port(host: str) -> int:
    with socket.socket() as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])


def default_workspace() -> Path:
    workspace = Path.home() / ".data-cleanup-workbench" / "sessions"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def build_server(
    host: str = "127.0.0.1",
    port: int | None = None,
    workspace: Path | None = None,
    open_browser: bool = True,
    token: str | None = None,
    ai_provider: str | None = None,
    ai_provider_url: str | None = None,
) -> uvicorn.Server:
    validate_loopback_host(host)
    resolved_port = port if port is not None else reserve_ephemeral_port(host)
    if token is None:
        token = new_session_token()
    config = AppConfig(
        workspace=workspace if workspace is not None else default_workspace(),
        allowed_origin=f"http://{host}:{resolved_port}",
        ai_provider="anthropic" if ai_provider == "anthropic" else None,
        ai_provider_url=ai_provider_url,
    )
    app = create_app(config, token)
    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=resolved_port, log_config=None)
    )
    if open_browser:
        # The token travels in the URL fragment, which browsers never send to
        # the server; the UI reads it once and strips it from history.
        url = f"http://{host}:{resolved_port}/#token={quote(token)}"
        threading.Timer(BROWSER_DELAY_SECONDS, webbrowser.open, [url]).start()
    return server


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="data-workbench",
        description="Local-first data cleanup workbench",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--token",
        default=None,
        help="Fixed session token (testing only; random by default)",
    )
    parser.add_argument(
        "--ai",
        choices=["anthropic"],
        default=None,
        help=(
            "Enable the AI dictionary assist. 'anthropic' uses Claude; the API"
            " key is read from the OS keyring (service data-cleanup-workbench,"
            " entry ai_api_key) or the ANTHROPIC_API_KEY environment variable."
        ),
    )
    parser.add_argument(
        "--ai-url",
        default=None,
        help="Custom HTTPS endpoint for the AI dictionary assist instead of --ai",
    )
    args = parser.parse_args()
    build_server(
        host=args.host,
        port=args.port,
        workspace=args.workspace,
        open_browser=not args.no_browser,
        token=args.token,
        ai_provider=args.ai,
        ai_provider_url=args.ai_url,
    ).run()


if __name__ == "__main__":
    main()
