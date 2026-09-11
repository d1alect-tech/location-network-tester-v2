"""Bounded reusable analytic band streams and phase-residual envelopes."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.characterization.bands import ResolvedBand, resolve_characterization_bands
from lnt.characterization.envelope_models import BandEnvelope, BandEnvelopes, EnvelopeChunk
from lnt.characterization.local_transform import (
    TransformChunk,
    TransformSpec,
    stream_local_transform,
)
from lnt.characterization.phase import PhaseCycles, phase_bins
from lnt.characterization.phase_model import PhaseMeans
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.analysis_store.recipe_v2 import CharacterizationRecipe

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]

_ENVELOPE_CORE_SAMPLES = 4096
_ANALYTIC_HALO_SAMPLES = 16_384


def stream_band_analytic(  # noqa: PLR0913
    samples: FloatInput,
    band: ResolvedBand,
    *,
    sample_rate_hz: float,
    filter_order: int,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
    detrend: bool = False,
) -> Iterator[TransformChunk]:
    """Stream a band's raw analytic signal independently of phase qualification."""
    if band.effective is None:
        yield from _unavailable_transforms(int(samples.size), resources, band.reason_code)
        return
    if filter_order <= 0:
        raise ValueError("filter order must be positive")
    effective = band.effective
    sos = np.asarray(
        signal.butter(
            filter_order,
            (effective.low_hz, effective.high_hz),
            btype="bandpass",
            fs=sample_rate_hz,
            output="sos",
        ),
        dtype=np.float64,
    )
    yield from stream_local_transform(
        samples,
        spec=TransformSpec(
            sos=sos,
            analytic=True,
            detrend=detrend,
            analytic_halo_samples=_ANALYTIC_HALO_SAMPLES,
        ),
        resources=replace(
            resources,
            chunk_samples=min(resources.chunk_samples, _ENVELOPE_CORE_SAMPLES),
        ),
        checkpoint=checkpoint,
    )


def prepare_band_envelopes(
    samples: FloatInput,
    phase: PhaseCycles,
    recipe: CharacterizationRecipe,
    *,
    sample_rate_hz: float,
    checkpoint: Callable[[], None] | None = None,
) -> BandEnvelopes:
    """Build each supported band's fixed phase-envelope summary exactly once."""
    if phase.sample_count != int(samples.size) or phase.sample_rate_hz != sample_rate_hz:
        raise ValueError("phase and envelope sample grids differ")
    resolved = resolve_characterization_bands(recipe, sample_rate_hz)
    family = next(item for item in recipe.families if item.id == "f13_band_envelope_coactivity")
    filter_order = cast("int", family.value("filter_order"))
    bin_count = recipe.phase.phase_bins
    bands = tuple(
        BandEnvelope(
            band,
            filter_order,
            _compute_envelope_means(
                samples=samples,
                phase=phase,
                band=band,
                filter_order=filter_order,
                bin_count=bin_count,
                minimum_support=recipe.phase.minimum_support_per_bin,
                resources=recipe.resource_limits,
                sample_rate_hz=sample_rate_hz,
                checkpoint=checkpoint,
            ),
        )
        for band in resolved
    )

    def stream_factory(
        band_index: int, replay_checkpoint: Callable[[], None] | None
    ) -> Iterator[EnvelopeChunk]:
        item = bands[band_index]
        return _stream_residuals(
            samples=samples,
            phase=phase,
            item=item,
            bin_count=bin_count,
            resources=recipe.resource_limits,
            sample_rate_hz=sample_rate_hz,
            checkpoint=replay_checkpoint,
        )

    return BandEnvelopes(bands, int(samples.size), sample_rate_hz, stream_factory)


def _compute_envelope_means(  # noqa: PLR0913
    *,
    samples: FloatInput,
    phase: PhaseCycles,
    band: ResolvedBand,
    filter_order: int,
    bin_count: int,
    minimum_support: int,
    resources: ResourceLimits,
    sample_rate_hz: float,
    checkpoint: Callable[[], None] | None,
) -> PhaseMeans:
    sums = np.zeros(bin_count, dtype=np.float64)
    counts = np.zeros(bin_count, dtype=np.int64)
    if band.effective is None:
        return _phase_means_result(sums, counts, minimum_support, band.reason_code)
    if phase.status is Status.UNAVAILABLE:
        return _phase_means_result(sums, counts, minimum_support, "phase_reference_unavailable")
    for chunk in stream_band_analytic(
        samples,
        band,
        sample_rate_hz=sample_rate_hz,
        filter_order=filter_order,
        resources=resources,
        checkpoint=checkpoint,
    ):
        if chunk.values is None:
            continue
        envelope = np.abs(chunk.values)
        indices, valid = phase_bins(phase, chunk.start_sample, chunk.stop_sample, bin_count)
        sums += np.bincount(indices[valid], weights=envelope[valid], minlength=bin_count)
        counts += np.bincount(indices[valid], minlength=bin_count)
    return _phase_means_result(sums, counts, minimum_support, None)


def _phase_means_result(
    sums: Float64Array, counts: NDArray[np.int64], minimum_support: int, reason: str | None
) -> PhaseMeans:
    valid = counts >= minimum_support
    means = np.zeros(sums.size, dtype=np.float64)
    means[valid] = sums[valid] / counts[valid]
    status = (
        Status.AVAILABLE
        if np.all(valid)
        else Status.PARTIAL
        if np.any(valid)
        else Status.UNAVAILABLE
    )
    result_reason = reason if reason is not None else "insuff_phase_support"
    if status is Status.AVAILABLE:
        result_reason = None
    return PhaseMeans(
        means_v=means,
        counts=counts,
        valid_bins=valid,
        status=status,
        reason_code=result_reason,
    )


def _stream_residuals(  # noqa: PLR0913
    *,
    samples: FloatInput,
    phase: PhaseCycles,
    item: BandEnvelope,
    bin_count: int,
    resources: ResourceLimits,
    sample_rate_hz: float,
    checkpoint: Callable[[], None] | None,
) -> Iterator[EnvelopeChunk]:
    unavailable = (
        item.phase_means.reason_code if item.phase_means.status is Status.UNAVAILABLE else None
    )
    if unavailable is not None:
        yield from _unavailable_residuals(int(samples.size), resources, unavailable)
        return
    for chunk in stream_band_analytic(
        samples,
        item.resolved,
        sample_rate_hz=sample_rate_hz,
        filter_order=item.filter_order,
        resources=resources,
        checkpoint=checkpoint,
    ):
        size = chunk.stop_sample - chunk.start_sample
        values = np.zeros(size, dtype=np.float64)
        valid = np.zeros(size, dtype=np.bool_)
        reason = chunk.reason_code or unavailable
        if chunk.values is not None and unavailable is None:
            envelope = np.abs(chunk.values)
            indices, valid = phase_bins(phase, chunk.start_sample, chunk.stop_sample, bin_count)
            valid &= item.phase_means.valid_bins[indices]
            values[valid] = envelope[valid] - item.phase_means.means_v[indices[valid]]
            if not np.all(valid):
                reason = phase.reason_code or "insufficient_phase_support"
        yield EnvelopeChunk(chunk.start_sample, chunk.stop_sample, values, valid, reason)


def _unavailable_transforms(
    sample_count: int, resources: ResourceLimits, reason: str | None
) -> Iterator[TransformChunk]:
    for start in range(0, sample_count, resources.chunk_samples):
        yield TransformChunk(
            start,
            min(sample_count, start + resources.chunk_samples),
            None,
            0,
            reason or "band_above_nyquist",
        )


def _unavailable_residuals(
    sample_count: int, resources: ResourceLimits, reason: str
) -> Iterator[EnvelopeChunk]:
    for start in range(0, sample_count, resources.chunk_samples):
        stop = min(sample_count, start + resources.chunk_samples)
        yield EnvelopeChunk(
            start,
            stop,
            np.zeros(stop - start, dtype=np.float64),
            np.zeros(stop - start, dtype=np.bool_),
            reason,
        )
