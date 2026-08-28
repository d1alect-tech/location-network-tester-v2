"""Константы детектора качества питания: огибающая ITIC 2000 и пороги RVC.

Доли выражены относительно опорного номинального RMS полупериода, который
детектор вычисляет сам как робастную медиану записи (шкала пробника неизвестна).
"""

from typing import Final

POWER_QUALITY_VERSION: Final = 1

# Огибающая ITIC (2000): шаги (верхняя граница длительности, с; нижний допуск;
# верхний допуск). Первый шаг допускает провал до нуля (dropout) до 20 мс.
ITIC_ENVELOPE: Final = (
    (0.02, 0.0, 1.20),
    (0.5, 0.70, 1.20),
    (10.0, 0.80, 1.10),
)
# Установившийся режим за пределами 10 с: полоса 90..110 %.
ITIC_STEADY_BAND: Final = (0.90, 1.10)

DEFAULT_BAND_LOW_PCT: Final = 90.0
DEFAULT_BAND_HIGH_PCT: Final = 110.0
DEFAULT_MERGE_GAP_HALF_CYCLES: Final = 2
DEFAULT_DROPOUT_MAX_PCT: Final = 10.0
RVC_STEP_THRESHOLD_PCT: Final = 10.0
RVC_SUSTAIN_CYCLES: Final = 1
RVC_SUSTAIN_TOLERANCE_PCT: Final = 3.0
