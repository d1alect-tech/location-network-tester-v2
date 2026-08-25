"""Atomic projection of a selected default artifact into legacy files."""

from __future__ import annotations

import os
import uuid
from pathlib import Path  # noqa: TC003 - runtime projection paths
from typing import Final

LEGACY_FILES: Final = (
    "metrics.json",
    "spectrum.csv",
    "spectrum_input_referred.csv",
    "cm_dm_spectrum.csv",
)


def project_default(session_dir: Path, artifact_dir: Path) -> None:
    """Atomically replace each available legacy root output after publication."""
    for name in LEGACY_FILES:
        source = artifact_dir / name
        if not source.is_file():
            continue
        target = session_dir / name
        temporary = session_dir / f".{name}.partial-{uuid.uuid4().hex}"
        try:
            with temporary.open("xb") as stream:
                stream.write(source.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)  # noqa: PTH105 - explicit atomic seam
        finally:
            temporary.unlink(missing_ok=True)
