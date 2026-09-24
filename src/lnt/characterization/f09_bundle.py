"""Маппер F09: переходы, ожидания и кластеры в конверт семейства."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f09_result import DECLARED_CODES
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.models import ArrayReference, FamilyResult, TableReference
from lnt.characterization.records import (
    Band,
    ScalarSummary,
    Status,
    Support,
    Unit,
    Window,
    validate_unit_name,
)
from lnt.characterization.tables import TableBlock, TableColumn, TableValueType

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f09_result import F09Result

F09_ID: Final = "f09_event_ordering"
F09_INDEX: Final = 8
_F09_UNITS = (Unit.S, Unit.COUNT)
# F09 читает инвентарь всей записи: объявленное окно это запись, а не окно F01.
_F09_WINDOW_KIND: Final = "record"
_TABLE_ID: Final = "f09_transitions"
_TABLE_ROLE: Final = "transition_counts"
# Ожидания, серии полярности и кластеры разной длины, поэтому маска своя у каждого ряда.
_ENTRIES: tuple[tuple[str, str, Unit], ...] = (
    ("f09_dt_s", "inter_arrival_time", Unit.S),
    ("f09_polarity_run_lengths", "polarity_run_length", Unit.COUNT),
    ("f09_cluster_start_s", "cluster_start_time", Unit.S),
    ("f09_cluster_spread_s", "cluster_spread", Unit.S),
    ("f09_cluster_sizes", "cluster_size", Unit.COUNT),
)


def build_f09_family(
    result: F09Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Собрать конверт F09 поверх результата движка без пересчёта математики.

    Тезис спеки ``method-notes-families-1-9.md:456-459`` публикуется существующим
    полем ``inference`` конверта (``family_envelope``): циклы одной записи не
    независимые повторы, популяционный вывод отклонён. Нового поля маппер не
    изобретает и числом тезис не подменяет.
    """
    if family.id != F09_ID:
        raise CharacterizationError("family_order", "recipe must declare f09 ninth")
    span = float(record_duration_s)
    if result.status is Status.UNAVAILABLE:
        return _unavailable(result, family, band, measured_channel, span)
    codes = _checked_published(result)
    arrays, refs = _packed(result, partial=result.status is Status.PARTIAL)
    spec = _spec(
        family, band, measured_channel=measured_channel, span=span,
        status=result.status, reasons=codes,
    )  # fmt: skip
    envelope = family_envelope(
        spec,
        _support(result),
        array_refs=tuple(refs),
        table_refs=(TableReference(table_id=_TABLE_ID, role=_TABLE_ROLE),),
        comparison_summary=_summaries(result),
    )
    return envelope, arrays, {_TABLE_ID: _transitions(result)}


def _unavailable(
    result: F09Result,
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    span: float,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Отказ без выдуманных значений: ни массивов, ни таблиц, поддержка нулевая."""
    reasons = _checked_codes(result.reason_codes)
    if not reasons:
        raise CharacterizationError("status_invariant", "unavailable f09 needs reasons")
    spec = _spec(
        family, band, measured_channel=measured_channel, span=span,
        status=Status.UNAVAILABLE, reasons=reasons,
    )  # fmt: skip
    return family_envelope(spec, zero_support()), {}, {}


def _checked_published(result: F09Result) -> tuple[str, ...]:
    """Инварианты публикуемого пути: статус и словарь причин."""
    if result.status is Status.AVAILABLE and result.reason_codes:
        raise CharacterizationError("status_invariant", "available f09 must have no reasons")
    if result.status is Status.PARTIAL and not result.reason_codes:
        raise CharacterizationError("status_invariant", "partial f09 needs reasons")
    if result.status not in (Status.AVAILABLE, Status.PARTIAL):
        raise CharacterizationError("status_invariant", "unknown f09 status")
    return _checked_codes(result.reason_codes)


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Отсортированные уникальные коды только из объявленного словаря движка."""
    if any(not code or code not in DECLARED_CODES for code in codes):
        raise CharacterizationError("status_invariant", "f09 reasons must use declared codes")
    if len(set(codes)) != len(codes):
        raise CharacterizationError("status_invariant", "f09 reasons must be unique")
    return tuple(sorted(codes))


def _series(result: F09Result, array_id: str, unit: Unit) -> np.ndarray:
    """Один хранимый ряд: счётчики целые, времена вещественные."""
    source = {
        "f09_dt_s": result.dt_s,
        "f09_polarity_run_lengths": result.polarity_run_lengths,
        "f09_cluster_start_s": result.cluster_start_s,
        "f09_cluster_spread_s": result.cluster_spread_s,
        "f09_cluster_sizes": result.cluster_sizes,
    }[array_id]
    return np.asarray(source, dtype=np.int64 if unit is Unit.COUNT else np.float64)


def _packed(
    result: F09Result, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Ряды с маской на каждый ряд и проверка, что кластерная тройка вровень."""
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for array_id, role, unit in _ENTRIES:
        validate_unit_name(array_id, unit)
        values = _series(result, array_id, unit)
        if values.ndim != 1:
            raise CharacterizationError("status_invariant", "f09 series must stay one dimensional")
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
                shape=(int(values.size),),
                validity_mask_id=mask_id,
                offsets_id=None,
            )
        )
    sizes = arrays["f09_cluster_sizes"]
    shapes = {
        arrays["f09_cluster_start_s"].shape,
        arrays["f09_cluster_spread_s"].shape,
        sizes.shape,
    }
    if len(shapes) != 1 or int(result.cluster_count) != int(sizes.size):
        raise CharacterizationError("status_invariant", "f09 cluster rows must stay aligned")
    return arrays, refs


def _transitions(result: F09Result) -> TableBlock:
    """Пара меток это ключ строки: счётчик ``n_ij`` в порядке первого появления."""
    if any(int(item.count) <= 0 for item in result.transitions):
        # Нулевые пары движок не публикует (F09-5), поэтому ноль здесь это рассогласование.
        raise CharacterizationError("status_invariant", "f09 transition counts must be positive")
    rows = tuple((item.source, item.target, int(item.count)) for item in result.transitions)
    return TableBlock(
        table_id=_TABLE_ID,
        columns=(
            TableColumn(name="source_label", unit=None, type=TableValueType.TEXT),
            TableColumn(name="target_label", unit=None, type=TableValueType.TEXT),
            TableColumn(name="n_ij", unit=Unit.COUNT, type=TableValueType.INTEGER),
        ),
        rows=rows,
        row_count=len(rows),
        stored_count=len(rows),
        selection_rule="all",
    )


def _summaries(result: F09Result) -> tuple[ScalarSummary, ...]:
    """Готовые счётчики движка один в один: новых чисел маппер не изобретает."""
    published = (
        ("f09_cluster_count", result.cluster_count, Unit.COUNT),
        ("f09_boundary_event_count", result.boundary_event_count, Unit.COUNT),
        ("f09_dead_time_rejected_count", result.dead_time_rejected_count, Unit.COUNT),
        ("f09_gap_count", result.gap_count, Unit.COUNT),
        ("f09_excluded_waiting_interval_count", result.excluded_waiting_interval_count, Unit.COUNT),
        ("f09_omitted_event_count", result.omitted_event_count, Unit.COUNT),
        ("f09_dead_time_s", result.dead_time_s, Unit.S),
    )
    return tuple(
        ScalarSummary(name=name, value=float(value), unit=unit) for name, value, unit in published
    )


def _support(result: F09Result) -> Support:
    """Учёт поддержки один в один из результата (F09-13); интервал точный."""
    start_raw = result.start_s
    end_raw = result.end_s
    if start_raw is None or end_raw is None:
        raise CharacterizationError("status_invariant", "published f09 needs support interval")
    start = float(start_raw)
    end = float(end_raw)
    sample = int(result.sample_count)
    observation = int(result.observation_count)
    missing = int(result.missing_count)
    stored = int(result.stored_count)
    if sample != observation + missing or stored != observation or observation <= 0:
        raise CharacterizationError("status_invariant", "invalid f09 support counts")
    return Support(
        start_s=start, end_s=end, duration_s=end - start, sample_count=sample,
        observation_count=observation, missing_count=missing,
        stored_count=stored, selection_rule="all"
    )  # fmt: skip


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
        family_id=F09_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F09_UNITS,
        window=Window(
            kind=_F09_WINDOW_KIND, duration_s=span, sample_count=None, overlap_fraction=0.0
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )
