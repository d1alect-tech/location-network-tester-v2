"""Max-hold тайлы обзора спектрограммы рядом с mean (очередь B2).

Truth: стационарный тон на точном бине даёт покадрово identical
мощности — mean и max-hold тайлы совпадают; громкий всплеск в середине
записи виден в max-hold ячейке всплеска, а mean той же ячейки разбавлен
тихими кадрами. Max-hold сверен с независимым пересчётом через scipy STFT.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import numpy as np
import pytest
from scipy import signal

from lnt.spectrogram import StftSettings, build_overview, load_overview, save_overview

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from lnt.spectrogram.models import SpectrogramOverview

_FS = 1024.0
_TONE_HZ = 128.0  # точный бин rfftfreq(256): df = 4 Гц, бин 32


def _settings() -> StftSettings:
    return StftSettings(
        version=1,
        window="hann",
        segment_samples=256,
        hop_samples=64,
        detrend="constant",
        scaling="psd",
    )


def _save(path: Path, values: NDArray[np.float32]) -> Path:
    np.save(path, values, allow_pickle=False)
    return path.with_suffix(".npy")


def _tone(time_s: np.ndarray) -> np.ndarray:
    return np.sin(2.0 * np.pi * _TONE_HZ * time_s)


def _hold_linear(overview: SpectrogramOverview) -> NDArray[np.float64]:
    """Обзор из движка всегда несёт max-hold — сужаем Optional одним местом."""
    hold = overview.max_hold_linear
    assert hold is not None, "обзор из build_overview обязан нести max_hold_linear"
    return hold


def _hold_db(overview: SpectrogramOverview) -> NDArray[np.float32]:
    """То же для dB-вида max-hold."""
    hold = overview.max_hold_db
    assert hold is not None, "обзор из build_overview обязан нести max_hold_db"
    return hold


def _direct_max_hold(
    values: NDArray[np.float32], settings: StftSettings, edges: np.ndarray, time_bins: int
) -> np.ndarray:
    """Независимый пересчёт max-hold тайла: STFT → полосовые мощности → max по ячейке."""
    stft = vars(signal)["stft"]
    frequency, _, transformed = stft(
        values,
        fs=_FS,
        window=settings.window,
        nperseg=settings.segment_samples,
        noverlap=settings.segment_samples - settings.hop_samples,
        detrend=settings.detrend,
        boundary=None,
        padded=False,
        scaling=settings.scaling,
    )
    power = np.abs(transformed) ** 2
    frames = power.shape[1]
    cells = np.minimum(np.arange(frames) * time_bins // frames, time_bins - 1)
    band_of = np.searchsorted(edges, frequency, side="right") - 1
    peak = np.full((edges.size - 1, time_bins), np.nan, dtype=np.float64)
    for band in range(edges.size - 1):
        rows = np.flatnonzero(band_of == band)
        if rows.size == 0:
            continue
        frame_power = power[rows].mean(axis=0)
        for cell in range(time_bins):
            members = frame_power[cells == cell]
            if members.size:
                peak[band, cell] = float(np.max(members))
    return peak


def test_stationary_tone_mean_equals_max_hold(tmp_path: Path) -> None:
    # Given: стационарный тон, hop кратен периоду — все кадры identical
    time_s = np.arange(2048, dtype=np.float64) / _FS
    overview = build_overview(
        _save(tmp_path / "tone", _tone(time_s).astype(np.float32)),
        sample_rate_hz=_FS,
        settings=_settings(),
        max_time_bins=4,
        max_frequency_bands=8,
        band_low_hz=20.0,
        band_high_hz=400.0,
    )

    # Then: тайлы совпадают, NaN только вне покрытия
    np.testing.assert_allclose(
        _hold_linear(overview), overview.linear_power, rtol=1e-6, atol=1e-21, equal_nan=True
    )
    assert np.array_equal(np.isnan(_hold_db(overview)), overview.coverage == 0)


def test_transient_survives_only_in_max_hold_tile(tmp_path: Path) -> None:
    # Given: тихий тон + громкий всплеск x10 в середине записи
    time_s = np.arange(2048, dtype=np.float64) / _FS
    burst = (np.abs(time_s - 1.0) < 0.1).astype(np.float64)
    values = (_tone(time_s) * (1.0 + 9.0 * burst)).astype(np.float32)
    overview = build_overview(
        _save(tmp_path / "burst", values),
        sample_rate_hz=_FS,
        settings=_settings(),
        max_time_bins=4,
        max_frequency_bands=8,
        band_low_hz=20.0,
        band_high_hz=400.0,
    )

    # When
    band = int(np.argmax(_hold_linear(overview)[:, 2]))
    burst_cell = int(np.argmin(np.abs(overview.time_s - 1.0)))
    quiet_cell = int(np.argmin(np.abs(overview.time_s - 0.25)))

    # Then: ячейка всплеска держит пик, тихая ячейка mean == hold
    ratio = _hold_linear(overview)[band, burst_cell] / overview.linear_power[band, burst_cell]
    assert ratio > 2.0
    assert _hold_linear(overview)[band, quiet_cell] == pytest.approx(
        overview.linear_power[band, quiet_cell], rel=1e-9
    )
    assert np.all(_hold_linear(overview)[overview.coverage > 0] >= 0.0)


def test_max_hold_matches_direct_scipy_recomputation(tmp_path: Path) -> None:
    # Given: шум со всплеском в середине записи.
    rng = np.random.default_rng(11)
    time_s = np.arange(2048, dtype=np.float64) / _FS
    burst = (np.abs(time_s - 1.4) < 0.12).astype(np.float64)
    values = (rng.normal(size=2048) * (1.0 + 4.0 * burst)).astype(np.float32)
    settings = _settings()
    overview = build_overview(
        _save(tmp_path / "noise", values),
        sample_rate_hz=_FS,
        settings=settings,
        max_time_bins=7,
        max_frequency_bands=9,
        band_low_hz=16.0,
        band_high_hz=400.0,
    )

    # When
    expected = _direct_max_hold(values, settings, overview.frequency_edges_hz, 7)

    # Then
    np.testing.assert_allclose(_hold_linear(overview), expected, rtol=2e-5, equal_nan=True)


def test_hold_round_trip_and_legacy_artifact_without_hold(tmp_path: Path) -> None:
    # Given: обзор с hold
    time_s = np.arange(1024, dtype=np.float64) / _FS
    overview = build_overview(
        _save(tmp_path / "source", _tone(time_s).astype(np.float32)),
        sample_rate_hz=_FS,
        settings=_settings(),
        max_time_bins=8,
        max_frequency_bands=8,
        band_low_hz=20.0,
        band_high_hz=400.0,
    )
    artifact = tmp_path / "overview.npz"
    save_overview(artifact, overview)

    # When / Then: round-trip хранит hold
    loaded = load_overview(artifact)
    np.testing.assert_array_equal(_hold_db(loaded), _hold_db(overview))
    np.testing.assert_allclose(
        _hold_linear(loaded), _hold_linear(overview), rtol=1e-4, equal_nan=True
    )

    # Given: legacy-артефакт без hold-ключа
    legacy = tmp_path / "legacy.npz"
    metadata = {
        "schema": 1,
        "settings": {
            "version": 1,
            "window": "hann",
            "segment_samples": 256,
            "hop_samples": 64,
            "detrend": "constant",
            "scaling": "psd",
        },
        "db_reference": 1.0,
        "floor_db": -200.0,
        "ceiling_db": 100.0,
    }
    with legacy.open("wb") as stream:
        np.savez(
            stream,
            power_db=overview.power_db,
            coverage=overview.coverage,
            time_s=overview.time_s,
            frequency_hz=overview.frequency_hz,
            frequency_edges_hz=overview.frequency_edges_hz,
            metadata=np.asarray(json.dumps(metadata, sort_keys=True)),
        )

    # When / Then: старый файл читается, hold — сплошной NaN
    legacy_loaded = load_overview(legacy)
    np.testing.assert_array_equal(legacy_loaded.power_db, overview.power_db)
    assert np.all(np.isnan(_hold_db(legacy_loaded)))
    assert np.all(np.isnan(_hold_linear(legacy_loaded)))
