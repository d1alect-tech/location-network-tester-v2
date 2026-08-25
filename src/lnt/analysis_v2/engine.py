"""Adapters from immutable recipes to the existing numerical engines."""

from __future__ import annotations

import dataclasses
import io
import json

import numpy as np

from lnt.cm_dm.analysis import (
    CM_DM_SPECTRUM_FILENAME,
    CSV_HEADER,
    analyze_cm_dm_session,
    cm_dm_analysis_to_payload,
)
from lnt.events import EventInventory, detect_events, event_preset
from lnt.features import BandSet, EstimandDirection, compute_event_features
from lnt.line_quality_v2 import compute_line_quality_v2, line_quality_v2_to_payload
from lnt.psd import FrequencyBand, PsdSettings, compute_welch
from lnt.spectrogram import StftSettings, build_overview

from .types import BranchContext, BranchOutput


class DefaultAnalysisEngine:
    """Dispatches branch names to pre-existing engines without reimplementing math."""

    def run_branch(self, name: str, context: BranchContext) -> BranchOutput:
        """Run one named optional branch using its existing engine."""
        context.checkpoint()
        match name:
            case "psd":
                output = self._psd(context)
            case "spectrogram":
                output = self._spectrogram(context)
            case "events":
                output = self._events(context)
            case "features":
                output = self._features(context)
            case "line_quality":
                result = compute_line_quality_v2(
                    context.channels[0], sample_rate_hz=context.sample_rate_hz
                )
                output = BranchOutput(
                    files={"metrics.json": _json(line_quality_v2_to_payload(result))}
                )
            case "cm_dm":
                output = self._cm_dm(context)
            case "correction":
                output = BranchOutput(
                    files={
                        "correction.json": _json(
                            {
                                "method": context.recipe.correction.method,
                                "status": "unavailable",
                                "reason_code": "analysis_v2_requires_declared_calibration",
                            }
                        )
                    }
                )
            case _:
                raise ValueError(f"unknown analysis branch: {name}")
        return output

    @staticmethod
    def _psd(context: BranchContext) -> BranchOutput:
        bands = tuple(
            FrequencyBand(name=f"band_{index}", low_hz=low, high_hz=high)
            for index, (low, high) in enumerate(
                zip(context.recipe.bands.edges_hz, context.recipe.bands.edges_hz[1:], strict=False)
            )
        )
        settings = PsdSettings.from_recipe(
            sample_rate_hz=context.sample_rate_hz,
            welch=context.recipe.welch,
            bands=bands,
            max_chunk_samples=max(context.recipe.welch.segment_samples, 262_144),
        )
        result = compute_welch(context.channels[0], settings=settings)
        table = io.StringIO()
        np.savetxt(
            table,
            np.column_stack((result.frequency_hz, result.psd_v2_per_hz)),
            delimiter=",",
            header="frequency_hz,psd_v2_per_hz",
            comments="",
            fmt="%.17g",
        )
        metrics = {
            "segment_count": result.segment_count,
            "band_rms": [
                {"name": item.band.name, "rms_v": item.rms_v, "unit": item.unit}
                for item in result.band_rms
            ],
        }
        return BranchOutput(
            files={"spectrum.csv": table.getvalue().encode(), "metrics.json": _json(metrics)}
        )

    @staticmethod
    def _spectrogram(context: BranchContext) -> BranchOutput:
        overview = build_overview(
            context.session_dir / f"{context.recipe.channels[0]}.npy",
            sample_rate_hz=context.sample_rate_hz,
            settings=StftSettings.from_recipe(context.recipe.spectrogram),
            max_time_bins=256,
            max_frequency_bands=128,
            band_low_hz=max(context.recipe.band_grid.low_hz, 1e-9),
            band_high_hz=context.recipe.band_grid.high_hz,
        )
        buffer = io.BytesIO()
        np.savez_compressed(
            buffer,
            time_s=overview.time_s,
            frequency_hz=overview.frequency_hz,
            power_db=overview.power_db,
        )
        return BranchOutput(files={"spectrogram.npz": buffer.getvalue()})

    @staticmethod
    def _cm_dm(context: BranchContext) -> BranchOutput:
        """Считает CM/DM-декомпозицию существующим v1-движком и упаковывает артефакты."""
        result = analyze_cm_dm_session(context.session_dir)
        band = result.band
        table = io.StringIO()
        np.savetxt(
            table,
            np.column_stack([band.frequency_hz, band.cm_psd, band.dm_psd, band.coherence]),
            delimiter=",",
            header=CSV_HEADER,
            comments="",
            fmt="%.9g",
        )
        return BranchOutput(
            files={
                "metrics.json": _json(cm_dm_analysis_to_payload(result)),
                CM_DM_SPECTRUM_FILENAME: table.getvalue().encode(),
            }
        )

    @staticmethod
    def _inventory(context: BranchContext) -> EventInventory:
        settings = dataclasses.replace(
            event_preset("impulses_default"), threshold_sigma=context.recipe.events.threshold_sigma
        )
        return detect_events(
            context.channels[0], sample_rate_hz=context.sample_rate_hz, settings=settings
        )

    def _events(self, context: BranchContext) -> BranchOutput:
        inventory = self._inventory(context)
        payload = {
            "schema_version": inventory.schema_version,
            "sample_count": inventory.sample_count,
            "events": [dataclasses.asdict(item) for item in inventory.events],
        }
        return BranchOutput(files={"events.json": _json(payload)})

    def _features(self, context: BranchContext) -> BranchOutput:
        edges = context.recipe.bands.edges_hz
        bands = BandSet.from_recipe_edges(
            edges,
            tuple(EstimandDirection.HIGHER for _ in range(len(edges) - 1)),
        )
        features = compute_event_features(self._inventory(context), bands)
        return BranchOutput(
            files={"features.json": _json({"bands": [item.to_dict() for item in features.bands]})}
        )


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()
