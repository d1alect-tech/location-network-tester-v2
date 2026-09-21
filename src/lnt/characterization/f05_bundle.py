"""F05 bundle assembly: mapped F05 beside an unchanged F01 and F02 family."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f02_bundle import build_f01_f02_bundle
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
    from lnt.characterization.f05_phase_stats import F05Result
    from lnt.characterization.tables import TableBlock

_F05_ID = "f05_phase_conditioned_statistics"
_F05_INDEX: Final = 4
_F05_UNITS = (Unit.V, Unit.V2, Unit.RATIO, Unit.COUNT, Unit.RAD)
# F05 не нарезает запись окнами: все годные циклы складываются в общие бины,
# поэтому объявленное окно это вся запись, а не окно F01.
_F05_WINDOW_KIND: Final = "record"
_MASK_ID: Final = "f05_bins_valid"
_ENTRIES: tuple[tuple[str, str, Unit], ...] = (
    ("f05_mu_v", "bin_mean", Unit.V),
    ("f05_sigma2_v2", "bin_variance", Unit.V2),
    ("f05_ms_v2", "bin_mean_square", Unit.V2),
    ("f05_p_event", "bin_event_probability", Unit.RATIO),
    ("f05_n_b", "bin_support", Unit.COUNT),
)


def build_f01_f02_f05_bundle(  # noqa: PLR0913 - рецепт, канал и длина записи задают сборку
    f01_result: F01Result,
    f02_result: F02Result,
    f05_result: F05Result,
    recipe: CharacterizationRecipe,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Assemble unchanged F01 and F02 beside mapped F05 and thirteen placeholders."""
    families = recipe.families
    if len(families) <= _F05_INDEX or families[_F05_INDEX].id != _F05_ID:
        raise CharacterizationError("family_order", "recipe must declare f05 fifth")
    f01_f02, arrays, tables = build_f01_f02_bundle(
        f01_result, f02_result, recipe, measured_channel=measured_channel
    )
    span = float(record_duration_s)
    band = Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)
    f05_family, f05_arrays = _mapped_f05(
        f05_result, families[_F05_INDEX], band, measured_channel, span
    )
    before = tuple(not_computed_family(item, band) for item in families[2:_F05_INDEX])
    after = tuple(not_computed_family(item, band) for item in families[_F05_INDEX + 1 :])
    bundle = CharacterizationBundle(
        families=(f01_f02.families[0], f01_f02.families[1], *before, f05_family, *after)
    )
    return bundle, {**arrays, **f05_arrays}, dict(tables)


def _spec(  # noqa: PLR0913 - конверт несёт весь объявленный инвариант семейства
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=_F05_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F05_UNITS,
        window=Window(
            kind=_F05_WINDOW_KIND, duration_s=span, sample_count=None, overlap_fraction=0.0
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _column(result: F05Result, array_id: str) -> np.ndarray:
    """One per-bin column; невалидные бины остаются нулями и объявляются маской."""
    source = {
        "f05_mu_v": result.means_v,
        "f05_sigma2_v2": result.variances_v2,
        "f05_ms_v2": result.mean_squares_v2,
        "f05_p_event": result.event_probabilities,
        "f05_n_b": result.counts,
    }[array_id]
    return np.asarray(source)


def _summaries(result: F05Result) -> tuple[ScalarSummary, ...]:
    """Resultant and direction are published only once peaks were distributed."""
    summaries: list[ScalarSummary] = []
    if result.event_phase_resultant is not None:
        summaries.append(
            ScalarSummary(
                name="f05_event_phase_resultant",
                value=float(result.event_phase_resultant),
                unit=Unit.RATIO,
            )
        )
    if result.event_phase_mean_rad is not None:
        summaries.append(
            ScalarSummary(
                name="f05_event_phase_mean_rad",
                value=float(result.event_phase_mean_rad),
                unit=Unit.RAD,
                circular=True,
            )
        )
    return tuple(summaries)


def _mapped_f05(
    result: F05Result,
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    span: float,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    if result.status is Status.UNAVAILABLE:
        if not result.reason_codes:
            raise CharacterizationError("status_invariant", "unavailable f05 needs reasons")
        spec = _spec(
            family,
            band,
            measured_channel=measured_channel,
            span=span,
            status=Status.UNAVAILABLE,
            reasons=result.reason_codes,
        )
        return family_envelope(spec, zero_support()), {}
    if result.status is Status.AVAILABLE and result.reason_codes:
        raise CharacterizationError("status_invariant", "available f05 must have no reasons")
    if result.status is Status.PARTIAL and not result.reason_codes:
        raise CharacterizationError("status_invariant", "partial f05 needs reasons")
    valid = np.asarray(result.valid_bins, dtype=np.bool_)
    bins = int(valid.size)
    partial = result.status is Status.PARTIAL
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    if partial:
        arrays[_MASK_ID] = valid.astype(np.uint8)
    for array_id, role, unit in _ENTRIES:
        column = _column(result, array_id)
        if column.shape != valid.shape:
            raise CharacterizationError("status_invariant", "f05 arrays must stay aligned")
        arrays[array_id] = column
        refs.append(
            ArrayReference(
                array_id=array_id,
                role=role,
                unit=unit,
                dtype=column.dtype.name,
                shape=tuple(int(size) for size in column.shape),
                validity_mask_id=_MASK_ID if partial else None,
                offsets_id=None,
            )
        )
    # Поддержка считается по бинам: гейт рецепта объявлен на бин, а не на запись.
    observation = int(np.count_nonzero(valid))
    support = Support(
        start_s=0.0, end_s=span, duration_s=span, sample_count=bins,
        observation_count=observation, missing_count=bins - observation,
        stored_count=observation, selection_rule="all"
    )  # fmt: skip
    spec = _spec(
        family,
        band,
        measured_channel=measured_channel,
        span=span,
        status=result.status,
        reasons=result.reason_codes,
    )
    envelope = family_envelope(
        spec, support, array_refs=tuple(refs), comparison_summary=_summaries(result)
    )
    return envelope, arrays
