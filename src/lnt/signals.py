"""Синтетический генератор сигналов сети: профили, иголки, звон, 50 Гц.

CH1 — ВЧ-картина X2-пробника: line-sync иголки (2 на цикл, у вершин напряжения)
как затухающий звон f0/Q + асинхронные пуассоновские импульсы + белый фон.
CH2 — вторичка трансформатора: 50 Гц синус с медленной огибающей.
`SyntheticTruth` профиля — одновременно спека генерации и ground truth анализа.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.types import SyntheticTruth

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]

LF_PEAK_V = 3.0
LF_NOISE_SIGMA_V = 0.01
HF_BACKGROUND_SIGMA_V = 0.002
ENVELOPE_FREQUENCY_HZ = 0.7
RING_LENGTH_TAUS = 6.0
ASYNC_AMPLITUDE_RATIO = 0.5

PROFILES: Mapping[str, SyntheticTruth] = MappingProxyType(
    {
        "bad": SyntheticTruth(
            needle_mean_v=0.20,
            needle_sigma_ratio=0.20,
            needle_jitter_us=1.5,
            ring_f0_hz=22_400.0,
            ring_q=16.0,
            async_rate_hz=120.0,
            lf_envelope_cv=0.015,
        ),
        "bad-damped": SyntheticTruth(
            needle_mean_v=0.05,
            needle_sigma_ratio=0.20,
            needle_jitter_us=1.5,
            ring_f0_hz=22_400.0,
            ring_q=16.0,
            async_rate_hz=120.0,
            lf_envelope_cv=0.015,
        ),
        "quiet": SyntheticTruth(
            needle_mean_v=0.01,
            needle_sigma_ratio=0.10,
            needle_jitter_us=1.5,
            ring_f0_hz=22_400.0,
            ring_q=16.0,
            async_rate_hz=5.0,
            lf_envelope_cv=0.005,
        ),
        "sync-only": SyntheticTruth(
            needle_mean_v=0.20,
            needle_sigma_ratio=0.20,
            needle_jitter_us=1.5,
            ring_f0_hz=22_400.0,
            ring_q=16.0,
            async_rate_hz=0.0,
            lf_envelope_cv=0.015,
        ),
        "async-heavy": SyntheticTruth(
            needle_mean_v=0.20,
            needle_sigma_ratio=0.20,
            needle_jitter_us=1.5,
            ring_f0_hz=22_400.0,
            ring_q=16.0,
            async_rate_hz=500.0,
            lf_envelope_cv=0.015,
        ),
    },
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SyntheticSession:
    """Сгенерированная пара каналов с ground truth профиля."""

    profile: str
    ch1: Float32Array
    ch2: Float32Array
    truth: SyntheticTruth


@dataclass(frozen=True, slots=True, kw_only=True)
class _Timebase:
    sample_count: int
    sample_rate_hz: float
    line_frequency_hz: float
    mains_phase_rad: float

    @property
    def duration_s(self) -> float:
        return self.sample_count / self.sample_rate_hz


def generate(
    *,
    profile: str,
    duration_s: float,
    sample_rate_hz: float,
    rng: np.random.Generator,
    line_frequency_hz: float = 50.0,
) -> SyntheticSession:
    """Генерирует синтетическую сессию по имени профиля из ``PROFILES``."""
    truth = PROFILES.get(profile)
    if truth is None:
        known = ", ".join(sorted(PROFILES))
        raise InputError(f"неизвестный profile {profile!r}; доступны: {known}")
    sample_count = round(duration_s * sample_rate_hz)
    if sample_count <= 0:
        raise InputError("длительность и частота дискретизации должны давать больше нуля отсчётов")
    timebase = _Timebase(
        sample_count=sample_count,
        sample_rate_hz=sample_rate_hz,
        line_frequency_hz=line_frequency_hz,
        mains_phase_rad=float(rng.uniform(0.0, 2.0 * np.pi)),
    )
    ch2 = _generate_lf(timebase, truth, rng)
    ch1 = _generate_hf(timebase, truth, rng)
    return SyntheticSession(profile=profile, ch1=ch1, ch2=ch2, truth=truth)


def _generate_lf(
    timebase: _Timebase,
    truth: SyntheticTruth,
    rng: np.random.Generator,
) -> Float32Array:
    t = np.arange(timebase.sample_count, dtype=np.float64) / timebase.sample_rate_hz
    envelope_phase = float(rng.uniform(0.0, 2.0 * np.pi))
    envelope = 1.0 + truth.lf_envelope_cv * np.sqrt(2.0) * np.sin(
        2.0 * np.pi * ENVELOPE_FREQUENCY_HZ * t + envelope_phase,
    )
    mains = np.sin(2.0 * np.pi * timebase.line_frequency_hz * t + timebase.mains_phase_rad)
    noise = rng.normal(0.0, LF_NOISE_SIGMA_V, timebase.sample_count)
    return (LF_PEAK_V * envelope * mains + noise).astype(np.float32)


def _generate_hf(
    timebase: _Timebase,
    truth: SyntheticTruth,
    rng: np.random.Generator,
) -> Float32Array:
    out = rng.normal(0.0, HF_BACKGROUND_SIGMA_V, timebase.sample_count)
    kernel = _ring_kernel(
        sample_rate_hz=timebase.sample_rate_hz,
        f0_hz=truth.ring_f0_hz,
        q=truth.ring_q,
    )
    half_period_s = 1.0 / (2.0 * timebase.line_frequency_hz)
    first_peak_s = ((np.pi / 2.0 - timebase.mains_phase_rad) % np.pi) / (
        2.0 * np.pi * timebase.line_frequency_hz
    )
    peak_times = np.arange(first_peak_s, timebase.duration_s, half_period_s)
    for index in range(peak_times.size):
        jitter_s = float(rng.normal(0.0, truth.needle_jitter_us * 1e-6))
        amplitude = truth.needle_mean_v * _amplitude_factor(truth.needle_sigma_ratio, rng)
        sign = 1.0 if index % 2 == 0 else -1.0
        start = round((float(peak_times[index]) + jitter_s) * timebase.sample_rate_hz)
        _add_burst(out, start, sign * amplitude * kernel)
    async_count = rng.poisson(truth.async_rate_hz * timebase.duration_s)
    for _ in range(async_count):
        position_s = float(rng.uniform(0.0, timebase.duration_s))
        amplitude = (
            ASYNC_AMPLITUDE_RATIO
            * truth.needle_mean_v
            * _amplitude_factor(truth.needle_sigma_ratio, rng)
        )
        sign = float(rng.choice((-1.0, 1.0)))
        _add_burst(out, round(position_s * timebase.sample_rate_hz), sign * amplitude * kernel)
    return out.astype(np.float32)


def _amplitude_factor(sigma_ratio: float, rng: np.random.Generator) -> float:
    return max(0.0, 1.0 + sigma_ratio * float(rng.standard_normal()))


def _ring_kernel(*, sample_rate_hz: float, f0_hz: float, q: float) -> Float64Array:
    tau_s = q / (np.pi * f0_hz)
    length = max(8, round(RING_LENGTH_TAUS * tau_s * sample_rate_hz))
    t = np.arange(length, dtype=np.float64) / sample_rate_hz
    return np.exp(-t / tau_s) * np.sin(2.0 * np.pi * f0_hz * t)


def _add_burst(out: Float64Array, start_index: int, burst: Float64Array) -> None:
    if start_index >= out.size or start_index + burst.size <= 0:
        return
    source_start = max(0, -start_index)
    target_start = max(0, start_index)
    count = min(out.size - target_start, burst.size - source_start)
    out[target_start : target_start + count] += burst[source_start : source_start + count]
