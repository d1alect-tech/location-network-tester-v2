"""T15: дисковое спулирование захвата — write_session_spooled + SpooledBlockCollector."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pytest
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.scope_io import (
    NEVER_CANCELLED,
    SpooledBlockCollector,
    _stream_capture,  # pyright: ignore[reportPrivateUsage]
)
from lnt.session_store import load_session, write_session, write_session_spooled
from tests.test_manifest import make_manifest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from lnt.types import AcquisitionTelemetry

SAMPLE_COUNT = 4_096

Float32Array = NDArray[np.float32]


def _chunked(array: Float32Array, sizes: list[int]) -> Iterator[Float32Array]:
    start = 0
    for size in sizes:
        yield array[start : start + size]
        start += size


def _full_arrays(rng: np.random.Generator) -> tuple[Float32Array, Float32Array]:
    ch1 = rng.standard_normal(SAMPLE_COUNT).astype(np.float32)
    ch2 = rng.standard_normal(SAMPLE_COUNT).astype(np.float32)
    return ch1, ch2


@dataclass(slots=True)
class _Shutdown:
    calls: list[str]

    def set(self) -> None:
        self.calls.append("shutdown")


@dataclass(slots=True)
class _FakeScope:
    """Мини-двойник драйвера: отдаёт блоки с различающимся содержимым."""

    blocks_before_complete: int = 1
    block_samples: int = 64
    is_device_firmware_present: bool = True
    calls: list[str] = field(default_factory=list)
    _callback: Callable[[object, object], None] | None = None
    _polls: int = 0

    def setup(self) -> None:
        self.calls.append("setup")

    def open_handle(self) -> bool:
        self.calls.append("open")
        return True

    def close_handle(self) -> None:
        self.calls.append("close")

    def flash_firmware(self) -> None:
        self.calls.append("flash")

    def set_interface(self, _index: int) -> None: ...

    def set_num_channels(self, _count: int) -> None: ...

    def set_sample_rate(self, _code: int) -> None: ...

    def set_ch1_voltage_range(self, _code: int) -> None: ...

    def set_ch2_voltage_range(self, _code: int) -> None: ...

    def read_async(
        self,
        callback: Callable[[object, object], None],
        data_size: int,
        outstanding_transfers: int,
        *,
        raw: bool,
    ) -> _Shutdown:
        assert raw
        del data_size, outstanding_transfers
        self.calls.append("read")
        self._callback = callback
        return _Shutdown(self.calls)

    def start_capture(self) -> None:
        self.calls.append("start")

    def stop_capture(self) -> None:
        self.calls.append("stop")

    def poll(self, timeout_ms: int) -> None:
        del timeout_ms
        self._polls += 1
        if self._polls >= self.blocks_before_complete:
            assert self._callback is not None
            raw = bytearray((np.arange(self.block_samples) * self._polls) % 256)
            self._callback(raw, raw[::-1])


def _stream(
    scope: _FakeScope, sink: SpooledBlockCollector | None
) -> tuple[NDArray[np.uint8], NDArray[np.uint8], AcquisitionTelemetry]:
    result = _stream_capture(
        scope,
        rate_code=1,
        ch1_range_code=1,
        sample_rate_hz=1_000_000.0,
        requested_samples=128,
        cancellation_token=NEVER_CANCELLED,
        sink=sink,
    )
    assert isinstance(result, tuple)
    ch1, ch2, telemetry = result
    return ch1, ch2, telemetry


def test_write_session_spooled_round_trip_matches_write_session(
    tmp_path: Path,
    rng: np.random.Generator,
) -> None:
    manifest = make_manifest(sample_count=SAMPLE_COUNT)
    ch1, ch2 = _full_arrays(rng)
    reference = tmp_path / "ses-ref"
    target = tmp_path / "ses-spooled"

    written_ref = write_session(session_dir=reference, manifest=manifest, ch1=ch1, ch2=ch2)
    written_spooled = write_session_spooled(
        session_dir=target,
        manifest=manifest,
        ch1_chunks=_chunked(ch1, [1_000, 1_000, 1_000, 1_096]),
        ch2_chunks=_chunked(ch2, [2_048, 2_048]),
    )
    loaded_ref = load_session(written_ref)
    loaded_spooled = load_session(written_spooled)

    assert written_spooled == target
    assert loaded_spooled.manifest == loaded_ref.manifest == manifest
    np.testing.assert_array_equal(np.asarray(loaded_spooled.ch1), np.asarray(loaded_ref.ch1))
    np.testing.assert_array_equal(np.asarray(loaded_spooled.ch2), np.asarray(loaded_ref.ch2))
    assert loaded_spooled.ch1.dtype == np.float32
    assert loaded_spooled.ch2 is not None
    assert loaded_spooled.ch2.dtype == np.float32


def test_write_session_spooled_length_mismatch_cleans_partial(tmp_path: Path) -> None:
    manifest = make_manifest(sample_count=SAMPLE_COUNT)
    short = np.zeros(3_000, dtype=np.float32)
    target = tmp_path / "ses-short"

    with pytest.raises(InputError, match="sample_count"):
        write_session_spooled(
            session_dir=target,
            manifest=manifest,
            ch1_chunks=_chunked(short, [1_500, 1_500]),
            ch2_chunks=None if manifest.ch2 is None else _chunked(short, [3_000]),
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_session_spooled_midstream_exception_cleans_partial(
    tmp_path: Path,
    rng: np.random.Generator,
) -> None:
    manifest = make_manifest(sample_count=SAMPLE_COUNT)
    ch1, ch2 = _full_arrays(rng)

    def broken_stream() -> Iterator[Float32Array]:
        yield ch1[:2_000]
        message = "шина данных отвалилась"
        raise RuntimeError(message)

    target = tmp_path / "ses-broken"

    with pytest.raises(RuntimeError, match="отвалилась"):
        write_session_spooled(
            session_dir=target,
            manifest=manifest,
            ch1_chunks=broken_stream(),
            ch2_chunks=_chunked(ch2, [SAMPLE_COUNT]),
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_spooled_collector_preserves_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = itertools.cycle([100.0, 100.5, 101.0])
    monkeypatch.setattr("lnt.scope_io.time.monotonic", lambda: next(clock))

    legacy_scope = _FakeScope(blocks_before_complete=2)
    _ch1_legacy, _ch2_legacy, legacy_telemetry = _stream(legacy_scope, sink=None)

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    spooled_scope = _FakeScope(blocks_before_complete=2)
    sink = SpooledBlockCollector(scratch)
    _ch1_spooled, _ch2_spooled, spooled_telemetry = _stream(spooled_scope, sink=sink)

    assert spooled_telemetry.requested_samples == legacy_telemetry.requested_samples
    assert spooled_telemetry.captured_samples == legacy_telemetry.captured_samples
    assert spooled_telemetry.callback_count == legacy_telemetry.callback_count
    assert spooled_telemetry.block_lengths == legacy_telemetry.block_lengths
    assert spooled_telemetry.callback_gaps_s == legacy_telemetry.callback_gaps_s
    assert spooled_telemetry.short_block_count == legacy_telemetry.short_block_count
    assert (
        spooled_telemetry.ch1_clip_low_count,
        spooled_telemetry.ch1_clip_high_count,
        spooled_telemetry.ch2_clip_low_count,
        spooled_telemetry.ch2_clip_high_count,
    ) == (
        legacy_telemetry.ch1_clip_low_count,
        legacy_telemetry.ch1_clip_high_count,
        legacy_telemetry.ch2_clip_low_count,
        legacy_telemetry.ch2_clip_high_count,
    )


def test_spooled_capture_equivalence_small_record(tmp_path: Path) -> None:
    legacy_scope = _FakeScope(blocks_before_complete=3)
    ch1_legacy, ch2_legacy, _telemetry = _stream(legacy_scope, sink=None)

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    sink = SpooledBlockCollector(scratch)
    spooled_scope = _FakeScope(blocks_before_complete=3)
    ch1_spooled, ch2_spooled, _telemetry = _stream(spooled_scope, sink=sink)

    np.testing.assert_array_equal(ch1_spooled, ch1_legacy)
    np.testing.assert_array_equal(ch2_spooled, ch2_legacy)
    capture = sink.finish()
    np.testing.assert_array_equal(
        np.concatenate(list(capture.iter_chunks("ch1")))[:128], ch1_legacy
    )
    np.testing.assert_array_equal(
        np.concatenate(list(capture.iter_chunks("ch2")))[:128], ch2_legacy
    )
