"""T7: CM/DM-анализатор сессии: payload metrics.json и CSV-артефакт спектра.

Повторяет прецедент line-quality анализа: канонический верхний уровень payload
с legacy-секциями в ``null`` плюс собственная секция ``cm_dm``. Артефакты —
``metrics.json`` и полосовой CSV ``cm_dm_spectrum.csv`` (частоты, PSD CM/DM,
дебиасированная когерентность). Калибровка пары пробников читается из
``parameters`` манифеста; отсутствие коррекции означает статус ``unavailable``
без остановки анализа.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

import numpy as np
from numpy.typing import NDArray

from lnt.cm_dm.capture_support import (
    PARAM_CORRECTION_FACTOR,
    PARAM_GAIN_RATIO,
    PARAM_REJECTION_DEPTH_DB,
)
from lnt.cm_dm.decompose import (
    CM_DM_LOW_HZ,
    PeakAttribution,
    band_mask,
    decompose,
    pick_peaks,
)
from lnt.cm_dm.spectra import compute_cross_welch
from lnt.errors import InputError
from lnt.session_store import load_session
from lnt.types import ParameterValue, SessionSource, SessionType

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

Float64Array = NDArray[np.float64]

METRICS_FILENAME: Final = "metrics.json"
CM_DM_SPECTRUM_FILENAME: Final = "cm_dm_spectrum.csv"
ANALYSIS_SCHEMA_VERSION: Final = 2
CM_DM_SECTION_SCHEMA_VERSION: Final = 1
CSV_HEADER: Final = "frequency_hz,cm_psd_v2_per_hz,dm_psd_v2_per_hz,coherence"
# Полоса проводимых помех: низ по CISPR 16-2-1, верх — мин(3 МГц, 0.45·fs).
BAND_HIGH_CEIL_HZ: Final = 3_000_000.0
BAND_NYQUIST_FRACTION: Final = 0.45
_TARGET_RESOLUTION_HZ: Final = 250.0
_NPERSEG_FLOOR: Final = 8_192
_NPERSEG_CEIL: Final = 262_144
MAX_PEAKS: Final = 8

Mode = Literal["cm", "dm"]
CalibrationStatus = Literal["ok", "unavailable"]


@dataclass(frozen=True, slots=True, kw_only=True)
class CmDmCalibration:
    """Калибровочные скаляры пары пробников из parameters манифеста."""

    correction_factor: float
    gain_ratio_epsilon: float
    rejection_depth_db: float


@dataclass(frozen=True, slots=True, kw_only=True)
class CmDmPeak:
    """Пик полосового CM/DM-спектра с отнесением к режиму."""

    frequency_hz: float
    mode: Mode
    psd_v2_per_hz: float


@dataclass(frozen=True, slots=True, kw_only=True)
class CmDmBandSpectra:
    """Полосовые массивы CSV-артефакта: частоты, PSD CM/DM, когерентность."""

    frequency_hz: Float64Array
    cm_psd: Float64Array
    dm_psd: Float64Array
    coherence: Float64Array


@dataclass(frozen=True, slots=True, kw_only=True)
class CmDmAnalysis:
    """Результат анализа cm_dm-сессии: канонические поля плюс секция cm_dm."""

    session_id: str
    profile: str | None
    source: SessionSource
    session_type: SessionType
    sample_rate_hz: float
    duration_s: float
    status: CalibrationStatus
    calibration: CmDmCalibration | None
    band_low_hz: float
    band_high_hz: float
    nperseg: int
    segment_count: int
    peaks: tuple[CmDmPeak, ...]
    band: CmDmBandSpectra


def _band_nperseg(sample_rate_hz: float) -> int:
    """Наибольшая степень двойки <= fs/250, зажатая в границы 8192..262144."""
    raw = 1 << (int(sample_rate_hz / _TARGET_RESOLUTION_HZ).bit_length() - 1)
    return min(max(raw, _NPERSEG_FLOOR), _NPERSEG_CEIL)


def _parameter_float(parameters: Mapping[str, ParameterValue], key: str) -> float | None:
    """Читает числовой параметр манифеста; нечисловое значение — отсутствие."""
    value = parameters.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _read_calibration(parameters: Mapping[str, ParameterValue]) -> CmDmCalibration | None:
    """Разбирает калибровочные скаляры; без коррекции калибровка недоступна."""
    correction_factor = _parameter_float(parameters, PARAM_CORRECTION_FACTOR)
    if correction_factor is None:
        return None
    gain_ratio_epsilon = _parameter_float(parameters, PARAM_GAIN_RATIO)
    rejection_depth_db = _parameter_float(parameters, PARAM_REJECTION_DEPTH_DB)
    if gain_ratio_epsilon is None or rejection_depth_db is None:
        missing = PARAM_GAIN_RATIO if gain_ratio_epsilon is None else PARAM_REJECTION_DEPTH_DB
        raise InputError(
            f"parameters: {missing} должен быть числом при заданном {PARAM_CORRECTION_FACTOR}",
        )
    return CmDmCalibration(
        correction_factor=correction_factor,
        gain_ratio_epsilon=gain_ratio_epsilon,
        rejection_depth_db=rejection_depth_db,
    )


def _attributed_peaks(
    frequency_hz: Float64Array,
    cm_psd: Float64Array,
    dm_psd: Float64Array,
    attributed: list[PeakAttribution],
) -> tuple[CmDmPeak, ...]:
    """Переносит пики pick_peaks в payload-вид с линейным значением PSD."""
    peaks: list[CmDmPeak] = []
    for peak in attributed:
        index = int(np.argmin(np.abs(frequency_hz - peak.frequency_hz)))
        psd = cm_psd[index] if peak.mode == "cm" else dm_psd[index]
        peaks.append(
            CmDmPeak(frequency_hz=peak.frequency_hz, mode=peak.mode, psd_v2_per_hz=float(psd)),
        )
    return tuple(peaks)


def analyze_cm_dm_session(session_dir: Path) -> CmDmAnalysis:
    """Загружает cm_dm-сессию и считает CM/DM-декомпозицию в полосе проводимых помех.

    Калибровочная сессия и одноканальная запись отвергаются ``InputError``;
    отсутствие коррекции в ``parameters`` даёт статус ``unavailable``.
    """
    loaded = load_session(session_dir)
    manifest = loaded.manifest
    if manifest.session_type is SessionType.CM_DM_CALIBRATION:
        raise InputError(f"сессия {manifest.session_id} — калибровочная, нужна сессия типа cm_dm")
    if loaded.ch2 is None:
        raise InputError(f"сессия {manifest.session_id} — одноканальная, для CM/DM нужны CH1 и CH2")
    band_low_hz = CM_DM_LOW_HZ
    band_high_hz = min(BAND_HIGH_CEIL_HZ, BAND_NYQUIST_FRACTION * manifest.sample_rate_hz)
    if band_high_hz <= band_low_hz:
        raise InputError(
            f"fs={manifest.sample_rate_hz:.0f} Гц: полоса проводимых помех не покрывается"
        )
    nperseg = _band_nperseg(manifest.sample_rate_hz)
    welch = compute_cross_welch(loaded.ch1, loaded.ch2, manifest.sample_rate_hz, nperseg=nperseg)
    decomposed = decompose(welch.s_ll, welch.s_nn, welch.s_ln_cplx, welch.segment_count)
    mask = band_mask(welch.frequency_hz, band_low_hz, band_high_hz)
    band_frequency_hz = welch.frequency_hz[mask]
    band_cm_psd = decomposed.cm_psd[mask]
    band_dm_psd = decomposed.dm_psd[mask]
    calibration = _read_calibration(manifest.parameters)
    return CmDmAnalysis(
        session_id=manifest.session_id,
        profile=manifest.profile,
        source=manifest.source,
        session_type=manifest.session_type,
        sample_rate_hz=manifest.sample_rate_hz,
        duration_s=manifest.duration_s,
        status="ok" if calibration is not None else "unavailable",
        calibration=calibration,
        band_low_hz=band_low_hz,
        band_high_hz=band_high_hz,
        nperseg=nperseg,
        segment_count=welch.segment_count,
        peaks=_attributed_peaks(
            band_frequency_hz,
            band_cm_psd,
            band_dm_psd,
            pick_peaks(band_frequency_hz, band_cm_psd, band_dm_psd, max_peaks=MAX_PEAKS),
        ),
        band=CmDmBandSpectra(
            frequency_hz=band_frequency_hz,
            cm_psd=band_cm_psd,
            dm_psd=band_dm_psd,
            coherence=decomposed.coherence[mask],
        ),
    )


def _section_to_payload(result: CmDmAnalysis) -> dict[str, object]:
    """Канонический JSON-вид секции cm_dm."""
    return {
        "schema_version": CM_DM_SECTION_SCHEMA_VERSION,
        "status": result.status,
        "calibration": (
            {
                "correction_factor": result.calibration.correction_factor,
                "gain_ratio_epsilon": result.calibration.gain_ratio_epsilon,
                "rejection_depth_db": result.calibration.rejection_depth_db,
            }
            if result.calibration is not None
            else None
        ),
        "band_low_hz": result.band_low_hz,
        "band_high_hz": result.band_high_hz,
        "nperseg": result.nperseg,
        "segment_count": result.segment_count,
        "peaks": [
            {
                "frequency_hz": peak.frequency_hz,
                "mode": peak.mode,
                "psd_v2_per_hz": peak.psd_v2_per_hz,
            }
            for peak in result.peaks
        ],
    }


def cm_dm_analysis_to_payload(result: CmDmAnalysis) -> dict[str, object]:
    """Канонический JSON-вид CM/DM-анализа, тот же, что metrics.json.

    Форма — надмножество канонического контракта: needle/line_quality/spectrum/
    ch1_input_reference явно null, режим различается по session_type и секции.
    """
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "session_id": result.session_id,
        "profile": result.profile,
        "source": result.source.value,
        "session_type": result.session_type.value,
        "sample_rate_hz": result.sample_rate_hz,
        "duration_s": result.duration_s,
        "needle": None,
        "line_quality": None,
        "spectrum": None,
        "ch1_input_reference": None,
        "cm_dm": _section_to_payload(result),
    }


def write_cm_dm_analysis(session_dir: Path, result: CmDmAnalysis) -> Path:
    """Пишет metrics.json и cm_dm_spectrum.csv в каталог сессии; возвращает путь метрик."""
    metrics_path = session_dir / METRICS_FILENAME
    metrics_path.write_text(
        json.dumps(cm_dm_analysis_to_payload(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    band = result.band
    table = np.column_stack([band.frequency_hz, band.cm_psd, band.dm_psd, band.coherence])
    np.savetxt(
        session_dir / CM_DM_SPECTRUM_FILENAME,
        table,
        delimiter=",",
        header=CSV_HEADER,
        comments="",
        fmt="%.9g",
    )
    return metrics_path
