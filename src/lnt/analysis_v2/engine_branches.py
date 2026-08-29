"""Batch 2–6 branch adapters for analysis v2."""

from __future__ import annotations

import json

from lnt.apd import apd_preset, compute_apd
from lnt.burst import burst_preset, detect_bursts
from lnt.harmonics import compute_harmonics
from lnt.notching import detect_notching, notching_preset
from lnt.power_quality import detect_half_cycle_rms, detect_power_quality, power_quality_preset
from lnt.trends import compute_trends, trends_preset

from .types import BranchContext, BranchOutput


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()


def run_notching(context: BranchContext) -> BranchOutput:
    """Detect notching and write ``notching.json``."""
    settings = notching_preset("notching_default")
    inventory = detect_notching(
        context.channels[0],
        sample_rate_hz=context.sample_rate_hz,
        settings=settings,
    )
    context.checkpoint()
    return BranchOutput(files={"notching.json": _json(inventory.to_dict())})


def run_apd(context: BranchContext) -> BranchOutput:
    """Compute APD and write ``apd.json``."""
    settings = apd_preset("apd_default")
    inv = compute_apd(context.channels[0], sample_rate_hz=context.sample_rate_hz, settings=settings)
    context.checkpoint()
    return BranchOutput(files={"apd.json": _json(inv.to_dict())})


def run_harmonics(context: BranchContext) -> BranchOutput:
    """Compute harmonics and write ``harmonics.json`` plus ``harmonic_spectra.json``."""
    inv = compute_harmonics(context.channels[0], sample_rate_hz=context.sample_rate_hz)
    context.checkpoint()
    spectra = {
        "estimated_grid_hz": inv.estimated_grid_frequency_hz,
        "windows": [
            {"index": w.index, "thd": w.thd, "fundamental_rms": w.fundamental_rms}
            for w in inv.windows
        ],
    }
    return BranchOutput(
        files={
            "harmonics.json": _json(inv.to_dict()),
            "harmonic_spectra.json": _json(spectra),
        }
    )


def run_burst(context: BranchContext) -> BranchOutput:
    """Detect bursts and write ``burst.json``."""
    settings = burst_preset("burst_default")
    inventory = detect_bursts(
        context.channels[0],
        sample_rate_hz=context.sample_rate_hz,
        settings=settings,
    )
    context.checkpoint()
    return BranchOutput(files={"burst.json": _json(inventory.to_dict())})


def run_trends(context: BranchContext) -> BranchOutput:
    """Compute trends and write ``trends.json``."""
    inv = compute_trends(
        context.channels[0], sample_rate_hz=context.sample_rate_hz, settings=trends_preset()
    )
    context.checkpoint()
    return BranchOutput(files={"trends.json": _json(inv.to_dict())})


def run_power_quality(context: BranchContext) -> BranchOutput:
    """Detect ITIC events and write ``power_quality.json`` plus ``half_cycle_rms.json``."""
    settings = power_quality_preset("itic_default")
    rms_series = detect_half_cycle_rms(
        context.channels[0],
        line_frequency_hz=50.0,
        chunk_samples=settings.chunk_samples,
    )
    context.checkpoint()
    inventory = detect_power_quality(rms_series, settings=settings)
    rms_payload = {
        "count": int(rms_series.rms_v.size),
        "times_s": rms_series.times_s.tolist(),
        "rms_v": rms_series.rms_v.tolist(),
        "edges_s": rms_series.edges_s.tolist(),
    }
    return BranchOutput(
        files={
            "power_quality.json": _json(inventory.to_dict()),
            "half_cycle_rms.json": _json(rms_payload),
        }
    )
