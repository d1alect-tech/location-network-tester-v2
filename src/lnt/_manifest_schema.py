"""Строгая сериализация/разбор manifest.json (schema v1/v2) без dataclass-эвристик.

ПРИМЕЧАНИЕ О ВОССТАНОВЛЕНИИ: первые ~4 КБ файла (до середины ``_validate_manifest``)
утрачены при сбое диска и реконструированы по контрактным тестам
(tests/test_manifest.py, tests/test_ch1_manifest_contract.py) и потребителям модуля.
Хвост файла — оригинальный.
"""

import math
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from lnt import _manifest_ch1_setup
from lnt._manifest_json import JsonValue
from lnt._manifest_truth import parse_synthetic_truth
from lnt.errors import InputError
from lnt.types import (
    CH1_MANIFEST_SCHEMA_VERSION,
    SCHEMA_VERSION,
    AcquisitionTelemetry,
    ChannelMeta,
    ChannelRole,
    ParameterValue,
    SessionManifest,
    SessionSource,
    SessionType,
    SyntheticTruth,
)

SESSION_ID_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
MIN_SERIES_TOTAL: Final = 2
SERIES_FIELDS: Final = frozenset({"series_index", "series_total", "series_interval_s"})
CHANNEL_FIELDS: Final = frozenset(
    {"filename", "role", "unit", "front_end", "range_code", "probe_multiplier"},
)
TELEMETRY_FIELDS: Final = frozenset(
    {
        "requested_samples",
        "captured_samples",
        "callback_count",
        "block_lengths",
        "callback_gaps_s",
        "expected_block_interval_s",
        "short_block_count",
        "ch1_clip_low_count",
        "ch1_clip_high_count",
        "ch2_clip_low_count",
        "ch2_clip_high_count",
        "calibration_used",
    },
)
MANIFEST_FIELDS: Final = frozenset(
    {
        "schema_version",
        "session_id",
        "created_utc",
        "completed_utc",
        "source",
        "session_type",
        "sample_rate_hz",
        "duration_s",
        "sample_count",
        "line_frequency_hz",
        "profile",
        "baseline_session",
        "parameters",
        "ch1",
        "ch2",
        "acquisition_telemetry",
        "synthetic_truth",
    },
)
CH1_MANIFEST_FIELDS: Final = MANIFEST_FIELDS | {"ch1_setup"}


def manifest_to_mapping(manifest: SessionManifest) -> dict[str, JsonValue]:
    """Сериализует манифест в канонический JSON-mapping (с полной валидацией)."""
    _validate_manifest(manifest)
    mapping: dict[str, JsonValue] = {
        "schema_version": manifest.schema_version,
        "session_id": manifest.session_id,
        "created_utc": manifest.created_utc,
        "completed_utc": manifest.completed_utc,
        "source": manifest.source.value,
        "session_type": manifest.session_type.value,
        "sample_rate_hz": manifest.sample_rate_hz,
        "duration_s": manifest.duration_s,
        "sample_count": manifest.sample_count,
        "line_frequency_hz": manifest.line_frequency_hz,
        "profile": manifest.profile,
        "baseline_session": manifest.baseline_session,
        "parameters": {key: value for key, value in manifest.parameters.items()},  # noqa: C416 -- comprehension выводится как dict[str, JsonValue], dict() — нет
        "ch1": _serialize_channel(manifest.ch1),
        "ch2": (_serialize_channel(manifest.ch2) if manifest.ch2 is not None else None),
        "acquisition_telemetry": _serialize_telemetry(manifest.acquisition_telemetry),
        "synthetic_truth": _serialize_truth(manifest.synthetic_truth),
    }
    if manifest.ch1_setup is not None:
        mapping["ch1_setup"] = _manifest_ch1_setup.serialize_ch1_setup(manifest.ch1_setup)
    return mapping


def _serialize_channel(channel: ChannelMeta) -> dict[str, JsonValue]:
    return {
        "filename": channel.filename,
        "role": channel.role.value,
        "unit": channel.unit,
        "front_end": channel.front_end,
        "range_code": channel.range_code,
        "probe_multiplier": channel.probe_multiplier,
    }


def _serialize_telemetry(telemetry: AcquisitionTelemetry | None) -> dict[str, JsonValue] | None:
    if telemetry is None:
        return None
    return {
        "requested_samples": telemetry.requested_samples,
        "captured_samples": telemetry.captured_samples,
        "callback_count": telemetry.callback_count,
        "block_lengths": list(telemetry.block_lengths),
        "callback_gaps_s": list(telemetry.callback_gaps_s),
        "expected_block_interval_s": telemetry.expected_block_interval_s,
        "short_block_count": telemetry.short_block_count,
        "ch1_clip_low_count": telemetry.ch1_clip_low_count,
        "ch1_clip_high_count": telemetry.ch1_clip_high_count,
        "ch2_clip_low_count": telemetry.ch2_clip_low_count,
        "ch2_clip_high_count": telemetry.ch2_clip_high_count,
        "calibration_used": telemetry.calibration_used,
    }


def _serialize_truth(truth: SyntheticTruth | None) -> dict[str, JsonValue] | None:
    if truth is None:
        return None
    return {
        "needle_mean_v": truth.needle_mean_v,
        "needle_sigma_ratio": truth.needle_sigma_ratio,
        "needle_jitter_us": truth.needle_jitter_us,
        "ring_f0_hz": truth.ring_f0_hz,
        "ring_q": truth.ring_q,
        "async_rate_hz": truth.async_rate_hz,
        "lf_envelope_cv": truth.lf_envelope_cv,
    }


def manifest_from_mapping(obj: Mapping[str, object]) -> SessionManifest:
    """Строго разбирает JSON-mapping манифеста; любое отклонение -> InputError."""
    schema_version = _req_int(obj, "schema_version")
    if schema_version == SCHEMA_VERSION:
        _reject_unknown_fields(obj, MANIFEST_FIELDS, "manifest")
    elif schema_version == CH1_MANIFEST_SCHEMA_VERSION:
        _reject_unknown_fields(obj, CH1_MANIFEST_FIELDS, "manifest")
    else:
        raise InputError(f"manifest: неподдерживаемая schema_version: {schema_version}")
    ch1_setup = None
    if schema_version == CH1_MANIFEST_SCHEMA_VERSION:
        raw_setup = _opt_object(obj, "ch1_setup")
        if raw_setup is not None:
            ch1_setup = _manifest_ch1_setup.parse_ch1_setup(raw_setup)
    manifest = SessionManifest(
        schema_version=schema_version,
        session_id=_req_str(obj, "session_id"),
        created_utc=_req_str(obj, "created_utc"),
        completed_utc=_req_str(obj, "completed_utc"),
        source=_req_enum(obj, "source", SessionSource),
        session_type=_req_enum(obj, "session_type", SessionType),
        sample_rate_hz=_req_float(obj, "sample_rate_hz"),
        duration_s=_req_float(obj, "duration_s"),
        sample_count=_req_int(obj, "sample_count"),
        line_frequency_hz=_req_float(obj, "line_frequency_hz"),
        profile=_opt_str(obj, "profile"),
        baseline_session=_opt_str(obj, "baseline_session"),
        parameters=_parse_parameters(obj),
        ch1=_parse_channel(obj, "ch1"),
        ch2=(_parse_channel(obj, "ch2") if _req(obj, "ch2") is not None else None),
        acquisition_telemetry=_parse_telemetry(obj),
        synthetic_truth=parse_synthetic_truth(_opt_object(obj, "synthetic_truth")),
        ch1_setup=ch1_setup,
    )
    _validate_manifest(manifest)
    return manifest


def _reject_unknown_fields(
    obj: Mapping[str, object],
    allowed: frozenset[str],
    context: str,
) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise InputError(f"{context}: неизвестные поля {names}")


def _validate_manifest(manifest: SessionManifest) -> None:
    if manifest.schema_version == SCHEMA_VERSION and manifest.ch1_setup is not None:
        raise InputError("manifest: schema v1 не допускает ch1_setup")
    if manifest.schema_version == CH1_MANIFEST_SCHEMA_VERSION and manifest.ch1_setup is None:
        raise InputError("manifest: schema v2 требует ch1_setup")
    if manifest.schema_version == CH1_MANIFEST_SCHEMA_VERSION:
        _manifest_ch1_setup.validate_session_setup_pairing(
            manifest.session_type,
            manifest.ch1_setup,
        )
    if SESSION_ID_PATTERN.fullmatch(manifest.session_id) is None:
        raise InputError("manifest: небезопасный session_id")
    _validate_parameters(manifest.parameters, manifest.session_id)


def _is_valid_label(value: ParameterValue) -> bool:
    return isinstance(value, str) and bool(value) and value.isprintable() and value == value.strip()


def _validate_parameters(parameters: Mapping[str, ParameterValue], session_id: str) -> None:
    if "seed" in parameters:
        seed = parameters["seed"]
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise InputError("manifest: parameters['seed'] должен быть неотрицательным целым")
    if "label" in parameters and not _is_valid_label(parameters["label"]):
        raise InputError("manifest: parameters['label'] должен быть непустой меткой без отступов")
    series_fields = SERIES_FIELDS.intersection(parameters)
    if series_fields and series_fields != SERIES_FIELDS:
        raise InputError(
            "manifest: параметры series_index/series_total/series_interval_s обязательны вместе"
        )
    if not series_fields:
        return
    index = parameters["series_index"]
    total = parameters["series_total"]
    interval = parameters["series_interval_s"]
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or isinstance(total, bool)
        or not isinstance(total, int)
        or not 1 <= index <= total
        or total < MIN_SERIES_TOTAL
    ):
        raise InputError("manifest: series_index/series_total: неверный размер или индекс")
    if (
        isinstance(interval, bool)
        or not isinstance(interval, int | float)
        or not math.isfinite(interval)
        or interval < 0.0
    ):
        raise InputError("manifest: series_interval_s должен быть конечным и неотрицательным")
    if not session_id.endswith(f"-{index:03d}"):
        raise InputError("manifest: session_id не соответствует series_index")


def _req(obj: Mapping[str, object], key: str) -> object:
    if key not in obj:
        raise InputError(f"manifest: отсутствует поле {key!r}")
    return obj[key]


def _req_str(obj: Mapping[str, object], key: str) -> str:
    value = _req(obj, key)
    if not isinstance(value, str):
        raise InputError(f"manifest: поле {key!r} должно быть строкой")
    return value


def _opt_str(obj: Mapping[str, object], key: str) -> str | None:
    value = _req(obj, key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InputError(f"manifest: поле {key!r} должно быть строкой или null")
    return value


def _req_int(obj: Mapping[str, object], key: str) -> int:
    value = _req(obj, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"manifest: поле {key!r} должно быть целым числом")
    return value


def _req_float(obj: Mapping[str, object], key: str) -> float:
    value = _req(obj, key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InputError(f"manifest: поле {key!r} должно быть числом")
    number = float(value)
    if not math.isfinite(number):
        raise InputError(f"manifest: поле {key!r} должно быть конечным числом")
    return number


def _req_bool(obj: Mapping[str, object], key: str) -> bool:
    value = _req(obj, key)
    if not isinstance(value, bool):
        raise InputError(f"manifest: поле {key!r} должно быть булевым")
    return value


def _req_object(obj: Mapping[str, object], key: str) -> dict[str, object]:
    value = _req(obj, key)
    if not isinstance(value, dict):
        raise InputError(f"manifest: поле {key!r} должно быть JSON-object")
    result: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise InputError(f"manifest: поле {key!r} должно быть JSON-object")
        result[raw_key] = raw_value
    return result


def _opt_object(obj: Mapping[str, object], key: str) -> dict[str, object] | None:
    value = _req(obj, key)
    if value is None:
        return None
    return _req_object(obj, key)


def _req_enum[E: StrEnum](obj: Mapping[str, object], key: str, enum_type: type[E]) -> E:
    raw = _req_str(obj, key)
    try:
        return enum_type(raw)
    except ValueError as error:
        raise InputError(f"manifest: недопустимое значение поля {key!r}: {raw!r}") from error


def _req_int_tuple(obj: Mapping[str, object], key: str) -> tuple[int, ...]:
    value = _req(obj, key)
    if not isinstance(value, list):
        raise InputError(f"manifest: поле {key!r} должно быть списком")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise InputError(f"manifest: элементы {key!r} должны быть целыми числами")
        result.append(item)
    return tuple(result)


def _req_float_tuple(obj: Mapping[str, object], key: str) -> tuple[float, ...]:
    value = _req(obj, key)
    if not isinstance(value, list):
        raise InputError(f"manifest: поле {key!r} должно быть списком")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int | float) or not math.isfinite(item):
            raise InputError(f"manifest: элементы {key!r} должны быть конечными числами")
        result.append(float(item))
    return tuple(result)


def _parse_channel(obj: Mapping[str, object], key: str) -> ChannelMeta:
    channel = _req_object(obj, key)
    _reject_unknown_fields(channel, CHANNEL_FIELDS, key)
    return ChannelMeta(
        filename=_req_str(channel, "filename"),
        role=_req_enum(channel, "role", ChannelRole),
        unit=_req_str(channel, "unit"),
        front_end=_req_str(channel, "front_end"),
        range_code=_req_int(channel, "range_code"),
        probe_multiplier=_req_float(channel, "probe_multiplier"),
    )


def _parse_telemetry(obj: Mapping[str, object]) -> AcquisitionTelemetry | None:
    telemetry = _opt_object(obj, "acquisition_telemetry")
    if telemetry is None:
        return None
    _reject_unknown_fields(telemetry, TELEMETRY_FIELDS, "acquisition_telemetry")
    return AcquisitionTelemetry(
        requested_samples=_req_int(telemetry, "requested_samples"),
        captured_samples=_req_int(telemetry, "captured_samples"),
        callback_count=_req_int(telemetry, "callback_count"),
        block_lengths=_req_int_tuple(telemetry, "block_lengths"),
        callback_gaps_s=_req_float_tuple(telemetry, "callback_gaps_s"),
        expected_block_interval_s=_req_float(telemetry, "expected_block_interval_s"),
        short_block_count=_req_int(telemetry, "short_block_count"),
        ch1_clip_low_count=_req_int(telemetry, "ch1_clip_low_count"),
        ch1_clip_high_count=_req_int(telemetry, "ch1_clip_high_count"),
        ch2_clip_low_count=_req_int(telemetry, "ch2_clip_low_count"),
        ch2_clip_high_count=_req_int(telemetry, "ch2_clip_high_count"),
        calibration_used=_req_bool(telemetry, "calibration_used"),
    )


def _parse_parameters(obj: Mapping[str, object]) -> dict[str, ParameterValue]:
    parameters = _req_object(obj, "parameters")
    result: dict[str, ParameterValue] = {}
    for key, value in parameters.items():
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise InputError(f"manifest: параметры должны быть числами или строками: {key!r}")
        if isinstance(value, float) and not math.isfinite(value):
            raise InputError(f"manifest: параметры должны быть конечными числами: {key!r}")
        result[key] = value
    return result
