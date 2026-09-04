"""Max-hold сайдкар спектра (очередь B2): ``spectrum_max_hold.csv`` рядом с spectrum.csv.

Формат spectrum.csv заморожен и не тронут: след пишется отдельным
двухколоночным файлом с честным заголовком. Отсутствие или порча
сайдкара — это отсутствие следа (``None``), а не сбой основного спектра.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.spectrum import BandSpectrum

HOLD_SPECTRUM_FILENAME: Final = "spectrum_max_hold.csv"
HOLD_SPECTRUM_HEADER: Final = "frequency_hz,psd_max_hold_v2_per_hz"

_TABLE_COLUMNS: Final = 2


def write_hold_spectrum(session_dir: Path, spectrum: BandSpectrum) -> Path | None:
    """Пишет max-hold след; без следа в результате файл не создаётся."""
    hold = spectrum.psd_max_hold_v2_per_hz
    if hold is None:
        return None
    path = session_dir / HOLD_SPECTRUM_FILENAME
    table = np.column_stack([spectrum.frequencies_hz, hold])
    np.savetxt(path, table, delimiter=",", header=HOLD_SPECTRUM_HEADER, comments="", fmt="%.9g")
    return path


def read_hold_spectrum(session_dir: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Читает сайдкар; отсутствие/порча означает отсутствие следа."""
    path = session_dir / HOLD_SPECTRUM_FILENAME
    if not path.is_file():
        return None
    try:
        table = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.float64, ndmin=2)
    except (OSError, ValueError):
        return None
    if table.ndim != _TABLE_COLUMNS or table.shape[1] != _TABLE_COLUMNS or table.shape[0] == 0:
        return None
    frequency, hold = table[:, 0], table[:, 1]
    if not np.all(np.isfinite(frequency)) or not np.all(np.isfinite(hold)):
        return None
    if np.any(frequency <= 0.0) or np.any(hold <= 0.0):
        return None
    return frequency, hold


def matching_hold_spectrum(
    spectrum_table: np.ndarray, hold: tuple[np.ndarray, np.ndarray] | None
) -> np.ndarray | None:
    """Возвращает hold-ряд только на сетке основного спектра; иначе следа нет."""
    if hold is None:
        return None
    hold_frequency, hold_psd = hold
    if hold_frequency.shape != spectrum_table[:, 0].shape:
        return None
    if not np.array_equal(hold_frequency, spectrum_table[:, 0]):
        return None
    return hold_psd
