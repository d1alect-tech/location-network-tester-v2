"""Аналитические тесты математики F12."""

from __future__ import annotations

import numpy as np
import pytest

from lnt.characterization.f12_contract import PHASE_REFERENCE_UNAVAILABLE
from lnt.characterization.f12_math import antoni_spectral_kurtosis, declared_phase_reason
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES


def test_antoni_estimator_matches_hand_derived_four_frame_value() -> None:
    """Для модулей 1,2,2,3 суммы дают SK=-26/81 при точном M/(M-1), M+1, -2."""
    coefficients = np.asarray([[1.0, 2.0, 2.0, 3.0]], dtype=np.complex128)

    result = antoni_spectral_kurtosis(coefficients)

    # sum(|X|²)=18, sum(|X|⁴)=114, M=4:
    # 4/3 * (5*114/18² - 2) = 4/3 * (95/54 - 2) = -26/81.
    assert result.tolist() == pytest.approx([-26.0 / 81.0], rel=1e-15, abs=0.0)


def test_zero_frequency_bin_is_explicit_nan_not_zero_or_infinite() -> None:
    """Нулевой second moment оставляет только явное отсутствие, не число zero."""
    coefficients = np.asarray([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.complex128)

    result = antoni_spectral_kurtosis(coefficients)

    assert np.isnan(result[0])
    # M=3, all |X|=1: 3/2 * (4 * 3/3² - 2) = -1.
    assert result[1] == pytest.approx(-1.0, rel=1e-15, abs=0.0)


@pytest.mark.parametrize("code", sorted(PHASE_ROOT_REASON_CODES))
def test_phase_root_codes_normalize_to_f12_vocabulary(code: str) -> None:
    """Каждый upstream phase code становится одним объявленным F12 reason code."""
    assert declared_phase_reason(code) == PHASE_REFERENCE_UNAVAILABLE
