"""Строгая сериализация/разбор manifest.json (schema v1/v2) без dataclass-эвристик.

ПРИМЕЧАНИЕ О ВОССТАНОВЛЕНИИ: первые ~4 КБ файла (до середины ``_validate_manifest``)
утрачены при сбое диска и реконструированы по контрактным тестам
(tests/test_manifest.py, tests/test_ch1_manifest_contract.py) и потребителям модуля.
Хвост файла — оригинальный.

Фасад: примитивы, разбор фрагментов и сериализация вынесены в листья
``_manifest_primitives`` / ``_manifest_parse`` / ``_manifest_serialize`` и
ре-экспортируются здесь, чтобы потребители модуля не менялись.
"""

import re
from collections.abc import Mapping
from typing import Final

from lnt import _manifest_ch1_setup
from lnt._manifest_json import JsonValue
from lnt._manifest_parse import (
    CHANNEL_FIELDS,
    MIN_SERIES_TOTAL,
    SERIES_FIELDS,
    TELEMETRY_FIELDS,
    _is_valid_label,
    _parse_channel,
    _parse_parameters,
    _parse_telemetry,
    _validate_parameters,
)
from lnt._manifest_primitives import (
    _opt_object,
    _opt_str,
    _reject_unknown_fields,
    _req,
    _req_bool,
    _req_enum,
    _req_float,
    _req_float_tuple,
    _req_int,
    _req_int_tuple,
    _req_object,
    _req_str,
)
from lnt._manifest_serialize import _serialize_channel, _serialize_telemetry, _serialize_truth
from lnt._manifest_truth import parse_synthetic_truth
from lnt.errors import InputError
from lnt.types import (
    CH1_MANIFEST_SCHEMA_VERSION,
    SCHEMA_VERSION,
    SessionManifest,
    SessionSource,
    SessionType,
)

__all__ = [
    "CH1_MANIFEST_FIELDS",
    "CHANNEL_FIELDS",
    "MANIFEST_FIELDS",
    "MIN_SERIES_TOTAL",
    "SERIES_FIELDS",
    "SESSION_ID_PATTERN",
    "TELEMETRY_FIELDS",
    "_is_valid_label",
    "_opt_object",
    "_opt_str",
    "_parse_channel",
    "_parse_parameters",
    "_parse_telemetry",
    "_reject_unknown_fields",
    "_req",
    "_req_bool",
    "_req_enum",
    "_req_float",
    "_req_float_tuple",
    "_req_int",
    "_req_int_tuple",
    "_req_object",
    "_req_str",
    "_serialize_channel",
    "_serialize_telemetry",
    "_serialize_truth",
    "_validate_manifest",
    "_validate_parameters",
    "manifest_from_mapping",
    "manifest_to_mapping",
]

SESSION_ID_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
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
