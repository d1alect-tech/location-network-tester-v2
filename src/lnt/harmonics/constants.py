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

# Оценка частоты сети: ниже этого числа отсчётов спектр слишком груб, берём номинал.
MIN_SAMPLES_FOR_GRID_ESTIMATE: Final = 1024
# Окно поиска пика сети (50 Гц ±10 Гц) и минимум бинов для параболической интерполяции.
GRID_SEARCH_LOW_HZ: Final = 40.0
GRID_SEARCH_HIGH_HZ: Final = 60.0
MIN_BINS_FOR_PARABOLIC: Final = 3
# Правдоподобный диапазон оценки: шире окна поиска, ловит 60-герцовые сети.
GRID_PLAUSIBLE_LOW_HZ: Final = 40.0
GRID_PLAUSIBLE_HIGH_HZ: Final = 70.0
# Порог вырожденности знаменателя и основной гармоники.
EPS_LEVEL: Final = 1e-12
