from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncIterator

from data_workbench.api.dependencies import Services, get_services
from data_workbench.jobs.manager import JobRecord

router = APIRouter()


def _job_or_404(services: Services, job_id: str) -> JobRecord:
    try:
        return services.jobs.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="job not found") from error


@router.get("/api/jobs/{job_id}")
def get_job(
    job_id: str,
    services: Services = Depends(get_services),
) -> dict[str, object]:
    job = _job_or_404(services, job_id)
    return {
        "id": job.id,
        "kind": job.kind,
        "state": job.state,
        "error_code": job.error_code,
    }


@router.get("/api/jobs/{job_id}/events")
def stream_job_events(
    job_id: str,
    services: Services = Depends(get_services),
) -> StreamingResponse:
    _job_or_404(services, job_id)

    async def stream() -> AsyncIterator[str]:
        async for event in services.jobs.events(job_id):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.delete("/api/jobs/{job_id}", status_code=202)
def cancel_job(
    job_id: str,
    services: Services = Depends(get_services),
) -> dict[str, object]:
    _job_or_404(services, job_id)
    services.jobs.cancel(job_id)
    return {"id": job_id, "state": "cancelling"}
