"""Ограниченная память анализа иголок (T17): те же числа, крошечный RAM.

Красные тесты пишены ДО рефакторинга. Эталоны «старого алгоритма»
переимплементированы инлайн с HEAD 6474d39 (цельноматричный ресемплинг,
один большой бутстрэп-тираж); золотые значения зафиксированы в
``.omo/start-work/evidence/b2-t17/golden.json`` до правок продакшена.
"""

import json
from pathlib import Path
from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray
from scipy import signal

from lnt import needles as nd
from lnt._needle_memory import (
    PHASE_BINS,
    bootstrap_quantiles,
    gather_interp,
    resample_mean_cycle,
    residual_async_power,
)
from lnt.signals import generate

Float64Array = NDArray[np.float64]

FS: Final = 100_000.0
FIXTURE_DURATION_S: Final = 3.0
FIXTURE_RNG_SEED: Final = 17
COMPUTE_SEED: Final = 42
EVIDENCE_DIR: Final = (
    Path(__file__).resolve().parents[1] / ".omo" / "start-work" / "evidence" / "b2-t17"
)


# ---------------------------------------------------------------------------
# Инлайн-эталон старого алгоритма (HEAD 6474d39, до ограничений памяти).
# ---------------------------------------------------------------------------


def _legacy_bootstrap(peaks: Float64Array, *, seed: int) -> nd.NeedleMetricIntervalPair | None:
    count = int(peaks.size)
    if count < nd.MIN_UNCERTAINTY_N:
        return None
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, count, size=(nd.BOOTSTRAP_SAMPLES, count))
    means = np.mean(peaks[indices], axis=1)
    sigmas = np.std(peaks[indices], axis=1, ddof=1)
    mean_low, mean_high = np.quantile(means, (0.025, 0.975))
    ratio_low, ratio_high = np.quantile(sigmas / np.maximum(means, nd.POWER_EPS), (0.025, 0.975))
    return nd.NeedleMetricIntervalPair(
        method=nd.INTERVAL_METHOD,
        confidence_level=nd.CONFIDENCE_LEVEL,
        needle_mean_v=nd.NeedleMetricInterval(low=float(mean_low), high=float(mean_high)),
        needle_sigma_ratio=nd.NeedleMetricInterval(low=float(ratio_low), high=float(ratio_high)),
    )


def _legacy_filtered(samples: NDArray[np.float32], cutoff_hz: float, kind: str) -> Float64Array:
    sos = signal.butter(nd.FILTER_ORDER, cutoff_hz, btype=kind, fs=FS, output="sos")
    return np.asarray(signal.sosfiltfilt(sos, samples.astype(np.float64)), dtype=np.float64)


def _legacy_rising_crossings(lf: Float64Array) -> Float64Array:
    below = lf[:-1] <= 0.0
    above = lf[1:] > 0.0
    idx = np.nonzero(below & above)[0]
    fractions = -lf[idx] / (lf[idx + 1] - lf[idx])
    return idx.astype(np.float64) + fractions


def _legacy_window_maxima(
    samples: Float64Array,
    positions: Float64Array,
    *,
    absolute: bool,
) -> Float64Array:
    maxima = np.empty(positions.size - 1, dtype=np.float64)
    for cycle_index in range(positions.size - 1):
        low = int(np.floor(positions[cycle_index]))
        high = min(samples.size, int(np.ceil(positions[cycle_index + 1])) + 1)
        window = np.abs(samples[low:high]) if absolute else samples[low:high]
        maxima[cycle_index] = float(np.max(window))
    return maxima


def _legacy_resampled_cycles(hf: Float64Array, positions: Float64Array) -> Float64Array:
    cycle_count = positions.size - 1
    starts = positions[:-1]
    lengths = np.diff(positions)
    phase_grid = np.arange(PHASE_BINS, dtype=np.float64) / PHASE_BINS
    sample_points = starts[:, np.newaxis] + lengths[:, np.newaxis] * phase_grid[np.newaxis, :]
    flat = np.interp(sample_points.ravel(), np.arange(hf.size, dtype=np.float64), hf)
    return flat.reshape(cycle_count, PHASE_BINS)


def _legacy_dual_metrics(
    ch1: NDArray[np.float32],
    ch2: NDArray[np.float32],
    *,
    seed: int,
) -> nd.NeedleMetrics:
    lf = ch2.astype(np.float64)
    rms = float(np.sqrt(np.mean(np.square(lf))))
    assert rms >= nd.MIN_LF_RMS_V
    positions = _legacy_rising_crossings(_legacy_filtered(ch2, nd.LF_LOWPASS_HZ, "lowpass"))
    line_frequency = FS / float(np.mean(np.diff(positions)))
    assert nd.MIN_LINE_HZ <= line_frequency <= nd.MAX_LINE_HZ
    cycle_count = positions.size - 1
    assert cycle_count >= nd.MIN_CYCLES
    hf_clean = _legacy_filtered(ch1, nd.HF_HIGHPASS_HZ, "highpass")
    cycles = _legacy_resampled_cycles(hf_clean, positions)
    mean_cycle = cycles.mean(axis=0)
    residual = cycles - mean_cycle
    sync_power = float(np.mean(np.square(mean_cycle)))
    async_power = float(np.mean(np.square(residual)))
    dominant_fraction = float(np.argmax(np.abs(mean_cycle))) / PHASE_BINS
    peaks = _legacy_peak_windows(hf_clean, positions, dominant_fraction)
    needle_mean = float(np.mean(peaks))
    needle_sigma = float(np.std(peaks, ddof=1))
    lf_peaks = _legacy_window_maxima(lf, positions, absolute=False)
    return nd.NeedleMetrics(
        sync_source=nd.SyncSource.CH2,
        cycles_analyzed=cycle_count,
        line_frequency_hz=line_frequency,
        needle_mean_v=needle_mean,
        needle_sigma_ratio=needle_sigma / max(needle_mean, nd.POWER_EPS),
        sync_power_v2=sync_power,
        async_power_v2=async_power,
        async_sync_ratio=async_power / max(sync_power, nd.POWER_EPS),
        lf_envelope_cv=float(np.std(lf_peaks, ddof=1))
        / max(float(np.mean(lf_peaks)), nd.POWER_EPS),
        uncertainty=_legacy_bootstrap(peaks, seed=seed),
    )


def _legacy_peak_windows(
    hf: Float64Array,
    positions: Float64Array,
    dominant_fraction: float,
) -> Float64Array:
    peaks = np.empty(positions.size - 1, dtype=np.float64)
    for cycle_index in range(positions.size - 1):
        start = positions[cycle_index]
        period = positions[cycle_index + 1] - start
        window_low = start + (dominant_fraction - nd.PEAK_WINDOW_FRACTION) * period
        window_high = start + (dominant_fraction + nd.PEAK_WINDOW_FRACTION) * period
        low = max(0, int(np.floor(window_low)))
        high = min(hf.size, int(np.ceil(window_high)) + 1)
        peaks[cycle_index] = float(np.max(np.abs(hf[low:high])))
    return peaks


def _legacy_single_metrics(ch1: NDArray[np.float32], *, seed: int) -> nd.NeedleMetrics:
    hf = ch1.astype(np.float64)
    samples_per_cycle = FS / 50.0
    cycle_count = int(hf.size / samples_per_cycle)
    assert cycle_count >= nd.MIN_CYCLES
    hf_clean = _legacy_filtered(ch1, nd.HF_HIGHPASS_HZ, "highpass")
    positions = np.arange(cycle_count + 1, dtype=np.float64) * samples_per_cycle
    peaks = np.empty(cycle_count, dtype=np.float64)
    for cycle_index in range(cycle_count):
        low = int(np.floor(positions[cycle_index]))
        high = min(hf_clean.size, int(np.ceil(positions[cycle_index + 1])) + 1)
        peaks[cycle_index] = float(np.max(np.abs(hf_clean[low:high])))
    needle_mean = float(np.mean(peaks))
    needle_sigma = float(np.std(peaks, ddof=1))
    return nd.NeedleMetrics(
        sync_source=nd.SyncSource.NOMINAL,
        cycles_analyzed=cycle_count,
        line_frequency_hz=None,
        needle_mean_v=needle_mean,
        needle_sigma_ratio=needle_sigma / max(needle_mean, nd.POWER_EPS),
        sync_power_v2=None,
        async_power_v2=None,
        async_sync_ratio=None,
        lf_envelope_cv=None,
        uncertainty=_legacy_bootstrap(peaks, seed=seed),
    )


# ---------------------------------------------------------------------------
# Сравнение метрик: точные поля против полей допуска rtol=1e-12.
# ---------------------------------------------------------------------------


def _assert_metrics_equivalent(left: nd.NeedleMetrics, right: nd.NeedleMetrics) -> None:
    """Бюджет дрейфа: степени P_sync/P_async меняют порядок суммирования (1e-12);

    пики, частота, CV и бутстрэп обязаны совпадать побитово.
    """
    assert left.sync_source == right.sync_source
    assert left.cycles_analyzed == right.cycles_analyzed
    exact_fields = (
        "line_frequency_hz",
        "needle_mean_v",
        "needle_sigma_ratio",
        "lf_envelope_cv",
    )
    for name in exact_fields:
        left_value = getattr(left, name)
        right_value = getattr(right, name)
        if left_value is None or right_value is None:
            assert left_value is right_value
        else:
            assert left_value == right_value, name
    for name in ("sync_power_v2", "async_power_v2", "async_sync_ratio"):
        left_value = getattr(left, name)
        right_value = getattr(right, name)
        if left_value is None or right_value is None:
            assert left_value is right_value
        else:
            assert left_value == pytest.approx(right_value, rel=1e-12, abs=0.0), name
    if left.uncertainty is None:
        assert right.uncertainty is None
        return
    assert right.uncertainty is not None
    assert left.uncertainty.method == right.uncertainty.method
    assert left.uncertainty.confidence_level == right.uncertainty.confidence_level
    for side in ("needle_mean_v", "needle_sigma_ratio"):
        left_interval = getattr(left.uncertainty, side)
        right_interval = getattr(right.uncertainty, side)
        assert left_interval.low == right_interval.low, side
        assert left_interval.high == right_interval.high, side


def _bad_fixture() -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    session = generate(
        profile="bad",
        duration_s=FIXTURE_DURATION_S,
        sample_rate_hz=FS,
        rng=np.random.default_rng(FIXTURE_RNG_SEED),
        line_frequency_hz=50.0,
    )
    return session.ch1, session.ch2


def _assert_metrics_match_golden(fresh: nd.NeedleMetrics, golden: dict[str, object]) -> None:
    """Сверяет свежие метрики с золотым словарём: точные поля и степени 1e-12."""
    assert fresh.sync_source == golden["sync_source"]
    assert fresh.cycles_analyzed == golden["cycles_analyzed"]
    assert fresh.line_frequency_hz == golden["line_frequency_hz"]
    assert fresh.needle_mean_v == golden["needle_mean_v"]
    assert fresh.needle_sigma_ratio == golden["needle_sigma_ratio"]
    for name in ("sync_power_v2", "async_power_v2", "async_sync_ratio", "lf_envelope_cv"):
        expected = golden[name]
        actual = getattr(fresh, name)
        if expected is None:
            assert actual is None
        else:
            assert actual == pytest.approx(expected, rel=1e-12, abs=0.0), name
    raw_uncertainty = golden["uncertainty"]
    uncertainty = fresh.uncertainty
    if raw_uncertainty is None:
        assert uncertainty is None
        return
    assert uncertainty is not None
    assert isinstance(raw_uncertainty, dict)
    assert uncertainty.method == raw_uncertainty["method"]
    assert uncertainty.confidence_level == raw_uncertainty["confidence_level"]
    for side in ("needle_mean_v", "needle_sigma_ratio"):
        interval = getattr(uncertainty, side)
        raw_interval = raw_uncertainty[side]
        assert isinstance(raw_interval, dict)
        assert interval.low == raw_interval["low"]
        assert interval.high == raw_interval["high"]


# ---------------------------------------------------------------------------
# Тесты (идентификаторы зафиксированы задачей T17).
# ---------------------------------------------------------------------------


def test_bootstrap_looped_matches_big_draw_exactly() -> None:
    peaks = np.array([0.21, 0.35, 0.18, 0.92, 0.55, 0.30, 0.77])
    samples = 500
    legacy_rng = np.random.default_rng(COMPUTE_SEED)
    indices = legacy_rng.integers(0, peaks.size, size=(samples, peaks.size))
    means = np.mean(peaks[indices], axis=1)
    sigmas = np.std(peaks[indices], axis=1, ddof=1)
    mean_low, mean_high = np.quantile(means, (0.025, 0.975))
    ratio_low, ratio_high = np.quantile(
        sigmas / np.maximum(means, nd.POWER_EPS),
        (0.025, 0.975),
    )

    looped = bootstrap_quantiles(peaks, seed=COMPUTE_SEED, samples=samples, eps=nd.POWER_EPS)

    assert looped == (
        float(mean_low),
        float(mean_high),
        float(ratio_low),
        float(ratio_high),
    )


def test_phase_resample_batched_matches_reference() -> None:
    rng = np.random.default_rng(9)
    cycle_count = 37
    steps = rng.uniform(195.0, 205.0, cycle_count)
    positions = np.concatenate(([0.0], np.cumsum(steps)))
    hf = rng.normal(0.0, 0.05, int(positions[-1]) + 10)

    starts = positions[:-1]
    lengths = np.diff(positions)
    phase_grid = np.arange(PHASE_BINS, dtype=np.float64) / PHASE_BINS
    points = starts[:, np.newaxis] + lengths[:, np.newaxis] * phase_grid[np.newaxis, :]
    reference = np.interp(
        points.ravel(),
        np.arange(hf.size, dtype=np.float64),
        hf,
    ).reshape(cycle_count, PHASE_BINS)
    reference_mean = reference.mean(axis=0)
    reference_async = float(np.mean(np.square(reference - reference_mean)))

    batched_mean = resample_mean_cycle(hf, positions, batch_size=8)
    batched_async = residual_async_power(hf, positions, batched_mean, batch_size=8)

    np.testing.assert_allclose(batched_mean, reference_mean, rtol=1e-12, atol=0.0)
    assert batched_async == pytest.approx(reference_async, rel=1e-12, abs=0.0)


def test_interpolation_gather_matches_np_interp() -> None:
    rng = np.random.default_rng(11)
    window = rng.normal(0.0, 0.3, 50_000)
    queries = np.concatenate(
        [
            np.array([0.0, 1.0, float(window.size - 1)]),
            rng.uniform(0.0, float(window.size - 1), 20_000),
            np.arange(100.0, 40_000.0, 997.0),
        ],
    )

    expected = np.interp(queries, np.arange(window.size, dtype=np.float64), window)

    np.testing.assert_allclose(gather_interp(queries, window), expected, rtol=1e-12, atol=0.0)


def test_existing_metrics_unchanged_on_synthetic_record() -> None:
    ch1, ch2 = _bad_fixture()
    legacy_dual = _legacy_dual_metrics(ch1, ch2, seed=COMPUTE_SEED)
    legacy_single = _legacy_single_metrics(ch1, seed=COMPUTE_SEED)

    fresh_dual = nd.compute_needle_metrics(
        ch1,
        ch2,
        sample_rate_hz=FS,
        seed=COMPUTE_SEED,
    )
    fresh_single = nd.compute_needle_metrics_single(ch1, sample_rate_hz=FS, seed=COMPUTE_SEED)

    _assert_metrics_equivalent(fresh_dual, legacy_dual)
    _assert_metrics_equivalent(fresh_single, legacy_single)

    golden_path = EVIDENCE_DIR / "golden.json"
    if not golden_path.is_file():
        pytest.skip("golden.json отсутствует: эталон не захватывался до рефакторинга")
    golden: dict[str, object] = json.loads(golden_path.read_text(encoding="utf-8"))
    raw_dual = golden["dual"]
    raw_single = golden["single"]
    assert isinstance(raw_dual, dict)
    assert isinstance(raw_single, dict)
    _assert_metrics_match_golden(fresh_dual, raw_dual)
    _assert_metrics_match_golden(fresh_single, raw_single)


def test_determinism_preserved_across_runs() -> None:
    ch1, ch2 = _bad_fixture()

    first = nd.compute_needle_metrics(ch1, ch2, sample_rate_hz=FS, seed=COMPUTE_SEED)
    second = nd.compute_needle_metrics(ch1, ch2, sample_rate_hz=FS, seed=COMPUTE_SEED)
    first_single = nd.compute_needle_metrics_single(ch1, sample_rate_hz=FS, seed=COMPUTE_SEED)
    second_single = nd.compute_needle_metrics_single(ch1, sample_rate_hz=FS, seed=COMPUTE_SEED)

    assert first == second
    assert first_single == second_single
