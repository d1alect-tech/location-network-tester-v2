"""F01 synchronous_relative_harmonic_dft RED analytic tests (Wave 1 todo 4)."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from lnt.characterization.f01_phase_cycle import (
    GRID_BAND_HIGH_HZ,
    GRID_BAND_LOW_HZ,
    H1_CONCENTRATION_RATIO_MIN,
    MAXIMUM_HARMONIC_ORDER,
    MIN_WINDOW_COUNT,
    PHASE_RESULTANT_MIN,
    WINDOW_S,
    compute_f01_phase_cycle,
    estimate_grid_frequency_quinn_fernandes,
)

FS_HZ = 500000.0
F1_HZ = 50.0
AMPS = {1: 6.0, 3: 0.6, 5: 0.3, 7: 0.15}
PHASES = {1: 0.4, 3: -0.7, 5: 1.1, 7: 0.2}

type Float64Array = NDArray[np.float64]


def _synthetic(
    duration_s: float,
    f1_hz: float = F1_HZ,
    shift_s: float = 0.0,
    conjugate: bool = False,
) -> Float64Array:
    n = round(FS_HZ * duration_s)
    t = np.arange(n, dtype=np.float64) / FS_HZ
    out = np.zeros(n, dtype=np.float64)
    for order, amp in AMPS.items():
        phi = PHASES[order]
        if conjugate:
            phi = -phi
        out += amp * np.sin(2.0 * np.pi * f1_hz * float(order) * (t - shift_s) + phi)
    return out


def _wrap(value: float) -> float:
    return float((value + np.pi) % (2.0 * np.pi) - np.pi)


def test_locked_parameters_match_contract() -> None:
    assert pytest.approx(0.2) == WINDOW_S
    assert MIN_WINDOW_COUNT == 12
    assert MAXIMUM_HARMONIC_ORDER == 40
    assert pytest.approx(0.8) == PHASE_RESULTANT_MIN
    assert pytest.approx(0.95) == H1_CONCENTRATION_RATIO_MIN
    assert pytest.approx((47.5, 52.5)) == (GRID_BAND_LOW_HZ, GRID_BAND_HIGH_HZ)


def test_recover_declared_amplitudes_within_one_percent() -> None:
    signal = _synthetic(2.4)
    result = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    assert result.c_k_v is not None
    for order, amp in AMPS.items():
        assert abs(abs(result.c_k_v[order - 1]) - amp) / amp < 0.01


def test_recover_relative_phases_within_point_zero_two_rad() -> None:
    signal = _synthetic(2.4)
    result = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    assert result.phi_rel_k_rad is not None
    for order, phi in PHASES.items():
        expected = _wrap(phi - float(order) * PHASES[1])
        assert abs(_wrap(float(result.phi_rel_k_rad[order - 1]) - expected)) < 0.02


def test_quinn_fernandes_refines_off_bin_frequency() -> None:
    window = _synthetic(WINDOW_S, f1_hz=50.13)[: round(FS_HZ * WINDOW_S)]
    refined = estimate_grid_frequency_quinn_fernandes(window, sample_rate_hz=FS_HZ)
    assert pytest.approx(50.13, abs=0.02) == refined


def test_out_of_band_frequency_clamps_to_grid_unstable() -> None:
    signal = _synthetic(2.4, f1_hz=60.0)
    result = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    assert "grid_unstable" in result.reason_codes


def test_full_record_evaluates_every_complete_window_without_crop() -> None:
    signal = _synthetic(3.0)
    result = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    assert result.evaluated_window_count == 15
    assert result.evaluated_window_count > 12


def test_unstable_phase_trips_phase_unstable() -> None:
    rng = np.random.default_rng(6022)
    n = round(FS_HZ * 2.4)
    t = np.arange(n, dtype=np.float64) / FS_HZ
    drift = np.cumsum(rng.standard_normal(n)) * 0.02
    signal = (6.0 * np.sin(2.0 * np.pi * F1_HZ * t + drift)).astype(np.float64)
    result = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    assert "phase_unstable" in result.reason_codes


def test_missing_fundamental_trips_fundamental_absent() -> None:
    n = round(FS_HZ * 2.4)
    t = np.arange(n, dtype=np.float64) / FS_HZ
    signal = (0.5 * np.sin(2.0 * np.pi * 150.0 * t + 0.3)).astype(np.float64)
    result = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    assert "fundamental_absent" in result.reason_codes


def test_leakage_window_trips_grid_unstable_by_h1_concentration() -> None:
    signal = _synthetic(2.4, f1_hz=48.5)
    result = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    assert "grid_unstable" in result.reason_codes


def test_short_record_trips_window_too_short() -> None:
    signal = _synthetic(0.3)
    result = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    assert "window_too_short" in result.reason_codes


def test_missing_sync_reference_is_unavailable_not_zero_phase() -> None:
    signal = _synthetic(2.4)
    result = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=None)
    assert "no_sync_reference" in result.reason_codes
    assert result.phi_rel_k_rad is None


def test_conjugate_spectra_do_not_collapse_to_equal_shape() -> None:
    signal = _synthetic(2.4)
    mirrored = _synthetic(2.4, conjugate=True)
    base = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    flip = compute_f01_phase_cycle(mirrored, sample_rate_hz=FS_HZ, sync_reference=mirrored)
    assert base.phi_rel_k_rad is not None
    assert flip.phi_rel_k_rad is not None
    assert float(np.max(np.abs(base.phi_rel_k_rad - flip.phi_rel_k_rad))) > 0.1


def test_time_shift_leaves_phi_rel_invariant() -> None:
    signal = _synthetic(2.4)
    shifted = _synthetic(2.4, shift_s=0.003)
    base = compute_f01_phase_cycle(signal, sample_rate_hz=FS_HZ, sync_reference=signal)
    moved = compute_f01_phase_cycle(shifted, sample_rate_hz=FS_HZ, sync_reference=shifted)
    assert base.phi_rel_k_rad is not None
    assert moved.phi_rel_k_rad is not None
    for order in AMPS:
        delta = _wrap(float(moved.phi_rel_k_rad[order - 1]) - float(base.phi_rel_k_rad[order - 1]))
        assert abs(delta) < 0.02
