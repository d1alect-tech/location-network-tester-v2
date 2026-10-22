"""Квалификация фона ripple: сравнение только рядом, без вычитания.

Коррекция контракта 2026-10-20 (B4/5): корневой приватный помощник
``_input_reference_baseline`` не является новым API совместимости —
переиспользуются только принципы: та же геометрия/адаптер/план вольтов/
частота/диапазон/пробник/конверсия/Welch и честная идентичность калибровки.
Несовместимый или отсутствующий фон делает недоступным СРАВНЕНИЕ, но не
измерение; вычитания, обратной transfer-коррекции и «выделенного шума
источника» в v1 нет.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.errors import InputError
from lnt.manifest import ch1_setup_mapping
from lnt.session_store import load_session
from lnt.types import ScopeInputTerminated, SessionSource, SessionType

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from lnt.session_store import LoadedSession
    from lnt.types import SessionManifest

    from .ripple_options import BaselineAttachment

REASON_ATTACHMENT: Final = "baseline_attachment_unqualified"
REASON_SOURCE: Final = "baseline_source_mismatch"
REASON_SAMPLE_RATE: Final = "baseline_sample_rate_mismatch"
REASON_RANGE_CODE: Final = "baseline_range_code_mismatch"
REASON_UNIT: Final = "baseline_unit_mismatch"
REASON_PROBE: Final = "baseline_probe_multiplier_mismatch"
REASON_CALIBRATION_FLAG: Final = "baseline_adc_calibration_mismatch"
REASON_CALIBRATION_IDENTITY: Final = "baseline_calibration_identity_unknown"
REASON_BASELINE_RESULT: Final = "baseline_result_unavailable"
REASON_MEASUREMENT_RESULT: Final = "measurement_result_unavailable"
REASON_DURATION: Final = "baseline_duration_mismatch"
REASON_GEOMETRY_MISSING: Final = "baseline_geometry_missing"
REASON_GEOMETRY_MISMATCH: Final = "baseline_geometry_mismatch"
REASON_INSTRUMENT_ONLY: Final = "baseline_instrument_only"
REASON_HOOKUP: Final = "baseline_hookup_mismatch"
REASON_SELF_BASELINE: Final = "baseline_is_measurement"
DEVICE_IDENTITY_NOT_RECORDED: Final = "not_recorded"


def load_baseline_session(path: Path) -> LoadedSession:
    """Читает явно заданный фон; битый путь/файл — типовой входной отказ."""
    try:
        return load_session(path)
    except InputError as error:
        raise InputError(f"ripple: фон не читается ({path}): {error.message}") from error
    except (OSError, ValueError) as error:
        raise InputError(f"ripple: фон не читается ({path}): {error}") from error


def baseline_identity_reasons(
    *,
    measurement: SessionManifest,
    baseline: SessionManifest,
    attachment: BaselineAttachment | None,
    measurement_dir: Path | None = None,
    baseline_dir: Path | None = None,
) -> tuple[str, ...]:
    """Типовые коды несовместимости; пустой кортеж — геометрия совпадает."""
    reasons: list[str] = []
    if _same_recording(
        measurement=measurement,
        baseline=baseline,
        measurement_dir=measurement_dir,
        baseline_dir=baseline_dir,
    ):
        reasons.append(REASON_SELF_BASELINE)
    if attachment is None:
        reasons.append(REASON_ATTACHMENT)
    if baseline.source != measurement.source:
        reasons.append(REASON_SOURCE)
    if baseline.sample_rate_hz != measurement.sample_rate_hz:
        reasons.append(REASON_SAMPLE_RATE)
    if baseline.ch1.range_code != measurement.ch1.range_code:
        reasons.append(REASON_RANGE_CODE)
    if baseline.ch1.unit != measurement.ch1.unit:
        reasons.append(REASON_UNIT)
    if baseline.ch1.probe_multiplier != measurement.ch1.probe_multiplier:
        reasons.append(REASON_PROBE)
    reasons.extend(_geometry_reasons(measurement, baseline))
    if baseline.ch1.role != measurement.ch1.role:
        reasons.append(REASON_HOOKUP)
    calibration_reason = _calibration_reason(measurement, baseline)
    if calibration_reason is not None:
        reasons.append(calibration_reason)
    return tuple(reasons)


def _same_recording(
    *,
    measurement: SessionManifest,
    baseline: SessionManifest,
    measurement_dir: Path | None,
    baseline_dir: Path | None,
) -> bool:
    """Самосравнение: тот же session_id или тот же разрешённый каталог."""
    if measurement.session_id == baseline.session_id:
        return True
    if measurement_dir is None or baseline_dir is None:
        return False
    try:
        return measurement_dir.resolve() == baseline_dir.resolve()
    except OSError:
        return False


def _geometry_reasons(
    measurement: SessionManifest,
    baseline: SessionManifest,
) -> tuple[str, ...]:
    """Записанная и совпадающая геометрия входа; синтетика — математический план."""
    if measurement.source is SessionSource.SYNTHETIC and baseline.source is SessionSource.SYNTHETIC:
        return ()
    if baseline.session_type is SessionType.SELF_NOISE or isinstance(
        baseline.ch1_setup, ScopeInputTerminated
    ):
        # 50-ом вход прибора без адаптера/сборки — только приборный референс.
        return (REASON_INSTRUMENT_ONLY,)
    if baseline.ch1_setup is None or measurement.ch1_setup is None:
        return (REASON_GEOMETRY_MISSING,)
    if baseline.ch1_setup != measurement.ch1_setup:
        return (REASON_GEOMETRY_MISMATCH,)
    return ()


def baseline_payload_block(  # noqa: PLR0913 - один аргумент на поле замороженной схемы
    *,
    manifest: SessionManifest,
    hashes: Mapping[str, str],
    session_dir: str | None,
    settling: str,
    attachment: BaselineAttachment | None,
    comparison_status: str,
    reason_codes: tuple[str, ...],
    selection: Mapping[str, object] | None,
    time_domain: Mapping[str, object],
    spectrum: Mapping[str, object],
    bands: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Блок фона: собственная идентичность и собственные числа рядом."""
    return {
        "session": {
            "session_id": manifest.session_id,
            "manifest_sha256": hashes["manifest_sha256"],
            "ch1_sha256": hashes["ch1_sha256"],
            "channel": "ch1",
            "source": manifest.source.value,
            "session_dir": session_dir,
            "session_type": manifest.session_type.value,
            "channel_role": manifest.ch1.role.value,
            "ch1_setup": ch1_setup_mapping(manifest.ch1_setup),
            "device_identity": DEVICE_IDENTITY_NOT_RECORDED,
            "connection_procedure": settling,
        },
        "attachment_basis": attachment.value if attachment is not None else None,
        "comparison_status": comparison_status,
        "reason_codes": list(reason_codes),
        "selection": dict(selection) if selection is not None else None,
        "time_domain": dict(time_domain),
        "spectrum": dict(spectrum),
        "bands": [dict(band) for band in bands],
    }


def _calibration_reason(measurement: SessionManifest, baseline: SessionManifest) -> str | None:
    """Равные булевы флаги калибровки — недостаточное условие совместимости."""
    if measurement.source is SessionSource.SYNTHETIC and baseline.source is SessionSource.SYNTHETIC:
        # Синтетический математический план не проходит через АЦП и его таблицу.
        return None
    measurement_used = _calibration_used(measurement)
    baseline_used = _calibration_used(baseline)
    if measurement_used is not None and baseline_used is not None:
        if measurement_used != baseline_used:
            return REASON_CALIBRATION_FLAG
        if measurement_used:
            return REASON_CALIBRATION_IDENTITY
        return None
    # Без телеметрии идентичность конверсии неизвестна; нули не выдумываем.
    return REASON_CALIBRATION_IDENTITY


def _calibration_used(manifest: SessionManifest) -> bool | None:
    telemetry = manifest.acquisition_telemetry
    return telemetry.calibration_used if telemetry is not None else None
