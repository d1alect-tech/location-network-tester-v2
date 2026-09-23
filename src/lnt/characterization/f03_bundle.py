"""Маппер F03: треки интергармоник в конверт семейства."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.models import ArrayReference, FamilyResult
from lnt.characterization.records import (
    Band,
    ScalarSummary,
    Status,
    Support,
    Unit,
    Window,
    validate_unit_name,
)

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f03_result import F03Result

F03_ID: Final = "f03_interharmonic_tracking"
F03_INDEX: Final = 2
_F03_UNITS = (Unit.HZ, Unit.V, Unit.S, Unit.COUNT)
_F03_WINDOW_KIND: Final = "fixed"
# Словарь семейства замкнут: движок других кодов не выдаёт.
_F03_CODES: Final = frozenset(
    {
        "below_resolution",
        "peak_not_observed",
        "track_too_short",
        "leakage_ambiguous",
        "grid_unstable",
    }
)
_ENTRIES: tuple[tuple[str, str, Unit], ...] = (
    ("f03_f_hz", "track_center_frequency", Unit.HZ),
    ("f03_a_v", "track_amplitude", Unit.V),
    ("f03_df_hz", "track_width", Unit.HZ),
    ("f03_t_life_s", "track_lifetime", Unit.S),
    ("f03_windows_observed", "track_presence_count", Unit.COUNT),
    ("f03_windows_missing", "track_gap_count", Unit.COUNT),
)


def build_f03_family(
    result: F03Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    window_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Треки F03 в конверт семейства: векторы, маски частичности, учёт."""
    if family.id != F03_ID:
        raise CharacterizationError("family_order", "f03 mapper needs the f03 family")
    span = float(window_s)
    reasons = _checked_codes(result.reason_codes)
    if result.status is Status.UNAVAILABLE:
        if not reasons:
            raise CharacterizationError("status_invariant", "unavailable f03 needs reasons")
        spec = _spec(family, band, measured_channel, span, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}
    if result.status is Status.AVAILABLE and reasons:
        raise CharacterizationError("status_invariant", "available f03 must have no reasons")
    if result.status is Status.PARTIAL and not reasons:
        raise CharacterizationError("status_invariant", "partial f03 needs reasons")
    arrays, refs = _tracks(result, partial=result.status is Status.PARTIAL)
    spec = _spec(family, band, measured_channel, span, result.status, reasons)
    envelope = family_envelope(
        spec,
        _support(result, span),
        array_refs=tuple(refs),
        comparison_summary=_summaries(result),
    )
    return envelope, arrays


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Коды только из объявленного словаря F03, в порядке сортировки."""
    if any(code not in _F03_CODES for code in codes):
        raise CharacterizationError("status_invariant", "f03 reason outside its vocabulary")
    return tuple(sorted(codes))


def _spec(  # noqa: PLR0913, PLR0917 - конверт несёт весь объявленный инвариант семейства
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    window_s: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F03_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F03_UNITS,
        window=Window(
            kind=_F03_WINDOW_KIND, duration_s=window_s, sample_count=None, overlap_fraction=0.0
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _support(result: F03Result, window_s: float) -> Support:
    """Окна в секунды; счётчики один в один из результата."""
    stored = int(result.stored_count)
    if stored != int(result.observation_count):
        raise CharacterizationError("status_invariant", "f03 stored must equal observed")
    end_s = float(result.evaluated_window_count) * window_s
    return Support(
        start_s=0.0, end_s=end_s, duration_s=end_s, sample_count=int(result.sample_count),
        observation_count=int(result.observation_count), missing_count=int(result.missing_count),
        stored_count=stored, selection_rule="all"
    )  # fmt: skip


def _source(result: F03Result, array_id: str) -> np.ndarray:
    """Один хранимый вектор треков."""
    return {
        "f03_f_hz": result.f_hz,
        "f03_a_v": result.a_v,
        "f03_df_hz": result.df_hz,
        "f03_t_life_s": result.t_life_s,
        "f03_windows_observed": result.windows_observed,
        "f03_windows_missing": result.windows_missing,
    }[array_id]


def _tracks(
    result: F03Result, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Векторы треков; частичность объявляется маской единиц на каждый массив."""
    stored = int(result.stored_count)
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for array_id, role, unit in _ENTRIES:
        validate_unit_name(array_id, unit)
        dtype = np.int64 if unit is Unit.COUNT else np.float64
        values = np.asarray(_source(result, array_id), dtype=dtype)
        if values.shape != (stored,):
            raise CharacterizationError("status_invariant", "f03 arrays must stay aligned")
        mask_id = f"{array_id}_valid" if partial else None
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
    return arrays, refs


def _summaries(result: F03Result) -> tuple[ScalarSummary, ...]:
    """Счётчики треков для сравнений: опубликовано и снято капом."""
    return (
        ScalarSummary(
            name="f03_track_count", value=float(result.observation_count), unit=Unit.COUNT
        ),
        ScalarSummary(
            name="f03_omitted_track_count",
            value=float(result.omitted_track_count),
            unit=Unit.COUNT,
        ),
    )
