"""Тренды: Theil-Sen, CUSUM, crest, discard 2000, EEPROM hash."""

from lnt.trends.detector import compute_trends
from lnt.trends.models import (
    TRENDS_VERSION,
    TrendChangePoint,
    TrendsInventory,
    TrendsSettings,
    trends_preset,
    trends_settings_hash,
)

__all__ = [
    "TRENDS_VERSION",
    "TrendChangePoint",
    "TrendsInventory",
    "TrendsSettings",
    "compute_trends",
    "trends_preset",
    "trends_settings_hash",
]
