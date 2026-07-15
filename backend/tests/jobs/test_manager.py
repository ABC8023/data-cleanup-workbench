from __future__ import annotations

import asyncio

import pytest

from data_workbench.jobs.manager import JobContext, JobFailure, JobManager


@pytest.mark.asyncio
async def test_cancel_sets_event_and_terminal_state() -> None:
    manager = JobManager(max_heavy_jobs=1)

    async def work(context: JobContext) -> None:
        while True:
            context.raise_if_cancelled()
            await asyncio.sleep(0)

    job = manager.submit("profile", work)
    manager.cancel(job.id)
    assert job.task is not None
    await job.task

    assert manager.get(job.id).state == "cancelled"
    assert manager.get(job.id).error_code is None


@pytest.mark.asyncio
async def test_successful_job_publishes_ordered_events() -> None:
    manager = JobManager(max_heavy_jobs=1)

    async def work(context: JobContext) -> None:
        context.publish("inspect", 0, 2, "starting")
        context.publish("persist", 2, 2, "done")

    job = manager.submit("profile", work)
    events = [event async for event in manager.events(job.id)]

    assert manager.get(job.id).state == "succeeded"
    assert [(event.sequence, event.stage) for event in events] == [
        (1, "inspect"),
        (2, "persist"),
    ]


@pytest.mark.asyncio
async def test_failures_map_to_sanitized_error_codes() -> None:
    manager = JobManager(max_heavy_jobs=2)

    async def unexpected(context: JobContext) -> None:
        raise RuntimeError("secret local path C:/Users/me/data.csv")

    async def typed(context: JobContext) -> None:
        raise JobFailure("invalid_input")

    unexpected_job = manager.submit("profile", unexpected)
    typed_job = manager.submit("profile", typed)
    assert unexpected_job.task is not None and typed_job.task is not None
    await asyncio.gather(unexpected_job.task, typed_job.task)

    assert manager.get(unexpected_job.id).state == "failed"
    assert manager.get(unexpected_job.id).error_code == "job_failed"
    assert manager.get(typed_job.id).state == "failed"
    assert manager.get(typed_job.id).error_code == "invalid_input"


@pytest.mark.asyncio
async def test_heavy_jobs_run_one_at_a_time() -> None:
    manager = JobManager(max_heavy_jobs=1)
    release = asyncio.Event()
    order: list[str] = []

    async def slow(context: JobContext) -> None:
        order.append("slow-start")
        await release.wait()
        order.append("slow-end")

    async def fast(context: JobContext) -> None:
        order.append("fast")

    slow_job = manager.submit("profile", slow)
    fast_job = manager.submit("profile", fast)
    await asyncio.sleep(0.05)
    assert order == ["slow-start"]

    release.set()
    assert slow_job.task is not None and fast_job.task is not None
    await asyncio.gather(slow_job.task, fast_job.task)
    assert order == ["slow-start", "slow-end", "fast"]


@pytest.mark.asyncio
async def test_unknown_job_raises_key_error() -> None:
    manager = JobManager(max_heavy_jobs=1)

    with pytest.raises(KeyError):
        manager.get("missing")
    with pytest.raises(KeyError):
        manager.cancel("missing")
