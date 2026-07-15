import errno
import hashlib
import os

import pytest

from data_workbench.storage import session_repository
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


@pytest.mark.asyncio
async def test_stage_durably_seals_source_before_publishing_manifest(
    tmp_path,
    monkeypatch,
):
    repo = SessionRepository(tmp_path, max_file_bytes=16)
    events = []
    real_chmod = os.chmod
    real_fsync = os.fsync
    real_replace = os.replace

    def record_fsync(descriptor):
        directory = next(tmp_path.iterdir())
        if not events:
            assert (directory / "source.bin").read_bytes() == b"data"
            events.append("fsync:source.bin")
        else:
            manifest_text = (directory / "session.json.tmp").read_text(
                encoding="utf-8"
            )
            assert '"filename": "sample.csv"' in manifest_text
            events.append("fsync:session.json.tmp")
        real_fsync(descriptor)

    def record_chmod(path, mode):
        assert events == ["fsync:source.bin"]
        real_chmod(path, mode)
        assert path.stat().st_mode & 0o222 == 0
        events.append("chmod:source.bin")

    def record_replace(source, destination):
        assert events == [
            "fsync:source.bin",
            "chmod:source.bin",
            "fsync:session.json.tmp",
        ]
        events.append("replace:session.json")
        real_replace(source, destination)

    monkeypatch.setattr(os, "fsync", record_fsync)
    monkeypatch.setattr(os, "chmod", record_chmod)
    monkeypatch.setattr(os, "replace", record_replace)

    async def chunks():
        yield b"data"

    await repo.stage("sample.csv", 4, chunks())

    assert events == [
        "fsync:source.bin",
        "chmod:source.bin",
        "fsync:session.json.tmp",
        "replace:session.json",
    ]


@pytest.mark.asyncio
async def test_stage_removes_read_only_source_when_manifest_sync_fails(
    tmp_path,
    monkeypatch,
):
    repo = SessionRepository(tmp_path, max_file_bytes=16)
    real_fsync = os.fsync
    sync_count = 0

    def fail_manifest_sync(descriptor):
        nonlocal sync_count
        sync_count += 1
        if sync_count == 2:
            raise OSError("manifest fsync failed")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_manifest_sync)

    async def chunks():
        yield b"data"

    with pytest.raises(OSError, match="manifest fsync failed"):
        await repo.stage("sample.csv", 4, chunks())

    assert list(tmp_path.iterdir()) == []


def test_directory_sync_closes_descriptor_and_propagates_unexpected_errors(
    tmp_path,
    monkeypatch,
):
    closed = []
    monkeypatch.setattr(session_repository.os, "open", lambda *_: 99)
    monkeypatch.setattr(
        session_repository.os,
        "fsync",
        lambda _: (_ for _ in ()).throw(OSError(errno.EIO, "disk error")),
    )
    monkeypatch.setattr(session_repository.os, "close", closed.append)

    with pytest.raises(OSError, match="disk error"):
        session_repository._fsync_directory_posix(tmp_path)

    assert closed == [99]
