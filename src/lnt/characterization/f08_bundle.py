"""Маппер F08: морфология переходных событий в конверт семейства."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f08_result import DECLARED_CODES
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
    from lnt.characterization.f08_result import F08Result

F08_ID: Final = "f08_transient_morphology"
F08_INDEX: Final = 7
_F08_UNITS = (Unit.S, Unit.V, Unit.V2_S, Unit.COUNT, Unit.HZ, Unit.RATIO)
# Фит идёт по спанам событий внутри всей записи, поэтому окно это запись (F04/F06).
_F08_WINDOW_KIND: Final = "record"
_Entry = tuple[str, str, Unit]
# Две группы величин (F08-18): прямые меры публикуются всегда, когда спан измерим,
# а параметры фита при отказе формы отсутствуют. Группы разной длины, поэтому маска
# своя у каждого массива (идиома F04). Внутри группы ``None`` исключается из массива
# целиком, а не заменяется нулём или NaN (идиома F02): снятое событие видно в
# ``Support.missing_count``, а не в выдуманном числе.
_MEASURED: tuple[_Entry, ...] = (
    ("f08_t_rise_s", "rise_time", Unit.S),
    ("f08_v_peak_v", "detrended_peak_amplitude", Unit.V),
    ("f08_v2_s", "span_integral", Unit.V2_S),
    ("f08_n_zc", "zero_crossing_count", Unit.COUNT),
)
_FITTED: tuple[_Entry, ...] = (
    ("f08_f_d_hz", "damped_frequency", Unit.HZ),
    ("f08_tau_d_s", "decay_time_constant", Unit.S),
    ("f08_zeta", "damping_ratio", Unit.RATIO),
    ("f08_residual_fraction", "fit_residual_fraction", Unit.RATIO),
)


def build_f08_family(
    result: F08Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Конверт F08 поверх результата движка: математика не пересчитывается."""
    if family.id != F08_ID:
        raise CharacterizationError("family_order", "f08 mapper needs the f08 family")
    span = float(record_duration_s)
    reasons = _checked_codes(result.reason_codes)
    if result.status is Status.UNAVAILABLE:
        if not reasons:
            raise CharacterizationError("status_invariant", "unavailable f08 needs reasons")
        spec = _spec(family, band, measured_channel, span, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}
    if result.status is Status.AVAILABLE and reasons:
        raise CharacterizationError("status_invariant", "available f08 must have no reasons")
    if result.status is Status.PARTIAL and not reasons:
        raise CharacterizationError("status_invariant", "partial f08 needs reasons")
    measured, fitted = _inventory(result)
    population = _population(result)
    evaluated = int(result.evaluated_event_count)
    if result.status is Status.AVAILABLE and not (len(measured) == len(fitted) == evaluated):
        # AVAILABLE означает, что фит получен для каждого ОЦЕНЁННОГО события (F08-19);
        # снятый капом maximum_events хвост статус не понижает, он виден в missing_count.
        raise CharacterizationError("status_invariant", "available f08 must fit every event")
    partial = result.status is Status.PARTIAL
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for entries in (_MEASURED, _FITTED):
        packed, group_refs = _packed(result, entries, partial=partial)
        arrays.update(packed)
        refs.extend(group_refs)
    spec = _spec(family, band, measured_channel, span, result.status, reasons)
    envelope = family_envelope(
        spec,
        _support(population, len(measured)),
        array_refs=tuple(refs),
        comparison_summary=_summaries(result, len(fitted)),
    )
    return envelope, arrays


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Отсортированные уникальные коды только из объявленного словаря движка."""
    if any(not code or code not in DECLARED_CODES for code in codes):
        raise CharacterizationError("status_invariant", "f08 reasons must use declared codes")
    if len(set(codes)) != len(codes):
        raise CharacterizationError("status_invariant", "f08 reasons must be unique")
    return tuple(sorted(codes))


def _population(result: F08Result) -> int:
    """Полный инвентарь: оценённые события плюс снятый капом ``maximum_events`` хвост."""
    return int(result.evaluated_event_count) + int(result.omitted_event_count)


def _inventory(result: F08Result) -> tuple[list[int], list[int]]:
    """Индексы измеренных спанов и подогнанных событий публикуемого результата."""
    population = _population(result)
    measured = _observed(result, _MEASURED, population)
    fitted = _observed(result, _FITTED, population)
    if not fitted:
        # Без единого фита движок объявляет UNAVAILABLE (F08-19): публикация ложна.
        raise CharacterizationError("status_invariant", "published f08 needs a fitted event")
    if not set(fitted) <= set(measured):
        raise CharacterizationError("status_invariant", "f08 fit needs a measured span")
    return measured, fitted


def _observed(result: F08Result, entries: tuple[_Entry, ...], population: int) -> list[int]:
    """Индексы непустых величин группы; рисунок ``None`` обязан быть общим."""
    columns = [_source(result, array_id) for array_id, _, _ in entries]
    if any(len(column) != population for column in columns):
        raise CharacterizationError("status_invariant", "f08 tuples must cover the inventory")
    if len({tuple(value is None for value in column) for column in columns}) != 1:
        raise CharacterizationError("status_invariant", "f08 group columns must stay aligned")
    return [index for index, value in enumerate(columns[0]) if value is not None]


def _source(result: F08Result, array_id: str) -> tuple[float | None, ...] | tuple[int | None, ...]:
    """Один объявленный кортеж результата по идентификатору массива."""
    return {
        "f08_t_rise_s": result.t_rise_s,
        "f08_v_peak_v": result.v_peak_v,
        "f08_v2_s": result.v2_s,
        "f08_n_zc": result.n_zc,
        "f08_f_d_hz": result.f_d_hz,
        "f08_tau_d_s": result.tau_d_s,
        "f08_zeta": result.zeta,
        "f08_residual_fraction": result.residual_fraction,
    }[array_id]


def _packed(
    result: F08Result, entries: tuple[_Entry, ...], *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Массивы группы: хранятся только измеренные события, частичность объявляет маска."""
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for array_id, role, unit in entries:
        validate_unit_name(array_id, unit)
        values = [value for value in _source(result, array_id) if value is not None]
        column = np.asarray(values, dtype=np.int64 if unit is Unit.COUNT else np.float64)
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
    return arrays, refs


def _spec(  # noqa: PLR0913, PLR0917 - конверт несёт весь объявленный инвариант семейства
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F08_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F08_UNITS,
        window=Window(
            kind=_F08_WINDOW_KIND, duration_s=span, sample_count=None, overlap_fraction=0.0
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _support(population: int, observation: int) -> Support:
    """Учёт по событиям: снятые капом и отклонённые остаются в ``missing_count``.

    Интервал вырожден, как у F02: позиций событий в ``F08Result`` нет, поэтому
    объявлять наблюденные секунды записи значило бы выдумать поддержку.
    """
    return Support(
        start_s=0.0, end_s=0.0, duration_s=0.0, sample_count=population,
        observation_count=observation, missing_count=population - observation,
        stored_count=observation, selection_rule="all"
    )  # fmt: skip


def _summaries(result: F08Result, fitted: int) -> tuple[ScalarSummary, ...]:
    """Счётчики инвентаря и число подогнанных событий.

    Третий счётчик нужен потому, что длина группы фита из поддержки не
    восстанавливается: ``observation_count`` считает измеренные спаны, а не фиты.
    """
    return (
        ScalarSummary(
            name="f08_evaluated_event_count",
            value=float(result.evaluated_event_count),
            unit=Unit.COUNT,
        ),
        ScalarSummary(
            name="f08_omitted_event_count",
            value=float(result.omitted_event_count),
            unit=Unit.COUNT,
        ),
        ScalarSummary(name="f08_fitted_event_count", value=float(fitted), unit=Unit.COUNT),
    )
