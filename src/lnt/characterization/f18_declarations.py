"""F18: разбор declared recipe slot в замороженный surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f18_result import F18Declarations

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily

__all__ = ["locked_declarations"]


def locked_declarations(family: CharacterizationFamily) -> F18Declarations:
    """Извлечь и заморозить полный declared F18 surface из recipe slot."""
    try:
        declarations = F18Declarations(
            phase_bins=_integer(family.value("phase_bins")),
            segment_samples=_integer(family.value("segment_samples")),
            window=_text(family.value("window")),
            overlap_fraction=_number(family.value("overlap_fraction")),
            base_frequencies_hz=_numbers(family.value("base_frequencies_hz")),
            triad_rule=_text(family.value("triad_rule")),
            analysis_high_hz=_number(family.value("analysis_high_hz")),
            nyquist_fraction_max=_number(family.value("nyquist_fraction_max")),
            frequency_mapping=_text(family.value("frequency_mapping")),
            maximum_triads=_integer(family.value("maximum_triads")),
            phase_randomized_surrogate_count=_integer(
                family.value("phase_randomized_surrogate_count")
            ),
            iaaft_surrogate_count=_integer(family.value("iaaft_surrogate_count")),
            iaaft_iterations=_integer(family.value("iaaft_iterations")),
            iaaft_relative_rms_magnitude_tolerance=_number(
                family.value("iaaft_relative_rms_magnitude_tolerance")
            ),
            surrogate_seed=_integer(family.value("surrogate_seed")),
            dual_null_p_value=_text(family.value("dual_null_p_value")),
            multiple_testing=_text(family.value("multiple_testing")),
            false_discovery_rate=_number(family.value("false_discovery_rate")),
            minimum_frames=_integer(family.value("minimum_frames")),
        )
    except ValueError as error:
        raise CharacterizationError(
            "status_invariant", "F18 recipe declarations are invalid"
        ) from error
    if declarations != F18Declarations.locked():
        raise CharacterizationError("status_invariant", "F18 recipe declarations are not locked")
    return declarations


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CharacterizationError("status_invariant", "F18 recipe value must be text")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CharacterizationError("status_invariant", "F18 recipe value must be an integer")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CharacterizationError("status_invariant", "F18 recipe value must be a number")
    return float(value)


def _numbers(value: object) -> tuple[float, ...]:
    if not isinstance(value, tuple | list) or not value:
        raise CharacterizationError("status_invariant", "F18 base-frequency axis has wrong shape")
    return tuple(_number(item) for item in value)
