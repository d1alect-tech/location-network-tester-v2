"""Канонический immutable AnalysisRecipe schema 1."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from lnt.analysis_store.errors import RecipeError
from lnt.analysis_store.settings import (
    BandGridSettings,
    BandsSettings,
    CorrectionSettings,
    EventSettings,
    SpectrogramSettings,
    UncertaintySettings,
    WelchSettings,
)
from lnt.context.json_codec import JsonValue, encode_canonical

if TYPE_CHECKING:
    from collections.abc import Mapping

SCHEMA_VERSION: Final = 1


def _group(value: JsonValue, name: str, expected: frozenset[str]) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RecipeError(f"рецепт анализа: {name} должен быть JSON-object")
    unknown = value.keys() - expected
    missing = expected - value.keys()
    if unknown or missing:
        raise RecipeError(
            f"рецепт анализа: {name}: неизвестные={sorted(unknown)}, отсутствуют={sorted(missing)}"
        )
    return value


def _string(value: JsonValue, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RecipeError(f"рецепт анализа: {name} должен быть непустой строкой")
    return value


def _integer(value: JsonValue, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RecipeError(f"рецепт анализа: {name} должен быть целым числом")
    return value


def _number(value: JsonValue, name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise RecipeError(f"рецепт анализа: {name} должен быть числом")
    return float(value)


def _boolean(value: JsonValue, name: str) -> bool:
    if not isinstance(value, bool):
        raise RecipeError(f"рецепт анализа: {name} должен быть boolean")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisRecipe:
    """Полный immutable-рецепт; идентичность равна SHA-256 канонического JSON."""

    schema_version: int
    mode: str
    channels: tuple[str, ...]
    band_grid: BandGridSettings
    welch: WelchSettings
    spectrogram: SpectrogramSettings
    events: EventSettings
    bands: BandsSettings
    correction: CorrectionSettings
    uncertainty: UncertaintySettings

    def __post_init__(self) -> None:
        """Проверяет root-level инварианты schema 1."""
        if self.schema_version != SCHEMA_VERSION:
            raise RecipeError(
                f"рецепт анализа: поддерживается только schema_version={SCHEMA_VERSION}"
            )
        if not self.mode or not self.channels or any(not channel for channel in self.channels):
            raise RecipeError("рецепт анализа: mode и channels не должны быть пустыми")
        if len(set(self.channels)) != len(self.channels):
            raise RecipeError("рецепт анализа: channels содержит дубликаты")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> AnalysisRecipe:
        """Строго разбирает JSON-совместимое отображение schema 1."""
        expected = frozenset(
            {
                "schema_version",
                "mode",
                "channels",
                "band_grid",
                "welch",
                "spectrogram",
                "events",
                "bands",
                "correction",
                "uncertainty",
            }
        )
        unknown = value.keys() - expected
        missing = expected - value.keys()
        if unknown or missing:
            raise RecipeError(
                f"рецепт анализа: неизвестные={sorted(unknown)}, отсутствуют={sorted(missing)}"
            )
        channels = value["channels"]
        if not isinstance(channels, list):
            raise RecipeError("рецепт анализа: channels должен быть массивом")
        band_grid = _group(
            value["band_grid"], "band_grid", frozenset({"low_hz", "high_hz", "grid_hz"})
        )
        welch = _group(
            value["welch"],
            "welch",
            frozenset(
                {"window", "segment_samples", "overlap_fraction", "detrend", "scaling", "average"}
            ),
        )
        spectrogram = _group(
            value["spectrogram"],
            "spectrogram",
            frozenset({"enabled", "segment_samples", "overlap_fraction"}),
        )
        events = _group(value["events"], "events", frozenset({"enabled", "threshold_sigma"}))
        bands = _group(value["bands"], "bands", frozenset({"edges_hz"}))
        correction = _group(value["correction"], "correction", frozenset({"method"}))
        uncertainty = _group(
            value["uncertainty"],
            "uncertainty",
            frozenset({"enabled", "confidence_level", "bootstrap_samples"}),
        )
        edges = bands["edges_hz"]
        if not isinstance(edges, list):
            raise RecipeError("рецепт анализа: bands.edges_hz должен быть массивом")
        return cls(
            schema_version=_integer(value["schema_version"], "schema_version"),
            mode=_string(value["mode"], "mode"),
            channels=tuple(_string(item, "channels[]") for item in channels),
            band_grid=BandGridSettings(
                low_hz=_number(band_grid["low_hz"], "band_grid.low_hz"),
                high_hz=_number(band_grid["high_hz"], "band_grid.high_hz"),
                grid_hz=_number(band_grid["grid_hz"], "band_grid.grid_hz"),
            ),
            welch=WelchSettings(
                window=_string(welch["window"], "welch.window"),
                segment_samples=_integer(welch["segment_samples"], "welch.segment_samples"),
                overlap_fraction=_number(welch["overlap_fraction"], "welch.overlap_fraction"),
                detrend=_string(welch["detrend"], "welch.detrend"),
                scaling=_string(welch["scaling"], "welch.scaling"),
                average=_string(welch["average"], "welch.average"),
            ),
            spectrogram=SpectrogramSettings(
                enabled=_boolean(spectrogram["enabled"], "spectrogram.enabled"),
                segment_samples=_integer(
                    spectrogram["segment_samples"], "spectrogram.segment_samples"
                ),
                overlap_fraction=_number(
                    spectrogram["overlap_fraction"], "spectrogram.overlap_fraction"
                ),
            ),
            events=EventSettings(
                enabled=_boolean(events["enabled"], "events.enabled"),
                threshold_sigma=_number(events["threshold_sigma"], "events.threshold_sigma"),
            ),
            bands=BandsSettings(
                edges_hz=tuple(_number(item, "bands.edges_hz[]") for item in edges)
            ),
            correction=CorrectionSettings(
                method=_string(correction["method"], "correction.method")
            ),
            uncertainty=UncertaintySettings(
                enabled=_boolean(uncertainty["enabled"], "uncertainty.enabled"),
                confidence_level=_number(
                    uncertainty["confidence_level"], "uncertainty.confidence_level"
                ),
                bootstrap_samples=_integer(
                    uncertainty["bootstrap_samples"], "uncertainty.bootstrap_samples"
                ),
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        """Возвращает полное JSON-представление без производных полей."""
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "channels": list(self.channels),
            "band_grid": {
                "low_hz": self.band_grid.low_hz,
                "high_hz": self.band_grid.high_hz,
                "grid_hz": self.band_grid.grid_hz,
            },
            "welch": {
                "window": self.welch.window,
                "segment_samples": self.welch.segment_samples,
                "overlap_fraction": self.welch.overlap_fraction,
                "detrend": self.welch.detrend,
                "scaling": self.welch.scaling,
                "average": self.welch.average,
            },
            "spectrogram": {
                "enabled": self.spectrogram.enabled,
                "segment_samples": self.spectrogram.segment_samples,
                "overlap_fraction": self.spectrogram.overlap_fraction,
            },
            "events": {
                "enabled": self.events.enabled,
                "threshold_sigma": self.events.threshold_sigma,
            },
            "bands": {"edges_hz": list(self.bands.edges_hz)},
            "correction": {"method": self.correction.method},
            "uncertainty": {
                "enabled": self.uncertainty.enabled,
                "confidence_level": self.uncertainty.confidence_level,
                "bootstrap_samples": self.uncertainty.bootstrap_samples,
            },
        }

    @property
    def canonical_json(self) -> bytes:
        """Возвращает sorted compact UTF-8 JSON для совместимого хеширования."""
        return encode_canonical(self.to_mapping(), "рецепт анализа")

    @property
    def recipe_sha256(self) -> str:
        """Возвращает lowercase SHA-256 только канонического рецепта."""
        return hashlib.sha256(self.canonical_json).hexdigest()

    def clone(self, *, mode: str | None = None) -> AnalysisRecipe:
        """Клонирует рецепт с изменениями; исходный объект не изменяется."""
        return replace(self, mode=self.mode if mode is None else mode)
