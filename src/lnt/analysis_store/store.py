"""Atomic immutable content-addressed analysis artifact store."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path, PurePath
from typing import TYPE_CHECKING

from lnt.analysis_store.errors import ArtifactConflictError, ArtifactCorruptError
from lnt.analysis_store.identity import SHA256_LENGTH, ArtifactInputs, NamedDigest
from lnt.analysis_store.manifest import MANIFEST_NAME, build_manifest, sha256_bytes, verify_artifact
from lnt.safe_paths import ensure_within_root, is_linked_path

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


class ArtifactStore:
    """Публикует immutable artifacts внутри каталога session/analyses."""

    def __init__(self, session_dir: Path) -> None:
        """Связывает store с одной session directory."""
        self._root: Path = session_dir / "analyses"

    def find(self, artifact_key: str) -> Path | None:
        """Возвращает только целый опубликованный artifact; partial игнорируются."""
        self._validate_key(artifact_key)
        self._validate_root()
        target = self._root / artifact_key
        if is_linked_path(target):
            raise ArtifactCorruptError(target, "linked_artifact")
        if not target.is_dir():
            return None
        ensure_within_root(self._root, target)
        verify_artifact(target, artifact_key)
        return target

    def publish(
        self,
        inputs: ArtifactInputs,
        outputs: Mapping[str, bytes],
        *,
        before_publish: Callable[[Path], None] | None = None,
    ) -> Path:
        """Пишет partial и атомарно публикует, никогда не перезаписывая target.

        Одинаковые байты гарантируются только в той же locked среде; метод не
        утверждает межплатформенную побитовую идентичность.
        """
        self._validate_key(inputs.artifact_key)
        self._validate_root()
        target = self._root / inputs.artifact_key
        if target.exists():
            verify_artifact(target, inputs.artifact_key)
            return target
        self._validate_outputs(outputs)
        self._root.mkdir(parents=True, exist_ok=True)
        partial = self._root / f"{inputs.artifact_key}.partial-{uuid.uuid4().hex}"
        partial.mkdir()
        try:
            output_digests = tuple(
                NamedDigest(name=name, digest=sha256_bytes(content))
                for name, content in sorted(outputs.items())
            )
            for name, content in sorted(outputs.items()):
                self._write_fsynced(partial / name, content)
            self._write_fsynced(partial / MANIFEST_NAME, build_manifest(inputs, output_digests))
            if before_publish is not None:
                before_publish(partial)
            verify_artifact(partial, inputs.artifact_key)
            try:
                partial.rename(target)
            except FileExistsError:
                if not target.is_dir():
                    raise ArtifactConflictError(target) from None
                verify_artifact(target, inputs.artifact_key)
            return target
        finally:
            shutil.rmtree(partial, ignore_errors=True)

    def invalidate(self, artifact_key: str) -> Path | None:
        """Явно перемещает corrupt artifact из publish namespace без удаления."""
        self._validate_key(artifact_key)
        target = self._root / artifact_key
        if is_linked_path(self._root) or is_linked_path(target):
            return None
        if not target.exists():
            return None
        ensure_within_root(self._root, target)
        invalid = self._root / f"{artifact_key}.invalid-{uuid.uuid4().hex}"
        target.rename(invalid)
        return invalid

    def _validate_root(self) -> None:
        if is_linked_path(self._root) or is_linked_path(self._root.parent):
            raise ArtifactCorruptError(self._root, "linked_analyses")

    @staticmethod
    def _validate_key(artifact_key: str) -> None:
        if len(artifact_key) != SHA256_LENGTH or any(
            char not in "0123456789abcdef" for char in artifact_key
        ):
            raise ValueError("artifact_key должен быть lowercase SHA-256")

    @staticmethod
    def _validate_outputs(outputs: Mapping[str, bytes]) -> None:
        if not outputs:
            raise ValueError("artifact должен содержать хотя бы один output")
        for name in outputs:
            path = PurePath(name)
            if path.name != name or name == MANIFEST_NAME:
                raise ValueError(f"недопустимое имя output: {name!r}")

    @staticmethod
    def _write_fsynced(path: Path, content: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
