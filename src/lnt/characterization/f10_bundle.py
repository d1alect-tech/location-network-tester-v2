"""Маппер F10: поверхность порог × длительность × бин фазы в конверт семейства.

Граница притязаний (спека `method-notes-families-10-18.md:73-74`): поверхность
описывает превышение порога в ОДНОЙ измеренной плоскости канала. Она не измеряет
энергию, повреждение, источник и полезность. `v2_s` — интеграл квадрата
измеренного напряжения по времени, а не джоули: ток и импеданс не измерены.

Модуль владеет только конвертом: статусы, словарь причин, окно, поддержка и
сводки. Опубликованная раскладка массивов живёт в `f10_arrays`.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f10_arrays import published
from lnt.characterization.f10_result import DECLARED_CODES
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.records import (
    ScalarSummary,
    Status,
    Support,
    Unit,
    Window,
)

if TYPE_CHECKING:
    import numpy as np

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f10_result import F10Result
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.records import Band

F10_ID: Final = "f10_threshold_episode_surface"
F10_INDEX: Final = 9
_F10_UNITS: Final = (Unit.RATIO, Unit.S, Unit.COUNT, Unit.V2_S)
# F10 обходит всю запись, разбитую по бинам фазы: окно это запись, а не кадр.
_F10_WINDOW_KIND: Final = "record"


def build_f10_family(
    result: F10Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str,
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Собрать конверт F10 поверх результата движка без пересчёта математики."""
    if family.id != F10_ID:
        raise CharacterizationError("family_order", "f10 mapper needs the f10 family")
    span = _span(record_duration_s)
    reasons = _checked_codes(result.reason_codes)
    if result.status is Status.UNAVAILABLE:
        if not reasons:
            raise CharacterizationError("status_invariant", "unavailable f10 needs reasons")
        spec = _spec(family, band, measured_channel, span, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}
    if result.status is Status.AVAILABLE and reasons:
        raise CharacterizationError("status_invariant", "available f10 must have no reasons")
    if result.status is Status.PARTIAL and not reasons:
        raise CharacterizationError("status_invariant", "partial f10 needs reasons")
    arrays, refs = published(result, partial=result.status is Status.PARTIAL)
    spec = _spec(family, band, measured_channel, span, result.status, reasons)
    envelope = family_envelope(
        spec, _support(result, span), array_refs=tuple(refs), comparison_summary=_summaries(result)
    )
    return envelope, arrays


def _span(value: float) -> float:
    """Конечная положительная длительность записи: строгий отказ вместо приведения."""
    span = float(value)
    if not math.isfinite(span) or span <= 0.0:
        raise CharacterizationError("status_invariant", "f10 record duration must be positive")
    return span


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Отсортированные уникальные коды только из объявленного словаря движка."""
    if any(not code or code not in DECLARED_CODES for code in codes):
        raise CharacterizationError("status_invariant", "f10 reasons must use declared codes")
    if len(set(codes)) != len(codes):
        raise CharacterizationError("status_invariant", "f10 reasons must be unique")
    return tuple(sorted(codes))


def _spec(  # noqa: PLR0913, PLR0917 - конверт несёт весь объявленный инвариант семейства
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F10_ID, method=family.method, method_version=family.method_version,
        status=status, reasons=reasons, units=_F10_UNITS,
        window=Window(
            kind=_F10_WINDOW_KIND, duration_s=span, sample_count=None, overlap_fraction=0.0
        ),
        band=band, signal_plane=signal_plane_for(measured_channel),
    )  # fmt: skip


def _support(result: F10Result, span: float) -> Support:
    """Учёт отсчётов записи один в один из результата (F10-17); интервал — вся запись.

    Единица поддержки выбрана явно: поверхность публикуется ЦЕЛИКОМ, поэтому
    `stored_count` равен наблюдаемым отсчётам, а правило отбора — `all`. Кап
    хранения эпизодов сюда не переносится: он виден в сводках
    `f10_stored_episode_count` и `f10_omitted_episode_count`, а `Support`
    считает отсчёты записи, а не строки эпизодов.
    """
    sample = int(result.sample_count)
    observation = int(result.observation_count)
    missing = int(result.missing_count)
    if sample != observation + missing or observation <= 0 or missing < 0:
        raise CharacterizationError("status_invariant", "invalid f10 support counts")
    return Support(
        start_s=0.0, end_s=span, duration_s=span, sample_count=sample,
        observation_count=observation, missing_count=missing,
        stored_count=observation, selection_rule="all"
    )  # fmt: skip


def _summaries(result: F10Result) -> tuple[ScalarSummary, ...]:
    """Готовые счётчики результата: новых чисел маппер не выводит."""
    stored = int(result.stored_count)
    omitted = int(result.omitted_count)
    if int(result.episode_total) != stored + omitted:
        raise CharacterizationError("status_invariant", "f10 episode accounting must add up")
    counters = (
        ("f10_qualified_cycles", result.qualified_cycles),
        ("f10_full_episode_count", result.episode_total),
        ("f10_truncated_episode_count", result.truncated_episode_total),
        ("f10_stored_episode_count", stored),
        ("f10_omitted_episode_count", omitted),
    )
    return tuple(
        ScalarSummary(name=name, value=float(value), unit=Unit.COUNT) for name, value in counters
    )
