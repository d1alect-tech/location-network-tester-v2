"""Ядро режима качества сети: частота, RMS, THD, гармоники, crest, огибающая."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.errors import AnalysisError
from lnt.line_quality import LineQualityMetrics, compute_line_quality, line_quality_to_payload

if TYPE_CHECKING:
    from numpy.typing import NDArray

RATE_HZ = 200_000.0
DURATION_S = 2.0


def _mains_wave(
    *,
    fundamental_hz: float = 50.2,
    amplitude_v: float = 15.0,
    harmonic_ratios: dict[int, float] | None = None,
    envelope_mod: float = 0.0,
    envelope_hz: float = 0.7,
) -> NDArray[np.float32]:
    t = np.arange(round(DURATION_S * RATE_HZ), dtype=np.float64) / RATE_HZ
    wave = np.sin(2.0 * np.pi * fundamental_hz * t)
    for order, ratio in (harmonic_ratios or {}).items():
        wave += ratio * np.sin(2.0 * np.pi * fundamental_hz * order * t + 0.4 * order)
    if envelope_mod > 0.0:
        wave *= 1.0 + envelope_mod * np.sin(2.0 * np.pi * envelope_hz * t)
    return (amplitude_v * wave).astype(np.float32)


def test_pure_sine_metrics_are_exact() -> None:
    # Given: a clean 50.2 Hz sine of known amplitude.
    ch1 = _mains_wave()

    # When: line quality is computed.
    metrics = compute_line_quality(ch1, sample_rate_hz=RATE_HZ)

    # Then: fundamental frequency, RMS, THD, and crest match the ground truth.
    assert metrics.fundamental_hz == pytest.approx(50.2, abs=0.05)
    assert metrics.fundamental_rms_v == pytest.approx(15.0 / math.sqrt(2.0), rel=0.01)
    assert metrics.total_rms_v == pytest.approx(15.0 / math.sqrt(2.0), rel=0.01)
    assert metrics.thd_ratio < 0.005
    assert metrics.crest_factor == pytest.approx(math.sqrt(2.0), rel=0.02)
    assert metrics.envelope_cv < 0.005
    assert metrics.cycles_analyzed >= 90


def test_known_harmonics_produce_expected_thd() -> None:
    # Given: H3 = 5% and H5 = 2% of the fundamental.
    ch1 = _mains_wave(harmonic_ratios={3: 0.05, 5: 0.02})

    # When: line quality is computed.
    metrics = compute_line_quality(ch1, sample_rate_hz=RATE_HZ)

    # Then: THD and per-harmonic ratios match the synthesis spec.
    expected_thd = math.sqrt(0.05**2 + 0.02**2)
    assert metrics.thd_ratio == pytest.approx(expected_thd, rel=0.05)
    by_order = {harmonic.order: harmonic for harmonic in metrics.harmonics}
    assert by_order[3].ratio == pytest.approx(0.05, rel=0.05)
    assert by_order[5].ratio == pytest.approx(0.02, rel=0.05)
    assert by_order[3].frequency_hz == pytest.approx(3 * 50.2, abs=0.5)


def test_amplitude_modulation_is_visible_in_envelope_cv() -> None:
    # Given: +-3% amplitude modulation at 0.7 Hz.
    ch1 = _mains_wave(envelope_mod=0.03)

    # When: line quality is computed.
    metrics = compute_line_quality(ch1, sample_rate_hz=RATE_HZ)

    # Then: envelope CV reflects the modulation depth (sine mod -> m/sqrt(2)).
    assert metrics.envelope_cv == pytest.approx(0.03 / math.sqrt(2.0), rel=0.2)


def test_weak_signal_is_rejected() -> None:
    # Given: white noise with no mains component.
    rng = np.random.default_rng(6022)
    ch1 = rng.normal(0.0, 0.01, size=round(DURATION_S * RATE_HZ)).astype(np.float32)

    # When/Then: the analysis refuses to fabricate line metrics.
    with pytest.raises(AnalysisError):
        compute_line_quality(ch1, sample_rate_hz=RATE_HZ)


def test_out_of_band_fundamental_is_rejected() -> None:
    # Given: a strong 400 Hz tone, far from mains.
    t = np.arange(round(DURATION_S * RATE_HZ), dtype=np.float64) / RATE_HZ
    ch1 = (10.0 * np.sin(2.0 * np.pi * 400.0 * t)).astype(np.float32)

    # When/Then: the fundamental search stays within the mains band.
    with pytest.raises(AnalysisError):
        compute_line_quality(ch1, sample_rate_hz=RATE_HZ)


def test_payload_shape_is_json_ready() -> None:
    # Given: metrics from a distorted mains wave.
    ch1 = _mains_wave(harmonic_ratios={3: 0.05})
    metrics = compute_line_quality(ch1, sample_rate_hz=RATE_HZ)

    # When: the metrics are converted for metrics.json.
    payload = line_quality_to_payload(metrics)

    # Then: every scalar field and the harmonics table are present.
    assert isinstance(metrics, LineQualityMetrics)
    assert set(payload) == {
        "fundamental_hz",
        "fundamental_rms_v",
        "total_rms_v",
        "thd_ratio",
        "crest_factor",
        "envelope_cv",
        "cycles_analyzed",
        "harmonics",
    }
    harmonics = payload["harmonics"]
    assert isinstance(harmonics, list)
    first = harmonics[0]
    assert isinstance(first, dict)
    assert set(first) == {"order", "frequency_hz", "amplitude_v", "ratio"}
    orders = [entry["order"] for entry in harmonics if isinstance(entry, dict)]
    assert orders[0] == 2
    assert 40 in orders


def test_crest_factor_ignores_single_sample_spike() -> None:
    """Одиночный сэмпл-выброс (мусор старта захвата) не должен раздувать crest."""
    wave = _mains_wave(amplitude_v=15.0)
    wave[4] = 40.0  # артефакт первых сэмплов USB-потока

    metrics = compute_line_quality(wave, sample_rate_hz=RATE_HZ)

    assert metrics.crest_factor == pytest.approx(math.sqrt(2.0), rel=0.03)
