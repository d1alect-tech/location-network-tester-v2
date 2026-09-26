"""F18: locked recipe, metadata, conventions, spec gaps and claim boundary."""

from __future__ import annotations

from typing import Final

import numpy as np

import lnt.characterization.f18_contract as contract
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f18_declarations import locked_declarations
from lnt.characterization.f18_rate_cells import (
    persisted_analysis_rate_hz,
    persisted_segment_samples,
)
from lnt.characterization.f18_result import F18Declarations
from lnt.characterization.f18_triads import declared_triads
from lnt.characterization.records import Unit
from lnt.characterization.tables import TableBlock, TableColumn, TableValueType

__all__ = [
    "BIPHASE_MASK",
    "F18_ARRAY_ENTRIES",
    "F18_METADATA_TABLE_ID",
    "PERSISTED_QUANTITIES",
    "SIGNIFICANT_NAME",
    "TRIAD_AVAILABLE_NAME",
    "F18ArrayEntry",
    "Quantity",
    "bicoherence_metadata",
    "locked_axes",
    "locked_declarations",
    "persisted_analysis_rate_hz",
    "persisted_segment_samples",
]

F18_METADATA_TABLE_ID: Final = "f18_bicoherence_metadata"
TRIAD_AVAILABLE_NAME: Final = "f18_triad_available"
SIGNIFICANT_NAME: Final = "f18_significant"
BIPHASE_MASK: Final = "f18_biphase_valid"
_ROW_COUNT: Final = 1

type Quantity = tuple[str, str, Unit]
type F18ArrayEntry = tuple[str, str, Unit, str, str | None]

F18_ARRAY_ENTRIES: Final[tuple[F18ArrayEntry, ...]] = (
    (contract.TRIAD_LOW_NAME, "triad_low_axis", Unit.HZ, "float64", None),
    (contract.TRIAD_HIGH_NAME, "triad_high_axis", Unit.HZ, "float64", None),
    (contract.TRIAD_SUM_NAME, "triad_sum_axis", Unit.HZ, "float64", None),
    (contract.BICOHERENCE_NAME, "bicoherence_squared", Unit.RATIO, "float64", TRIAD_AVAILABLE_NAME),
    (contract.BIPHASE_NAME, "biphase", Unit.RAD, "float64", BIPHASE_MASK),
    (
        contract.PHASE_RANDOMIZED_P_NAME,
        "phase_randomized_p",
        Unit.RATIO,
        "float64",
        TRIAD_AVAILABLE_NAME,
    ),
    (contract.IAAFT_P_NAME, "iaaft_p", Unit.RATIO, "float64", TRIAD_AVAILABLE_NAME),
    (contract.DUAL_P_NAME, "dual_null_p", Unit.RATIO, "float64", TRIAD_AVAILABLE_NAME),
    (contract.ADJUSTED_P_NAME, "adjusted_p", Unit.RATIO, "float64", TRIAD_AVAILABLE_NAME),
    (TRIAD_AVAILABLE_NAME, "triad_availability", Unit.COUNT, "uint8", None),
    (SIGNIFICANT_NAME, "triad_significance", Unit.COUNT, "uint8", None),
    (contract.FRAME_SUPPORT_NAME, "triad_frame_support", Unit.COUNT, "int64", None),
)
PERSISTED_QUANTITIES: Final[tuple[Quantity, ...]] = (
    ("triad_low", contract.TRIAD_LOW_NAME, Unit.HZ),
    ("triad_high", contract.TRIAD_HIGH_NAME, Unit.HZ),
    ("triad_sum", contract.TRIAD_SUM_NAME, Unit.HZ),
    ("bicoherence", contract.BICOHERENCE_NAME, Unit.RATIO),
    ("biphase", contract.BIPHASE_NAME, Unit.RAD),
    ("phase_randomized_p", contract.PHASE_RANDOMIZED_P_NAME, Unit.RATIO),
    ("iaaft_p", contract.IAAFT_P_NAME, Unit.RATIO),
    ("dual_null_p", contract.DUAL_P_NAME, Unit.RATIO),
    ("adjusted_p", contract.ADJUSTED_P_NAME, Unit.RATIO),
    ("frame_support", contract.FRAME_SUPPORT_NAME, Unit.COUNT),
    ("triad_available", TRIAD_AVAILABLE_NAME, Unit.COUNT),
    ("significant", SIGNIFICANT_NAME, Unit.COUNT),
)


def _columns(
    kind: TableValueType, unit: Unit | None, names: tuple[str, ...]
) -> tuple[TableColumn, ...]:
    return tuple(TableColumn(name=name, unit=unit, type=kind) for name in names)


_COLUMNS: Final = (
    TableColumn(name="family_id", unit=None, type=TableValueType.TEXT),
    *_columns(TableValueType.INTEGER, Unit.COUNT, ("family_index",)),
    TableColumn(name="method", unit=None, type=TableValueType.TEXT),
    *_columns(TableValueType.INTEGER, Unit.COUNT, ("method_version",)),
    *_columns(
        TableValueType.INTEGER,
        Unit.COUNT,
        (
            "phase_bins",
            "segment_samples",
            "maximum_triads",
            "phase_randomized_surrogate_count",
            "iaaft_surrogate_count",
            "iaaft_iterations",
            "surrogate_seed",
            "minimum_frames",
        ),
    ),
    *_columns(TableValueType.TEXT, None, ("window",)),
    # Длительность объявлена, число отсчётов выведено движком: обе формы публикуются,
    # поэтому locked-поверка сверяет только первую, а вторую читают обратно.
    *_columns(TableValueType.NUMBER, Unit.S, ("segment_duration_s",)),
    *_columns(
        TableValueType.NUMBER,
        Unit.RATIO,
        (
            "overlap_fraction",
            "nyquist_fraction_max",
            "iaaft_relative_rms_magnitude_tolerance",
            "false_discovery_rate",
        ),
    ),
    *_columns(
        TableValueType.NUMBER,
        Unit.HZ,
        (
            "analysis_rate_hz",
            "analysis_high_hz",
            *(f"base_frequency_{i}_hz" for i in range(1, 6)),
        ),
    ),
    *_columns(
        TableValueType.TEXT,
        None,
        (
            "dual_null_p_value",
            "multiple_testing",
            "bicoherence_convention",
            "biphase_convention",
            "surrogate_exceedance",
            "dual_null_combination",
            "iaaft_step_order",
            "iaaft_amplitude_rule",
            "iaaft_convergence",
            "iaaft_divergence_reporting",
            "bh_scope",
            "biphase_availability",
            "framed_support_convention",
            "triad_cap_convention",
            "surrogate_phase_mean_convention",
            "seed_stream_convention",
            "triad_rule",
            "frequency_mapping",
            "claim_boundary",
            *(f"spec_gap_{i}" for i in range(1, len(contract.SPEC_GAPS) + 1)),
        ),
    ),
    *_columns(
        TableValueType.TEXT,
        None,
        tuple(
            label
            for _, name, _ in PERSISTED_QUANTITIES
            for label in (f"{name}_quantity_name", f"{name}_unit")
        ),
    ),
)


def bicoherence_metadata(
    declarations: F18Declarations, segment_samples: int, analysis_rate_hz: float
) -> TableBlock:
    """Сохранить весь declared F18 surface без пересказа или сокращений."""
    if declarations != F18Declarations.locked() or len(contract.SPEC_GAPS) != 5:  # noqa: PLR2004
        raise CharacterizationError("status_invariant", "F18 metadata declarations are not locked")
    # Опубликованные частота и сегмент обязаны описывать одну геометрию: сегмент
    # выведен из объявленной длительности по ИЗМЕРЕННОЙ частоте, поэтому непротиворечивая
    # пара доказывает, что таблица не описывает частоту захвата вместо частоты анализа.
    if contract.segment_samples_for(analysis_rate_hz) != segment_samples:
        raise CharacterizationError(
            "status_invariant", "F18 published segment contradicts the published analysis rate"
        )
    values = (
        contract.F18_ID,
        contract.F18_INDEX,
        contract.METHOD,
        1,
        *_recipe_counts(declarations, segment_samples),
        declarations.window,
        declarations.segment_duration_s,
        declarations.overlap_fraction,
        declarations.nyquist_fraction_max,
        declarations.iaaft_relative_rms_magnitude_tolerance,
        declarations.false_discovery_rate,
        analysis_rate_hz,
        declarations.analysis_high_hz,
        *declarations.base_frequencies_hz,
        declarations.dual_null_p_value,
        declarations.multiple_testing,
        contract.BICOHERENCE_CONVENTION,
        contract.BIPHASE_CONVENTION,
        contract.SURROGATE_EXCEEDANCE,
        contract.DUAL_NULL_COMBINATION,
        contract.IAAFT_STEP_ORDER,
        contract.IAAFT_AMPLITUDE_RULE,
        contract.IAAFT_CONVERGENCE,
        contract.IAAFT_DIVERGENCE_REPORTING,
        contract.BH_SCOPE,
        contract.BIPHASE_AVAILABILITY,
        contract.FRAMED_SUPPORT_CONVENTION,
        contract.TRIAD_CAP_CONVENTION,
        contract.SURROGATE_PHASE_MEAN_CONVENTION,
        contract.SEED_STREAM_CONVENTION,
        contract.TRIAD_RULE,
        contract.FREQUENCY_MAPPING,
        contract.CLAIM_BOUNDARY,
        *contract.SPEC_GAPS,
        *_quantity_values(),
    )
    return TableBlock(
        table_id=F18_METADATA_TABLE_ID,
        columns=_COLUMNS,
        rows=(values,),
        row_count=_ROW_COUNT,
        stored_count=_ROW_COUNT,
        selection_rule="all",
    )


# Универсальный column builder определён до module-level schema.


def _recipe_counts(value: F18Declarations, segment_samples: int) -> tuple[int, ...]:
    return (
        value.phase_bins,
        segment_samples,
        value.maximum_triads,
        value.phase_randomized_surrogate_count,
        value.iaaft_surrogate_count,
        value.iaaft_iterations,
        value.surrogate_seed,
        value.minimum_frames,
    )


def _quantity_values() -> tuple[str, ...]:
    return tuple(cell for _, name, unit in PERSISTED_QUANTITIES for cell in (name, unit.value))


def locked_axes(declarations: F18Declarations) -> tuple[np.ndarray, int]:
    """Материализовать declared triad axis и count-cap без rounding."""
    expected = np.asarray(
        declared_triads(declarations.base_frequencies_hz, declarations.maximum_triads),
        dtype=np.float64,
    )
    count = len(declarations.base_frequencies_hz)
    candidate_count = count * (count + 1) // 2
    return expected, max(0, candidate_count - declarations.maximum_triads)
