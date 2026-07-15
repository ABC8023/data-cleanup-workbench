from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

EVENT_BUFFER_SIZE = 500
EVENT_POLL_SECONDS = 0.05
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})

Publish = Callable[[str, int, "int | None", str], None]


class JobEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int
    stage: str
    completed: int
    total: int | None
    message: str


class JobFailure(Exception):
    """Raised by job work to surface a sanitized error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class JobContext:
    def __init__(self, cancelled: asyncio.Event, publish: Publish) -> None:
        self.cancelled = cancelled
        self.publish = publish

    def raise_if_cancelled(self) -> None:
        if self.cancelled.is_set():
            raise asyncio.CancelledError


@dataclass
class JobRecord:
    id: str
    kind: str
    state: str = "queued"
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None
    error_code: str | None = None
    next_sequence: int = 1


class JobManager:
    def __init__(self, max_heavy_jobs: int) -> None:
        self._gate = asyncio.Semaphore(max_heavy_jobs)
        self._jobs: dict[str, JobRecord] = {}
        self._events: dict[str, deque[JobEvent]] = {}

    def submit(
        self,
        kind: str,
        work: Callable[[JobContext], Awaitable[None]],
    ) -> JobRecord:
        job = JobRecord(id=uuid4().hex, kind=kind)
        self._jobs[job.id] = job
        self._events[job.id] = deque(maxlen=EVENT_BUFFER_SIZE)
        job.task = asyncio.create_task(self._run(job, work))
        return job

    def cancel(self, job_id: str) -> None:
        self._jobs[job_id].cancelled.set()

    def get(self, job_id: str) -> JobRecord:
        return self._jobs[job_id]

    def _publish_for(self, job: JobRecord) -> Publish:
        def publish(
            stage: str, completed: int, total: int | None, message: str
        ) -> None:
            self._events[job.id].append(
                JobEvent(
                    sequence=job.next_sequence,
                    stage=stage,
                    completed=completed,
                    total=total,
                    message=message,
                )
            )
            job.next_sequence += 1

        return publish

    async def events(self, job_id: str) -> AsyncIterator[JobEvent]:
        next_sequence = 1
        while True:
            job = self.get(job_id)
            for event in tuple(self._events[job_id]):
                if event.sequence >= next_sequence:
                    next_sequence = event.sequence + 1
                    yield event
            if job.state in TERMINAL_STATES:
                return
            await asyncio.sleep(EVENT_POLL_SECONDS)

    async def _run(
        self,
        job: JobRecord,
        work: Callable[[JobContext], Awaitable[None]],
    ) -> None:
        job.state = "running"
        try:
            async with self._gate:
                await work(JobContext(job.cancelled, self._publish_for(job)))
            job.state = "succeeded"
        except asyncio.CancelledError:
            job.state = "cancelled"
        except JobFailure as failure:
            job.state = "failed"
            job.error_code = failure.code
        except Exception:
            job.state = "failed"
            job.error_code = "job_failed"
