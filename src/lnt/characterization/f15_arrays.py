"""F15 numeric array layout and feature metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f15_result import (
    FEATURE_NAMES,
    FEATURE_UNITS,
    STABILITY_BLOCK_TOO_SHORT,
)
from lnt.characterization.models import ArrayReference
from lnt.characterization.records import Unit, validate_unit_name
from lnt.characterization.tables import TableBlock, TableColumn, TableValueType

if TYPE_CHECKING:
    from lnt.characterization.f15_result import F15Result

type Entry = tuple[str, str, Unit]

_FEATURE_COUNT: Final = 7
_CLUSTER_COUNT: Final = 4
_STABILITY_COUNT: Final = 8
FEATURE_METADATA_TABLE_ID: Final = "f15_feature_metadata"
_ENTRIES: Final[tuple[Entry, ...]] = (
    ("f15_feature_medians", "feature_median", Unit.RATIO),
    ("f15_feature_mads", "feature_mad", Unit.RATIO),
    ("f15_standardized_features", "standardized_feature", Unit.RATIO),
    ("f15_window_indices", "window_index", Unit.COUNT),
    ("f15_medoid_indices", "medoid_window_index", Unit.COUNT),
    ("f15_medoid_features", "medoid_feature", Unit.RATIO),
    ("f15_medoid_rms_v", "medoid_rms", Unit.V),
    ("f15_labels", "window_label", Unit.COUNT),
    ("f15_dwell_labels", "dwell_label", Unit.COUNT),
    ("f15_dwell_durations_s", "dwell_duration", Unit.S),
    ("f15_transition_counts", "transition_count", Unit.COUNT),
    ("f15_transition_probabilities", "transition_probability", Unit.RATIO),
    ("f15_stability_ari", "stability_adjusted_rand_index", Unit.RATIO),
)


def published(
    result: F15Result, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Publish aligned F15 arrays; partial status adds a mask to each reference."""
    shapes = _shapes(result)
    _check_accounting(result)
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for array_id, role, unit in _ENTRIES:
        values = _value(result, array_id, shapes[array_id], unit=unit)
        mask_id = f"{array_id}_valid" if partial else None
        _store(arrays, refs, (array_id, role, unit), values, mask_id)
    return arrays, refs


def feature_metadata(result: F15Result) -> TableBlock:
    """Publish the locked feature order and each feature's declared unit."""
    if result.feature_names != FEATURE_NAMES:
        raise CharacterizationError("status_invariant", "f15 feature declaration is not locked")
    rows = tuple(
        (index, name, unit.value)
        for index, (name, unit) in enumerate(zip(FEATURE_NAMES, FEATURE_UNITS, strict=True))
    )
    return TableBlock(
        table_id=FEATURE_METADATA_TABLE_ID,
        columns=(
            TableColumn(name="feature_index", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(name="feature_name", unit=None, type=TableValueType.TEXT),
            TableColumn(name="unit", unit=None, type=TableValueType.TEXT),
        ),
        rows=rows,
        row_count=len(rows),
        stored_count=len(rows),
        selection_rule="all",
    )


def _store(
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
    entry: Entry,
    values: np.ndarray,
    mask_id: str | None,
) -> None:
    array_id, role, unit = entry
    validate_unit_name(array_id, unit)
    if mask_id is not None:
        arrays[mask_id] = np.ones(values.shape, dtype=np.uint8)
    arrays[array_id] = values
    refs.append(
        ArrayReference(
            array_id=array_id,
            role=role,
            unit=unit,
            dtype=values.dtype.name,
            shape=tuple(int(size) for size in values.shape),
            validity_mask_id=mask_id,
            offsets_id=None,
        )
    )


def _shapes(result: F15Result) -> dict[str, tuple[int, ...]]:
    rows = int(result.qualified_window_count)
    stability = (0,) if STABILITY_BLOCK_TOO_SHORT in result.reason_codes else (_STABILITY_COUNT,)
    return {
        "f15_feature_medians": (_FEATURE_COUNT,),
        "f15_feature_mads": (_FEATURE_COUNT,),
        "f15_standardized_features": (rows, _FEATURE_COUNT),
        "f15_window_indices": (rows,),
        "f15_medoid_indices": (_CLUSTER_COUNT,),
        "f15_medoid_features": (_CLUSTER_COUNT, _FEATURE_COUNT),
        "f15_medoid_rms_v": (_CLUSTER_COUNT,),
        "f15_labels": (rows,),
        "f15_dwell_labels": (result.dwell_labels.size,),
        "f15_dwell_durations_s": (result.dwell_durations_s.size,),
        "f15_transition_counts": (_CLUSTER_COUNT, _CLUSTER_COUNT),
        "f15_transition_probabilities": (_CLUSTER_COUNT, _CLUSTER_COUNT),
        "f15_stability_ari": stability,
    }


def _value(
    result: F15Result, array_id: str, expected: tuple[int, ...], *, unit: Unit
) -> np.ndarray:
    source = {
        "f15_feature_medians": result.feature_medians,
        "f15_feature_mads": result.feature_mads,
        "f15_standardized_features": result.standardized_features,
        "f15_window_indices": result.window_indices,
        "f15_medoid_indices": result.medoid_indices,
        "f15_medoid_features": result.medoid_features,
        "f15_medoid_rms_v": result.medoid_rms_v,
        "f15_labels": result.labels,
        "f15_dwell_labels": result.dwell_labels,
        "f15_dwell_durations_s": result.dwell_durations_s,
        "f15_transition_counts": result.transition_counts,
        "f15_transition_probabilities": result.transition_probabilities,
        "f15_stability_ari": result.stability_ari,
    }[array_id]
    dtype = np.int64 if unit is Unit.COUNT else np.float64
    values = np.asarray(source, dtype=dtype)
    if values.shape != expected:
        raise CharacterizationError("status_invariant", f"f15 array {array_id} has wrong shape")
    if not bool(np.all(np.isfinite(values))):
        raise CharacterizationError("status_invariant", f"f15 array {array_id} is nonfinite")
    return values


def _check_accounting(result: F15Result) -> None:
    """Check relationships that make the published domain self-consistent."""
    labels = np.asarray(result.labels, dtype=np.int64)
    counts = np.asarray(result.transition_counts, dtype=np.int64)
    probabilities = np.asarray(result.transition_probabilities, dtype=np.float64)
    if (
        labels.ndim != 1
        or labels.size == 0
        or bool(np.any((labels < 0) | (labels >= _CLUSTER_COUNT)))
        or counts.shape != (_CLUSTER_COUNT, _CLUSTER_COUNT)
        or probabilities.shape != (_CLUSTER_COUNT, _CLUSTER_COUNT)
    ):
        raise CharacterizationError("status_invariant", "f15 published domains are invalid")
    starts = np.concatenate((np.asarray([0], dtype=np.int64), np.flatnonzero(np.diff(labels)) + 1))
    stops = np.concatenate((starts[1:], np.asarray([labels.size], dtype=np.int64)))
    expected_labels = labels[starts]
    expected_durations = (stops - starts).astype(np.float64) * result.window_s
    if not np.array_equal(result.dwell_labels, expected_labels) or not np.allclose(
        result.dwell_durations_s, expected_durations, rtol=0.0, atol=1e-12
    ):
        raise CharacterizationError("status_invariant", "f15 dwell accounting is inconsistent")
    expected_counts = np.zeros((_CLUSTER_COUNT, _CLUSTER_COUNT), dtype=np.int64)
    if labels.size > 1:
        np.add.at(expected_counts, (labels[:-1], labels[1:]), 1)
    if not np.array_equal(counts, expected_counts):
        raise CharacterizationError("status_invariant", "f15 transition accounting is inconsistent")
    totals = np.sum(counts, axis=1, keepdims=True)
    expected_probabilities = np.divide(
        counts, totals, out=np.zeros_like(counts, dtype=np.float64), where=totals != 0
    )
    if not np.array_equal(probabilities, expected_probabilities):
        raise CharacterizationError(
            "status_invariant", "f15 transition probabilities are inconsistent"
        )
