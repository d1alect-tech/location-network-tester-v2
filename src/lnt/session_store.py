"""Атомарное хранилище сессий: manifest.json + ch1.npy/ch2.npy (float32, вольты).

Запись идёт в сосед-каталог ``<имя>.partial-<uuid>`` с финальным rename:
на диске сессия либо целиком есть, либо её нет.
"""

import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.manifest import manifest_from_json, manifest_to_json
from lnt.types import SessionManifest

MANIFEST_FILENAME = "manifest.json"

Float32Array = NDArray[np.float32]


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadedSession:
    """Сессия, прочитанная с диска; каналы отображены в память (mmap, read-only)."""

    session_dir: Path
    manifest: SessionManifest
    ch1: Float32Array
    ch2: Float32Array | None


def write_session(  # noqa: PLR0913 - atomic lifecycle requires both publish boundary seams
    *,
    session_dir: Path,
    manifest: SessionManifest,
    ch1: Float32Array,
    ch2: Float32Array | None,
    before_publish: Callable[[Path], None] | None = None,
    after_publish: Callable[[Path], None] | None = None,
) -> Path:
    """Атомарно записывает сессию в новый каталог ``session_dir``.

    Возвращает ``session_dir``. Существующий каталог, неверный dtype/форма,
    расхождение с ``manifest.sample_count`` или несоответствие ``ch2``
    манифесту (однокональная сессия — без массива и без мета) -> ``InputError``.
    """
    _validate_array(ch1, expected_count=manifest.sample_count, label="ch1")
    if (manifest.ch2 is None) != (ch2 is None):
        raise InputError("ch2: массив и метаданные канала должны быть заданы вместе")
    if ch2 is not None:
        _validate_array(ch2, expected_count=manifest.sample_count, label="ch2")
    if session_dir.exists():
        raise InputError(f"каталог сессии уже существует: {session_dir}")
    partial = session_dir.with_name(f"{session_dir.name}.partial-{uuid.uuid4().hex[:8]}")
    partial.mkdir(parents=True)
    try:
        np.save(partial / manifest.ch1.filename, ch1)
        if manifest.ch2 is not None and ch2 is not None:
            np.save(partial / manifest.ch2.filename, ch2)
        manifest_path = partial / MANIFEST_FILENAME
        manifest_path.write_text(manifest_to_json(manifest), encoding="utf-8")
        if before_publish is not None:
            before_publish(partial)
        partial.rename(session_dir)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    if after_publish is not None:
        after_publish(session_dir)
    return session_dir


def load_session(session_dir: Path) -> LoadedSession:
    """Читает сессию: строгий разбор манифеста, каналы через ``np.load(mmap_mode="r")``."""
    manifest_path = session_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise InputError(f"не найден {MANIFEST_FILENAME} в {session_dir}")
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise InputError("manifest.json: файл должен быть в кодировке UTF-8") from error
    manifest = manifest_from_json(manifest_text)
    ch1 = _load_channel(session_dir / manifest.ch1.filename, manifest.sample_count, "ch1")
    ch2 = (
        _load_channel(session_dir / manifest.ch2.filename, manifest.sample_count, "ch2")
        if manifest.ch2 is not None
        else None
    )
    return LoadedSession(session_dir=session_dir, manifest=manifest, ch1=ch1, ch2=ch2)


def _validate_array(data: Float32Array, *, expected_count: int, label: str) -> None:
    if data.dtype != np.float32:
        raise InputError(f"{label}: ожидается dtype float32, получено {data.dtype}")
    if data.ndim != 1:
        raise InputError(f"{label}: ожидается одномерный массив, получено ndim={data.ndim}")
    if data.size != expected_count:
        raise InputError(
            f"{label}: длина {data.size} не совпадает с manifest.sample_count={expected_count}",
        )


def _load_channel(path: Path, expected_count: int, label: str) -> Float32Array:
    if not path.is_file():
        raise InputError(f"{label}: файл канала не найден: {path}")
    data = np.load(path, mmap_mode="r", allow_pickle=False)
    _validate_array(data, expected_count=expected_count, label=label)
    return cast("Float32Array", data)
