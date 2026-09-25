"""Тесты magnitude-preserving phase-randomized surrogates F12."""

from __future__ import annotations

import numpy as np

from lnt.characterization.f12_surrogates import iter_phase_randomized_surrogates


def test_surrogates_preserve_fft_magnitudes_and_repeat_bit_identically() -> None:
    """Local default_rng(6022) даёт real surrogates с exact magnitude spectrum."""
    time_s = np.arange(96, dtype=np.float64) / 12_000.0
    residual = np.sin(2.0 * np.pi * 1500.0 * time_s) + 0.25 * np.cos(2.0 * np.pi * 4000.0 * time_s)
    magnitudes = np.abs(np.fft.rfft(residual))

    first = list(iter_phase_randomized_surrogates(residual, magnitudes, 3, 6022))
    second = list(iter_phase_randomized_surrogates(residual, magnitudes, 3, 6022))

    assert len(first) == 3
    assert all(np.isrealobj(surrogate) for surrogate in first)
    roundoff = 8.0 * np.finfo(np.float64).eps * float(np.max(magnitudes))
    for surrogate in first:
        # Forward/inverse FFT roundoff is O(eps * ||X||); 8*eps*||X|| covers
        # N=96 с запасом и не маскирует изменение spectrum на ненулевом scale.
        np.testing.assert_allclose(
            np.abs(np.fft.rfft(surrogate)), magnitudes, rtol=1e-13, atol=roundoff
        )
        spectrum = np.fft.rfft(surrogate)
        original = np.fft.rfft(residual)
        assert abs(float(spectrum[0].real - original[0].real)) <= roundoff
        assert abs(float(spectrum[-1].real - original[-1].real)) <= roundoff
    for left, right in zip(first, second, strict=True):
        np.testing.assert_array_equal(left, right)
