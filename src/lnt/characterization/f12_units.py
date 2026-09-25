"""F12: closed persisted quantity names и unit validation."""

from __future__ import annotations

from lnt.characterization.f12_contract import (
    ADJUSTED_P_VALUE_NAME,
    FRAME_COUNT_NAME,
    FREQUENCY_AXIS_NAME,
    MAXIMUM_SPECTRAL_KURTOSIS_NAME,
    SCALE_INDEX_NAME,
    SELECTED_BAND_HIGH_NAME,
    SELECTED_BAND_LOW_NAME,
    SPECTRAL_KURTOSIS_NAME,
    SURROGATE_SUPPORT_NAME,
    WINDOW_SUPPORT_NAME,
)
from lnt.characterization.records import Unit, validate_unit_name


def validate_f12_units() -> None:
    """Проверить persisted F12 names через closed unit vocabulary."""
    for name, unit in (
        (SPECTRAL_KURTOSIS_NAME, Unit.RATIO),
        (ADJUSTED_P_VALUE_NAME, Unit.RATIO),
        (MAXIMUM_SPECTRAL_KURTOSIS_NAME, Unit.RATIO),
        (FREQUENCY_AXIS_NAME, Unit.HZ),
        (SELECTED_BAND_LOW_NAME, Unit.HZ),
        (SELECTED_BAND_HIGH_NAME, Unit.HZ),
        (FRAME_COUNT_NAME, Unit.COUNT),
        (SCALE_INDEX_NAME, Unit.COUNT),
        (SURROGATE_SUPPORT_NAME, Unit.COUNT),
        (WINDOW_SUPPORT_NAME, Unit.COUNT),
    ):
        validate_unit_name(name, unit)
