"""Потоковый односторонний взаимный спектр Уэлча для CM/DM-декомпозиции.

Численные соглашения повторяют ``lnt.psd.engine``: периодическое окно Ханна
(``fftbins=True``), вычитание среднего по сегменту перед окном, перекрытие
50 %, плотностная нормировка ``1/(fs*sum(w^2))`` с удвоением всех бинов,
кроме DC и Найквиста. Взаимный спектр следует конвенции
``scipy.signal.csd`` — усреднённое ``conj(X1)*X2``. Сегментация потоковая:
между порциями переносится хвост до ``nperseg`` отсчётов, поэтому выравнивание
сегментов совпадает с однопроходным расчётом по всей записи.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.psd.errors import PsdDataError, PsdSettingsError

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]
InputArray = Float32Array | Float64Array
Complex128Array = NDArray[np.complex128]

DEFAULT_BLOCK_SAMPLES: Final = 65_536
_NPERSEG_FLOOR: Final = 8_192
_NPERSEG_CEIL: Final = 262_144
_TARGET_RESOLUTION_HZ: Final = 250.0
_MIN_NPERSEG: Final = 2
_SEGMENT_COVERAGE_FACTOR: Final = 2


@dataclass(frozen=True, slots=True)
class CrossWelchResult:
    """Односторонние автоспектры и взаимный спектр пары каналов."""

    frequency_hz: Float64Array
    s_ll: Float64Array
    s_nn: Float64Array
    s_ln_cplx: Complex128Array
    segment_count: int


def _default_nperseg(sample_rate_hz: float) -> int:
    """Зажимает next_pow2(fs/250) в границы 8192..262144."""
    target = max(math.ceil(sample_rate_hz / _TARGET_RESOLUTION_HZ), 1)
    raw = 1 << (target - 1).bit_length()
    return min(max(raw, _NPERSEG_FLOOR), _NPERSEG_CEIL)


def _validate_pair(ch1: InputArray, ch2: InputArray, nperseg: int) -> int:
    """Проверяет пару каналов и возвращает общую длину записи."""
    first = np.asarray(ch1)
    second = np.asarray(ch2)
    sample_count = int(first.size)
    if sample_count == 0:
        raise PsdDataError("CrossWelch: входной массив пуст")
    if first.ndim != 1 or second.ndim != 1:
        raise PsdDataError("CrossWelch: ожидается одномерный входной массив")
    if int(second.size) != sample_count:
        raise PsdDataError(
            f"CrossWelch: длины каналов не совпадают: {sample_count} и {int(second.size)}"
        )
    minimum = _SEGMENT_COVERAGE_FACTOR * nperseg
    if sample_count < minimum:
        raise PsdDataError(
            f"CrossWelch: запись слишком короткая: {sample_count}, нужно >= {minimum}"
        )
    return sample_count


def compute_cross_welch(
    ch1: InputArray,
    ch2: InputArray,
    sample_rate_hz: float,
    nperseg: int | None = None,
    *,
    block_samples: int = DEFAULT_BLOCK_SAMPLES,
) -> CrossWelchResult:
    """Считает S_LL, S_NN и S_LN потоково, порциями по ``block_samples``."""
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise PsdSettingsError("PSD: частота дискретизации должна быть конечной и > 0")
    segment_size = _default_nperseg(sample_rate_hz) if nperseg is None else nperseg
    if segment_size < _MIN_NPERSEG:
        raise PsdSettingsError("PSD: nperseg должен быть >= 2")
    if block_samples <= 0:
        raise PsdSettingsError("CrossWelch: размер порции должен быть >= 1")
    sample_count = _validate_pair(ch1, ch2, segment_size)

    step = segment_size // 2
    segment_total = 1 + (sample_count - segment_size) // step
    window = np.asarray(signal.get_window("hann", segment_size, fftbins=True), dtype=np.float64)
    scale = 1.0 / (sample_rate_hz * float(np.sum(window * window)))
    bins = segment_size // 2 + 1
    acc_ll = np.zeros(bins, dtype=np.float64)
    acc_nn = np.zeros(bins, dtype=np.float64)
    acc_ln = np.zeros(bins, dtype=np.complex128)
    tail1 = np.empty(0, dtype=np.float64)
    tail2 = np.empty(0, dtype=np.float64)

    for start in range(0, sample_count, block_samples):
        stop = min(start + block_samples, sample_count)
        buf1 = np.concatenate((tail1, np.asarray(ch1[start:stop], dtype=np.float64)))
        buf2 = np.concatenate((tail2, np.asarray(ch2[start:stop], dtype=np.float64)))
        available = int(buf1.size)
        ready = 0 if available < segment_size else (available - segment_size) // step + 1
        for offset in range(0, ready * step, step):
            hi = offset + segment_size
            seg1 = buf1[offset:hi]
            seg2 = buf2[offset:hi]
            transformed1 = np.fft.rfft((seg1 - float(np.mean(seg1))) * window)
            transformed2 = np.fft.rfft((seg2 - float(np.mean(seg2))) * window)
            acc_ll += np.asarray(transformed1.real**2 + transformed1.imag**2) * scale
            acc_nn += np.asarray(transformed2.real**2 + transformed2.imag**2) * scale
            acc_ln += np.conj(transformed1) * transformed2 * scale
        tail1 = buf1[ready * step :].copy()
        tail2 = buf2[ready * step :].copy()

    interior = slice(1, -1) if segment_size % 2 == 0 else slice(1, None)
    acc_ll[interior] *= 2.0
    acc_nn[interior] *= 2.0
    acc_ln[interior] *= 2.0
    return CrossWelchResult(
        frequency_hz=np.fft.rfftfreq(segment_size, d=1.0 / sample_rate_hz),
        s_ll=acc_ll / segment_total,
        s_nn=acc_nn / segment_total,
        s_ln_cplx=acc_ln / segment_total,
        segment_count=int(segment_total),
    )
