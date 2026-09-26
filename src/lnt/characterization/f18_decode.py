"""F18: канонический декод формы статуса, причин и счётчиков.

Guards без публикации: они превращают persisted/engine форму в доверенные
примитивы, а результат в declared domain не трогают. Учётная четвёрка
(`_SUMMARY_NAMES`, `_counter_values`, `_summaries`, `_summary_counts`) остаётся
в `f18_bundle.py` рядом с публичным швом.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

import lnt.characterization.f18_contract as contract
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from lnt.characterization.f18_result import F18Result


def checked_f18_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Проверить, что коды причин объявлены, уникальны и отсортированы."""
    if (
        any(code not in contract.DECLARED_CODES for code in codes)
        or len(set(codes)) != len(codes)
        or codes != tuple(sorted(codes))
    ):
        raise CharacterizationError("status_invariant", "F18 reasons are not canonical")
    return codes


def checked_f18_status(status: object, reasons: tuple[str, ...]) -> None:
    """Проверить согласованность статуса с набором причин и их терминальность."""
    if not isinstance(status, Status):
        raise CharacterizationError("status_invariant", "unknown F18 status")
    if (status is Status.AVAILABLE and reasons) or (status is not Status.AVAILABLE and not reasons):
        raise CharacterizationError("status_invariant", "invalid F18 status/reasons")
    if status is Status.PARTIAL and any(
        code in reasons
        for code in (contract.PHASE_REFERENCE_UNAVAILABLE, contract.INSUFFICIENT_FRAMES)
    ):
        raise CharacterizationError("status_invariant", "terminal F18 reason cannot be partial")


def checked_f18_reasons(result: F18Result, reasons: tuple[str, ...]) -> None:
    """Проверить, что набор причин в точности соответствует счётчикам результата."""
    available = int(np.count_nonzero(result.triad_available))
    expected = (
        (contract.TRIAD_OFF_GRID, result.off_grid_triad_count > 0),
        (contract.TRIAD_ABOVE_NYQUIST, result.above_nyquist_triad_count > 0),
        (contract.ARTIFACT_LIMIT, result.dropped_triad_count > 0),
        (contract.ZERO_DENOMINATOR, result.measurable_triad_count != available),
        (
            contract.IAAFT_NOT_CONVERGED,
            result.iaaft_converged_count < contract.IAAFT_SURROGATE_COUNT,
        ),
        (contract.NO_SIGNIFICANT_TRIAD, not bool(np.any(result.significant))),
    )
    if any((code in reasons) != present for code, present in expected):
        _fail("F18 reason accounting is not exact")


def f18_record_span(value: float) -> float:
    """Принять длительность записи как положительное конечное число секунд."""
    span = float(value)
    if not math.isfinite(span) or span <= 0.0:
        raise CharacterizationError("status_invariant", "F18 record duration must be positive")
    return span


def f18_count(value: object, name: str) -> int:
    """Принять счётчик как неотрицательное целое без булева подмены."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CharacterizationError("status_invariant", f"F18 {name} must be a nonnegative integer")
    return value


def _fail(detail: str) -> None:
    raise CharacterizationError("status_invariant", detail)
