"""RBW-селектор, окна Welch и ENBW: истина от синтетических тонов.

Аналитическая основа (не зависит от движка):
* мощность тона A²/2 сохраняется интегрированием PSD при любом окне;
* ENBW Hann ровно 1.5 бина (замкнутая формула сумм окна);
* flat-top сконструирован под минимальный scalloping, боковые лепестки
  Hann/Blackman/Kaiser упорядочены известными константами затухания.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np
import pytest
from scipy import signal

from lnt.analysis_store.errors import RecipeError
from lnt.analysis_store.recipe import AnalysisRecipe
from lnt.analysis_store.settings import WelchSettings
from lnt.psd import FrequencyBand, PsdSettings, compute_welch
from lnt.spectrum import compute_band_spectrum
from tests.science.corpus import pure_tone
from tests.science.truth import verify_scalar

if TYPE_CHECKING:
    from lnt.context.json_codec import JsonValue

FS_HZ = 16_384.0
NPERSEG = 4_096
DF_HZ = FS_HZ / NPERSEG
TONE_HZ = 1_024.0
AMPLITUDE_V = 0.8
TONE_POWER_V2 = AMPLITUDE_V**2 / 2

WINDOWS = ("hann", "flattop", "kaiser", "blackman")


def _welch(window: str) -> WelchSettings:
    return WelchSettings(
        window=window,
        segment_samples=NPERSEG,
        overlap_fraction=0.5,
        detrend="constant",
        scaling="density",
        average="mean",
    )


def _settings(window: str) -> PsdSettings:
    return PsdSettings.from_recipe(
        sample_rate_hz=FS_HZ,
        welch=_welch(window),
        bands=(FrequencyBand(name="all", low_hz=0.0, high_hz=FS_HZ / 2),),
    )


def _tone(frequency_hz: float) -> np.ndarray:
    time = np.arange(16_384, dtype=np.float64) / FS_HZ
    return (AMPLITUDE_V * np.sin(2 * np.pi * frequency_hz * time)).astype(np.float32)


def _integrated_tone_power(window: str, frequency_hz: float) -> float:
    result = compute_welch(_tone(frequency_hz), settings=_settings(window))
    mask = (result.frequency_hz >= TONE_HZ - 100.0) & (result.frequency_hz <= TONE_HZ + 100.0)
    return float(np.sum(result.psd_v2_per_hz[mask]) * DF_HZ)


@pytest.mark.parametrize("window", WINDOWS)
def test_tone_power_is_window_independent(window: str) -> None:
    """Интеграл PSD вокруг тона равен A²/2 при любом окне (сохранение мощности)."""
    verify_scalar(
        _integrated_tone_power(window, TONE_HZ),
        expected=TONE_POWER_V2,
        absolute_tolerance=0.03 * TONE_POWER_V2,
        rationale=(
            "Плотностной скейл 1/(fs·Σw²) нормирует мощность окна; 3% покрывают "
            "конечную ширину интегрирования ±100 Гц и float32-округление."
        ),
    )


def test_hann_enbw_is_analytically_one_and_half_bins() -> None:
    """ENBW периодического Hann ровно 1.5 бина по замкнутой формуле сумм."""
    result = compute_welch(_tone(TONE_HZ), settings=_settings("hann"))
    verify_scalar(
        result.enbw_hz / DF_HZ,
        expected=1.5,
        absolute_tolerance=1e-9,
        rationale="Σw=N/2 и Σw²=3N/8 для периодического Hann дают N·Σw²/(Σw)²=1.5 точно.",
    )


@pytest.mark.parametrize("window", WINDOWS)
def test_reported_enbw_matches_independent_window_sums(window: str) -> None:
    """enbw_hz движка совпадает с независимым расчётом по окну SciPy."""
    scipy_name = {
        "hann": "hann",
        "flattop": "flattop",
        "kaiser": ("kaiser", 14.0),
        "blackman": "blackman",
    }[window]
    weights = np.asarray(signal.get_window(scipy_name, NPERSEG, fftbins=True), dtype=np.float64)
    expected_hz = FS_HZ * float(np.sum(weights * weights)) / float(np.sum(weights)) ** 2
    result = compute_welch(_tone(TONE_HZ), settings=_settings(window))
    verify_scalar(
        result.enbw_hz,
        expected=expected_hz,
        absolute_tolerance=1e-12 * expected_hz,
        rationale="ENBW определяется только весами окна; тест строит окно напрямую из SciPy.",
    )
    assert result.window == window


def _onbin_peak(window: str) -> float:
    result = compute_welch(_tone(TONE_HZ), settings=_settings(window))
    return float(np.max(result.psd_v2_per_hz))


def test_onbin_peak_height_follows_enbw_ordering() -> None:
    """Пик тон-на-бине тем ниже, чем шире ENBW: та же мощность размазана шире."""
    narrow_to_wide = ("hann", "blackman", "kaiser", "flattop")
    peaks = [_onbin_peak(window) for window in narrow_to_wide]
    for higher, lower in pairwise(peaks):
        assert lower < 0.95 * higher, f"{peaks}"


def _two_tone_dip(window: str) -> float:
    time = np.arange(16_384, dtype=np.float64) / FS_HZ
    samples = (
        AMPLITUDE_V * np.sin(2 * np.pi * TONE_HZ * time)
        + AMPLITUDE_V * np.sin(2 * np.pi * (TONE_HZ + 4 * DF_HZ) * time)
    ).astype(np.float32)
    result = compute_welch(samples, settings=_settings(window))
    freqs = result.frequency_hz
    peak_lo = result.psd_v2_per_hz[np.argmin(np.abs(freqs - TONE_HZ))]
    peak_hi = result.psd_v2_per_hz[np.argmin(np.abs(freqs - (TONE_HZ + 4 * DF_HZ)))]
    midpoint = result.psd_v2_per_hz[np.argmin(np.abs(freqs - (TONE_HZ + 2 * DF_HZ)))]
    return float(midpoint / min(float(peak_lo), float(peak_hi)))


def test_two_close_tones_resolved_by_hann_merged_by_flattop() -> None:
    """Два тона через 4 бина: Hann разделяет провалом, flat-top сливает в один холм."""
    assert _two_tone_dip("hann") < 0.1
    assert _two_tone_dip("flattop") > 1.0


def _peak_drop_db(window: str) -> float:
    on_bin = compute_welch(_tone(TONE_HZ), settings=_settings(window))
    half_bin = compute_welch(_tone(TONE_HZ + DF_HZ / 2), settings=_settings(window))
    return float(10.0 * np.log10(np.max(on_bin.psd_v2_per_hz) / np.max(half_bin.psd_v2_per_hz)))


def test_flattop_scalloping_is_smaller_than_hann() -> None:
    """Просадка пика при полубиновом сдвиге у flat-top меньше, чем у Hann."""
    assert _peak_drop_db("flattop") + 0.5 < _peak_drop_db("hann")


def test_default_path_is_hann_fifty_hertz() -> None:
    """Дефолтный тракт: окно Hann, RBW 50 Гц, ENBW 1.5 бина."""
    fixture = pure_tone()
    spectrum = compute_band_spectrum(fixture.samples, sample_rate_hz=fixture.sample_rate_hz)
    assert spectrum.window == "hann"
    verify_scalar(
        spectrum.resolution_hz,
        expected=16.0,
        absolute_tolerance=1e-9,
        rationale="fs=16384, RBW 50: пол nperseg=1024 даёт df=16 Гц.",
    )
    verify_scalar(
        spectrum.enbw_hz / spectrum.resolution_hz,
        expected=1.5,
        absolute_tolerance=1e-9,
        rationale="Дефолтное окно Hann: ENBW ровно 1.5 бина.",
    )


def test_rbw_selector_controls_resolution() -> None:
    """RBW 100 Гц при fs=102400 даёт nperseg=1024 и df ровно 100 Гц."""
    rate_hz = 102_400.0
    time = np.arange(102_400, dtype=np.float64) / rate_hz
    samples = (1.0 * np.sin(2 * np.pi * 10_000.0 * time)).astype(np.float32)
    spectrum = compute_band_spectrum(samples, sample_rate_hz=rate_hz, rbw_hz=100.0)
    verify_scalar(
        spectrum.resolution_hz,
        expected=100.0,
        absolute_tolerance=1e-9,
        rationale="fs/RBW=1024 — точная степень двойки, floor-выбор nperseg детерминирован.",
    )
    assert spectrum.window == "hann"
    verify_scalar(
        spectrum.enbw_hz,
        expected=150.0,
        absolute_tolerance=1e-6,
        rationale="Hann ENBW = 1.5 · df = 150 Гц.",
    )


def _recipe_mapping(*, dual_channel: bool, window: str) -> dict[str, JsonValue]:
    channels: JsonValue = ["ch1", "ch2"] if dual_channel else ["ch1"]
    return {
        "schema_version": 1,
        "mode": "standard",
        "channels": channels,
        "band_grid": {"low_hz": 3000.0, "high_hz": 200000.0, "grid_hz": 50.0},
        "welch": {
            "window": window,
            "segment_samples": 4096,
            "overlap_fraction": 0.5,
            "detrend": "constant",
            "scaling": "density",
            "average": "mean",
        },
        "spectrogram": {"enabled": True, "segment_samples": 1024, "overlap_fraction": 0.25},
        "events": {"enabled": True, "threshold_sigma": 5.0},
        "bands": {"edges_hz": [3000.0, 10000.0, 200000.0]},
        "correction": {"method": "none"},
        "uncertainty": {"enabled": False, "confidence_level": 0.95, "bootstrap_samples": 0},
    }


def _welch_group(mapping: dict[str, JsonValue]) -> dict[str, JsonValue]:
    welch = mapping["welch"]
    assert isinstance(welch, dict)
    return welch


def test_legacy_recipe_without_rbw_migrates_to_fifty_hann() -> None:
    """Старый рецепт без rbw_hz разбирается как RBW 50 Гц (текущее поведение)."""
    mapping = _recipe_mapping(dual_channel=True, window="hann_periodic")
    recipe = AnalysisRecipe.from_mapping(mapping)
    assert recipe.welch.rbw_hz == 50.0
    migrated = recipe.to_mapping()["welch"]
    assert isinstance(migrated, dict)
    assert migrated["rbw_hz"] == 50.0


def test_invalid_rbw_and_window_are_rejected() -> None:
    """RBW вне (10/30/50/100/300) и неизвестные окна отклоняются рецептом."""
    bad_rbw = _recipe_mapping(dual_channel=False, window="hann")
    _welch_group(bad_rbw)["rbw_hz"] = 77.0
    with pytest.raises(RecipeError):
        AnalysisRecipe.from_mapping(bad_rbw)
    bad_window = _recipe_mapping(dual_channel=False, window="hann")
    _welch_group(bad_window)["window"] = "boxcar"
    with pytest.raises(RecipeError):
        AnalysisRecipe.from_mapping(bad_window)
