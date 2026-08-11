"""Atomic immutable content-addressed analysis artifact store."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path, PurePath
from typing import TYPE_CHECKING

from lnt.analysis_store.errors import ArtifactConflictError
from lnt.analysis_store.identity import ArtifactInputs, NamedDigest
from lnt.analysis_store.manifest import MANIFEST_NAME, build_manifest, sha256_bytes, verify_artifact

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


class ArtifactStore:
    """Публикует immutable artifacts внутри каталога session/analyses."""

    def __init__(self, session_dir: Path) -> None:
        """Связывает store с одной session directory."""
        self._root: Path = session_dir / "analyses"

    def find(self, artifact_key: str) -> Path | None:
        """Возвращает только целый опубликованный artifact; partial игнорируются."""
        target = self._root / artifact_key
        if not target.is_dir():
            return None
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
        target = self._root / artifact_key
        if not target.exists():
            return None
        invalid = self._root / f"{artifact_key}.invalid-{uuid.uuid4().hex}"
        target.rename(invalid)
        return invalid

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
