"""Публичный API гармоник IEC 61000-4-7."""

from lnt.harmonics.constants import (
    BIN_HZ,
    DFT_BINS_PER_HARMONIC,
    H_MAX,
    H_MIN,
    HARMONICS_VERSION,
    IHG_COUNT,
    NOMINAL_GRID_HZ,
    RECORD_DURATION_S,
    WINDOW_COUNT,
    WINDOW_DURATION_S,
)
from lnt.harmonics.detector import compute_harmonics
from lnt.harmonics.models import (
    HarmonicsInventory,
    HarmonicsSettings,
    HarmonicsWindow,
    harmonics_preset,
    harmonics_settings_hash,
)

__all__ = [
    "BIN_HZ",
    "DFT_BINS_PER_HARMONIC",
    "HARMONICS_VERSION",
    "H_MAX",
    "H_MIN",
    "IHG_COUNT",
    "NOMINAL_GRID_HZ",
    "RECORD_DURATION_S",
    "WINDOW_COUNT",
    "WINDOW_DURATION_S",
    "HarmonicsInventory",
    "HarmonicsSettings",
    "HarmonicsWindow",
    "compute_harmonics",
    "harmonics_preset",
    "harmonics_settings_hash",
]
