"""F13: совместная активность трёх фазово-остаточных полосовых огибающих."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.f13_math import (
    PAIR_INDICES,
    LagAccumulator,
    declared_lag_samples,
    envelope_mad,
    select_peak_lag,
)
from lnt.characterization.f13_result import (
    INSUFFICIENT_ACTIVITY,
    LAG_SUPPORT_TOO_SHORT,
    MIXED_UNAVAILABLE_SUPPORT,
    NONFINITE_INPUT,
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_ZERO,
    F13Declarations,
    F13Result,
)
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.envelope_models import BandEnvelopes, EnvelopeChunk


def compute_f13_band_envelope_coactivity(
    source: BandEnvelopes,
    declarations: F13Declarations,
    resolved_bands: tuple[ResolvedBand, ...],
    *,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F13Result:
    """Считать F13 только из уже подготовленных общих band-envelope остатков."""
    _validate_inputs(source, declarations, resolved_bands, resources)
    lag_samples = declared_lag_samples(
        declarations.lag_low_s,
        declarations.lag_high_s,
        source.sample_rate_hz,
        declarations.maximum_lag_points,
    )
    lag = LagAccumulator.empty(lag_samples)
    segments, reasons = _collect_segments(source, lag, checkpoint)
    if not segments:
        return _unavailable(_reasons(reasons, PHASE_REFERENCE_UNAVAILABLE), source, resolved_bands)
    values = np.concatenate(segments, axis=1)
    qualified = values.shape[1]
    mads = np.asarray([envelope_mad(row) for row in values], dtype=np.float64)
    if bool(np.any(mads <= 0.0)) or not np.all(np.isfinite(mads)):
        return _unavailable(_reasons(reasons, SCALE_ZERO), source, resolved_bands)
    active = values > declarations.activity_threshold_mad * mads[:, None]
    active_counts = np.count_nonzero(active, axis=1).astype(np.int64)
    if bool(np.any(active_counts < declarations.minimum_active_samples)):
        return _unavailable(_reasons(reasons, INSUFFICIENT_ACTIVITY), source, resolved_bands)
    if lag.usable_segment_count == 0:
        return _unavailable(_reasons(reasons, LAG_SUPPORT_TOO_SHORT), source, resolved_bands)
    try:
        lag_correlations = lag.normalized()
        zero, coincidence, lift = _pair_summaries(values, active)
    except ValueError:
        return _unavailable(_reasons(reasons, SCALE_ZERO), source, resolved_bands)
    maximum_lag, maximum_correlation = _lag_summaries(lag_samples, lag_correlations)
    maximum_lag /= source.sample_rate_hz
    return F13Result(
        status=Status.PARTIAL if reasons else Status.AVAILABLE,
        reason_codes=tuple(sorted(reasons)),
        band_names=tuple(band.requested.name for band in resolved_bands),
        bands_hz=tuple((band.requested.low_hz, band.requested.high_hz) for band in resolved_bands),
        lag_s=lag_samples / source.sample_rate_hz,
        activity_fraction=active_counts / qualified,
        active_sample_count=active_counts,
        sample_count=source.sample_count,
        qualified_sample_count=qualified,
        zero_lag_correlation=zero,
        coincidence_probability=coincidence,
        lift=lift,
        maximum_lag_s=maximum_lag,
        maximum_lag_correlation=maximum_correlation,
    )


def _validate_inputs(
    source: BandEnvelopes,
    declarations: F13Declarations,
    bands: tuple[ResolvedBand, ...],
    resources: ResourceLimits,
) -> None:
    """Сверить общий корень с объявленными F13 полосами и фазовой сеткой."""
    declared = tuple((float(pair[0]), float(pair[1])) for pair in declarations.bands_hz)
    if (
        not math.isfinite(source.sample_rate_hz)
        or source.sample_rate_hz <= 0.0
        or source.sample_count < 0
        or resources.chunk_samples <= 0
        or len(bands) != len(PAIR_INDICES)
        or len(source.bands) != len(PAIR_INDICES)
    ):
        raise ValueError("F13 shared roots do not match the declared geometry")
    if any(
        (band.requested.low_hz, band.requested.high_hz) != pair
        for band, pair in zip(bands, declared, strict=True)
    ):
        raise ValueError("F13 resolved bands do not match the recipe declarations")
    for prepared, band in zip(source.bands, bands, strict=True):
        if (
            prepared.resolved != band
            or prepared.filter_order != declarations.filter_order
            or prepared.phase_means.means_v.size != declarations.phase_bins
        ):
            raise ValueError("F13 band-envelope root does not match shared bands")


def _collect_segments(
    source: BandEnvelopes,
    lag: LagAccumulator,
    checkpoint: Callable[[], None] | None,
) -> tuple[list[np.ndarray], set[str]]:
    """Склеить только непрерывные общие-qualified спаны, не переходя разрывы."""
    parts: list[np.ndarray] = []
    segments: list[np.ndarray] = []
    reasons: set[str] = set()

    def flush() -> None:
        if not parts:
            return
        segment = np.concatenate(parts, axis=1)
        parts.clear()
        segments.append(segment)
        lag.add(segment)

    for _, _, values, valid, chunk_reasons in _aligned_chunks(source, checkpoint):
        if checkpoint is not None:
            checkpoint()
        reasons.update(chunk_reasons)
        common = np.all(valid, axis=0)
        bounds = np.flatnonzero(np.diff(np.concatenate(([False], common, [False]))))
        for low, high in bounds.reshape(-1, 2).tolist():
            if low > 0:
                flush()
            parts.append(values[:, low:high].copy())
        if not bool(common[-1]):
            flush()
    flush()
    if len(reasons) > 1:
        reasons.add(MIXED_UNAVAILABLE_SUPPORT)
    return segments, reasons


def _aligned_chunks(  # noqa: C901 - выравнивание трёх независимых потоков
    source: BandEnvelopes, checkpoint: Callable[[], None] | None
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray, set[str]]]:
    """Совместить три независимых потока остатков на нативной сетке отсчётов."""
    streams = [source.stream_residuals(index, checkpoint) for index in range(3)]
    chunks: list[EnvelopeChunk | None] = [next(stream, None) for stream in streams]
    cursor = 0
    while cursor < source.sample_count:
        stop = source.sample_count
        for index, stream in enumerate(streams):
            while (chunk := chunks[index]) is not None and chunk.stop_sample <= cursor:
                chunks[index] = next(stream, None)
            chunk = chunks[index]
            if chunk is None:
                continue
            if chunk.start_sample > cursor:
                stop = min(stop, chunk.start_sample)
            else:
                stop = min(stop, chunk.stop_sample)
        if stop <= cursor or stop > source.sample_count:
            raise ValueError("F13 residual stream has invalid chunk geometry")
        size = stop - cursor
        values = np.zeros((3, size), dtype=np.float64)
        valid = np.zeros((3, size), dtype=np.bool_)
        reasons: set[str] = set()
        for index, chunk in enumerate(chunks):
            if chunk is None or not chunk.start_sample <= cursor < chunk.stop_sample:
                continue
            low = cursor - chunk.start_sample
            high = stop - chunk.start_sample
            span = chunk.stop_sample - chunk.start_sample
            if chunk.values.shape != (span,) or chunk.valid.shape != (span,):
                raise ValueError("F13 residual chunk shape differs from its sample span")
            source_values = chunk.values[low:high]
            finite = np.isfinite(source_values)
            values[index] = source_values
            valid[index] = chunk.valid[low:high] & finite
            if not bool(np.all(finite)):
                reasons.add(NONFINITE_INPUT)
            if chunk.reason_code is not None:
                reasons.add(chunk.reason_code)
        yield cursor, stop, values, valid, reasons
        cursor = stop


def _pair_summaries(
    values: np.ndarray, active: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Посчитать три уникальные пары и заполнить симметричные матрицы."""
    zero = np.eye(3, dtype=np.float64)
    coincidence = np.diag(np.mean(active, axis=1))
    fraction = np.mean(active, axis=1)
    lift = np.eye(3, dtype=np.float64)
    for first, second in PAIR_INDICES:
        probability = float(np.mean(active[first] & active[second]))
        enrichment = probability / (fraction[first] * fraction[second])
        correlation = float(np.clip(np.corrcoef(values[first], values[second])[0, 1], -1.0, 1.0))
        zero[first, second] = zero[second, first] = correlation
        coincidence[first, second] = coincidence[second, first] = probability
        lift[first, second] = lift[second, first] = enrichment
    return zero, coincidence, lift


def _lag_summaries(
    lag_samples: np.ndarray, correlations: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Выбрать лаг каждой пары с locked absolute-then-negative правилом."""
    lag = np.zeros((3, 3), dtype=np.float64)
    peak = np.eye(3, dtype=np.float64)
    for pair, (first, second) in enumerate(PAIR_INDICES):
        index = select_peak_lag(correlations[pair], lag_samples)
        selected = float(lag_samples[index])
        value = float(correlations[pair, index])
        lag[first, second] = lag[second, first] = selected
        peak[first, second] = peak[second, first] = value
    return lag, peak


def _reasons(reasons: set[str], required: str) -> tuple[str, ...]:
    """Сохранить машинную причину; fallback добавить только при её отсутствии."""
    selected = set(reasons)
    if not selected:
        selected.add(required)
    if len(selected) > 1:
        selected.add(MIXED_UNAVAILABLE_SUPPORT)
    return tuple(sorted(selected))


def _unavailable(
    codes: tuple[str, ...], source: BandEnvelopes, bands: tuple[ResolvedBand, ...]
) -> F13Result:
    """Вернуть пустые измерения, сохранив объявленные оси и честный размер записи."""
    empty_float = np.empty(0, dtype=np.float64)
    empty_int = np.empty(0, dtype=np.int64)
    return F13Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        band_names=tuple(band.requested.name for band in bands),
        bands_hz=tuple((band.requested.low_hz, band.requested.high_hz) for band in bands),
        lag_s=empty_float,
        activity_fraction=empty_float,
        active_sample_count=empty_int,
        sample_count=source.sample_count,
        qualified_sample_count=0,
        zero_lag_correlation=empty_float,
        coincidence_probability=empty_float,
        lift=empty_float,
        maximum_lag_s=empty_float,
        maximum_lag_correlation=empty_float,
    )
