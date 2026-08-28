"""Детектор APD ITU-R P.2089 + Middleton Class A moment matching (chunked)."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from lnt.apd.models import (
    APD_VERSION,
    ApdInventory,
    ApdPoint,
    ApdSettings,
    MiddletonParams,
    apd_preset,
    apd_settings_hash,
)
from lnt.errors import InputError

FloatArray = NDArray[np.floating]


def _validate(samples: FloatArray, sample_rate_hz: float, settings: ApdSettings) -> int:
    view = np.asarray(samples)
    if view.ndim != 1 or view.size == 0:
        raise InputError("apd: требуется непустой одномерный ряд")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise InputError("apd: частота дискретизации должна быть конечной и >0")
    if settings.chunk_samples <= 0:
        raise InputError("apd: размер блока должен быть >0")
    return int(view.size)


def _stream_moments(samples: FloatArray, chunk_samples: int) -> tuple[float, float, float]:
    """Потоко-совместимые моменты: mean_power, mean четвертой степени, rms."""
    n = int(np.asarray(samples).size)
    sum2 = 0.0
    sum4 = 0.0
    count = 0
    for start in range(0, n, chunk_samples):
        stop = min(n, start + chunk_samples)
        chunk = np.asarray(samples[start:stop], dtype=np.float64)
        # ignore non-finite chunk values for robustness? treat as 0 not counted?
        # мы требуем finite, иначе InputError выше; но на всякий
        finite = chunk[np.isfinite(chunk)]
        if finite.size == 0:
            continue
        sum2 += float(np.sum(finite * finite))
        sum4 += float(np.sum(finite**4))
        count += int(finite.size)
    if count == 0:
        raise InputError("apd: ряд не содержит конечных значений")
    mean_power = sum2 / float(count)
    mean_pow4 = sum4 / float(count)
    rms = math.sqrt(mean_power) if mean_power > 0 else 0.0
    return mean_power, mean_pow4, rms


def _estimate_middleton(mean_power: float, mean_pow4: float, rms: float) -> MiddletonParams:
    """Оценивает A и Gamma по эксцессу (моментный матчинг)."""
    if mean_power <= 1e-18:  # noqa: PLR2004
        return MiddletonParams(
            overlap_index_A=10.0, gamma=100.0, rms_v=rms, kurtosis=3.0, mean_power=mean_power
        )
    kurtosis = mean_pow4 / (mean_power * mean_power) if mean_power > 0 else 3.0
    if not math.isfinite(kurtosis):
        kurtosis = 3.0
    excess = max(float(kurtosis) - 3.0, 0.0)
    # moment-matching mapping: Gaussian -> A~10 Gamma~10 ; impulsive excess large -> small A/Gamma
    overlap = 10.0 / (1.0 + 2.0 * excess)
    overlap = float(min(max(overlap, 0.001), 10.0))
    gamma = 10.0 / (1.0 + excess)
    gamma = float(min(max(gamma, 0.01), 100.0))
    return MiddletonParams(
        overlap_index_A=overlap,
        gamma=gamma,
        rms_v=rms,
        kurtosis=float(kurtosis),
        mean_power=float(mean_power),
    )


def _build_envelope(samples: FloatArray, chunk_samples: int) -> NDArray[np.float64]:
    """Строит огибающую |x| блоками (bounded scan)."""
    n = int(np.asarray(samples).size)
    out = np.empty(n, dtype=np.float64)
    for start in range(0, n, chunk_samples):
        stop = min(n, start + chunk_samples)
        chunk = np.asarray(samples[start:stop], dtype=np.float64)
        out[start:stop] = np.abs(chunk)
    return out


def _apd_points(envelope: NDArray[np.float64], rms: float, num_levels: int) -> tuple[ApdPoint, ...]:
    """Строит APD как CCDF огибающей (ITU-R P.2089)."""
    n = int(envelope.size)
    if n == 0 or rms <= 1e-18:  # noqa: PLR2004
        return ()
    sorted_env = np.sort(envelope)[::-1]
    # вероятности превышения
    probs = (np.arange(1, n + 1, dtype=np.float64) / float(n)).astype(np.float64)
    # downsample to num_levels uniformly in index space (log-like coverage)
    if n <= num_levels:
        idx = np.arange(n)
    else:
        idx = np.unique(np.linspace(0, n - 1, num_levels, dtype=np.int64))
    sel_env = sorted_env[idx]
    sel_prob = probs[idx]
    # levels in dB above rms: 20log10(A/rms)
    # clip to avoid log(0)
    ratio = sel_env / rms
    ratio = np.maximum(ratio, 1e-12)
    levels_db = 20.0 * np.log10(ratio)
    points: list[ApdPoint] = []
    for lvl, prob, amp in zip(levels_db, sel_prob, sel_env, strict=False):
        points.append(
            ApdPoint(level_db=float(lvl), exceedance_prob=float(prob), amplitude_v=float(amp))
        )
    return tuple(points)


def _apd_slope(points: tuple[ApdPoint, ...]) -> float:
    """Наклон APD: линейная регрессия level_db vs log10(prob) (dB/decade)."""
    if len(points) < 4:  # noqa: PLR2004
        return 0.0
    xs = np.array(
        [math.log10(max(p.exceedance_prob, 1e-12)) for p in points],
        dtype=np.float64,
    )
    ys = np.array([p.level_db for p in points], dtype=np.float64)
    # least squares slope
    x_mean = float(np.mean(xs))
    y_mean = float(np.mean(ys))
    denom = float(np.sum((xs - x_mean) ** 2))
    if denom < 1e-12:  # noqa: PLR2004
        return 0.0
    return float(np.sum((xs - x_mean) * (ys - y_mean)) / denom)


def compute_apd(
    samples: FloatArray,
    *,
    sample_rate_hz: float,
    settings: ApdSettings | None = None,
) -> ApdInventory:
    """Вычисляет APD и параметры Middleton Class A блоками."""
    if settings is None:
        settings = apd_preset()
    n = _validate(samples, sample_rate_hz, settings)
    duration_s = float(n) / float(sample_rate_hz)
    mean_power, mean_pow4, rms = _stream_moments(samples, settings.chunk_samples)
    middleton = _estimate_middleton(mean_power, mean_pow4, rms)
    envelope = _build_envelope(samples, settings.chunk_samples)
    apd = _apd_points(envelope, rms, settings.num_levels)
    slope = _apd_slope(apd)
    return ApdInventory(
        schema_version=APD_VERSION,
        settings_hash=apd_settings_hash(settings),
        settings=settings,
        sample_rate_hz=float(sample_rate_hz),
        sample_count=n,
        duration_s=duration_s,
        rms_v=float(rms),
        middleton=middleton,
        apd_slope_db_per_decade=float(slope),
        apd=apd,
    )
