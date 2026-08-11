"""JSON-safe result type for qualified input-reference artifacts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from lnt.context.json_codec import JsonValue
    from lnt.spectrum import SpectrumPeak

Float64Array = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrectedInputReference:
    """Artifact-ready qualified excess PSD, ASD, metrics и provenance."""

    frequencies_hz: Float64Array
    corrected_psd_v2_per_hz: Float64Array
    corrected_asd_v_per_sqrt_hz: Float64Array
    corrected_standard_uncertainty_v2_per_hz: Float64Array | None
    uncertainty_reason_code: str | None
    qualified: BoolArray
    corrected_peaks: tuple[SpectrumPeak, ...]
    qualified_band_power_v2: float
    qualified_band_rms_v: float
    metadata: dict[str, JsonValue]

    def to_artifact_mapping(self) -> dict[str, JsonValue]:
        """Сериализует NaN как null, не фабрикуя значения failed bins."""
        uncertainty = self.corrected_standard_uncertainty_v2_per_hz
        return {
            "status": "available",
            "frequencies_hz": self.frequencies_hz.tolist(),
            "corrected_psd_v2_per_hz": _nullable(self.corrected_psd_v2_per_hz),
            "corrected_asd_v_per_sqrt_hz": _nullable(self.corrected_asd_v_per_sqrt_hz),
            "corrected_standard_uncertainty_v2_per_hz": (
                None if uncertainty is None else _nullable(uncertainty)
            ),
            "uncertainty_reason_code": self.uncertainty_reason_code,
            "qualified": self.qualified.tolist(),
            "qualified_band_power_v2": self.qualified_band_power_v2,
            "qualified_band_rms_v": self.qualified_band_rms_v,
            "corrected_peaks": [
                {
                    "frequency_hz": peak.frequency_hz,
                    "level_db": peak.level_db,
                    "prominence_db": peak.prominence_db,
                    "q_factor": peak.q_factor,
                }
                for peak in self.corrected_peaks
            ],
            "correction": self.metadata,
        }


def _nullable(values: Float64Array) -> list[JsonValue]:
    return [float(value) if math.isfinite(value) else None for value in values]
