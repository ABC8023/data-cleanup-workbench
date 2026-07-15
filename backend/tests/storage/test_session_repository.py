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
async def test_stage_publishes_manifest_atomically(tmp_path):
    repo = SessionRepository(tmp_path, max_file_bytes=16)

    async def chunks():
        yield b"data"

    manifest = await repo.stage("sample.csv", 4, chunks())

    manifest_path = manifest.source_path.parent / "session.json"
    assert manifest_path.is_file()
    assert not manifest_path.with_suffix(".json.tmp").exists()


@pytest.mark.asyncio
async def test_stage_durably_seals_source_before_publishing_manifest(
    tmp_path,
    monkeypatch,
):
    repo = SessionRepository(tmp_path, max_file_bytes=16)
    events = []
    directory_descriptor = 999
    real_chmod = os.chmod
    real_fsync = os.fsync
    real_replace = os.replace
    replaced = False

    def record_fsync(descriptor):
        nonlocal replaced
        directory = next(tmp_path.iterdir())
        temporary_manifest_path = directory / "session.json.tmp"
        source_path = directory / "source.bin"
        if descriptor == directory_descriptor:
            assert replaced
            events.append("fsync:directory")
        elif temporary_manifest_path.exists():
            manifest_text = temporary_manifest_path.read_text(encoding="utf-8")
            assert '"filename": "sample.csv"' in manifest_text
            events.append("fsync:session.json.tmp")
            real_fsync(descriptor)
        elif source_path.stat().st_mode & 0o222 == 0:
            events.append("fsync:source.bin:metadata")
            real_fsync(descriptor)
        else:
            assert (directory / "source.bin").read_bytes() == b"data"
            events.append("fsync:source.bin:data")
            real_fsync(descriptor)

    def record_chmod(path, mode):
        if mode != 0o444:
            return real_chmod(path, mode)
        assert events == ["fsync:source.bin:data"]
        real_chmod(path, mode)
        assert path.stat().st_mode & 0o222 == 0
        events.append("chmod:source.bin")

    def record_replace(source, destination):
        nonlocal replaced
        assert events == [
            "fsync:source.bin:data",
            "chmod:source.bin",
            "fsync:source.bin:metadata",
            "fsync:session.json.tmp",
        ]
        replaced = True
        events.append("replace:session.json")
        real_replace(source, destination)

    monkeypatch.setattr(session_repository.os, "name", "posix")
    monkeypatch.setattr(os, "open", lambda *_: directory_descriptor)
    monkeypatch.setattr(
        os,
        "close",
        lambda descriptor: events.append("close:directory"),
    )
    monkeypatch.setattr(os, "fsync", record_fsync)
    monkeypatch.setattr(os, "chmod", record_chmod)
    monkeypatch.setattr(os, "replace", record_replace)

    async def chunks():
        yield b"data"

    await repo.stage("sample.csv", 4, chunks())

    assert events == [
        "fsync:source.bin:data",
        "chmod:source.bin",
        "fsync:source.bin:metadata",
        "fsync:session.json.tmp",
        "replace:session.json",
        "fsync:directory",
        "close:directory",
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
        if sync_count == 3:
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


def test_windows_manifest_promotion_uses_replace_and_write_through(tmp_path):
    calls = []

    def move_file_ex(source, destination, flags):
        calls.append((source, destination, flags))
        return 1

    source = tmp_path / "session.json.tmp"
    destination = tmp_path / "session.json"

    session_repository._replace_manifest_windows(
        source,
        destination,
        move_file_ex=move_file_ex,
        error_factory=lambda: OSError("unused"),
    )

    assert calls == [(str(source), str(destination), 0x1 | 0x8)]


def test_windows_manifest_promotion_propagates_move_failure(tmp_path):
    expected_error = OSError(5, "access denied")

    with pytest.raises(OSError, match="access denied") as captured:
        session_repository._replace_manifest_windows(
            tmp_path / "session.json.tmp",
            tmp_path / "session.json",
            move_file_ex=lambda *_: 0,
            error_factory=lambda: expected_error,
        )

    assert captured.value is expected_error


@pytest.mark.asyncio
async def test_stage_removes_session_when_windows_promotion_fails(
    tmp_path,
    monkeypatch,
):
    repo = SessionRepository(tmp_path, max_file_bytes=16)

    def fail_promotion(*_):
        raise OSError(5, "promotion failed")

    monkeypatch.setattr(
        session_repository,
        "_replace_manifest_windows",
        fail_promotion,
    )

    async def chunks():
        yield b"data"

    with pytest.raises(OSError, match="promotion failed"):
        await repo.stage("sample.csv", 4, chunks())

    assert list(tmp_path.iterdir()) == []
