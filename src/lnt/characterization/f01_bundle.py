"""F01 bundle assembly over the exact eighteen ordered families."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    not_computed_family,
    signal_plane_for,
)
from lnt.characterization.models import (
    ArrayReference,
    CharacterizationBundle,
    FamilyResult,
    TableReference,
)
from lnt.characterization.records import (
    Band,
    ScalarSummary,
    Status,
    Support,
    Unit,
    Window,
)
from lnt.characterization.tables import TableBlock, TableColumn, TableValueType

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from lnt.analysis_store import CharacterizationRecipe
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f01_phase_cycle import F01Result

_F01_ID = "f01_phase_cycle"
_WINDOW_KIND = "fixed"
_UNITS = (Unit.HZ, Unit.V, Unit.RAD, Unit.RATIO)
_TABLE_ID = "f01_harmonics"


def build_f01_bundle(
    result: F01Result,
    recipe: CharacterizationRecipe,
    *,
    measured_channel: str = "ch1",
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Assemble F01 outputs with seventeen not_computed placeholders."""
    families = recipe.families
    if not families or families[0].id != _F01_ID:
        raise CharacterizationError("family_order", "recipe must start with f01_phase_cycle")
    raw_window = families[0].value("window_s")
    if isinstance(raw_window, bool) or not isinstance(raw_window, int | float):
        raise CharacterizationError("status_invariant", "f01 window_s must be a number")
    window_s = float(raw_window)
    band = Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)
    support = _support(result, window_s)
    if result.status is Status.UNAVAILABLE:
        family = _unavailable_f01(result, families[0], support, window_s, band, measured_channel)
        rest = tuple(not_computed_family(item, band) for item in families[1:])
        return CharacterizationBundle(families=(family, *rest)), {}, {}
    family, arrays, tables = _mapped_f01(
        result, families[0], support, window_s, band, measured_channel
    )
    rest = tuple(not_computed_family(item, band) for item in families[1:])
    return CharacterizationBundle(families=(family, *rest)), arrays, tables


def _support(result: F01Result, window_s: float) -> Support:
    total = result.window_count
    evaluated = result.evaluated_window_count
    if total < 0 or evaluated < 0 or evaluated > total:
        raise CharacterizationError("status_invariant", "invalid f01 window counts")
    end_s = float(total) * window_s
    missing = total - evaluated
    return Support(
        start_s=0.0, end_s=end_s, duration_s=end_s, sample_count=total,
        observation_count=evaluated, missing_count=missing,
        stored_count=evaluated, selection_rule="all"
    )  # fmt: skip


def _spec(  # noqa: PLR0913, PLR0917 - конверт несёт весь инвариант семейства
    family: CharacterizationFamily,
    band: Band,
    window_s: float,
    measured_channel: str,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=_F01_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_UNITS,
        window=Window(
            kind=_WINDOW_KIND, duration_s=window_s, sample_count=None, overlap_fraction=0.0
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _unavailable_f01(  # noqa: PLR0913, PLR0917 - маппинг F01 несёт контекст семейства
    result: F01Result,
    family: CharacterizationFamily,
    support: Support,
    window_s: float,
    band: Band,
    measured_channel: str,
) -> FamilyResult:
    if not result.reason_codes:
        raise CharacterizationError("status_invariant", "unavailable f01 needs reasons")
    outputs = (
        result.f1_hz,
        result.c_k_v,
        result.phi_rel_k_rad,
        result.phase_resultant_k,
        result.x_template_v,
    )
    if any(value is not None for value in outputs):
        raise CharacterizationError("status_invariant", "unavailable f01 must have no outputs")
    spec = _spec(family, band, window_s, measured_channel, Status.UNAVAILABLE, result.reason_codes)
    return family_envelope(spec, support)


def _mapped_f01(  # noqa: PLR0913, PLR0917 - маппинг F01 несёт контекст семейства
    result: F01Result,
    family: CharacterizationFamily,
    support: Support,
    window_s: float,
    band: Band,
    measured_channel: str,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    f1_hz = result.f1_hz
    c_k_raw = result.c_k_v
    phi_raw = result.phi_rel_k_rad
    resultant_raw = result.phase_resultant_k
    template_raw = result.x_template_v
    if (
        f1_hz is None
        or c_k_raw is None
        or phi_raw is None
        or resultant_raw is None
        or template_raw is None
    ):
        raise CharacterizationError("status_invariant", "mapped f01 needs all outputs")
    if result.status is Status.AVAILABLE and result.reason_codes:
        raise CharacterizationError("status_invariant", "available f01 must have no reasons")
    if result.status is Status.PARTIAL and not result.reason_codes:
        raise CharacterizationError("status_invariant", "partial f01 needs reasons")
    if result.status is Status.UNAVAILABLE:
        raise CharacterizationError("status_invariant", "unexpected unavailable f01")
    c_k = np.asarray(c_k_raw, dtype=np.complex128)
    phi = np.asarray(phi_raw, dtype=np.float64)
    template = np.asarray(template_raw, dtype=np.float64)
    resultant = np.asarray(resultant_raw, dtype=np.float64)
    partial = result.status is Status.PARTIAL
    entries: tuple[tuple[str, str, Unit, np.ndarray], ...] = (
        ("f01_c_k_v", "harmonic_coefficients", Unit.V, c_k),
        ("f01_phi_rel_k_rad", "relative_phase", Unit.RAD, phi),
        ("f01_x_template_v", "aligned_cycle_template", Unit.V, template),
    )
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for array_id, role, unit, values in entries:
        mask_id = f"{array_id.removesuffix('_v').removesuffix('_rad')}_valid" if partial else None
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
    table = _harmonics_table(c_k, phi, resultant)
    spec = _spec(family, band, window_s, measured_channel, result.status, result.reason_codes)
    envelope = family_envelope(
        spec,
        support,
        array_refs=tuple(refs),
        table_refs=(TableReference(table_id=_TABLE_ID, role="harmonic_inventory"),),
        comparison_summary=(ScalarSummary(name="f1_hz", value=float(f1_hz), unit=Unit.HZ),),
    )
    return envelope, arrays, {_TABLE_ID: table}


def _harmonics_table(
    c_k: NDArray[np.complex128],
    phi: NDArray[np.float64],
    resultant: NDArray[np.float64],
) -> TableBlock:
    rows = tuple(
        (index + 1, float(abs(c_k[index])), float(phi[index]), float(resultant[index]))
        for index in range(int(c_k.size))
    )
    count = len(rows)
    return TableBlock(
        table_id=_TABLE_ID,
        columns=(
            TableColumn(name="harmonic_order", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(name="c_k_mag_v", unit=Unit.V, type=TableValueType.NUMBER),
            TableColumn(name="phi_rel_k_rad", unit=Unit.RAD, type=TableValueType.NUMBER),
            TableColumn(name="phase_resultant", unit=Unit.RATIO, type=TableValueType.NUMBER),
        ),
        rows=rows,
        row_count=count,
        stored_count=count,
        selection_rule="all",
    )
