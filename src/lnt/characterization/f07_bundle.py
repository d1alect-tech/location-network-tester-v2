"""Маппер F07: скалярный кепстр-срез в конверт семейства без массивов."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f07_result import DECLARED_CODES
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
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
    import numpy as np

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f07_result import F07Result
    from lnt.characterization.models import FamilyResult

F07_ID: Final = "f07_comb_sideband_cepstrum"
F07_INDEX: Final = 6
# F07 публикует скаляры, а не временные ряды: имена и единицы по F07-8.
_F07_UNITS = (Unit.HZ, Unit.RATIO, Unit.S, Unit.COUNT)
# Анализируется ведущий кадр объявленной длины (F07-11), а не вся запись.
_F07_WINDOW_KIND: Final = "fixed"


def build_f07_family(  # noqa: PLR0913 - кадр, запись и канал задают объявленную геометрию
    result: F07Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
    sample_rate_hz: float,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Скаляры F07 в конверт семейства: ни массивов, ни масок частичности.

    Длительность окна берётся из объявленной длины кадра ``fft_samples`` и
    частоты выборки: выдуманного числа в конверте нет. Скалярная сводка
    публикуется только при непустом поле результата (F07-14: пустая агрегация
    боковых оставляет семейство AVAILABLE без сводки ``f07_sym_db``).
    """
    if family.id != F07_ID:
        raise CharacterizationError("family_order", "f07 mapper needs the f07 family")
    frame_s = _frame_seconds(family, sample_rate_hz)
    record_s = _positive(record_duration_s, "f07 record duration")
    reasons = _checked_codes(result.reason_codes)
    if result.status is Status.UNAVAILABLE:
        if not reasons:
            raise CharacterizationError("status_invariant", "unavailable f07 needs reasons")
        spec = _spec(family, band, measured_channel, frame_s, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}
    if result.status is Status.AVAILABLE and reasons:
        raise CharacterizationError("status_invariant", "available f07 must have no reasons")
    if result.status is not Status.AVAILABLE:
        # Объявленный словарь F07 не знает частичного результата: срез либо есть, либо нет.
        raise CharacterizationError("status_invariant", "f07 publishes no partial result")
    spec = _spec(family, band, measured_channel, frame_s, Status.AVAILABLE, ())
    envelope = family_envelope(
        spec, _support(result, frame_s, record_s), comparison_summary=_summaries(result)
    )
    return envelope, {}


def _frame_seconds(family: CharacterizationFamily, sample_rate_hz: float) -> float:
    """Объявленная длина кадра в секундах: строгий отказ вместо приведения типов."""
    raw = family.value("fft_samples")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise CharacterizationError(
            "status_invariant", "f07 fft_samples must be a positive integer"
        )
    rate = _positive(sample_rate_hz, "f07 sample rate")
    return float(raw) / rate


def _positive(value: float, field: str) -> float:
    """Конечное положительное число объявленной геометрии."""
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise CharacterizationError("status_invariant", f"{field} must be positive and finite")
    return number


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Отсортированные уникальные коды только из объявленного словаря движка."""
    if any(not code or code not in DECLARED_CODES for code in codes):
        raise CharacterizationError("status_invariant", "f07 reasons must use declared codes")
    if len(set(codes)) != len(codes):
        raise CharacterizationError("status_invariant", "f07 reasons must be unique")
    return tuple(sorted(codes))


def _spec(  # noqa: PLR0913, PLR0917 - конверт несёт весь объявленный инвариант семейства
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    frame_s: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F07_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F07_UNITS,
        window=Window(
            kind=_F07_WINDOW_KIND, duration_s=frame_s, sample_count=None, overlap_fraction=0.0
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _support(result: F07Result, frame_s: float, record_s: float) -> Support:
    """Учёт скалярного семейства 1:1 из результата (F07-9); интервал не длиннее записи.

    Кадр нулями дополняется до объявленной длины (F07-11), поэтому наблюдённый
    интервал записи ограничен и кадром, и самой записью: поддержка не заявляет
    отсчётов, которых в записи нет.
    """
    sample = int(result.sample_count)
    observation = int(result.observation_count)
    missing = int(result.missing_count)
    stored = int(result.stored_count)
    if sample != observation + missing or stored != observation or observation <= 0:
        raise CharacterizationError("status_invariant", "invalid f07 support counts")
    span = min(frame_s, record_s)
    return Support(
        start_s=0.0, end_s=span, duration_s=span, sample_count=sample,
        observation_count=observation, missing_count=missing,
        stored_count=stored, selection_rule="all"
    )  # fmt: skip


def _published(result: F07Result) -> tuple[tuple[str, float | None, Unit], ...]:
    """Скаляры среза в порядке публикации: индекс несущей едет как COUNT."""
    carrier = result.carrier_bin
    return (
        ("f07_df_hz", result.df_hz, Unit.HZ),
        ("f07_sym_db", result.sym_db, Unit.RATIO),
        ("f07_q_s", result.q_s, Unit.S),
        ("f07_quefrency_amplitude", result.quefrency_amplitude, Unit.RATIO),
        ("f07_carrier_bin", None if carrier is None else float(carrier), Unit.COUNT),
    )


def _summaries(result: F07Result) -> tuple[ScalarSummary, ...]:
    """Сводка только при живом скаляре: пустое поле семейство не публикует."""
    summaries: list[ScalarSummary] = []
    for name, value, unit in _published(result):
        validate_unit_name(name, unit)
        if value is not None:
            summaries.append(ScalarSummary(name=name, value=float(value), unit=unit))
    return tuple(summaries)
