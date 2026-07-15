import errno
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

from data_workbench.domain.session import SessionManifest

_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = {
    errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}


def _fsync_directory_posix(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno not in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
                raise
    finally:
        os.close(descriptor)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        # Python cannot open Windows directory handles with backup semantics,
        # so the standard library provides no portable directory-fsync path.
        return
    _fsync_directory_posix(directory)


def _remove_staging_directory(directory: Path, source_path: Path) -> None:
    try:
        os.chmod(source_path, 0o600)
    except FileNotFoundError:
        pass
    shutil.rmtree(directory)


class SessionRepository:
    def __init__(self, root: Path, max_file_bytes: int):
        self.root = root
        self.max_file_bytes = max_file_bytes

    async def stage(
        self,
        filename: str,
        size_bytes: int,
        chunks: AsyncIterator[bytes],
    ) -> SessionManifest:
        if size_bytes > self.max_file_bytes:
            raise ValueError("file exceeds 5 GB limit")
        session_id = uuid4().hex
        directory = self.root / session_id
        directory.mkdir(parents=True)
        source_path = directory / "source.bin"
        digest = hashlib.sha256()
        written = 0
        try:
            with source_path.open("xb") as target:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > size_bytes or written > self.max_file_bytes:
                        raise ValueError("stream exceeded declared size")
                    digest.update(chunk)
                    target.write(chunk)
                if written != size_bytes:
                    raise ValueError("stream size did not match Content-Length")
                target.flush()
                os.fsync(target.fileno())
            os.chmod(source_path, 0o444)
            manifest = SessionManifest(
                id=session_id,
                filename=filename,
                size_bytes=written,
                sha256=digest.hexdigest(),
                source_path=source_path,
            )
            manifest_path = directory / "session.json"
            temporary_manifest_path = manifest_path.with_suffix(".json.tmp")
            with temporary_manifest_path.open("x", encoding="utf-8") as target:
                target.write(
                    json.dumps(manifest.model_dump(mode="json"), indent=2)
                )
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_manifest_path, manifest_path)
            _fsync_directory(directory)
        except BaseException:
            _remove_staging_directory(directory, source_path)
            raise
        return manifest

    def get(self, session_id: str) -> SessionManifest | None:
        if re.fullmatch(r"[0-9a-f]{32}", session_id) is None:
            return None
        manifest_path = self.root / session_id / "session.json"
        try:
            return SessionManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return None
