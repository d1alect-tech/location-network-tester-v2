"""Pinned builtin measurement recipe for panel Analyze."""

from typing import Final

from lnt.analysis_store import AnalysisRecipe
from lnt.context.json_codec import JsonValue

_BUILTIN_MAPPING: Final[dict[str, JsonValue]] = {
    "schema_version": 1,
    "mode": "standard",
    "channels": ["ch1", "ch2"],
    "band_grid": {"low_hz": 3000.0, "high_hz": 200000.0, "grid_hz": 50.0},
    "welch": {
        "window": "hann",
        "segment_samples": 4096,
        "overlap_fraction": 0.5,
        "detrend": "constant",
        "scaling": "density",
        "average": "mean",
    },
    "spectrogram": {"enabled": True, "segment_samples": 1024, "overlap_fraction": 0.25},
    "events": {"enabled": True, "threshold_sigma": 5.0},
    "bands": {"edges_hz": [3000.0, 10000.0, 200000.0]},
    "correction": {"method": "none"},
    "uncertainty": {"enabled": False, "confidence_level": 0.95, "bootstrap_samples": 0},
}

BUILTIN_MEASUREMENT_RECIPE: Final = AnalysisRecipe.from_mapping(_BUILTIN_MAPPING)
