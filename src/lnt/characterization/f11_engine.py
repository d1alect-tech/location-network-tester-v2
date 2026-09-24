"""Движок F11: условные распределения по фазе, полосе и канонической F15 моде."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lnt.characterization.f11_cells import CellAccumulator, add_event, build_cells
from lnt.characterization.f11_contract import (
    F11Declarations,
    build_settings,
    check_rules,
    phase_edges,
    unavailable_result,
)
from lnt.characterization.f11_modes import assign_mode, build_mode_model
from lnt.characterization.f11_result import (
    BIN_EMPTY,
    DOMINANT_BAND_UNAVAILABLE,
    EVENT_LIMIT,
    GAPS_PRESENT,
    INSUFFICIENT_SUPPORT,
    MODE_ASSIGNMENT_UNAVAILABLE,
    MODE_UNAVAILABLE,
    PHASE_REFERENCE_UNAVAILABLE,
    CellKey,
    EventValues,
    F11Cell,
    F11Event,
    F11EventInventory,
    F11Result,
    F15ModeSource,
)
from lnt.characterization.phase import phase_bins
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.phase_model import PhaseCycles


def compute_f11_conditional_distributions(
    phase: PhaseCycles,
    inventory: F11EventInventory,
    mode_source: F15ModeSource,
    declarations: F11Declarations,
    resolved_bands: tuple[ResolvedBand, ...],
) -> F11Result:
    """Посчитать 192 условные ячейки и четыре эмпирические CDF на общей сетке."""
    settings = build_settings(declarations, resolved_bands)
    check_rules(declarations)
    if phase.status is Status.UNAVAILABLE:
        return unavailable_result(
            (PHASE_REFERENCE_UNAVAILABLE,),
            inventory,
            mode_source,
            settings,
            n_phase_unavailable=len(inventory.events),
        )
    model = build_mode_model(mode_source, sample_rate_hz=phase.sample_rate_hz)
    if model is None:
        return unavailable_result((MODE_UNAVAILABLE,), inventory, mode_source, settings)
    if len(model.canonical_labels) != settings.mode_count:
        raise ValueError("F11 mode_count does not match F15 canonical labels")
    ordered = sorted(inventory.events, key=lambda event: (event.peak_sample, event.ordinal))
    kept = ordered[: settings.maximum_events]
    members: dict[CellKey, CellAccumulator] = {}
    band_indices = {
        band.requested.name: index for index, band in enumerate(settings.resolved_bands)
    }
    n_missing = 0
    n_mode_missing = 0
    n_band_missing = 0
    n_phase_missing = 0
    for event in kept:
        values = _event_values(event)
        n_missing += int(any(value is None for value in values))
        event_phase = _event_phase(phase, event.peak_sample, settings.phase_bins)
        # RootEvent уже применил half_open_last_closed upstream; метка сохраняет
        # тот же результат, поэтому F11 не пересчитывает и не подменяет частоту.
        event_band = None if event.dominant_band is None else band_indices.get(event.dominant_band)
        event_mode = assign_mode(model, event.peak_sample)
        n_phase_missing += int(event_phase is None)
        n_band_missing += int(event_band is None)
        n_mode_missing += int(event_mode is None)
        if event_phase is None or event_band is None or event_mode is None:
            continue
        add_event(members, (event_phase, event_band, event_mode), event, values)
    cells, grids = build_cells(members, model.canonical_labels, settings)
    codes = _codes(
        inventory,
        cells,
        members,
        _Accounting(
            n_mode_missing=n_mode_missing,
            n_band_missing=n_band_missing,
            n_phase_missing=n_phase_missing,
            omitted=len(ordered) - len(kept),
        ),
    )
    has_supported = any(cell.status in (Status.AVAILABLE, Status.PARTIAL) for cell in cells)
    status = (
        Status.UNAVAILABLE if not has_supported else Status.PARTIAL if codes else Status.AVAILABLE
    )
    # Дом: UNAVAILABLE публикует пустые домены (наследованный инвариант
    # status_invariant, закреплён тестом F10). Поэтому 192 явные ячейки с
    # per-cell кодами bin_empty/insufficient_support относятся только к
    # AVAILABLE/PARTIAL; при отказе маппер иначе обязан отвергнуть результат.
    published_cells = cells if status is not Status.UNAVAILABLE else ()
    published_grids = grids if status is not Status.UNAVAILABLE else tuple(() for _ in grids)
    return F11Result(
        status=status,
        reason_codes=codes if status is not Status.AVAILABLE else (),
        cells=published_cells,
        phase_bin_edges_rad=phase_edges(settings.phase_bins),
        bands_hz=settings.bands_hz,
        mode_labels=model.canonical_labels,
        quantiles=settings.quantiles,
        cdf_probabilities=settings.cdf_probabilities,
        cdf_grids=published_grids,
        event_count=len(ordered),
        evaluated_event_count=len(kept),
        omitted_event_count=len(ordered) - len(kept),
        n_missing=n_missing,
        n_mode_missing=n_mode_missing,
        n_dominant_band_unavailable=n_band_missing,
        n_phase_unavailable=n_phase_missing,
    )


def _event_phase(phase: PhaseCycles, peak_sample: int, bins: int) -> int | None:
    """Приписать пику левозамкнутый правый открытый бин фазы."""
    if peak_sample < 0 or peak_sample >= phase.sample_count:
        return None
    indices, valid = phase_bins(phase, peak_sample, peak_sample + 1, bins)
    return int(indices[0]) if bool(valid[0]) else None


def _event_values(event: F11Event) -> EventValues:
    """Нормализовать три измеренные величины; недоступное значение равно None."""
    return (
        _quantity(event.absolute_peak_v, "absolute_peak_v"),
        _quantity(event.duration_s, "duration_s"),
        _quantity(event.v2_s, "v2_s"),
    )


def _quantity(value: float | None, name: str) -> float | None:
    """Недоступное нефинитное значение скрыть; отрицательное отвергнуть."""
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    if number < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return number


@dataclass(frozen=True, slots=True, kw_only=True)
class _Accounting:
    """Счётчики, которые превращаются в семейные QC-коды."""

    n_mode_missing: int
    n_band_missing: int
    n_phase_missing: int
    omitted: int


def _codes(
    inventory: F11EventInventory,
    cells: tuple[F11Cell, ...],
    members: Mapping[CellKey, CellAccumulator],
    accounting: _Accounting,
) -> tuple[str, ...]:
    """Собрать только объявленные семейные коды в уникальном sorted порядке."""
    raw: set[str] = set()
    if accounting.n_phase_missing:
        raw.add(PHASE_REFERENCE_UNAVAILABLE)
    if accounting.n_band_missing:
        raw.add(DOMINANT_BAND_UNAVAILABLE)
    if accounting.n_mode_missing:
        raw.add(MODE_ASSIGNMENT_UNAVAILABLE)
    if accounting.omitted:
        raw.add(EVENT_LIMIT)
    if inventory.gap_count or inventory.omitted_gap_count:
        raw.add(GAPS_PRESENT)
    if not members and not inventory.events:
        raw.add(BIN_EMPTY)
    if members and not any(cell.status is Status.AVAILABLE for cell in cells):
        raw.add(INSUFFICIENT_SUPPORT)
    if any(cell.status is Status.PARTIAL for cell in cells):
        raw.add(INSUFFICIENT_SUPPORT)
    return tuple(sorted(raw))
