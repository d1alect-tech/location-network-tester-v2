"""Безопасное нерекурсивное обнаружение и fingerprint каталогов."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Final

from lnt.catalog.reconcile_models import ScannedDirectory

_HASHED_NAMES: Final = frozenset(
    {"manifest.json", "context.json", "context.events.jsonl", "metrics.json"},
)
_RELEVANT_SUFFIXES: Final = frozenset({".npy", ".csv", ".json", ".jsonl"})


def _is_reparse(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _fingerprint(directory: Path, *, reparse_point: bool) -> tuple[str, str | None]:
    digest = hashlib.sha256()
    digest.update(b"reparse\0" if reparse_point else b"directory\0")
    if reparse_point:
        return digest.hexdigest(), None
    manifest_text: str | None = None
    try:
        entries = sorted(os.scandir(directory), key=lambda item: item.name)
    except OSError as error:
        digest.update(f"scan-error:{error.errno}".encode())
        return digest.hexdigest(), None
    for entry in entries:
        if Path(entry.name).suffix not in _RELEVANT_SUFFIXES and ".partial-" not in entry.name:
            continue
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError as error:
            digest.update(f"{entry.name}:stat-error:{error.errno}\0".encode())
            continue
        digest.update(f"{entry.name}\0{metadata.st_size}\0{metadata.st_mtime_ns}\0".encode())
        if entry.name in _HASHED_NAMES and entry.is_file(follow_symlinks=False):
            try:
                content = Path(entry.path).read_bytes()
                digest.update(hashlib.sha256(content).digest())
                if entry.name == "manifest.json":
                    manifest_text = content.decode("utf-8")
            except UnicodeDecodeError:
                manifest_text = None
            except OSError as error:
                digest.update(f"read-error:{error.errno}".encode())
    return digest.hexdigest(), manifest_text


def scan_immediate_directories(root: Path) -> tuple[ScannedDirectory, ...]:
    """Сканирует только непосредственных детей, не следуя reparse points."""
    if not root.is_dir():
        return ()
    discovered: list[ScannedDirectory] = []
    with os.scandir(root) as entries:
        for entry in entries:
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            reparse = _is_reparse(metadata) or entry.is_symlink()
            if not reparse and not entry.is_dir(follow_symlinks=False):
                continue
            path = Path(entry.path).absolute()
            fingerprint, manifest_text = _fingerprint(path, reparse_point=reparse)
            discovered.append(
                ScannedDirectory(
                    path=path,
                    fingerprint=fingerprint,
                    reparse_point=reparse,
                    manifest_text=manifest_text,
                ),
            )
    return tuple(sorted(discovered, key=lambda item: str(item.path)))
