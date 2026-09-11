"""JSON mappings for immutable characterization metadata."""

from lnt.characterization.models import CharacterizationBundle, FamilyResult
from lnt.context.json_codec import JsonValue


def bundle_mapping(bundle: CharacterizationBundle) -> dict[str, JsonValue]:
    """Map one complete bundle to JSON values."""
    return {
        "schema_version": bundle.schema_version,
        "families": [family_mapping(item) for item in bundle.families],
    }


def family_mapping(item: FamilyResult) -> dict[str, JsonValue]:
    """Map one family envelope to exact JSON fields."""
    return {
        "family_id": item.family_id,
        "status": item.status.value,
        "reason_codes": list(item.reason_codes),
        "method": item.method,
        "method_version": item.method_version,
        "units": [unit.value for unit in item.units],
        "window": {
            "kind": item.window.kind,
            "duration_s": item.window.duration_s,
            "sample_count": item.window.sample_count,
            "overlap_fraction": item.window.overlap_fraction,
        },
        "band": {"low_hz": item.band.low_hz, "high_hz": item.band.high_hz},
        "filter": {
            "kind": item.filter.kind,
            "order": item.filter.order,
            "phase": item.filter.phase,
        },
        "n": item.n,
        "support": {
            "start_s": item.support.start_s,
            "end_s": item.support.end_s,
            "duration_s": item.support.duration_s,
            "sample_count": item.support.sample_count,
            "observation_count": item.support.observation_count,
            "missing_count": item.support.missing_count,
            "stored_count": item.support.stored_count,
            "selection_rule": item.support.selection_rule,
        },
        "missing_rule": item.missing_rule,
        "qc": {"passed": item.qc.passed, "reason_codes": list(item.qc.reason_codes)},
        "signal_plane": item.signal_plane.value,
        "inference": {
            "estimate_scope": item.inference.estimate_scope,
            "population_inference": item.inference.population_inference,
            "reason_code": item.inference.reason_code,
        },
        "array_refs": [
            {
                "array_id": ref.array_id,
                "role": ref.role,
                "unit": ref.unit.value,
                "dtype": ref.dtype,
                "shape": list(ref.shape),
                "validity_mask_id": ref.validity_mask_id,
                "offsets_id": ref.offsets_id,
            }
            for ref in item.array_refs
        ],
        "table_refs": [{"table_id": ref.table_id, "role": ref.role} for ref in item.table_refs],
        "comparison_summary": [
            {
                "name": value.name,
                "value": value.value,
                "unit": value.unit.value,
                "circular": value.circular,
            }
            for value in item.comparison_summary
        ],
    }
