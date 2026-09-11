"""Qualify clipping from immutable capture provenance and already-saved volts.

Synthetic not-applicability means no hardware ADC clipping occurred by design;
it is distinct from observing a hardware span and finding it unclipped. Saved
voltage samples are classified as-is and are never converted again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from lnt.adc_calibration import apply_adc_calibration
from lnt.types import SessionManifest, SessionSource

type ChannelName = Literal["ch1", "ch2"]
type FloatArray = NDArray[np.floating]

_LOCALIZATION_UNAVAILABLE = "clipping_localization_unavailable"
_NOT_APPLICABLE_SYNTHETIC = "not_applicable_synthetic"


@dataclass(frozen=True, slots=True, kw_only=True)
class ClippingBounds:
    """Qualified voltage rails and whole-capture rail telemetry for one channel."""

    low_v: float | None
    high_v: float | None
    reason_code: str | None
    telemetry_rail_count: int | None

    def classify(self, samples: FloatArray) -> bool | None:
        """Classify one bounded finite span without changing its saved volt samples."""
        if self.reason_code == _NOT_APPLICABLE_SYNTHETIC:
            return False
        if self.low_v is None or self.high_v is None:
            return None
        return bool(np.min(samples) <= self.low_v or np.max(samples) >= self.high_v)


def resolve_clipping(
    manifest: SessionManifest,
    channel: ChannelName,
    fraction_of_range: float,
) -> ClippingBounds:
    """Resolve tri-state clipping qualification from saved session metadata only.

    A declared ideal synthetic signal returns ``False`` because hardware ADC
    clipping is not applicable, not because an ADC capture was observed below
    its rails. Device spans are known only when nominal conversion was used.
    Whole-capture telemetry counts are retained as context and never localize a
    hit to every classified span.
    """
    channel_meta = manifest.ch1 if channel == "ch1" else manifest.ch2
    if channel_meta is None:
        return ClippingBounds(
            low_v=None,
            high_v=None,
            reason_code="channel_missing",
            telemetry_rail_count=None,
        )

    telemetry = manifest.acquisition_telemetry
    telemetry_rail_count = None
    if telemetry is not None:
        telemetry_rail_count = (
            telemetry.ch1_clip_low_count + telemetry.ch1_clip_high_count
            if channel == "ch1"
            else telemetry.ch2_clip_low_count + telemetry.ch2_clip_high_count
        )

    if (
        manifest.source is SessionSource.SYNTHETIC
        and manifest.synthetic_truth is not None
        and channel_meta.front_end == "synthetic"
    ):
        return ClippingBounds(
            low_v=None,
            high_v=None,
            reason_code=_NOT_APPLICABLE_SYNTHETIC,
            telemetry_rail_count=telemetry_rail_count,
        )

    if (
        manifest.source is not SessionSource.DEVICE
        or telemetry is None
        or telemetry.calibration_used
    ):
        return ClippingBounds(
            low_v=None,
            high_v=None,
            reason_code=_LOCALIZATION_UNAVAILABLE,
            telemetry_rail_count=telemetry_rail_count,
        )

    endpoints_v = apply_adc_calibration(
        np.array([0, 255], dtype=np.uint8),
        range_code=channel_meta.range_code,
        probe_multiplier=channel_meta.probe_multiplier,
    )
    return ClippingBounds(
        low_v=float(endpoints_v[0]) * fraction_of_range,
        high_v=float(endpoints_v[1]) * fraction_of_range,
        reason_code=None,
        telemetry_rail_count=telemetry_rail_count,
    )
