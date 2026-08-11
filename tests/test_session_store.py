from pathlib import Path
from typing import cast

import numpy as np
import pytest
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.session_store import load_session, write_session
from tests.test_manifest import make_manifest

SAMPLE_COUNT = 1024

Float32Array = NDArray[np.float32]


def make_arrays(rng: np.random.Generator) -> tuple[Float32Array, Float32Array]:
    ch1 = rng.standard_normal(SAMPLE_COUNT).astype(np.float32)
    ch2 = rng.standard_normal(SAMPLE_COUNT).astype(np.float32)
    return ch1, ch2


class TestWriteLoadRoundTrip:
    def test_round_trip_preserves_arrays_and_manifest(
        self,
        tmp_path: Path,
        rng: np.random.Generator,
    ) -> None:
        manifest = make_manifest(sample_count=SAMPLE_COUNT)
        ch1, ch2 = make_arrays(rng)
        target = tmp_path / "ses-0001"

        written = write_session(session_dir=target, manifest=manifest, ch1=ch1, ch2=ch2)
        loaded = load_session(written)

        assert written == target
        assert loaded.manifest == manifest
        np.testing.assert_array_equal(np.asarray(loaded.ch1), ch1)
        np.testing.assert_array_equal(np.asarray(loaded.ch2), ch2)
        assert loaded.ch1.dtype == np.float32
        assert loaded.ch2 is not None
        assert loaded.ch2.dtype == np.float32

    def test_loaded_arrays_are_memmapped(
        self,
        tmp_path: Path,
        rng: np.random.Generator,
    ) -> None:
        manifest = make_manifest(sample_count=SAMPLE_COUNT)
        ch1, ch2 = make_arrays(rng)
        target = tmp_path / "ses-0002"

        write_session(session_dir=target, manifest=manifest, ch1=ch1, ch2=ch2)
        loaded = load_session(target)

        assert isinstance(loaded.ch1, np.memmap)
        assert isinstance(loaded.ch2, np.memmap)


class TestWriteValidation:
    def test_existing_target_rejected(
        self,
        tmp_path: Path,
        rng: np.random.Generator,
    ) -> None:
        manifest = make_manifest(sample_count=SAMPLE_COUNT)
        ch1, ch2 = make_arrays(rng)
        target = tmp_path / "ses-0003"
        target.mkdir()
        (target / "sentinel.txt").write_text("не трогать", encoding="utf-8")

        with pytest.raises(InputError, match="существует"):
            write_session(session_dir=target, manifest=manifest, ch1=ch1, ch2=ch2)
        assert (target / "sentinel.txt").read_text(encoding="utf-8") == "не трогать"

    def test_sample_count_mismatch_rejected(
        self,
        tmp_path: Path,
        rng: np.random.Generator,
    ) -> None:
        manifest = make_manifest(sample_count=SAMPLE_COUNT * 2)
        ch1, ch2 = make_arrays(rng)

        with pytest.raises(InputError, match="sample_count"):
            write_session(
                session_dir=tmp_path / "ses-0004",
                manifest=manifest,
                ch1=ch1,
                ch2=ch2,
            )

    def test_wrong_dtype_rejected(
        self,
        tmp_path: Path,
        rng: np.random.Generator,
    ) -> None:
        manifest = make_manifest(sample_count=SAMPLE_COUNT)
        ch1 = cast("Float32Array", rng.standard_normal(SAMPLE_COUNT))
        ch2 = rng.standard_normal(SAMPLE_COUNT).astype(np.float32)

        with pytest.raises(InputError, match="float32"):
            write_session(
                session_dir=tmp_path / "ses-0005",
                manifest=manifest,
                ch1=ch1,
                ch2=ch2,
            )

    def test_write_failure_cleans_partial_dirs(
        self,
        tmp_path: Path,
        rng: np.random.Generator,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manifest = make_manifest(sample_count=SAMPLE_COUNT)
        ch1, ch2 = make_arrays(rng)
        target = tmp_path / "ses-0006"

        def boom(*_args: object, **_kwargs: object) -> None:
            message = "диск переполнен"
            raise OSError(message)

        monkeypatch.setattr(np, "save", boom)

        with pytest.raises(OSError, match="переполнен"):
            write_session(session_dir=target, manifest=manifest, ch1=ch1, ch2=ch2)

        assert not target.exists()
        assert list(tmp_path.iterdir()) == []


class TestLoadValidation:
    def test_missing_manifest_rejected(self, tmp_path: Path) -> None:
        empty = tmp_path / "ses-0007"
        empty.mkdir()

        with pytest.raises(InputError, match="manifest"):
            load_session(empty)

    def test_missing_channel_file_rejected(
        self,
        tmp_path: Path,
        rng: np.random.Generator,
    ) -> None:
        manifest = make_manifest(sample_count=SAMPLE_COUNT)
        ch1, ch2 = make_arrays(rng)
        target = tmp_path / "ses-0008"
        write_session(session_dir=target, manifest=manifest, ch1=ch1, ch2=ch2)
        assert manifest.ch2 is not None
        (target / manifest.ch2.filename).unlink()

        with pytest.raises(InputError, match="ch2"):
            load_session(target)

    def test_invalid_utf8_manifest_rejected(self, tmp_path: Path) -> None:
        target = tmp_path / "ses-invalid-utf8"
        target.mkdir()
        (target / "manifest.json").write_bytes(b"\xff")

        with pytest.raises(InputError) as captured:
            load_session(target)

        assert str(captured.value) == "manifest.json: файл должен быть в кодировке UTF-8"
        assert isinstance(captured.value.__cause__, UnicodeDecodeError)
