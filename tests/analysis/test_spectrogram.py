from __future__ import annotations

import threading
import tracemalloc
from typing import TYPE_CHECKING, override

import numpy as np
import pytest
from scipy import signal

from lnt.analysis_store.settings import SpectrogramSettings
from lnt.spectrogram import (
    CancellationToken,
    SpectrogramArtifactError,
    SpectrogramCancelledError,
    SpectrogramLimitError,
    StftSettings,
    ZoomLimits,
    ZoomRequest,
    build_overview,
    compute_exact_zoom,
    load_overview,
    save_overview,
)
from lnt.spectrogram.overview import linear_power_to_db

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray


class EventToken(CancellationToken):
    def __init__(self, event: threading.Event) -> None:
        self._event: threading.Event = event

    @override
    def cancelled(self) -> bool:
        return self._event.is_set()


def _save(path: Path, values: NDArray[np.float32]) -> Path:
    np.save(path, values, allow_pickle=False)
    return path.with_suffix(".npy")


def _settings(*, segment: int = 256, hop: int = 64) -> StftSettings:
    return StftSettings(
        version=1,
        window="hann",
        segment_samples=segment,
        hop_samples=hop,
        detrend="constant",
        scaling="psd",
    )


def _direct(
    values: NDArray[np.float32], fs: float, settings: StftSettings
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    stft = vars(signal)["stft"]
    frequency, time_s, complex_stft = stft(
        values,
        fs=fs,
        window=settings.window,
        nperseg=settings.segment_samples,
        noverlap=settings.segment_samples - settings.hop_samples,
        detrend=settings.detrend,
        boundary=None,
        padded=False,
        scaling=settings.scaling,
    )
    return frequency, time_s, np.abs(complex_stft) ** 2


def test_settings_from_analysis_recipe_preserves_versioned_geometry() -> None:
    recipe = SpectrogramSettings(enabled=True, segment_samples=200, overlap_fraction=0.75)

    settings = StftSettings.from_recipe(recipe)

    assert (settings.version, settings.window, settings.hop_samples) == (1, "hann", 50)
    assert (settings.detrend, settings.scaling) == ("constant", "psd")


@pytest.mark.parametrize(
    ("kind", "expected_time", "expected_hz"),
    [("tone", 0.5, 125.0), ("chirp", 0.75, 180.0), ("burst", 0.5, 125.0)],
)
def test_overview_localizes_fixture(
    tmp_path: Path, kind: str, expected_time: float, expected_hz: float
) -> None:
    fs = 1024.0
    time_s = np.arange(1024, dtype=np.float64) / fs
    match kind:
        case "tone":
            values = np.sin(2 * np.pi * expected_hz * time_s)
        case "chirp":
            values = signal.chirp(time_s, f0=40.0, f1=220.0, t1=1.0)
        case "burst":
            values = np.sin(2 * np.pi * expected_hz * time_s) * (np.abs(time_s - 0.5) < 0.1)
        case _:
            raise ValueError(f"Unknown kind: {kind}")
    overview = build_overview(
        _save(tmp_path / kind, values.astype(np.float32)),
        sample_rate_hz=fs,
        settings=_settings(),
        max_time_bins=32,
        max_frequency_bands=64,
        band_low_hz=20.0,
        band_high_hz=400.0,
    )

    if kind == "chirp":
        time_cell = int(np.argmin(np.abs(overview.time_s - expected_time)))
        peak = (int(np.nanargmax(overview.power_db[:, time_cell])), time_cell)
    else:
        peak = np.unravel_index(np.nanargmax(overview.power_db), overview.power_db.shape)

    assert abs(float(overview.frequency_hz[peak[0]]) - expected_hz) <= 35.0
    if kind != "tone":
        assert abs(float(overview.time_s[peak[1]]) - expected_time) <= 0.18


def test_overview_matches_direct_linear_aggregation_and_coverage(tmp_path: Path) -> None:
    rng = np.random.default_rng(22)
    values = rng.normal(size=2048).astype(np.float32)
    settings = _settings()
    overview = build_overview(
        _save(tmp_path / "noise", values),
        sample_rate_hz=1024.0,
        settings=settings,
        max_time_bins=7,
        max_frequency_bands=9,
        band_low_hz=16.0,
        band_high_hz=400.0,
    )
    frequency, _, direct = _direct(values, 1024.0, settings)
    expected_sum = np.zeros(overview.coverage.shape, dtype=np.float64)
    expected_count = np.zeros(overview.coverage.shape, dtype=np.uint32)
    time_cells = np.minimum(np.arange(direct.shape[1]) * 7 // direct.shape[1], 6)
    frequency_cells = np.searchsorted(overview.frequency_edges_hz, frequency, side="right") - 1
    for source_frequency, target_frequency in enumerate(frequency_cells):
        if 0 <= target_frequency < 9:
            np.add.at(expected_sum[target_frequency], time_cells, direct[source_frequency])
            np.add.at(expected_count[target_frequency], time_cells, 1)
    expected = np.full(expected_sum.shape, np.nan)
    np.divide(expected_sum, expected_count, out=expected, where=expected_count > 0)

    assert np.array_equal(overview.coverage, expected_count)
    assert np.allclose(overview.linear_power, expected, rtol=2e-5, equal_nan=True)


def test_db_is_computed_after_linear_mean() -> None:
    actual = linear_power_to_db(
        np.array([[1.0, 100.0]]), reference=1.0, floor_db=-200.0, ceiling_db=200.0
    ).mean()
    aggregate = linear_power_to_db(
        np.array([[50.5]]), reference=1.0, floor_db=-200.0, ceiling_db=200.0
    )[0, 0]

    assert aggregate == pytest.approx(10.0 * np.log10(50.5))
    assert aggregate != pytest.approx(actual)


def test_overview_caps_dimensions_and_uses_nan_for_unavailable(tmp_path: Path) -> None:
    values = np.ones(4096, dtype=np.float32)
    overview = build_overview(
        _save(tmp_path / "dc", values),
        sample_rate_hz=2048.0,
        settings=_settings(),
        max_time_bins=11,
        max_frequency_bands=13,
        band_low_hz=900.0,
        band_high_hz=1000.0,
    )

    assert overview.power_db.shape[0] <= 13
    assert overview.power_db.shape[1] <= 11
    assert overview.power_db.dtype == np.float32
    assert np.array_equal(np.isnan(overview.power_db), overview.coverage == 0)


def test_exact_zoom_matches_direct_scipy(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    values = rng.normal(size=4096).astype(np.float32)
    settings = _settings()
    zoom = compute_exact_zoom(
        _save(tmp_path / "zoom", values),
        sample_rate_hz=1024.0,
        settings=settings,
        request=ZoomRequest(start_s=0.0, end_s=4.0, low_hz=80.0, high_hz=240.0),
        limits=ZoomLimits(max_samples=5000, max_cells=100_000, max_wall_time_s=2.0),
    )
    frequency, time_s, direct = _direct(values, 1024.0, settings)
    mask = (frequency >= 80.0) & (frequency <= 240.0)

    assert np.allclose(zoom.time_s, time_s)
    assert np.allclose(zoom.frequency_hz, frequency[mask])
    assert np.allclose(zoom.linear_power, direct[mask], rtol=2e-5)


def test_oversized_zoom_fails_before_large_allocation(tmp_path: Path) -> None:
    path = _save(tmp_path / "large", np.zeros(100_000, dtype=np.float32))
    tracemalloc.start()
    with pytest.raises(SpectrogramLimitError) as caught:
        compute_exact_zoom(
            path,
            sample_rate_hz=10_000.0,
            settings=_settings(),
            request=ZoomRequest(start_s=0.0, end_s=10.0, low_hz=1.0, high_hz=4000.0),
            limits=ZoomLimits(max_samples=1000, max_cells=1000, max_wall_time_s=2.0),
        )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert caught.value.limit_kind == "samples"
    assert peak < 2_000_000


def test_artifact_round_trip_and_corruption(tmp_path: Path) -> None:
    overview = build_overview(
        _save(tmp_path / "source", np.zeros(1024, dtype=np.float32)),
        sample_rate_hz=1024.0,
        settings=_settings(),
        max_time_bins=8,
        max_frequency_bands=8,
        band_low_hz=20.0,
        band_high_hz=400.0,
    )
    artifact = tmp_path / "overview.npz"
    save_overview(artifact, overview)

    loaded = load_overview(artifact)
    assert np.array_equal(loaded.coverage, overview.coverage)
    artifact.write_bytes(b"not-an-npz")
    with pytest.raises(SpectrogramArtifactError):
        load_overview(artifact)


def test_cancelled_save_leaves_no_partial_artifact(tmp_path: Path) -> None:
    event = threading.Event()
    event.set()
    overview = build_overview(
        _save(tmp_path / "source", np.zeros(1024, dtype=np.float32)),
        sample_rate_hz=1024.0,
        settings=_settings(),
        max_time_bins=8,
        max_frequency_bands=8,
        band_low_hz=20.0,
        band_high_hz=400.0,
    )
    artifact = tmp_path / "cancelled.npz"

    with pytest.raises(SpectrogramCancelledError):
        save_overview(artifact, overview, cancellation=EventToken(event))

    assert not artifact.exists()
    assert list(tmp_path.glob("*.partial-*")) == []
