from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from data_workbench.engine.duckdb_runtime import DuckDBRuntime
from data_workbench.findings.registry import FindingRegistry
from data_workbench.ingest.registry import AdapterRegistry
from data_workbench.jobs.manager import JobManager
from data_workbench.profiling.profiler import Profiler
from data_workbench.storage.session_repository import SessionRepository


@dataclass(frozen=True)
class Services:
    sessions: SessionRepository
    adapters: AdapterRegistry
    duckdb: DuckDBRuntime
    profiler: Profiler
    findings: FindingRegistry
    jobs: JobManager


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
