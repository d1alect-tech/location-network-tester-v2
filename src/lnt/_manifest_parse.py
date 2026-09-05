"""Разбор фрагментов manifest.json (каналы, телеметрия, параметры)."""

import math
from collections.abc import Mapping
from typing import Final

from lnt._manifest_primitives import (
    _opt_object,
    _reject_unknown_fields,
    _req_bool,
    _req_enum,
    _req_float,
    _req_float_tuple,
    _req_int,
    _req_int_tuple,
    _req_object,
    _req_str,
)
from lnt.errors import InputError
from lnt.types import AcquisitionTelemetry, ChannelMeta, ChannelRole, ParameterValue

__all__ = [
    "CHANNEL_FIELDS",
    "MIN_SERIES_TOTAL",
    "SERIES_FIELDS",
    "TELEMETRY_FIELDS",
    "_is_valid_label",
    "_parse_channel",
    "_parse_parameters",
    "_parse_telemetry",
    "_validate_parameters",
]

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
