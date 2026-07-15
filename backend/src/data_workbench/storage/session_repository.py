import errno
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import AsyncIterator, Callable
from uuid import uuid4

from data_workbench.domain.finding import Finding
from data_workbench.domain.profile import DatasetProfile
from data_workbench.domain.session import SessionManifest

_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = {
    errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}
_MOVEFILE_REPLACE_EXISTING = 0x1
_MOVEFILE_WRITE_THROUGH = 0x8


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


def _replace_manifest_windows(
    source: Path,
    destination: Path,
    *,
    move_file_ex: Callable[[str, str, int], int] | None = None,
    error_factory: Callable[[], OSError] | None = None,
) -> None:
    if move_file_ex is None or error_factory is None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        move_file_ex = kernel32.MoveFileExW
        move_file_ex.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        move_file_ex.restype = wintypes.BOOL

        def windows_error() -> OSError:
            return ctypes.WinError(  # type: ignore[attr-defined]
                ctypes.get_last_error()
            )

        error_factory = windows_error

    flags = _MOVEFILE_REPLACE_EXISTING | _MOVEFILE_WRITE_THROUGH
    if not move_file_ex(str(source), str(destination), flags):
        raise error_factory()


def _publish_manifest(
    source: Path,
    destination: Path,
    directory: Path,
) -> None:
    if os.name == "nt":
        _replace_manifest_windows(source, destination)
        return
    os.replace(source, destination)
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
                os.fsync(target.fileno())
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
            _publish_manifest(temporary_manifest_path, manifest_path, directory)
        except BaseException:
            _remove_staging_directory(directory, source_path)
            raise
        return manifest

    def _write_durable(self, directory: Path, filename: str, payload: str) -> None:
        destination = directory / filename
        temporary = directory / f"{filename}.tmp"
        with temporary.open("w", encoding="utf-8") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        _publish_manifest(temporary, destination, directory)

    def save_profile(
        self,
        session_id: str,
        profile: DatasetProfile,
        findings: list[Finding],
    ) -> None:
        manifest = self.get(session_id)
        if manifest is None:
            raise KeyError(session_id)
        directory = self.root / session_id
        self._write_durable(directory, "profile.json", profile.model_dump_json(indent=2))
        self._write_durable(
            directory,
            "findings.json",
            json.dumps(
                [finding.model_dump(mode="json") for finding in findings], indent=2
            ),
        )
        updated = manifest.model_copy(update={"state": "profiled"})
        self._write_durable(
            directory,
            "session.json",
            json.dumps(updated.model_dump(mode="json"), indent=2),
        )

    def save_recipe(self, session_id: str, recipe_yaml: str) -> None:
        if self.get(session_id) is None:
            raise KeyError(session_id)
        self._write_durable(self.root / session_id, "recipe.yaml", recipe_yaml)

    def save_execution(self, session_id: str, result: dict[str, object]) -> None:
        if self.get(session_id) is None:
            raise KeyError(session_id)
        self._write_durable(
            self.root / session_id, "execution.json", json.dumps(result, indent=2)
        )

    def load_execution(self, session_id: str) -> dict[str, object] | None:
        if self.get(session_id) is None:
            return None
        try:
            raw = (self.root / session_id / "execution.json").read_text(
                encoding="utf-8"
            )
        except FileNotFoundError:
            return None
        loaded: dict[str, object] = json.loads(raw)
        return loaded

    def load_profile(self, session_id: str) -> dict[str, object] | None:
        if self.get(session_id) is None:
            return None
        directory = self.root / session_id
        try:
            profile = json.loads(
                (directory / "profile.json").read_text(encoding="utf-8")
            )
            findings = json.loads(
                (directory / "findings.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return None
        return {"profile": profile, "findings": findings}

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
