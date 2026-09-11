"""Canonical JSON codec for characterization metadata."""

from __future__ import annotations

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.json_parse import (
    array,
    boolean,
    decode,
    enum,
    enum_value,
    exact,
    integer,
    integer_value,
    mapping,
    number,
    optional_integer,
    optional_number,
    optional_string,
    string,
    strings,
)
from lnt.characterization.metadata_mapping import bundle_mapping
from lnt.characterization.models import (
    ArrayReference,
    CharacterizationBundle,
    FamilyResult,
    TableReference,
)
from lnt.characterization.records import (
    Band,
    Filter,
    Inference,
    Qc,
    ScalarSummary,
    SignalPlane,
    Status,
    Support,
    Unit,
    Window,
)
from lnt.context.json_codec import JsonValue, encode_canonical

_ROOT = frozenset({"schema_version", "families"})
_FAMILY = frozenset(
    [
        "family_id",
        "status",
        "reason_codes",
        "method",
        "method_version",
        "units",
        "window",
        "band",
        "filter",
        "n",
        "support",
        "missing_rule",
        "qc",
        "signal_plane",
        "inference",
        "array_refs",
        "table_refs",
        "comparison_summary",
    ]
)


def encode_metadata(bundle: CharacterizationBundle) -> bytes:
    """Return canonical finite metadata bytes."""
    return encode_canonical(bundle_mapping(bundle), "characterization metadata")


def decode_metadata(data: bytes) -> CharacterizationBundle:
    """Strictly decode and require canonical metadata bytes."""
    raw = decode(data, "characterization metadata")
    exact(raw, _ROOT, "metadata")
    families = array(raw, "families", "metadata")
    bundle = CharacterizationBundle(
        schema_version=integer(raw, "schema_version", "metadata"),
        families=tuple(
            _parse_family(mapping(item, "family"), index) for index, item in enumerate(families)
        ),
    )
    if encode_metadata(bundle) != data:
        raise CharacterizationError("canonical_json", "metadata JSON is not canonical")
    return bundle


def _parse_family(raw: dict[str, JsonValue], index: int) -> FamilyResult:
    label = f"family[{index}]"
    exact(raw, _FAMILY, label)
    window = mapping(raw["window"], f"{label}.window")
    band = mapping(raw["band"], f"{label}.band")
    filter_ = mapping(raw["filter"], f"{label}.filter")
    support = mapping(raw["support"], f"{label}.support")
    qc = mapping(raw["qc"], f"{label}.qc")
    inference = mapping(raw["inference"], f"{label}.inference")
    exact(window, frozenset(["kind", "duration_s", "sample_count", "overlap_fraction"]), "window")
    exact(band, frozenset(["low_hz", "high_hz"]), "band")
    exact(filter_, frozenset(["kind", "order", "phase"]), "filter")
    exact(
        support,
        frozenset(
            [
                "start_s",
                "end_s",
                "duration_s",
                "sample_count",
                "observation_count",
                "missing_count",
                "stored_count",
                "selection_rule",
            ]
        ),
        "support",
    )
    exact(qc, frozenset(["passed", "reason_codes"]), "qc")
    exact(
        inference,
        frozenset(["estimate_scope", "population_inference", "reason_code"]),
        "inference",
    )
    return FamilyResult(
        family_id=string(raw, "family_id", label),
        status=enum(raw, "status", Status, label),
        reason_codes=strings(raw, "reason_codes", label),
        method=string(raw, "method", label),
        method_version=integer(raw, "method_version", label),
        units=tuple(enum_value(value, Unit, "units") for value in array(raw, "units", label)),
        window=Window(
            kind=string(window, "kind", label),
            duration_s=optional_number(window, "duration_s", label),
            sample_count=optional_integer(window, "sample_count", label),
            overlap_fraction=number(window, "overlap_fraction", label),
        ),
        band=Band(low_hz=number(band, "low_hz", label), high_hz=number(band, "high_hz", label)),
        filter=Filter(
            kind=string(filter_, "kind", label),
            order=optional_integer(filter_, "order", label),
            phase=string(filter_, "phase", label),
        ),
        n=integer(raw, "n", label),
        support=Support(
            start_s=number(support, "start_s", label),
            end_s=number(support, "end_s", label),
            duration_s=number(support, "duration_s", label),
            sample_count=integer(support, "sample_count", label),
            observation_count=integer(support, "observation_count", label),
            missing_count=integer(support, "missing_count", label),
            stored_count=integer(support, "stored_count", label),
            selection_rule=string(support, "selection_rule", label),
        ),
        missing_rule=string(raw, "missing_rule", label),
        qc=Qc(passed=boolean(qc, "passed", label), reason_codes=strings(qc, "reason_codes", label)),
        signal_plane=enum(raw, "signal_plane", SignalPlane, label),
        inference=Inference(
            estimate_scope=string(inference, "estimate_scope", label),
            population_inference=string(inference, "population_inference", label),
            reason_code=string(inference, "reason_code", label),
        ),
        array_refs=tuple(
            _parse_array(mapping(value, "array_ref")) for value in array(raw, "array_refs", label)
        ),
        table_refs=tuple(
            _parse_table_ref(mapping(value, "table_ref"))
            for value in array(raw, "table_refs", label)
        ),
        comparison_summary=tuple(
            _parse_summary(mapping(value, "summary"))
            for value in array(raw, "comparison_summary", label)
        ),
    )


def _parse_array(raw: dict[str, JsonValue]) -> ArrayReference:
    exact(
        raw,
        frozenset(["array_id", "role", "unit", "dtype", "shape", "validity_mask_id", "offsets_id"]),
        "array_ref",
    )
    return ArrayReference(
        array_id=string(raw, "array_id", "array_ref"),
        role=string(raw, "role", "array_ref"),
        unit=enum(raw, "unit", Unit, "array_ref"),
        dtype=string(raw, "dtype", "array_ref"),
        shape=tuple(
            integer_value(value, "array_ref.shape") for value in array(raw, "shape", "array_ref")
        ),
        validity_mask_id=optional_string(raw, "validity_mask_id", "array_ref"),
        offsets_id=optional_string(raw, "offsets_id", "array_ref"),
    )


def _parse_table_ref(raw: dict[str, JsonValue]) -> TableReference:
    exact(raw, frozenset(["table_id", "role"]), "table_ref")
    return TableReference(
        table_id=string(raw, "table_id", "table_ref"),
        role=string(raw, "role", "table_ref"),
    )


def _parse_summary(raw: dict[str, JsonValue]) -> ScalarSummary:
    exact(raw, frozenset(["name", "value", "unit", "circular"]), "summary")
    return ScalarSummary(
        name=string(raw, "name", "summary"),
        value=number(raw, "value", "summary"),
        unit=enum(raw, "unit", Unit, "summary"),
        circular=boolean(raw, "circular", "summary"),
    )
