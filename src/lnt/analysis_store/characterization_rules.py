"""Geometric and resource validation for characterization families."""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

from lnt.analysis_store.characterization_links import (
    validate_resource_links,
    validate_shared_settings,
)
from lnt.analysis_store.characterization_numeric_rules import validate_numeric_shapes
from lnt.analysis_store.errors import RecipeError

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.analysis_store.characterization_parse import ParameterValue
    from lnt.analysis_store.characterization_settings import (
        CharacterizationEventSettings,
        PhaseSettings,
        ResourceLimits,
        StftSettings,
    )


def _number(value: ParameterValue, path: str) -> float:
    if not isinstance(value, int | float):
        raise RecipeError(f"рецепт characterization: {path} должен быть числом")
    return float(value)


def _sequence(value: ParameterValue, path: str) -> tuple[ParameterValue, ...]:
    if not isinstance(value, tuple) or not value:
        raise RecipeError(f"рецепт characterization: {path} должен быть непустым массивом")
    return value


def _increasing(value: ParameterValue, path: str, *, allow_zero: bool = False) -> None:
    items = tuple(_number(item, f"{path}[]") for item in _sequence(value, path))
    lower = 0 if allow_zero else 0.0
    if (
        items[0] < lower
        or (not allow_zero and items[0] <= 0)
        or any(left >= right for left, right in pairwise(items))
    ):
        raise RecipeError(f"рецепт characterization: {path} должен строго возрастать")


def _bands(value: ParameterValue, path: str) -> tuple[tuple[float, float], ...]:
    result: list[tuple[float, float]] = []
    for item in _sequence(value, path):
        pair = _sequence(item, f"{path}[]")
        if len(pair) != 1 + 1:
            raise RecipeError(f"рецепт characterization: {path} содержит неверную полосу")
        low, high = (_number(edge, f"{path}[][]") for edge in pair)
        if low < 0 or high <= low or (result and low < result[-1][1]):
            raise RecipeError(f"рецепт characterization: {path} содержит пересекающиеся полосы")
        result.append((low, high))
    return tuple(result)


def validate_family_values(families: tuple[CharacterizationFamily, ...]) -> None:
    """Validate family-local numeric lists, bands, and geometry."""
    increasing = {
        "f03_interharmonic_tracking": ("subharmonic_orders",),
        "f04_multicycle_periodicity": ("averaging_factors", "autocorrelation_lags_cycles"),
        "f07_comb_sideband_cepstrum": ("offset_bins",),
        "f10_threshold_episode_surface": ("threshold_sigma", "minimum_duration_s", "quantiles"),
        "f11_conditional_distributions": ("quantiles",),
        "f12_spectral_kurtosis": ("segment_samples",),
        "f14_cross_channel_event_association": ("cycle_shift_offsets",),
        "f16_multiscale_memory": ("lags_s", "recurrence_radius_mad", "count_windows_s"),
        "f17_cyclic_spectral_coherence": ("cyclic_frequencies_hz",),
        "f18_bicoherence_triads": ("base_frequencies_hz",),
    }
    for family in families:
        for name in increasing.get(family.id, ()):
            _increasing(
                family.value(name),
                f"{family.id}.{name}",
                allow_zero=name == "minimum_duration_s",
            )
    validate_numeric_shapes(families)
    for family_id in ("f11_conditional_distributions", "f13_band_envelope_coactivity"):
        family = _find(families, family_id)
        _bands(family.value("bands_hz"), f"{family_id}.bands_hz")
    _validate_geometries(families)


def _validate_geometries(families: tuple[CharacterizationFamily, ...]) -> None:
    by_id = {family.id: family for family in families}
    ordered_pairs = (
        ("f06_modulation_trajectories", "band_low_hz", "band_high_hz"),
        ("f08_transient_morphology", "ringing_frequency_low_hz", "ringing_frequency_high_hz"),
        ("f08_transient_morphology", "phase_low_rad", "phase_high_rad"),
        ("f13_band_envelope_coactivity", "lag_low_s", "lag_high_s"),
        ("f14_cross_channel_event_association", "trigger_window_low_s", "trigger_window_high_s"),
        (
            "f14_cross_channel_event_association",
            "nearest_event_lag_low_s",
            "nearest_event_lag_high_s",
        ),
    )
    for family_id, low_name, high_name in ordered_pairs:
        family = by_id[family_id]
        if _number(family.value(low_name), low_name) >= _number(family.value(high_name), high_name):
            raise RecipeError(f"рецепт characterization: {family_id}: границы перепутаны")
    f03 = by_id["f03_interharmonic_tracking"]
    if _number(f03.value("bin_spacing_hz"), "F03") != 1 / _number(f03.value("window_s"), "F03"):
        raise RecipeError("рецепт characterization: F03 grid не согласован с window")


def validate_dependencies(
    families: tuple[CharacterizationFamily, ...],
    resources: ResourceLimits,
    phase: PhaseSettings,
    stft: StftSettings,
    events: CharacterizationEventSettings,
) -> None:
    """Validate family references and shared root dependencies."""
    by_id = {family.id: family for family in families}
    f02, f04, f11, f15 = (
        by_id[key]
        for key in (
            "f02_amplitude_time_shape",
            "f04_multicycle_periodicity",
            "f11_conditional_distributions",
            "f15_interpretable_modes",
        )
    )
    if f02.value("template_family_id") != "f01_phase_cycle":
        raise RecipeError("рецепт characterization: F02 должен использовать F01")
    if f04.value("carrier_source_family_id") != "f06_modulation_trajectories":
        raise RecipeError("рецепт characterization: F04 должен использовать F06")
    if f11.value("mode_source_family_id") != f15.id or f11.value("mode_count") != f15.value(
        "cluster_count"
    ):
        raise RecipeError("рецепт characterization: F11 и F15 имеют разные mode count/source")
    if _find(families, "f11_conditional_distributions").value("bands_hz") != _find(
        families, "f13_band_envelope_coactivity"
    ).value("bands_hz"):
        raise RecipeError("рецепт characterization: F11 и F13 имеют разные bands")
    if stft.segment_samples > resources.hard_max_chunk_samples:
        raise RecipeError("рецепт characterization: STFT segment превышает лимит")
    validate_resource_links(by_id, resources, events)
    validate_shared_settings(by_id, phase, stft)


def _find(families: tuple[CharacterizationFamily, ...], family_id: str) -> CharacterizationFamily:
    return next(family for family in families if family.id == family_id)
