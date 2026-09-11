"""Canonical immutable characterization recipe schema 2."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lnt.analysis_store.characterization_contract import FAMILY_IDS
from lnt.analysis_store.characterization_family import CharacterizationFamily
from lnt.analysis_store.characterization_parse import integer, root_group, string, string_list
from lnt.analysis_store.characterization_root_parse import (
    parse_events,
    parse_phase,
    parse_resources,
    parse_stft,
)
from lnt.analysis_store.characterization_rules import validate_dependencies, validate_family_values
from lnt.analysis_store.errors import RecipeError
from lnt.context.json_codec import JsonValue, encode_canonical

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.analysis_store.characterization_settings import (
        CharacterizationEventSettings,
        PhaseSettings,
        ResourceLimits,
        StftSettings,
    )

SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterizationRecipe:
    """Strict schema-2 recipe with all descriptor families present."""

    schema_version: int
    mode: str
    channels: tuple[str, ...]
    resource_limits: ResourceLimits
    phase: PhaseSettings
    stft: StftSettings
    events: CharacterizationEventSettings
    families: tuple[CharacterizationFamily, ...]

    def __post_init__(self) -> None:
        """Validate root identity, channel support, families, and dependencies."""
        if self.schema_version != SCHEMA_VERSION or self.mode != "characterization":
            raise RecipeError("рецепт characterization: schema_version/mode не поддерживается")
        if not self.channels or len(set(self.channels)) != len(self.channels):
            raise RecipeError("рецепт characterization: channels пуст или содержит дубликаты")
        if any(channel not in {"ch1", "ch2"} for channel in self.channels):
            raise RecipeError("рецепт characterization: неизвестный channel")
        if tuple(family.id for family in self.families) != FAMILY_IDS:
            raise RecipeError("рецепт characterization: нужны ровно 18 families в заданном порядке")
        validate_family_values(self.families)
        validate_dependencies(
            self.families, self.resource_limits, self.phase, self.stft, self.events
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> CharacterizationRecipe:
        """Strictly parse a complete schema-2 mapping without defaults."""
        raw = root_group(value)
        family_values = raw["families"]
        if not isinstance(family_values, list) or len(family_values) != len(FAMILY_IDS):
            raise RecipeError("рецепт characterization: families должен содержать 18 блоков")
        return cls(
            schema_version=integer(raw["schema_version"], "schema_version"),
            mode=string(raw["mode"], "mode"),
            channels=string_list(raw["channels"], "channels"),
            resource_limits=parse_resources(raw["resource_limits"]),
            phase=parse_phase(raw["phase"]),
            stft=parse_stft(raw["stft"]),
            events=parse_events(raw["events"]),
            families=tuple(
                CharacterizationFamily.from_mapping(item, family_id)
                for item, family_id in zip(family_values, FAMILY_IDS, strict=True)
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        """Return the complete semantic JSON mapping."""
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "channels": list(self.channels),
            "resource_limits": {
                "chunk_samples": self.resource_limits.chunk_samples,
                "hard_max_chunk_samples": self.resource_limits.hard_max_chunk_samples,
                "max_work_bytes": self.resource_limits.max_work_bytes,
                "max_artifact_bytes": self.resource_limits.max_artifact_bytes,
                "max_stored_trajectories": self.resource_limits.max_stored_trajectories,
                "max_surrogates": self.resource_limits.max_surrogates,
                "deterministic_seed": self.resource_limits.deterministic_seed,
            },
            "phase": {
                "reference_channel": self.phase.reference_channel,
                "reference_event": self.phase.reference_event,
                "grid_frequency_low_hz": self.phase.grid_frequency_low_hz,
                "grid_frequency_high_hz": self.phase.grid_frequency_high_hz,
                "phase_bins": self.phase.phase_bins,
                "minimum_support_per_bin": self.phase.minimum_support_per_bin,
            },
            "stft": {
                "window": self.stft.window,
                "segment_samples": self.stft.segment_samples,
                "overlap_fraction": self.stft.overlap_fraction,
                "detrend": self.stft.detrend,
                "analysis_low_hz": self.stft.analysis_low_hz,
                "analysis_high_hz": self.stft.analysis_high_hz,
                "nyquist_fraction_max": self.stft.nyquist_fraction_max,
            },
            "events": {
                "detector": self.events.detector,
                "threshold_sigma": self.events.threshold_sigma,
                "minimum_snr_db": self.events.minimum_snr_db,
                "dead_time_s": self.events.dead_time_s,
                "dead_time_handling": self.events.dead_time_handling,
                "clipping_fraction_of_range": self.events.clipping_fraction_of_range,
                "maximum_events": self.events.maximum_events,
                "gap_handling": self.events.gap_handling,
            },
            "families": [family.to_mapping() for family in self.families],
        }

    @property
    def canonical_json(self) -> bytes:
        """Return compact sorted UTF-8 identity bytes."""
        return encode_canonical(self.to_mapping(), "рецепт characterization")

    @property
    def recipe_sha256(self) -> str:
        """Hash only the canonical recipe bytes."""
        return hashlib.sha256(self.canonical_json).hexdigest()
