"""Атомарная публикация сайдкара ripple.json поверх неизменяемой сессии.

Сайдкар — производная проекция последнего результата (не артефакт
``ArtifactStore``): заменяется целиком через уникальный частичный файл-сосед
с ``fsync`` и ``os.replace``; байты всех остальных файлов сессии не меняются.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, Final

from .artifact_inputs import sha256_file

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from lnt.session_store import LoadedSession

SIDECAR_FILENAME: Final = "ripple.json"


def session_input_hashes(session: LoadedSession) -> dict[str, str]:
    """Хэши входов сессии: manifest.json и файл канала ch1 из манифеста."""
    session_dir = session.session_dir
    return {
        "manifest_sha256": sha256_file(session_dir / "manifest.json"),
        "ch1_sha256": sha256_file(session_dir / session.manifest.ch1.filename),
    }


def write_ripple_sidecar(
    session_dir: Path,
    payload: Mapping[str, object],
) -> Path:
    """Атомарно заменяет только ``ripple.json``; конечный JSON или отказ.

    ``allow_nan=False`` — финальный страж: NaN/Infinity не попадут на диск.
    """
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    target = session_dir / SIDECAR_FILENAME
    temporary = session_dir / f".{SIDECAR_FILENAME}.partial-{uuid.uuid4().hex}"
    try:
        with temporary.open("xb") as stream:
            stream.write(text.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)  # noqa: PTH105 - явная атомарная граница, как в projection.py
    finally:
        temporary.unlink(missing_ok=True)
    return target
