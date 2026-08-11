# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=2.1,<3", "scipy>=1.14,<2"]
# ///
# ─── How to run ───
# uv run benchmarks/scientific.py --json benchmark.json
"""30 s × 8 MHz scientific streaming benchmark with enforced budgets."""

from __future__ import annotations

import argparse
import ctypes
import json
import platform
import sys
import tempfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Final, TypedDict, final

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lnt.events import detect_events, event_preset
from lnt.events.settings import DetectionSettings
from lnt.psd import PsdSettings, compute_welch
from lnt.spectrogram import StftSettings, build_overview

if TYPE_CHECKING:
    from collections.abc import Callable

SAMPLE_RATE_HZ: Final = 8_000_000.0
DURATION_S: Final = 30.0
SAMPLE_COUNT: Final = round(SAMPLE_RATE_HZ * DURATION_S)
CHUNK_SAMPLES: Final = 8_000_000
PSD_BUDGET_S: Final = 60.0
SPECTROGRAM_BUDGET_S: Final = 120.0
EVENTS_BUDGET_S: Final = 120.0
RSS_BUDGET_BYTES: Final = 2 * 1024**3


@dataclass(frozen=True, slots=True)
class Measurement:
    """One timed engine operation and its enforced wall-time budget."""

    name: str
    runtime_s: float
    budget_s: float
    detail: str
    passed: bool


class ScientificResult(TypedDict):
    """Machine-readable benchmark evidence schema."""

    schema_version: int
    host: str
    sample_rate_hz: float
    duration_s: float
    sample_count: int
    peak_rss_bytes: int
    rss_budget_bytes: int
    measurements: list[MeasurementPayload]
    passed: bool


class MeasurementPayload(TypedDict):
    """JSON shape for one measurement."""

    name: str
    runtime_s: float
    budget_s: float
    detail: str
    passed: bool


@final
class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_rss_bytes() -> int:
    """Read process high-water RSS without psutil (GetProcessMemoryInfo on Windows)."""
    if platform.system() != "Windows":
        raise OSError("scientific benchmark peak RSS currently requires Windows")
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessMemoryCounters),
        ctypes.c_ulong,
    )
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    process = kernel32.GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
    if not ok:
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return int(counters.PeakWorkingSetSize)


def _generate(path: Path) -> np.memmap:
    """Generate the 960 MB deterministic capture blockwise, never as one RAM array."""
    writable = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=(SAMPLE_COUNT,))
    rng = np.random.default_rng(20260811)
    for start in range(0, SAMPLE_COUNT, CHUNK_SAMPLES):
        stop = min(SAMPLE_COUNT, start + CHUNK_SAMPLES)
        count = stop - start
        time = np.arange(start, stop, dtype=np.float64) / SAMPLE_RATE_HZ
        writable[start:stop] = (
            0.01 * np.sin(2 * np.pi * 22_400 * time) + rng.normal(0, 0.001, count)
        ).astype(np.float32)
    writable.flush()
    return writable


def _measure(name: str, budget_s: float, operation: Callable[[], str]) -> Measurement:
    started = perf_counter()
    detail = str(operation())
    runtime = perf_counter() - started
    return Measurement(name, runtime, budget_s, detail, runtime < budget_s)


def _payload(measurement: Measurement) -> MeasurementPayload:
    return {
        "name": measurement.name,
        "runtime_s": measurement.runtime_s,
        "budget_s": measurement.budget_s,
        "detail": measurement.detail,
        "passed": measurement.passed,
    }


def _run_psd(samples: np.memmap, settings: PsdSettings) -> str:
    return f"segments={compute_welch(samples, settings=settings).segment_count}"


def _run_events(samples: np.memmap, settings: DetectionSettings) -> str:
    inventory = detect_events(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=settings)
    return f"events={len(inventory.events)}"


def run() -> ScientificResult:
    """Generate a temporary memmap and run PSD, overview, and event inventory."""
    measurements: list[Measurement] = []
    with tempfile.TemporaryDirectory(prefix="lnt-science-") as temporary:
        path = Path(temporary) / "capture.npy"
        samples = _generate(path)
        psd_settings = PsdSettings.default(sample_rate_hz=SAMPLE_RATE_HZ)
        measurements.append(
            _measure(
                "streaming_psd",
                PSD_BUDGET_S,
                partial(_run_psd, samples, psd_settings),
            )
        )
        stft = StftSettings(
            version=1,
            window="hann",
            segment_samples=16_384,
            hop_samples=8_192,
            detrend="constant",
            scaling="psd",
        )
        measurements.append(
            _measure(
                "spectrogram_overview",
                SPECTROGRAM_BUDGET_S,
                lambda: (
                    "cells="
                    + str(
                        build_overview(
                            path,
                            sample_rate_hz=SAMPLE_RATE_HZ,
                            settings=stft,
                            max_time_bins=256,
                            max_frequency_bands=128,
                            band_low_hz=3_000,
                            band_high_hz=3_000_000,
                        ).linear_power.size
                    )
                ),
            )
        )
        settings = event_preset("impulses_default")
        measurements.append(
            _measure(
                "events",
                EVENTS_BUDGET_S,
                partial(_run_events, samples, settings),
            )
        )
        samples.flush()
        del samples
    rss = peak_rss_bytes()
    payloads = [_payload(item) for item in measurements]
    passed = all(item.passed for item in measurements) and rss < RSS_BUDGET_BYTES
    return {
        "schema_version": 1,
        "host": platform.node(),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "duration_s": DURATION_S,
        "sample_count": SAMPLE_COUNT,
        "peak_rss_bytes": rss,
        "rss_budget_bytes": RSS_BUDGET_BYTES,
        "measurements": payloads,
        "passed": passed,
    }


def main() -> int:
    """Write JSON evidence and fail the process if any budget is exceeded."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, type=Path)
    output: Path = parser.parse_args().json
    result = run()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
