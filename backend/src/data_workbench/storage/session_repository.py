import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

from data_workbench.domain.session import SessionManifest


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
        except BaseException:
            shutil.rmtree(directory)
            raise
        manifest = SessionManifest(
            id=session_id,
            filename=filename,
            size_bytes=written,
            sha256=digest.hexdigest(),
            source_path=source_path,
        )
        manifest_path = directory / "session.json"
        temporary_manifest_path = manifest_path.with_suffix(".json.tmp")
        try:
            temporary_manifest_path.write_text(
                json.dumps(manifest.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_manifest_path, manifest_path)
            os.chmod(source_path, 0o444)
        except BaseException:
            shutil.rmtree(directory)
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
