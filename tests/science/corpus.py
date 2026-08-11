"""Compact seeded waveform generators with analytic, non-engine-derived truth."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

import numpy as np
from numpy.typing import NDArray

Float32Array = NDArray[np.float32]
RATE_HZ: Final = 16_384.0
COUNT: Final = 16_384
SEED: Final = 20260811


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalyticTruth:
    """Expected physical estimands and why each tolerance is scientifically valid."""

    rms_v: float
    peak_hz: float | None = None
    peak_amplitude_v: float | None = None
    thd_ratio: float | None = None
    band_power_v2: float | None = None
    event_samples: tuple[int, ...] = ()
    tolerance_rationale: str = (
        "Frequency tolerance is one FFT bin; RMS/amplitude tolerances cover float32 "
        "roundoff and periodic-Hann leakage; noise powers use finite-sample estimator variance."
    )
    block_labels: tuple[str, ...] = ()
    effect_size_v: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ScienceFixture:
    """Generated samples plus their seed, sample geometry, and analytic truth."""

    name: str
    samples: Float32Array
    sample_rate_hz: float
    seed: int
    truth: AnalyticTruth

    def digest(self) -> str:
        """Return a stable byte-level identity for determinism checks."""
        return sha256(self.samples.tobytes()).hexdigest()


def _time(count: int = COUNT, rate_hz: float = RATE_HZ) -> NDArray[np.float64]:
    return np.arange(count, dtype=np.float64) / rate_hz


def pure_tone() -> ScienceFixture:
    amplitude, frequency = 0.8, 1_024.0
    samples = (amplitude * np.sin(2 * np.pi * frequency * _time())).astype(np.float32)
    return ScienceFixture(
        name="pure_tone",
        samples=samples,
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=amplitude / np.sqrt(2),
            peak_hz=frequency,
            peak_amplitude_v=amplitude,
            band_power_v2=amplitude**2 / 2,
        ),
    )


def multitone_harmonics() -> ScienceFixture:
    fundamental, amplitudes = 512.0, (1.0, 0.1, 0.05)
    phase = 2 * np.pi * fundamental * _time()
    samples = sum(a * np.sin((index + 1) * phase) for index, a in enumerate(amplitudes))
    harmonic_rms = np.sqrt(amplitudes[1] ** 2 + amplitudes[2] ** 2) / np.sqrt(2)
    return ScienceFixture(
        name="multitone_harmonics",
        samples=np.asarray(samples, dtype=np.float32),
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=np.sqrt(sum(a * a for a in amplitudes) / 2),
            peak_hz=fundamental,
            peak_amplitude_v=amplitudes[0],
            thd_ratio=harmonic_rms / (amplitudes[0] / np.sqrt(2)),
        ),
    )


def chirp() -> ScienceFixture:
    start, end, duration = 200.0, 3_000.0, COUNT / RATE_HZ
    time = _time()
    phase = 2 * np.pi * (start * time + 0.5 * (end - start) / duration * time**2)
    return ScienceFixture(
        name="chirp",
        samples=np.sin(phase).astype(np.float32),
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=1 / np.sqrt(2),
            band_power_v2=0.5,
            tolerance_rationale=(
                "RMS tolerance covers incomplete endpoint cycles; chirp band is analytic."
            ),
        ),
    )


def amplitude_modulated() -> ScienceFixture:
    carrier, modulation, depth = 2_000.0, 64.0, 0.5
    time = _time()
    samples = (1 + depth * np.cos(2 * np.pi * modulation * time)) * np.sin(
        2 * np.pi * carrier * time
    )
    rms = np.sqrt((1 + depth**2 / 2) / 2)
    return ScienceFixture(
        name="am",
        samples=samples.astype(np.float32),
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(rms_v=rms, peak_hz=carrier, peak_amplitude_v=1.0),
    )


def switching_burst() -> ScienceFixture:
    start, stop, frequency = 4_096, 6_144, 2_048.0
    samples = np.zeros(COUNT, dtype=np.float32)
    samples[start:stop] = np.sin(2 * np.pi * frequency * _time(stop - start)).astype(np.float32)
    return ScienceFixture(
        name="switching_burst",
        samples=samples,
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=np.sqrt((stop - start) / COUNT / 2),
            peak_hz=frequency,
            event_samples=(start, stop - 1),
        ),
    )


def impulses() -> ScienceFixture:
    locations = (2_048, 8_192, 14_336)
    samples = np.zeros(COUNT, dtype=np.float32)
    samples[list(locations)] = (0.5, -0.75, 1.0)
    return ScienceFixture(
        name="impulses",
        samples=samples,
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=np.sqrt((0.5**2 + 0.75**2 + 1.0) / COUNT), event_samples=locations
        ),
    )


def clipped() -> ScienceFixture:
    raw = 1.5 * np.sin(2 * np.pi * 512 * _time())
    samples = np.clip(raw, -1.0, 1.0).astype(np.float32)
    return ScienceFixture(
        name="clipping",
        samples=samples,
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))),
            peak_hz=512.0,
            peak_amplitude_v=1.0,
            tolerance_rationale=(
                "Clipped RMS is the exact deterministic sample sum; peak tolerance is one bin."
            ),
        ),
    )


def dropout() -> ScienceFixture:
    samples = np.sin(2 * np.pi * 1_024 * _time()).astype(np.float32)
    samples[6_000:7_000] = 0
    return ScienceFixture(
        name="dropout",
        samples=samples,
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))),
            event_samples=(6_000, 6_999),
            tolerance_rationale="Dropout endpoints are exact; RMS uses analytic sample sum.",
        ),
    )


def drift() -> ScienceFixture:
    time = _time()
    phase = 2 * np.pi * (49.5 * time + 0.5 * time**2)
    return ScienceFixture(
        name="drift",
        samples=(12 * np.sin(phase)).astype(np.float32),
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=12 / np.sqrt(2),
            peak_hz=50.0,
            tolerance_rationale="One-second linear chirp spans 49.5–50.5 Hz; FFT peak is midpoint.",
        ),
    )


def baseline_excess() -> ScienceFixture:
    rng = np.random.default_rng(SEED)
    baseline_sigma, excess_sigma = 0.01, 0.02
    samples = rng.normal(0, np.sqrt(baseline_sigma**2 + excess_sigma**2), COUNT).astype(np.float32)
    return ScienceFixture(
        name="baseline_excess",
        samples=samples,
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=np.sqrt(baseline_sigma**2 + excess_sigma**2),
            band_power_v2=excess_sigma**2,
            tolerance_rationale=(
                "5% covers Gaussian RMS variance at N=16384; excess is variance subtraction."
            ),
        ),
    )


def aba_effect() -> ScienceFixture:
    rng = np.random.default_rng(SEED)
    block = 4_096
    offsets = np.repeat(np.array([0.0, 0.2, 0.0, 0.2]), block)
    samples = (offsets + rng.normal(0, 0.01, offsets.size)).astype(np.float32)
    return ScienceFixture(
        name="aba_effect",
        samples=samples,
        sample_rate_hz=RATE_HZ,
        seed=SEED,
        truth=AnalyticTruth(
            rms_v=float(np.sqrt(0.5 * 0.2**2 + 0.01**2)),
            block_labels=("A1", "B1", "A2", "B2"),
            effect_size_v=0.2,
            tolerance_rationale=(
                "Mean-effect tolerance follows sigma/sqrt(block N); blocks are explicit."
            ),
        ),
    )


def all_fixtures() -> tuple[ScienceFixture, ...]:
    """Generate the complete requested corpus from compact recipes."""
    return (
        pure_tone(),
        multitone_harmonics(),
        chirp(),
        amplitude_modulated(),
        switching_burst(),
        impulses(),
        clipped(),
        dropout(),
        drift(),
        baseline_excess(),
        aba_effect(),
    )
