"""Накопление и явная публикация 192 ячеек F11."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.f11_result import (
    BIN_EMPTY,
    INSUFFICIENT_SUPPORT,
    QUANTITIES,
    CellKey,
    EventValues,
    F11Cell,
    F11Event,
    F11QuantityResult,
)
from lnt.characterization.records import Status
from lnt.events.models import Polarity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.characterization.f11_contract import F11Settings

_MEASURED_QUANTITY_INDICES: Final = (0, 1, 3)
_FREQUENCY_INDEX: Final = 2


@dataclass(slots=True)
class CellAccumulator:
    """Изменяемый накопитель одного распределения; итоговая запись неизменна."""

    support_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    values: list[list[float]] = field(
        default_factory=lambda: [[] for _ in _MEASURED_QUANTITY_INDICES]
    )


def add_event(
    members: dict[CellKey, CellAccumulator], key: CellKey, event: F11Event, values: EventValues
) -> None:
    """Добавить событие в ячейку и три измеренные непрерывные величины."""
    cell = members.setdefault(key, CellAccumulator())
    cell.support_count += 1
    cell.positive_count += int(event.polarity is Polarity.POSITIVE)
    cell.negative_count += int(event.polarity is Polarity.NEGATIVE)
    for members_for_quantity, value in zip(cell.values, values, strict=True):
        if value is not None:
            members_for_quantity.append(value)


def build_cells(
    members: Mapping[CellKey, CellAccumulator],
    mode_labels: tuple[str, ...],
    settings: F11Settings,
) -> tuple[tuple[F11Cell, ...], tuple[tuple[float, ...], ...]]:
    """Собрать полную сетку и общие сетки CDF."""
    grids = _grids(members, len(settings.cdf_probabilities))
    cells = tuple(
        _cell(
            members.get((phase_bin, band_index, label), CellAccumulator()),
            (phase_bin, band_index, label),
            grids,
            settings,
        )
        for phase_bin in range(settings.phase_bins)
        for band_index in range(len(settings.bands_hz))
        for label in mode_labels
    )
    return cells, grids


def _grids(
    members: Mapping[CellKey, CellAccumulator], points: int
) -> tuple[tuple[float, ...], ...]:
    """Построить общие сетки трёх измеренных величин; частотная сетка пуста."""
    grids: list[tuple[float, ...]] = []
    for index in _MEASURED_QUANTITY_INDICES:
        values_index = _MEASURED_QUANTITY_INDICES.index(index)
        pooled = [value for cell in members.values() for value in cell.values[values_index]]
        if not pooled:
            grids.append(())
            continue
        low, high = min(pooled), max(pooled)
        grid = np.linspace(low, high, points, dtype=np.float64)
        grids.append(tuple(float(value) for value in grid))
    return grids[0], grids[1], (), grids[2]


def _cell(
    member: CellAccumulator,
    key: CellKey,
    grids: tuple[tuple[float, ...], ...],
    settings: F11Settings,
) -> F11Cell:
    """Опубликовать одну ячейку без выдуманных квантилей."""
    distributions = tuple(
        _absent_frequency(member.support_count, settings)
        if index == _FREQUENCY_INDEX
        else _distribution(
            quantity,
            member.values[_MEASURED_QUANTITY_INDICES.index(index)],
            member.support_count,
            grids[index],
            settings,
        )
        for index, quantity in enumerate(QUANTITIES[:-1])
    )
    empty = member.support_count == 0
    under = member.support_count < settings.minimum_support
    partial = any(
        item.status is not Status.AVAILABLE
        for index, item in enumerate(distributions)
        if index != _FREQUENCY_INDEX
    )
    if empty:
        status, codes = Status.UNAVAILABLE, (BIN_EMPTY,)
    elif under or partial:
        status = Status.UNAVAILABLE if under else Status.PARTIAL
        codes = (INSUFFICIENT_SUPPORT,)
    else:
        status, codes = Status.AVAILABLE, ()
    return F11Cell(
        phase_bin=key[0],
        band_index=key[1],
        mode_label=key[2],
        support_count=member.support_count,
        positive_count=member.positive_count,
        negative_count=member.negative_count,
        status=status,
        reason_codes=codes,
        distributions=distributions,
    )


def _absent_frequency(support_count: int, settings: F11Settings) -> F11QuantityResult:
    """Опубликовать структурно недоступную частотную величину без выдуманных значений."""
    return F11QuantityResult(
        quantity="dominant_frequency_hz",
        observed_count=0,
        missing_count=support_count,
        status=Status.UNAVAILABLE,
        reason_codes=(INSUFFICIENT_SUPPORT,),
        quantiles=(None,) * len(settings.quantiles),
        cdf_probabilities=None,
    )


def _distribution(
    quantity: str,
    values: list[float],
    support_count: int,
    grid: tuple[float, ...],
    settings: F11Settings,
) -> F11QuantityResult:
    """Посчитать линейные квантили и правую непрерывную эмпирическую CDF."""
    observed = len(values)
    missing = support_count - observed
    if support_count == 0:
        status, codes = Status.UNAVAILABLE, (BIN_EMPTY,)
    elif observed < settings.minimum_support:
        status, codes = Status.UNAVAILABLE, (INSUFFICIENT_SUPPORT,)
    else:
        status, codes = Status.AVAILABLE, ()
    quantiles_result: tuple[float | None, ...]
    cdf_result: tuple[float, ...] | None
    if status is Status.AVAILABLE:
        ordered = np.sort(np.asarray(values, dtype=np.float64), kind="stable")
        selected = np.quantile(ordered, settings.quantiles, method="linear")
        quantiles_result = tuple(float(value) for value in selected)
        positions = np.searchsorted(ordered, np.asarray(grid), side="right")
        cdf_result = tuple(float(position / observed) for position in positions.astype(np.float64))
    else:
        quantiles_result = (None,) * len(settings.quantiles)
        cdf_result = None
    return F11QuantityResult(
        quantity=quantity,
        observed_count=observed,
        missing_count=missing,
        status=status,
        reason_codes=codes,
        quantiles=quantiles_result,
        cdf_probabilities=cdf_result,
    )
