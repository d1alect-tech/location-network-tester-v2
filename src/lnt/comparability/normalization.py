"""Консервативный whitelist научно допустимых преобразований."""

from dataclasses import dataclass
from enum import StrEnum

from .models import WelchGrid


class NormalizationKind(StrEnum):
    """Закрытый набор запрашиваемых преобразований."""

    IDENTITY = "identity"
    PSD_GRID_DECIMATION = "psd_grid_decimation"
    ARBITRARY_RESAMPLE = "arbitrary_resample"


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizationRequest:
    """Все параметры решения о преобразовании PSD."""

    kind: NormalizationKind
    source_grid: WelchGrid
    target_grid: WelchGrid
    sample_rate_hz: float


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
            return NormalizationDecision(
                permitted=False,
                rule_id=None,
                reason_code="normalization_not_whitelisted",
                rationale_ru="Произвольный resample меняет статистику PSD и не разрешён.",
            )
