"""Консервативный whitelist научно допустимых преобразований."""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .models import WelchGrid

# Объявленная частота анализа F18: запись выше неё приводится вниз целым числом
# отсчётов на отсчёт (lnt.characterization.f18_contract.ANALYSIS_RATE_HZ). Проверка
# согласованности — относительная, потому что частоты приходят float64.
_EXACT_RATE_RELATIVE_TOLERANCE: Final = 1e-12
_ANALYSIS_DECIMATION_PERMITTED_RU: Final = (
    "Разрешено только целочисленное приведение к объявленной частоте анализа."
)
_ANALYSIS_DECIMATION_REFUSAL_RU: Final = (
    "Дробный ресемплинг меняет статистику и не разрешён; обе частоты должны "
    "воспроизводиться объявленным целым фактором."
)


class NormalizationKind(StrEnum):
    """Закрытый набор запрашиваемых преобразований."""

    IDENTITY = "identity"
    PSD_GRID_DECIMATION = "psd_grid_decimation"
    BICOHERENCE_DECIMATION = "bicoherence_decimation"
    ARBITRARY_RESAMPLE = "arbitrary_resample"


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizationRequest:
    """Все параметры решения о преобразовании.

    Три поля ``analysis_*`` — частота захвата и частота анализа ветки F18. У неё нет
    сетки Welch, поэтому объявлять их приходится здесь; ``None`` означает «не
    объявлено» и закрывает путь, а не разрешает его.
    """

    kind: NormalizationKind
    source_grid: WelchGrid
    target_grid: WelchGrid
    sample_rate_hz: float
    analysis_factor: int | None = None
    source_analysis_rate_hz: float | None = None
    target_analysis_rate_hz: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizationDecision:
    """Явное разрешение либо блокировка с обоснованием."""

    permitted: bool
    rule_id: str | None
    reason_code: str
    rationale_ru: str


def assess_normalization(request: NormalizationRequest) -> NormalizationDecision:
    """Разрешает identity и целочисленное выравнивание Welch без интерполяции."""
    match request.kind:
        case NormalizationKind.IDENTITY:
            permitted = request.source_grid == request.target_grid
            return NormalizationDecision(
                permitted=permitted,
                rule_id="identity_v1" if permitted else None,
                reason_code="identity" if permitted else "identity_grid_mismatch",
                rationale_ru="Числа не изменяются; сетка должна совпадать полностью.",
            )
        case NormalizationKind.PSD_GRID_DECIMATION:
            source = request.source_grid
            target = request.target_grid
            divisor = target.nperseg > 0 and source.nperseg % target.nperseg == 0
            ratio_preserved = source.noverlap * target.nperseg == target.noverlap * source.nperseg
            permitted = (
                request.sample_rate_hz > 0.0
                and source.window == target.window
                and divisor
                and ratio_preserved
                and source.nperseg >= target.nperseg
            )
            return NormalizationDecision(
                permitted=permitted,
                rule_id="psd_welch_nperseg_decimation_v1" if permitted else None,
                reason_code="permitted" if permitted else "welch_decimation_incompatible",
                rationale_ru=(
                    "Разрешено только целочисленное укрупнение nperseg при том же окне "
                    "и той же доле overlap; произвольная интерполяция запрещена."
                ),
            )
        case NormalizationKind.ARBITRARY_RESAMPLE:
            return _refused("Произвольный resample меняет статистику PSD и не разрешён.")
        case NormalizationKind.BICOHERENCE_DECIMATION:
            return _analysis_decimation(request)


def _refused(rationale_ru: str) -> NormalizationDecision:
    """Единый машинно-читаемый отказ для всех не внесённых в whitelist преобразований."""
    return NormalizationDecision(
        permitted=False,
        rule_id=None,
        reason_code="normalization_not_whitelisted",
        rationale_ru=rationale_ru,
    )


def _declared_analysis_rates(request: NormalizationRequest) -> tuple[int, float, float] | None:
    """Отдать объявленные фактор и частоты либо None, если они не объявлены."""
    factor = request.analysis_factor
    source = request.source_analysis_rate_hz
    target = request.target_analysis_rate_hz
    if factor is None or isinstance(factor, bool) or factor < 1:
        return None
    if source is None or target is None or source <= 0.0 or target <= 0.0:
        return None
    return factor, source, target


def _analysis_decimation(request: NormalizationRequest) -> NormalizationDecision:
    """Разрешить только целочисленное приведение к частоте анализа.

    Ключевое условие — объявленный целый фактор, воспроизводящий обе частоты:
    без него запрос на 1.5 МГц -> 1 МГц прошёл бы как «фактор 2» и ресемплировал
    бы запись дробно. Поэтому любое несоответствие — тот же отказ, что и у
    произвольного resample.
    """
    declared = _declared_analysis_rates(request)
    if declared is None:
        return _refused(_ANALYSIS_DECIMATION_REFUSAL_RU)
    factor, source, target = declared
    if not math.isclose(source, factor * target, rel_tol=_EXACT_RATE_RELATIVE_TOLERANCE):
        return _refused(_ANALYSIS_DECIMATION_REFUSAL_RU)
    return NormalizationDecision(
        permitted=True,
        rule_id="bicoherence_analysis_rate_decimation_v1",
        reason_code="permitted",
        rationale_ru=_ANALYSIS_DECIMATION_PERMITTED_RU,
    )
