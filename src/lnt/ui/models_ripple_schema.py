"""Глубокая проверка ``ripple.json`` v1: идентичности, QC и фон рядом.

Верхний уровень проверяет ``models_ripple``; этот модуль проверяет каждый
вложенный блок, который читает UI, и возвращает идентичность фона для сверки
хэшей на GET. Битое вложенное поле — ``RippleSchemaError("schema_incompatible")``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models_ripple_blocks import (
    validate_bands,
    validate_interval,
    validate_metrics,
    validate_qc,
    validate_selection,
    validate_spectrum,
)
from .models_ripple_primitives import (
    ATTACHMENT_BASES,
    AVAILABILITY,
    CHANNEL_ROLES,
    COMPONENT_BASES,
    OPERATOR_ATTACHMENTS,
    REFERENCE_ASSUMPTIONS,
    SESSION_NAME,
    SESSION_TYPES,
    SETUP_KINDS,
    SOURCES,
    TRANSFER_STATUSES,
    VOLTAGE_PLANES,
    codes,
    enum,
    fail,
    integer,
    list_of,
    number,
    obj,
    sha256,
    text,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def validate_ripple_payload(payload: Mapping[str, object]) -> dict[str, object] | None:
    """Проверяет все вложенные блоки v1; возвращает идентичность фона."""
    _algorithm(payload["algorithm"])
    _options(payload["options"])
    _session(payload["session"], "session", baseline=False)
    _provenance(payload["provenance"])
    _adapter(payload["adapter"])
    validate_selection(payload["selection"], "selection")
    validate_qc(payload["qc"])
    validate_metrics(payload["time_domain"], "time_domain")
    for index, interval in enumerate(list_of(payload["intervals"], "intervals")):
        validate_interval(interval, f"intervals[{index}]")
    validate_spectrum(payload["spectrum"], "spectrum")
    validate_bands(payload["bands"], "bands")
    baseline = payload["baseline"]
    return None if baseline is None else _baseline(baseline)


def _algorithm(value: object) -> None:
    block = obj(value, "algorithm")
    if block.get("id") != "ripple_observed_v1":
        fail("algorithm.id должен быть ripple_observed_v1")
    if type(block.get("version")) is not int or block["version"] != 1:
        fail("algorithm.version должен быть 1")
    if block.get("rms") != "population_centered_float64":
        fail("algorithm.rms должен быть population_centered_float64")


def _options(value: object) -> None:
    block = obj(value, "options")
    low = number(block.get("band_low_hz"), "options.band_low_hz")
    high = number(block.get("band_high_hz"), "options.band_high_hz")
    if low < 0.0 or high <= low:
        fail("options.band_low_hz/high_hz нарушают порядок полосы")
    if number(block.get("interval_window_s"), "options.interval_window_s") <= 0.0:
        fail("options.interval_window_s должен быть > 0")


def _session(value: object, label: str, *, baseline: bool) -> dict[str, object]:
    block = obj(value, label)
    text(block.get("session_id"), f"{label}.session_id")
    sha256(block.get("manifest_sha256"), f"{label}.manifest_sha256")
    sha256(block.get("ch1_sha256"), f"{label}.ch1_sha256")
    if block.get("channel") != "ch1":
        fail(f"{label}.channel должен быть ch1")
    enum(block.get("source"), f"{label}.source", SOURCES)
    if not baseline:
        return block
    if block.get("session_dir") is not None:
        name = text(block["session_dir"], f"{label}.session_dir")
        if SESSION_NAME.fullmatch(name) is None:
            fail(f"{label}.session_dir должен быть именем каталога")
    if "session_type" in block:
        enum(block["session_type"], f"{label}.session_type", SESSION_TYPES)
    if "channel_role" in block:
        enum(block["channel_role"], f"{label}.channel_role", CHANNEL_ROLES)
    if "ch1_setup" in block and block["ch1_setup"] is not None:
        _ch1_setup(block["ch1_setup"], f"{label}.ch1_setup")
    if "device_identity" in block:
        text(block["device_identity"], f"{label}.device_identity")
    if "connection_procedure" in block:
        enum(block["connection_procedure"], f"{label}.connection_procedure", OPERATOR_ATTACHMENTS)
    return block


def _ch1_setup(value: object, label: str) -> None:
    block = obj(value, label)
    kind = enum(block.get("kind"), f"{label}.kind", SETUP_KINDS)
    if kind == "floating_differential_rc_shunt_v1":
        for name in ("resistance_ohm", "c1_f", "c2_f"):
            if number(block.get(name), f"{label}.{name}") <= 0.0:
                fail(f"{label}.{name} должен быть > 0")
        enum(
            block.get("component_values_basis"),
            f"{label}.component_values_basis",
            COMPONENT_BASES,
        )
        enum(
            block.get("reference_assumption"),
            f"{label}.reference_assumption",
            REFERENCE_ASSUMPTIONS,
        )
        return
    if kind == "scope_input_terminated_v1":
        ohms = number(
            block.get("termination_resistance_ohm"),
            f"{label}.termination_resistance_ohm",
        )
        if ohms <= 0.0:
            fail(f"{label}.termination_resistance_ohm должен быть > 0")
        return
    for name in ("nominal_primary_v", "nominal_secondary_v", "probe_multiplier"):
        if number(block.get(name), f"{label}.{name}") <= 0.0:
            fail(f"{label}.{name} должен быть > 0")


def _provenance(value: object) -> None:
    block = obj(value, "provenance")
    if block.get("capture_metadata_basis") != "legacy_capture_metadata_not_adapter_provenance":
        fail("provenance.capture_metadata_basis нарушен")
    enum(block.get("operator_attachment"), "provenance.operator_attachment", OPERATOR_ATTACHMENTS)
    enum(block.get("voltage_plane"), "provenance.voltage_plane", VOLTAGE_PLANES)
    integer(block.get("range_code"), "provenance.range_code")
    if number(block.get("probe_multiplier"), "provenance.probe_multiplier") <= 0.0:
        fail("provenance.probe_multiplier должен быть > 0")
    if block.get("calibration_used") is not None and type(block["calibration_used"]) is not bool:
        fail("provenance.calibration_used должен быть bool или null")
    if block.get("calibration_identity") is not None:
        text(block["calibration_identity"], "provenance.calibration_identity")
    if block.get("hardware_qualification") != "unverified":
        fail("provenance.hardware_qualification должен быть unverified")


def _adapter(value: object) -> None:
    block = obj(value, "adapter")
    if block.get("topology_id") != "series_c_at_dut_tip_x1_v1":
        fail("adapter.topology_id нарушен")
    if number(block.get("cap_nf"), "adapter.cap_nf") <= 0.0:
        fail("adapter.cap_nf должен быть > 0")
    if number(block.get("series_r_ohm"), "adapter.series_r_ohm") < 0.0:
        fail("adapter.series_r_ohm должен быть >= 0")
    if number(block.get("rin_ohm"), "adapter.rin_ohm") <= 0.0:
        fail("adapter.rin_ohm должен быть > 0")
    integer(block.get("probe_multiplier"), "adapter.probe_multiplier", minimum=1)
    enum(block.get("component_values_basis"), "adapter.component_values_basis", COMPONENT_BASES)
    for name in ("rail_nominal_v", "fc_hz", "tau_s", "plateau_gain"):
        if block.get(name) is not None:
            number(block[name], f"adapter.{name}")
    enum(block.get("transfer_status"), "adapter.transfer_status", TRANSFER_STATUSES)
    codes(block.get("assumption_codes"), "adapter.assumption_codes")


def _baseline(value: object) -> dict[str, object]:
    block = obj(value, "baseline")
    session = _session(block.get("session"), "baseline.session", baseline=True)
    if block.get("attachment_basis") not in ATTACHMENT_BASES:
        fail("baseline.attachment_basis имеет недопустимое значение")
    status = enum(block.get("comparison_status"), "baseline.comparison_status", AVAILABILITY)
    reason_codes = codes(block.get("reason_codes"), "baseline.reason_codes")
    if status == "available" and reason_codes:
        fail("baseline: доступное сравнение с кодами причин")
    if status == "unavailable" and not reason_codes:
        fail("baseline: недоступное сравнение без кодов причин")
    if block.get("selection") is not None:
        validate_selection(block["selection"], "baseline.selection")
    validate_metrics(block.get("time_domain"), "baseline.time_domain")
    validate_spectrum(block.get("spectrum"), "baseline.spectrum")
    validate_bands(block.get("bands"), "baseline.bands")
    return session
