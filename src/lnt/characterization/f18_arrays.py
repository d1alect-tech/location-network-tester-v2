"""F18: finite arrays, validity masks и strict reconstruction."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.f18_contract import (
    ADJUSTED_P_NAME,
    BICOHERENCE_NAME,
    BIPHASE_NAME,
    DUAL_P_NAME,
    F18_ID,
    FRAME_SUPPORT_NAME,
    IAAFT_P_NAME,
    METHOD,
    PHASE_RANDOMIZED_P_NAME,
    TRIAD_HIGH_NAME,
    TRIAD_LOW_NAME,
    TRIAD_SUM_NAME,
)
from lnt.characterization.f18_result import F18Declarations, F18Result
from lnt.characterization.f18_shaping import (
    check_f18_axes,
    checked_f18_array,
    f18_array_references,
    f18_result_arrays,
    fail_f18_invariant,
    persist_f18_measurement,
    persisted_f18_entry,
    restore_f18_measurement,
    store_f18_array,
)
from lnt.characterization.f18_tables import (
    BIPHASE_MASK,
    F18_METADATA_TABLE_ID,
    SIGNIFICANT_NAME,
    TRIAD_AVAILABLE_NAME,
    bicoherence_metadata,
    locked_axes,
    persisted_segment_samples,
)
from lnt.characterization.f18_tables import (
    F18_ARRAY_ENTRIES as _ENTRIES,
)
from lnt.characterization.f18_validation import validate_f18_result
from lnt.characterization.models import ArrayReference, TableReference
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

# Canonical array schema is imported under its private local name.


def published(
    result: F18Result, declarations: F18Declarations, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Опубликовать finite arrays с явными masks без изменения engine domain."""
    validate_f18_result(result)
    check_f18_axes(result, declarations)
    shape = (result.declared_triad_count,)
    values = f18_result_arrays(result)
    arrays: dict[str, np.ndarray] = {}
    references: list[ArrayReference] = []
    for entry in _ENTRIES:
        array_id, _, _, dtype_name, domain_mask = entry
        checked = checked_f18_array(array_id, values[array_id], dtype_name, shape, domain_mask)
        if domain_mask is not None:
            mask = result.significant if array_id == BIPHASE_NAME else result.triad_available
            checked = persist_f18_measurement(checked, mask)
            arrays[domain_mask] = np.asarray(mask, dtype=np.uint8)
        store_f18_array(arrays, references, entry, checked, partial=partial)
    return arrays, references


def decode_f18_arrays(
    family: FamilyResult,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
    declared_count: int,
    dropped_count: int,
) -> dict[str, np.ndarray]:
    """Восстановить engine-форму из finite persisted arrays и явных масок."""
    declarations = F18Declarations.locked()
    shape = (declared_count,)
    if (
        family.family_id != F18_ID
        or family.method != METHOD
        or family.method_version != 1
        or family.status not in (Status.AVAILABLE, Status.PARTIAL)
        or family.table_refs
        != (TableReference(table_id=F18_METADATA_TABLE_ID, role="bicoherence_metadata"),)
        or set(tables) != {F18_METADATA_TABLE_ID}
    ):
        fail_f18_invariant("F18 persisted identity or metadata is not locked")
    metadata = tables[F18_METADATA_TABLE_ID]
    # Выведенный сегмент читается из самой таблицы: locked-сверка ниже поэтому
    # фиксирует все объявленные ячейки, а rate-зависимую проверяет decoder,
    # восстанавливающий из неё F18Result.segment_samples.
    if metadata != bicoherence_metadata(declarations, persisted_segment_samples(metadata)):
        fail_f18_invariant("F18 persisted identity or metadata is not locked")
    references = f18_array_references(family.status, shape)
    if family.array_refs != tuple(references):
        fail_f18_invariant("F18 persisted array references are not canonical")
    expected_members = {reference.array_id for reference in references} | {
        reference.validity_mask_id
        for reference in references
        if reference.validity_mask_id is not None
    }
    if set(arrays) != expected_members:
        fail_f18_invariant("F18 persisted array members are not canonical")
    values: dict[str, np.ndarray] = {}
    for index, entry in enumerate(_ENTRIES):
        # Entry itself carries id, dtype, and semantic mask.
        values[entry[0]] = persisted_f18_entry(
            arrays, entry, shape, references[index].validity_mask_id
        )
    expected_axis, expected_dropped = locked_axes(declarations)
    actual_axes = np.column_stack(
        (values[TRIAD_LOW_NAME], values[TRIAD_HIGH_NAME], values[TRIAD_SUM_NAME])
    )
    if (
        not np.array_equal(actual_axes, expected_axis)
        or declared_count != expected_axis.shape[0]
        or dropped_count != expected_dropped
    ):
        fail_f18_invariant(
            "F18 persisted triad axes or count-cap accounting differ from declarations"
        )
    available = np.asarray(values[TRIAD_AVAILABLE_NAME], dtype=np.bool_)
    significant = np.asarray(values[SIGNIFICANT_NAME], dtype=np.bool_)
    restored: dict[str, np.ndarray] = {}
    for array_id, mask_id in (
        (BICOHERENCE_NAME, TRIAD_AVAILABLE_NAME),
        (BIPHASE_NAME, BIPHASE_MASK),
        (PHASE_RANDOMIZED_P_NAME, TRIAD_AVAILABLE_NAME),
        (IAAFT_P_NAME, TRIAD_AVAILABLE_NAME),
        (DUAL_P_NAME, TRIAD_AVAILABLE_NAME),
        (ADJUSTED_P_NAME, TRIAD_AVAILABLE_NAME),
    ):
        restored[array_id], _ = restore_f18_measurement(
            values[array_id], np.asarray(arrays[mask_id], dtype=np.bool_)
        )
    restored.update(
        {
            TRIAD_LOW_NAME: values[TRIAD_LOW_NAME].copy(),
            TRIAD_HIGH_NAME: values[TRIAD_HIGH_NAME].copy(),
            TRIAD_SUM_NAME: values[TRIAD_SUM_NAME].copy(),
            FRAME_SUPPORT_NAME: values[FRAME_SUPPORT_NAME].copy(),
            TRIAD_AVAILABLE_NAME: available,
            SIGNIFICANT_NAME: significant,
        }
    )
    return restored
