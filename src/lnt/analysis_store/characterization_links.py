"""Cross-root resource and shared-setting checks for recipe schema 2."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lnt.analysis_store.errors import RecipeError

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.analysis_store.characterization_settings import (
        CharacterizationEventSettings,
        PhaseSettings,
        ResourceLimits,
        StftSettings,
    )


def _integer(family: CharacterizationFamily, name: str) -> int:
    value = family.value(name)
    if not isinstance(value, int):
        raise RecipeError(f"рецепт characterization: {family.id}.{name} должен быть целым")
    return value


def validate_resource_links(
    by_id: dict[str, CharacterizationFamily],
    resources: ResourceLimits,
    events: CharacterizationEventSettings,
) -> None:
    """Enforce root limits over all bounded family work and output."""
    capped_names = {
        "maximum_events",
        "maximum_tracks",
        "maximum_stored_samples",
        "maximum_episodes",
        "maximum_stored_bins",
        "maximum_lag_points",
        "maximum_triggers_per_direction",
        "maximum_labels",
        "maximum_triads",
        "maximum_stored_cells",
    }
    for family in by_id.values():
        for name, value in family.parameters:
            if name in capped_names and _integer(family, name) > resources.max_stored_trajectories:
                raise RecipeError(f"рецепт characterization: {family.id}.{name} превышает лимит")
            if name == "surrogate_count" and _integer(family, name) > resources.max_surrogates:
                raise RecipeError("рецепт characterization: превышен max_surrogates")
            if name == "surrogate_seed" and value != resources.deterministic_seed:
                raise RecipeError("рецепт characterization: surrogate seed не совпадает")
    f18 = by_id["f18_bicoherence_triads"]
    if (
        _integer(f18, "phase_randomized_surrogate_count") + _integer(f18, "iaaft_surrogate_count")
        > resources.max_surrogates
    ):
        raise RecipeError("рецепт characterization: F18 surrogate total превышает лимит")
    if events.maximum_events > resources.max_stored_trajectories:
        raise RecipeError("рецепт characterization: maximum_events превышает лимит")
    _validate_fft_and_events(by_id, resources, events)


def _validate_fft_and_events(
    by_id: dict[str, CharacterizationFamily],
    resources: ResourceLimits,
    events: CharacterizationEventSettings,
) -> None:
    f12_segments = by_id["f12_spectral_kurtosis"].value("segment_samples")
    if not isinstance(f12_segments, tuple):
        raise RecipeError("рецепт characterization: F12 segments должен быть массивом")
    fft_sizes = (
        _integer(by_id["f07_comb_sideband_cepstrum"], "fft_samples"),
        _integer(by_id["f16_multiscale_memory"], "maximum_fft_segment_samples"),
        *f12_segments,
    )
    if any(
        not isinstance(value, int) or value > resources.hard_max_chunk_samples
        for value in fft_sizes
    ):
        raise RecipeError("рецепт characterization: family FFT превышает hard chunk")
    event_families = (
        "f02_amplitude_time_shape",
        "f08_transient_morphology",
        "f09_event_ordering",
        "f11_conditional_distributions",
    )
    if any(
        _integer(by_id[family_id], "maximum_events") > events.maximum_events
        for family_id in event_families
    ):
        raise RecipeError("рецепт characterization: family event limit превышает root events")


def validate_shared_settings(
    by_id: dict[str, CharacterizationFamily], phase: PhaseSettings, stft: StftSettings
) -> None:
    """Require duplicated phase and STFT declarations to match their root settings."""
    phase_families = (
        "f05_phase_conditioned_statistics",
        "f10_threshold_episode_surface",
        "f12_spectral_kurtosis",
        "f13_band_envelope_coactivity",
        "f14_cross_channel_event_association",
        "f16_multiscale_memory",
        "f17_cyclic_spectral_coherence",
        "f18_bicoherence_triads",
    )
    if any(
        by_id[family_id].value("phase_bins") != phase.phase_bins for family_id in phase_families
    ):
        raise RecipeError("рецепт characterization: family phase_bins не совпадает с root")
    if (
        by_id["f05_phase_conditioned_statistics"].value("minimum_support_per_bin")
        != phase.minimum_support_per_bin
    ):
        raise RecipeError("рецепт characterization: F05 support не совпадает с root phase")
    _validate_stft(by_id, stft)


def _validate_stft(by_id: dict[str, CharacterizationFamily], stft: StftSettings) -> None:
    shared = (
        "window",
        "overlap_fraction",
        "analysis_high_hz",
        "nyquist_fraction_max",
    )
    f12 = by_id["f12_spectral_kurtosis"]
    for name in (*shared, "detrend", "analysis_low_hz"):
        if f12.value(name) != getattr(stft, name):
            raise RecipeError(f"рецепт characterization: F12.{name} не совпадает с root STFT")
    for family_id in ("f17_cyclic_spectral_coherence", "f18_bicoherence_triads"):
        family = by_id[family_id]
        # F18 объявляет сегмент длительностью, а не числом отсчётов, поэтому его
        # segment_samples выводится движком из частоты записи и равняться root-значению
        # не обязан (на 1 МГц это 1000 против 4096). Parse-time частоты нет, поэтому
        # равенство живёт в движке; здесь остаются четыре общих имени.
        names = ("segment_samples", *shared) if family_id.startswith("f17") else shared
        for name in names:
            if family.value(name) != getattr(stft, name):
                raise RecipeError(f"рецепт characterization: {family_id}.{name} не совпадает")
    if by_id["f17_cyclic_spectral_coherence"].value("analysis_low_hz") != stft.analysis_low_hz:
        raise RecipeError("рецепт characterization: F17.analysis_low_hz не совпадает")
    segments = f12.value("segment_samples")
    if not isinstance(segments, tuple) or stft.segment_samples not in segments:
        raise RecipeError("рецепт characterization: root STFT segment отсутствует в F12")
