"""Контракт опубликованной записи F13."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f13_result import (
    ACTIVITY_FRACTION_NAME,
    BANDS_HZ,
    CLAIM_BOUNDARY,
    DECLARED_CODES,
    FILTER_SUPPORT_TOO_SHORT,
    METHOD,
    PAIR_QUANTITY_NAMES,
    PAIR_QUANTITY_UNITS,
    PHASE_REFERENCE_UNAVAILABLE,
    F13Result,
)
from lnt.characterization.records import Status, Unit, validate_unit_name

BAND_NAMES = ("band_0001", "band_0002", "band_0003")


def _unavailable(sample_count: int = 100) -> F13Result:
    empty_float = np.empty(0, dtype=np.float64)
    empty_int = np.empty(0, dtype=np.int64)
    return F13Result(
        status=Status.UNAVAILABLE,
        reason_codes=(PHASE_REFERENCE_UNAVAILABLE,),
        band_names=BAND_NAMES,
        bands_hz=BANDS_HZ,
        lag_s=empty_float,
        activity_fraction=empty_float,
        active_sample_count=empty_int,
        sample_count=sample_count,
        qualified_sample_count=0,
        zero_lag_correlation=empty_float,
        coincidence_probability=empty_float,
        lift=empty_float,
        maximum_lag_s=empty_float,
        maximum_lag_correlation=empty_float,
    )


def test_unavailable_f13_keeps_axes_and_uses_empty_measurement_domains() -> None:
    """Недоступность сохраняет объявленные оси, но не публикует нули как измерения."""
    result = _unavailable()

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    assert result.band_names == BAND_NAMES
    assert result.bands_hz == BANDS_HZ
    assert result.qualified_sample_count == 0
    assert result.lag_s.size == 0
    assert result.activity_fraction.size == 0
    assert result.active_sample_count.size == 0
    assert result.zero_lag_correlation.shape == (0,)
    assert result.coincidence_probability.shape == (0,)
    assert result.lift.shape == (0,)
    assert result.maximum_lag_s.shape == (0,)
    assert result.maximum_lag_correlation.shape == (0,)


def _available() -> F13Result:
    identity = np.eye(3, dtype=np.float64)
    zero_lag = np.asarray(((1.0, 0.8, -0.5), (0.8, 1.0, 0.4), (-0.5, 0.4, 1.0)))
    coincidence = np.asarray(((0.25, 0.1, 0.0), (0.1, 0.5, 0.2), (0.0, 0.2, 0.25)))
    lift = np.asarray(((1.0, 0.8, 0.0), (0.8, 1.0, 1.6), (0.0, 1.6, 1.0)))
    lag = np.asarray(((0.0, -1.0, 0.0), (-1.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
    return F13Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        band_names=BAND_NAMES,
        bands_hz=BANDS_HZ,
        lag_s=np.asarray((-1.0, 0.0, 1.0)),
        activity_fraction=np.asarray((0.25, 0.5, 0.25)),
        active_sample_count=np.asarray((25, 50, 25), dtype=np.int64),
        sample_count=120,
        qualified_sample_count=100,
        zero_lag_correlation=zero_lag,
        coincidence_probability=coincidence,
        lift=lift,
        maximum_lag_s=lag,
        maximum_lag_correlation=identity,
    )


def test_locked_f13_metadata_and_closed_reason_vocabulary() -> None:
    """Метод, коды, единицы и граница притязаний совпадают с авторитетными источниками."""
    assert METHOD == "phase_residual_hilbert_envelope_coactivity"
    assert DECLARED_CODES == (
        "phase_reference_unavailable",
        "band_above_nyquist",
        "filter_support_too_short",
        "filter_context_unstable",
        "nonfinite_input",
        "mixed_unavailable_support",
        "scale_zero",
        "insufficient_activity",
        "lag_support_too_short",
        "leakage_ambiguous",
    )
    assert "do not establish coupling, direction, source, or causality" in CLAIM_BOUNDARY
    validate_unit_name(ACTIVITY_FRACTION_NAME, Unit.RATIO)
    for name, unit in zip(PAIR_QUANTITY_NAMES, PAIR_QUANTITY_UNITS, strict=True):
        validate_unit_name(name, unit)
    assert PAIR_QUANTITY_UNITS == (Unit.RATIO, Unit.RATIO, Unit.RATIO, Unit.S, Unit.RATIO)


def test_available_f13_result_accepts_one_symmetric_analytic_matrix() -> None:
    """Три пары публикуют симметричные матрицы и диагональные истины."""
    result = _available()

    assert result.status is Status.AVAILABLE
    assert result.zero_lag_correlation.shape == (3, 3)
    assert result.coincidence_probability.shape == (3, 3)
    assert result.lift.shape == (3, 3)
    assert result.maximum_lag_s.shape == (3, 3)
    assert np.array_equal(result.maximum_lag_correlation, np.eye(3))
    assert np.allclose(result.zero_lag_correlation, result.zero_lag_correlation.T)
    assert np.allclose(np.diag(result.coincidence_probability), result.activity_fraction)
    assert np.allclose(np.diag(result.lift), 1.0)
    assert np.allclose(np.diag(result.maximum_lag_s), 0.0)


def test_f13_result_rejects_unknown_and_unsorted_reason_codes() -> None:
    """Причины остаются закрытым словарём и требуют sorted unique порядка."""
    with pytest.raises(CharacterizationError) as unknown:
        replace(_available(), reason_codes=("invented",))
    with pytest.raises(CharacterizationError) as unsorted:
        replace(
            _unavailable(),
            reason_codes=(PHASE_REFERENCE_UNAVAILABLE, FILTER_SUPPORT_TOO_SHORT),
        )

    assert unknown.value.reason_code == "status_invariant"
    assert unsorted.value.reason_code == "status_invariant"


def test_f13_result_rejects_duplicate_reasons_and_available_reason() -> None:
    """AVAILABLE не публикует причины; повтор причины также недействителен."""
    with pytest.raises(CharacterizationError) as available_reason:
        replace(_available(), reason_codes=(PHASE_REFERENCE_UNAVAILABLE,))
    with pytest.raises(CharacterizationError) as duplicate:
        replace(
            _unavailable(),
            reason_codes=(PHASE_REFERENCE_UNAVAILABLE, PHASE_REFERENCE_UNAVAILABLE),
        )

    assert available_reason.value.reason_code == "status_invariant"
    assert duplicate.value.reason_code == "status_invariant"


def test_f13_result_rejects_nonfinite_and_wrong_matrix_shapes() -> None:
    """Опубликованные числа конечны, а все матрицы имеют форму 3 x 3."""
    nonfinite = _available().zero_lag_correlation.copy()
    nonfinite[0, 1] = np.nan
    with pytest.raises(CharacterizationError) as bad_number:
        replace(_available(), zero_lag_correlation=nonfinite)
    with pytest.raises(CharacterizationError) as bad_shape:
        replace(_available(), lift=np.zeros((3, 2), dtype=np.float64))

    assert bad_number.value.reason_code == "status_invariant"
    assert bad_shape.value.reason_code == "status_invariant"


def test_f13_result_rejects_asymmetric_pair_matrices() -> None:
    """Матрица пары симметрична по определению одной неупорядоченной пары."""
    asymmetric = _available().coincidence_probability.copy()
    asymmetric[0, 1] = 0.3

    with pytest.raises(CharacterizationError) as raised:
        replace(_available(), coincidence_probability=asymmetric)

    assert raised.value.reason_code == "status_invariant"
