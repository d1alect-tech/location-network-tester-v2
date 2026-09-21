"""F02 bundle assembly: mapped F02 beside an unchanged F01 family."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f01_bundle import build_f01_bundle
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    not_computed_family,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.models import ArrayReference, CharacterizationBundle, FamilyResult
from lnt.characterization.records import Band, ScalarSummary, Status, Support, Unit, Window

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f01_phase_cycle import F01Result
    from lnt.characterization.f02_amplitude_shape import F02Result
    from lnt.characterization.tables import TableBlock

_F02_ID = "f02_amplitude_time_shape"
_F02_INDEX: Final = 1
_F02_UNITS = (Unit.RATIO, Unit.S, Unit.V2_S)
_F02_WINDOW = Window(kind="event", duration_s=None, sample_count=None, overlap_fraction=0.0)
_ENTRIES: tuple[tuple[str, str, Unit], ...] = (
    ("f02_a", "amplitude_scale", Unit.RATIO),
    ("f02_tau_s", "time_shift", Unit.S),
    ("f02_rho", "residual_fraction", Unit.RATIO),
    ("f02_e_res_v2_s", "residual_energy", Unit.V2_S),
)


def build_f01_f02_bundle(
    f01_result: F01Result,
    f02_result: F02Result,
    recipe: CharacterizationRecipe,
    *,
    measured_channel: str = "ch1",
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Assemble an unchanged F01 family, mapped F02, and sixteen not_computed slots."""
    families = recipe.families
    if len(families) <= _F02_INDEX or families[_F02_INDEX].id != _F02_ID:
        raise CharacterizationError("family_order", "recipe must declare f02 second")
    f01_bundle, f01_arrays, f01_tables = build_f01_bundle(
        f01_result, recipe, measured_channel=measured_channel
    )
    band = Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)
    f02_family, f02_arrays = _mapped_f02(f02_result, families[_F02_INDEX], band, measured_channel)
    rest = tuple(not_computed_family(item, band) for item in families[_F02_INDEX + 1 :])
    bundle = CharacterizationBundle(families=(f01_bundle.families[0], f02_family, *rest))
    return bundle, {**f01_arrays, **f02_arrays}, dict(f01_tables)


def _spec(
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=_F02_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F02_UNITS,
        window=_F02_WINDOW,
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _column(result: F02Result, array_id: str, fitted: list[int]) -> np.ndarray:
    """Pack only the fitted events; rejected slots stay out of the stored arrays."""
    source = {
        "f02_a": result.amplitudes,
        "f02_tau_s": result.delays_s,
        "f02_rho": result.residual_fractions,
        "f02_e_res_v2_s": result.residual_energies_v2_s,
    }[array_id]
    values = [value for value in (source[index] for index in fitted) if value is not None]
    return np.asarray(values, dtype=np.float64)


def _mapped_f02(
    result: F02Result,
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    if result.status is Status.UNAVAILABLE:
        if not result.reason_codes:
            raise CharacterizationError("status_invariant", "unavailable f02 needs reasons")
        spec = _spec(family, band, measured_channel, Status.UNAVAILABLE, result.reason_codes)
        return family_envelope(spec, zero_support()), {}
    if result.status is Status.AVAILABLE and result.reason_codes:
        raise CharacterizationError("status_invariant", "available f02 must have no reasons")
    if result.status is Status.PARTIAL and not result.reason_codes:
        raise CharacterizationError("status_invariant", "partial f02 needs reasons")
    fitted = [index for index, value in enumerate(result.amplitudes) if value is not None]
    evaluated = int(result.evaluated_event_count)
    omitted = int(result.omitted_event_count)
    # Полный инвентарь: подогнанные + отвергнутые + усечённый хвост за
    # maximum_events. Хвост обязан быть виден в учёте поддержки, иначе запись
    # длиннее капа публикует семейство как полное.
    population = evaluated + omitted
    observation = len(fitted)
    partial = result.status is Status.PARTIAL
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    columns: list[np.ndarray] = []
    for array_id, role, unit in _ENTRIES:
        column = _column(result, array_id, fitted)
        columns.append(column)
        mask_id = f"{array_id}_valid" if partial else None
        if mask_id is not None:
            arrays[mask_id] = np.ones(column.shape, dtype=np.uint8)
        arrays[array_id] = column
        refs.append(
            ArrayReference(
                array_id=array_id,
                role=role,
                unit=unit,
                dtype=column.dtype.name,
                shape=tuple(int(size) for size in column.shape),
                validity_mask_id=mask_id,
                offsets_id=None,
            )
        )
    # _column фильтрует None независимо по каждому массиву, поэтому несогласованная
    # F02Result дала бы столбцы разной длины и битый бандл.
    if len({int(column.size) for column in columns}) != 1:
        raise CharacterizationError("status_invariant", "f02 arrays must stay aligned")
    support = Support(
        start_s=0.0, end_s=0.0, duration_s=0.0, sample_count=population,
        observation_count=observation, missing_count=population - observation,
        stored_count=observation, selection_rule="all"
    )  # fmt: skip
    spec = _spec(family, band, measured_channel, result.status, result.reason_codes)
    summary = (
        ScalarSummary(name="f02_event_count", value=float(observation), unit=Unit.COUNT),
        ScalarSummary(name="f02_omitted_event_count", value=float(omitted), unit=Unit.COUNT),
    )
    envelope = family_envelope(spec, support, array_refs=tuple(refs), comparison_summary=summary)
    return envelope, arrays
