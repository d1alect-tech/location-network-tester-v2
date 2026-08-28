"""Burst EFT 5нс/50нс детектор (61000-4-4)."""

from lnt.burst.detector import detect_bursts
from lnt.burst.models import (
    BURST_VERSION,
    BurstEvent,
    BurstInventory,
    BurstSequence,
    BurstSettings,
    burst_preset,
    burst_settings_hash,
)

__all__ = [
    "BURST_VERSION",
    "BurstEvent",
    "BurstInventory",
    "BurstSequence",
    "BurstSettings",
    "burst_preset",
    "burst_settings_hash",
    "detect_bursts",
]
