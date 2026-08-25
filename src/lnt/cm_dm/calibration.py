"""Калибровка пары пробников CM/DM: оценка, совместимость, разрешение ссылки (T4).

Оба пробника крепятся на один и тот же проводник, поэтому записи совпадают
с точностью до коэффициента усиления g. Оценка делается узкополосным FFT по
полной записи — намеренно НЕ движком Уэлча: для сети 50 Гц нужно субгерцовое
разрешение, недостижимое при сегментном усреднении. epsilon = sqrt(P2/P1)
в полосе 45–55 Гц; коррекция k = 1/epsilon применяется к CH2.

Глубина подавления считается на пиковом бине полосы после коррекции:
CM = |X1 + k·X2|²/4, DM = |X1 − k·X2|²/4, depth = 10·log10(CM/DM). Вместо
бесконечностей используются конечные сентинелы ±200 дБ (JSON-безопасность):
нулевая DM означает идеальное подавление общего сигнала (+200), нулевая CM —
противофазную пару (−200).

Совместимость калибровки с measurement-сессией — чистые функции над
манифестами и телеметрией, без I/O (стиль lnt._input_reference_baseline).
Опубликованные оценки калибровочной сессии читаются из ``parameters``
манифеста (ключи ``snr_db`` и ``gain_ratio_epsilon``); отсутствие публикации
трактуется как непригодная калибровка. Резолвер пересчитывает факторы
из записанных волновых форм через :func:`estimate_gain_ratio` и не доверяет
устаревшим опубликованным значениям.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.session_store import load_session
from lnt.types import AcquisitionTelemetry, SessionManifest, SessionType

if TYPE_CHECKING:
    from pathlib import Path

Float64Array = NDArray[np.float64]

# Полоса сетевой помехи и окрестность для узкополосного SNR.
BAND_LOW_HZ: Final = 45.0
BAND_HIGH_HZ: Final = 55.0
NEIGHBOR_LOW_HZ: Final = 30.0
NEIGHBOR_HIGH_HZ: Final = 70.0

# Пороги пригодности калибровки.
MIN_SNR_DB: Final = 20.0
MIN_GAIN_RATIO: Final = 0.5
MAX_GAIN_RATIO: Final = 2.0

# Конечные сентинелы глубины подавления вместо бесконечностей.
MAX_REJECTION_DEPTH_DB: Final = 200.0
MIN_REJECTION_DEPTH_DB: Final = -200.0

# Ключи parameters манифеста калибровочной сессии с опубликованными оценками.
PARAM_SNR_DB: Final = "snr_db"
PARAM_GAIN_RATIO_EPSILON: Final = "gain_ratio_epsilon"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProbePairCalibration:
    """Узкополосная оценка пары пробников по полной записи."""

    gain_ratio_epsilon: float
    correction_factor: float
    rejection_depth_db: float
    snr_db: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedProbePairCalibration:
    """Пригодная калибровка пары пробников для measurement-сессии."""

    session_id: str
    correction_factor: float
    gain_ratio_epsilon: float
    rejection_depth_db: float


@dataclass(frozen=True, slots=True, kw_only=True)
class UnavailableProbePairCalibration:
    """Machine-readable причина недоступности калибровки пары пробников."""

    reason_code: str


type ProbePairCalibrationResolution = ResolvedProbePairCalibration | UnavailableProbePairCalibration


def estimate_gain_ratio(
    ch1: NDArray[np.float32 | np.float64],
    ch2: NDArray[np.float32 | np.float64],
    sample_rate_hz: float,
) -> ProbePairCalibration:
    """Оценивает gain-отношение пары пробников узкополосным FFT полной записи."""
    spectrum1 = np.fft.fft(np.asarray(ch1, dtype=np.float64))
    spectrum2 = np.fft.fft(np.asarray(ch2, dtype=np.float64))
    freqs = np.fft.fftfreq(int(spectrum1.size), d=1.0 / sample_rate_hz)
    in_band = (freqs >= BAND_LOW_HZ) & (freqs <= BAND_HIGH_HZ)
    band1 = spectrum1[in_band]
    band2 = spectrum2[in_band]
    if int(band1.size) == 0:
        raise InputError("estimate_gain_ratio: запись не содержит бинов в полосе 45–55 Гц")
    power1_band = float(np.sum(np.abs(band1) ** 2))
    power2_band = float(np.sum(np.abs(band2) ** 2))
    epsilon = math.sqrt(power2_band / power1_band) if power1_band > 0.0 else math.inf
    correction_factor = 1.0 / epsilon if epsilon > 0.0 else 0.0
    peak = int(np.argmax(np.abs(band1) ** 2 + np.abs(band2) ** 2))
    tone1 = complex(band1[peak])
    tone2 = complex(band2[peak])
    common_power = abs(tone1 + correction_factor * tone2) ** 2 / 4.0
    differential_power = abs(tone1 - correction_factor * tone2) ** 2 / 4.0
    return ProbePairCalibration(
        gain_ratio_epsilon=epsilon,
        correction_factor=correction_factor,
        rejection_depth_db=_rejection_depth_db(common_power, differential_power),
        snr_db=_narrowband_snr_db(spectrum1, spectrum2, freqs, power1_band + power2_band),
    )


def _rejection_depth_db(common_power: float, differential_power: float) -> float:
    """Глубина подавления в дБ с конечными сентинелами вместо бесконечностей."""
    if common_power <= 0.0:
        return MIN_REJECTION_DEPTH_DB
    if differential_power <= 0.0:
        return MAX_REJECTION_DEPTH_DB
    depth = 10.0 * math.log10(common_power / differential_power)
    return min(MAX_REJECTION_DEPTH_DB, max(MIN_REJECTION_DEPTH_DB, depth))


def _narrowband_snr_db(
    spectrum1: NDArray[np.complex128],
    spectrum2: NDArray[np.complex128],
    freqs: Float64Array,
    in_band_power: float,
) -> float:
    """SNR полосы 45–55 Гц против окрестности 30–45 ∪ 55–70 Гц по обоим каналам."""
    neighborhood = ((freqs >= NEIGHBOR_LOW_HZ) & (freqs < BAND_LOW_HZ)) | (
        (freqs > BAND_HIGH_HZ) & (freqs <= NEIGHBOR_HIGH_HZ)
    )
    out_power = float(
        np.sum(np.abs(spectrum1[neighborhood]) ** 2) + np.sum(np.abs(spectrum2[neighborhood]) ** 2),
    )
    if in_band_power <= 0.0:
        return -math.inf
    if out_power <= 0.0:
        return math.inf
    return 10.0 * math.log10(in_band_power / out_power)


def validate_calibration_compatibility(
    calibration_manifest: SessionManifest,
    measurement_manifest: SessionManifest,
) -> list[str]:
    """Все machine-readable причины непригодности калибровки ([] — совместима)."""
    return [
        *_structural_reasons(calibration_manifest, measurement_manifest),
        *_snr_reason(_parameter_float(calibration_manifest, PARAM_SNR_DB)),
        *_epsilon_reason(_parameter_float(calibration_manifest, PARAM_GAIN_RATIO_EPSILON)),
    ]


def resolve_probe_pair_calibration(
    sessions_root: Path,
    calibration_ref: str | None,
    measurement_manifest: SessionManifest,
) -> ProbePairCalibrationResolution:
    """Резолвит ссылку на калибровочную сессию или возвращает typed-причину."""
    if calibration_ref is None:
        return UnavailableProbePairCalibration(reason_code="missing_probe_pair_calibration")
    try:
        calibration = load_session(sessions_root / calibration_ref)
    except InputError:
        return UnavailableProbePairCalibration(reason_code="calibration_unreadable")
    if calibration.ch2 is None:
        return UnavailableProbePairCalibration(reason_code="calibration_unreadable")
    estimate = estimate_gain_ratio(
        calibration.ch1,
        calibration.ch2,
        calibration.manifest.sample_rate_hz,
    )
    reasons = [
        *_structural_reasons(calibration.manifest, measurement_manifest),
        *_snr_reason(estimate.snr_db),
        *_epsilon_reason(estimate.gain_ratio_epsilon),
    ]
    if reasons:
        return UnavailableProbePairCalibration(reason_code=reasons[0])
    return ResolvedProbePairCalibration(
        session_id=calibration.manifest.session_id,
        correction_factor=estimate.correction_factor,
        gain_ratio_epsilon=estimate.gain_ratio_epsilon,
        rejection_depth_db=estimate.rejection_depth_db,
    )


def _structural_reasons(candidate: SessionManifest, expected: SessionManifest) -> list[str]:
    """Причины несовпадения сырых предпосылок записи между сессиями."""
    telemetry = candidate.acquisition_telemetry
    checks = (
        (
            candidate.session_type is not SessionType.CM_DM_CALIBRATION,
            "calibration_session_type_mismatch",
        ),
        (candidate.source != expected.source, "calibration_source_mismatch"),
        (candidate.sample_rate_hz != expected.sample_rate_hz, "calibration_sample_rate_mismatch"),
        (candidate.ch1.range_code != expected.ch1.range_code, "calibration_range_code_mismatch"),
        (_pair_clipped(telemetry), "calibration_clipping"),
    )
    return [reason for failed, reason in checks if failed]


def _pair_clipped(telemetry: AcquisitionTelemetry | None) -> bool:
    """Любой ненулевой клип-счётчик любого канала пары."""
    if telemetry is None:
        return False
    return (
        telemetry.ch1_clip_low_count
        + telemetry.ch1_clip_high_count
        + telemetry.ch2_clip_low_count
        + telemetry.ch2_clip_high_count
    ) > 0


def _snr_reason(snr_db: float | None) -> list[str]:
    """Отсутствие опубликованной SNR-оценки трактуется как непригодная калибровка."""
    if snr_db is not None and snr_db >= MIN_SNR_DB:
        return []
    return ["calibration_snr_low"]


def _epsilon_reason(epsilon: float | None) -> list[str]:
    """Отношение усиления вне физичного диапазона [0.5, 2.0] отвергает калибровку."""
    if epsilon is not None and MIN_GAIN_RATIO <= epsilon <= MAX_GAIN_RATIO:
        return []
    return ["calibration_gain_ratio_implausible"]


def _parameter_float(manifest: SessionManifest, key: str) -> float | None:
    """Читает числовой параметр манифеста; нечисловое значение — отсутствие."""
    value = manifest.parameters.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
