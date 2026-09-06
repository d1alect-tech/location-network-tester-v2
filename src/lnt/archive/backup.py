"""Полный backup корня: все каталоги с manifest.json в один архив."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import ArchiveError
from .export import ExportSelection, create_archive

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from .models import ArchiveManifest


def backup_output_name(now: datetime) -> str:
    """Возвращает имя вида ``backup-YYYYMMDD-HHMMSS.zip``."""
    return f"backup-{now:%Y%m%d-%H%M%S}.zip"


def backup_all_sessions(output: Path, root: Path) -> ArchiveManifest:
    """Архивирует каждый непосредственный подкаталог корня с manifest.json."""
    session_ids = tuple(
        sorted(
            child.name
            for child in root.iterdir()
            if child.is_dir() and (child / "manifest.json").is_file()
        )
    )
    if not session_ids:
        raise ArchiveError(f"корень не содержит сессий: {root}")
    return create_archive(
        output,
        ExportSelection(root=root, session_ids=session_ids, experiment_ids=()),
    )
