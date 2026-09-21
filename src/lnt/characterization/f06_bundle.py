"""F06 bundle assembly: mapped F06 beside an unchanged F01, F02 and F05 family."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f05_bundle import build_f01_f02_f05_bundle
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.models import ArrayReference, CharacterizationBundle, FamilyResult
from lnt.characterization.records import Band, Filter, Status, Support, Unit, Window

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f01_phase_cycle import F01Result
    from lnt.characterization.f02_amplitude_shape import F02Result
    from lnt.characterization.f05_phase_stats import F05Result
    from lnt.characterization.f06_modulation import F06Result
    from lnt.characterization.tables import TableBlock

_F06_ID = "f06_modulation_trajectories"
_F06_INDEX: Final = 5
_F06_UNITS = (Unit.V, Unit.RAD, Unit.HZ)
# F06 тянет траекторию по всей записи: объявленное окно это запись, а не окно F01.
_F06_WINDOW_KIND: Final = "record"
# Траектория хранится разрежённо, кандидаты floor(k * N / M) по записи.
_F06_SELECTION_RULE: Final = "even_floor_index"
_ENTRIES: tuple[tuple[str, str, Unit], ...] = (
    ("f06_envelope_v", "modulation_envelope", Unit.V),
    ("f06_phase_rad", "analytic_phase", Unit.RAD),
    ("f06_frequency_hz", "instantaneous_frequency", Unit.HZ),
)


def build_f01_f02_f05_f06_bundle(  # noqa: PLR0913 - рецепт, канал и сетка записи задают сборку
    f01_result: F01Result,
    f02_result: F02Result,
    f05_result: F05Result,
    f06_result: F06Result,
    recipe: CharacterizationRecipe,
    *,
    measured_channel: str = "ch1",
    sample_rate_hz: float,
    record_duration_s: float,
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Assemble unchanged F01, F02 and F05 beside mapped F06 and twelve placeholders."""
    families = recipe.families
    if len(families) <= _F06_INDEX or families[_F06_INDEX].id != _F06_ID:
        raise CharacterizationError("family_order", "recipe must declare f06 sixth")
    previous, arrays, tables = build_f01_f02_f05_bundle(
        f01_result,
        f02_result,
        f05_result,
        recipe,
        measured_channel=measured_channel,
        record_duration_s=record_duration_s,
    )
    f06_family, f06_arrays = _mapped_f06(
        f06_result,
        families[_F06_INDEX],
        measured_channel,
        float(sample_rate_hz),
        float(record_duration_s),
    )
    bundle = CharacterizationBundle(
        families=(
            *previous.families[:_F06_INDEX],
            f06_family,
            *previous.families[_F06_INDEX + 1 :],
        )
    )
    return bundle, {**arrays, **f06_arrays}, dict(tables)


def _number(family: CharacterizationFamily, name: str) -> float:
    """One declared numeric parameter, refused instead of coerced when it is not a number."""
    raw = family.value(name)
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise CharacterizationError("status_invariant", f"f06 {name} must be a number")
    return float(raw)


def _text(family: CharacterizationFamily, name: str) -> str:
    """One declared textual parameter: filter kind and phase are names, not free text."""
    raw = family.value(name)
    if not isinstance(raw, str) or not raw:
        raise CharacterizationError("status_invariant", f"f06 {name} must be text")
    return raw


def _spec(
    family: CharacterizationFamily,
    *,
    span: float,
    measured_channel: str,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=_F06_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F06_UNITS,
        window=Window(
            kind=_F06_WINDOW_KIND, duration_s=span, sample_count=None, overlap_fraction=0.0
        ),
        # Полоса конверта это объявленная полоса несущей F06, а не полоса STFT:
        # семейство фильтрует именно её, а не отдаёт весь спектр анализа.
        band=Band(low_hz=_number(family, "band_low_hz"), high_hz=_number(family, "band_high_hz")),
        signal_plane=signal_plane_for(measured_channel),
        filter=Filter(
            kind=_text(family, "filter"),
            order=int(_number(family, "filter_order")),
            phase=_text(family, "filter_phase"),
        ),
    )


def _support(result: F06Result, sample_rate_hz: float) -> Support:
    """Спан наблюдения в секундах; остаток записи честно остаётся в missing_count."""
    span = int(result.observation_count)
    missing = int(result.missing_count)
    stored = int(result.stored_count)
    if span < 0 or missing < 0 or stored < 0 or stored > span:
        raise CharacterizationError("status_invariant", "invalid f06 support counts")
    start_s = result.start_sample / sample_rate_hz
    end_s = result.stop_sample / sample_rate_hz
    return Support(
        start_s=start_s, end_s=end_s, duration_s=end_s - start_s,
        sample_count=span + missing, observation_count=span, missing_count=missing,
        stored_count=stored,
        selection_rule="all" if stored == span else _F06_SELECTION_RULE
    )  # fmt: skip


def _source(result: F06Result, array_id: str) -> np.ndarray:
    """One stored trajectory; позиции восстанавливаются объявленным правилом отбора."""
    return {
        "f06_envelope_v": result.amplitudes_v,
        "f06_phase_rad": result.phases_rad,
        "f06_frequency_hz": result.frequencies_hz,
    }[array_id]


def _trajectory(result: F06Result) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    stored = int(result.stored_count)
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for array_id, role, unit in _ENTRIES:
        values = np.asarray(_source(result, array_id), dtype=np.float64)
        if values.shape != (stored,):
            raise CharacterizationError("status_invariant", "f06 arrays must stay aligned")
        arrays[array_id] = values
        refs.append(
            ArrayReference(
                array_id=array_id,
                role=role,
                unit=unit,
                dtype=values.dtype.name,
                shape=(stored,),
                validity_mask_id=None,
                offsets_id=None,
            )
        )
    return arrays, refs


def _mapped_f06(
    result: F06Result,
    family: CharacterizationFamily,
    measured_channel: str,
    sample_rate_hz: float,
    span: float,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    if result.status is Status.UNAVAILABLE:
        if not result.reason_codes:
            raise CharacterizationError("status_invariant", "unavailable f06 needs reasons")
        spec = _spec(
            family,
            span=span,
            measured_channel=measured_channel,
            status=Status.UNAVAILABLE,
            reasons=result.reason_codes,
        )
        return family_envelope(spec, zero_support()), {}
    if result.reason_codes:
        raise CharacterizationError("status_invariant", "available f06 must have no reasons")
    if result.status is not Status.AVAILABLE:
        # Объявленный словарь F06 не знает частичного результата: траектория либо есть, либо нет.
        raise CharacterizationError("status_invariant", "f06 publishes no partial result")
    arrays, refs = _trajectory(result)
    spec = _spec(
        family,
        span=span,
        measured_channel=measured_channel,
        status=Status.AVAILABLE,
        reasons=(),
    )
    envelope = family_envelope(
        spec, _support(result, sample_rate_hz), array_refs=tuple(refs), comparison_summary=()
    )
    return envelope, arrays
