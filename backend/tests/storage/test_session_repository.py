import hashlib
import os

import pytest

from data_workbench.storage.session_repository import SessionRepository


@pytest.mark.asyncio
async def test_stage_streams_and_fingerprints_without_mutation(tmp_path):
    repo = SessionRepository(tmp_path, max_file_bytes=16)

    async def chunks():
        yield b"a,b\n"
        yield b"1,2\n"

    manifest = await repo.stage("sample.csv", 8, chunks())

    assert manifest.sha256 == hashlib.sha256(b"a,b\n1,2\n").hexdigest()
    assert manifest.source_path.read_bytes() == b"a,b\n1,2\n"
    assert manifest.source_path.stat().st_mode & 0o222 == 0


@pytest.mark.asyncio
async def test_stage_rejects_declared_size_above_limit_without_creating_session(
    tmp_path,
):
    repo = SessionRepository(tmp_path, max_file_bytes=4)

    async def chunks():
        yield b"12345"

    with pytest.raises(ValueError, match="file exceeds 5 GB limit"):
        await repo.stage("large.csv", 5, chunks())

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_stage_rejects_stream_larger_than_declared_without_partial_session(
    tmp_path,
):
    repo = SessionRepository(tmp_path, max_file_bytes=16)

    async def chunks():
        yield b"1234"
        yield b"5"

    with pytest.raises(ValueError, match="stream exceeded declared size"):
        await repo.stage("wrong-size.csv", 4, chunks())

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_stage_rejects_stream_smaller_than_declared_without_partial_session(
    tmp_path,
):
    repo = SessionRepository(tmp_path, max_file_bytes=16)

    async def chunks():
        yield b"123"

    with pytest.raises(
        ValueError,
        match="stream size did not match Content-Length",
    ):
        await repo.stage("wrong-size.csv", 4, chunks())

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_stage_publishes_manifest_with_atomic_replace(tmp_path, monkeypatch):
    repo = SessionRepository(tmp_path, max_file_bytes=16)
    replacements = []
    real_replace = os.replace

    def record_replace(source, destination):
        replacements.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", record_replace)

    async def chunks():
        yield b"data"

    manifest = await repo.stage("sample.csv", 4, chunks())

    manifest_path = manifest.source_path.parent / "session.json"
    assert replacements == [(manifest_path.with_suffix(".json.tmp"), manifest_path)]
    assert manifest_path.is_file()
    assert not manifest_path.with_suffix(".json.tmp").exists()
