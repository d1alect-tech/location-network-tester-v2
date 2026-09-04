"""Межсессионное усреднение спектра повторов серии (очередь B2).

Truth: громкий выброс в одном повторе из трёх — max-hold след хранит
его уровень бит-в-бит, mean разбавляет ровно в 3 раза. Сетки повторов
обязаны совпадать строго, иначе честная ошибка вместо тихого мусора.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.errors import InputError
from lnt.series_average import average_repeat_spectra, average_series_sessions

if TYPE_CHECKING:
    from pathlib import Path


def _flat(value: float, size: int = 16) -> tuple[np.ndarray, np.ndarray]:
    frequency = np.linspace(3000.0, 9000.0, size)
    return frequency, np.full(size, value, dtype=np.float64)


def test_transient_survives_only_in_max_hold_trace() -> None:
    # Given: три повтора, средний с выбросом x100 в одном бине
    frequency, quiet = _flat(2.0)
    _, loud = _flat(2.0)
    loud[7] = 200.0

    # When
    result = average_repeat_spectra(
        [(frequency, quiet), (frequency.copy(), loud), (frequency.copy(), quiet)]
    )

    # Then: точные уровни mean и max-hold
    assert result.repeat_count == 3
    np.testing.assert_array_equal(result.frequency_hz, frequency)
    assert result.psd_max_hold_v2_per_hz[7] == 200.0
    assert result.psd_mean_v2_per_hz[7] == pytest.approx((2.0 + 200.0 + 2.0) / 3.0)
    np.testing.assert_array_equal(result.psd_mean_v2_per_hz[np.arange(16) != 7], 2.0)
    np.testing.assert_array_equal(result.psd_max_hold_v2_per_hz[np.arange(16) != 7], 2.0)


def test_single_repeat_is_identity() -> None:
    # Given / When
    frequency, psd = _flat(3.5)
    result = average_repeat_spectra([(frequency, psd)])

    # Then
    assert result.repeat_count == 1
    np.testing.assert_array_equal(result.psd_mean_v2_per_hz, psd)
    np.testing.assert_array_equal(result.psd_max_hold_v2_per_hz, psd)


def test_grid_mismatch_rejected() -> None:
    # Given
    frequency, psd = _flat(1.0)
    shifted = frequency + 1.0

    # When / Then: разная сетка и разная длина — честная ошибка
    with pytest.raises(InputError):
        average_repeat_spectra([(frequency, psd), (shifted, psd)])
    with pytest.raises(InputError):
        average_repeat_spectra([(frequency, psd), (frequency[:8], psd[:8])])
    with pytest.raises(InputError):
        average_repeat_spectra([])


def test_non_finite_rejected() -> None:
    # Given
    frequency, psd = _flat(1.0)
    broken = psd.copy()
    broken[3] = np.nan

    # When / Then
    with pytest.raises(InputError):
        average_repeat_spectra([(frequency, psd), (frequency.copy(), broken)])


def _write_spectrum_csv(session_dir: Path, frequency: np.ndarray, psd: np.ndarray) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    table = np.column_stack([frequency, psd])
    np.savetxt(
        session_dir / "spectrum.csv",
        table,
        delimiter=",",
        header="frequency_hz,psd_v2_per_hz",
        comments="",
        fmt="%.9g",
    )


def test_average_series_sessions_reads_spectrum_csv(tmp_path: Path) -> None:
    # Given: два повтора на диске, второй с выбросом
    frequency, quiet = _flat(2.0)
    _, loud = _flat(2.0)
    loud[5] = 50.0
    first = tmp_path / "run-001"
    second = tmp_path / "run-002"
    _write_spectrum_csv(first, frequency, quiet)
    _write_spectrum_csv(second, frequency, loud)

    # When
    result = average_series_sessions([first, second])

    # Then
    assert result.repeat_count == 2
    np.testing.assert_allclose(result.frequency_hz, frequency)
    assert result.psd_max_hold_v2_per_hz[5] == pytest.approx(50.0)
    assert result.psd_mean_v2_per_hz[5] == pytest.approx(26.0)


def test_average_series_sessions_missing_file_rejected(tmp_path: Path) -> None:
    # Given: каталог без spectrum.csv
    empty = tmp_path / "run-001"
    empty.mkdir()

    # When / Then
    with pytest.raises(InputError):
        average_series_sessions([empty])
