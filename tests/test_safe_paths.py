"""GAP-2 regression: единый runtime-барьер путей (имена файлов и корень)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.errors import InputError
from lnt.manifest import manifest_to_json
from lnt.safe_paths import ensure_safe_filename, ensure_within_root, is_safe_filename
from lnt.session_store import load_session, write_session
from lnt.types import (
    ChannelMeta,
    ChannelRole,
    SessionManifest,
    SessionSource,
    SessionType,
)

if TYPE_CHECKING:
    from pathlib import Path


def _manifest(fname: str) -> SessionManifest:
    return SessionManifest(
        schema_version=1,
        session_id="gap2-sess",
        created_utc="2026-08-20T10:00:00Z",
        completed_utc="2026-08-20T10:00:01Z",
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=250_000.0,
        duration_s=64 / 250_000.0,
        sample_count=64,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        parameters={},
        ch1=ChannelMeta(
            filename=fname,
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="high_z",
            range_code=5,
            probe_multiplier=1.0,
        ),
        ch2=None,
        acquisition_telemetry=None,
        synthetic_truth=None,
    )


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("ch1.npy", True),
        ("ch2.npy", True),
        ("../ch1.npy", False),
        ("..\\ch1.npy", False),
        ("sub/dir.npy", False),
        ("sub\\dir.npy", False),
        ("C:\\temp\\ch1.npy", False),
        ("\\\\server\\share\\x.npy", False),
        ("stream:npy", False),
        ("CON.npy", False),
        ("NUL", False),
        ("ch1.", False),
        ("ch1 ", False),
        (".", False),
        ("..", False),
        ("", False),
    ],
)
def test_is_safe_filename_matrix(filename: str, expected: bool) -> None:
    assert is_safe_filename(filename) is expected


def test_ensure_safe_filename_raises_typed_error() -> None:
    with pytest.raises(InputError, match="небезопасно"):
        ensure_safe_filename("..\\escape.npy", label="ch1: имя файла")


def test_write_session_rejects_hostile_manifest_filename(tmp_path: Path) -> None:
    # Given: манифест с именем, выходящим за пределы каталога сессии.
    ch1 = np.zeros(64, dtype=np.float32)

    # When
    with pytest.raises(InputError, match="небезопасно"):
        write_session(
            session_dir=tmp_path / "victim",
            manifest=_manifest("..\\gap2-escaped-write.npy"),
            ch1=ch1,
            ch2=None,
        )

    # Then: файл не материализуется ни в корне, ни рядом.
    assert not (tmp_path / "gap2-escaped-write.npy").exists()
    assert not list(tmp_path.rglob("*.partial-*"))


def test_load_session_rejects_hostile_manifest_filename(tmp_path: Path) -> None:
    # Given: сессия на диске с манифестом, указывающим наружу.
    outside = tmp_path / "outside.npy"
    np.save(outside, np.zeros(64, dtype=np.float32))
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    (session_dir / "manifest.json").write_text(
        manifest_to_json(_manifest("..\\outside.npy")),
        encoding="utf-8",
    )

    # When / Then
    with pytest.raises(InputError, match="небезопасно"):
        load_session(session_dir)


def test_write_and_load_round_trip_with_safe_names(tmp_path: Path) -> None:
    # Легитимный поток не изменён: ch1.npy записывается и читается.
    ch1 = np.arange(64, dtype=np.float32)
    session_dir = write_session(
        session_dir=tmp_path / "good",
        manifest=_manifest("ch1.npy"),
        ch1=ch1,
        ch2=None,
    )
    loaded = load_session(session_dir)
    assert np.array_equal(np.asarray(loaded.ch1), ch1)


def test_ensure_within_root_blocks_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    inside = ensure_within_root(root, root / "session-a")
    assert inside == (root / "session-a").resolve()
    with pytest.raises(InputError, match="выходит за пределы корня"):
        ensure_within_root(root, tmp_path / "elsewhere")
