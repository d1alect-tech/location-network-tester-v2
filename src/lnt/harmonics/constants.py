"""Константы гармоник IEC 61000-4-7."""

from typing import Final

HARMONICS_VERSION: Final = 1
WINDOW_DURATION_S: Final = 0.2
WINDOW_COUNT: Final = 12
RECORD_DURATION_S: Final = 2.4
H_MIN: Final = 1
H_MAX: Final = 40
IHG_COUNT: Final = 39
NOMINAL_GRID_HZ: Final = 50.0
BIN_HZ: Final = 5.0
DFT_BINS_PER_HARMONIC: Final = 10
DEFAULT_CHUNK_SAMPLES: Final = 1_048_576
MIN_SAMPLES_FOR_WINDOW: Final = 256
