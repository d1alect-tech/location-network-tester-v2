from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy import signal

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.bands import resolve_characterization_bands
from lnt.characterization.envelopes import prepare_band_envelopes, stream_band_analytic
from lnt.characterization.phase import PhaseCycles, phase_bins
from lnt.characterization.records import Status
from lnt.context.json_codec import decode_object
from lnt.errors import InputError

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"


def _recipe() -> CharacterizationRecipe:
    recipe = parse_analysis_recipe(decode_object(_EXAMPLE.read_text(encoding="utf-8"), "recipe"))
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _resources(
    *, chunk: int = 4096, hard_chunk: int = 262_144, work_bytes: int = 67_108_864
) -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=chunk,
        hard_max_chunk_samples=hard_chunk,
        max_work_bytes=work_bytes,
        max_artifact_bytes=1_000_000,
        max_stored_trajectories=4096,
        max_surrogates=19,
        deterministic_seed=6022,
    )


def _phase(sample_count: int, sample_rate_hz: float, *, available: bool = True) -> PhaseCycles:
    if not available:
        return PhaseCycles(
            sample_rate_hz=sample_rate_hz,
            sample_count=sample_count,
            cycle_start_samples=np.empty(0, dtype=np.float64),
            cycle_end_samples=np.empty(0, dtype=np.float64),
            cycle_valid=np.empty(0, dtype=np.bool_),
            status=Status.UNAVAILABLE,
            reason_code="no_sync_reference",
        )
    period = sample_rate_hz / 50.0
    boundaries = np.arange(0.0, sample_count + period, period, dtype=np.float64)
    boundaries = boundaries[boundaries <= sample_count]
    return PhaseCycles(
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        cycle_start_samples=boundaries[:-1],
        cycle_end_samples=boundaries[1:],
        cycle_valid=np.ones(boundaries.size - 1, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def test_raw_analytic_carrier_has_expected_zero_phase_filter_gain() -> None:
    sample_rate_hz = 128_000.0
    carrier_hz = 24_000.0
    times = np.arange(1_048_576, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * carrier_hz * times)
    band = resolve_characterization_bands(_recipe(), sample_rate_hz)[1]

    chunks = list(
        stream_band_analytic(
            samples,
            band,
            sample_rate_hz=sample_rate_hz,
            filter_order=4,
            resources=_resources(hard_chunk=1_048_576, work_bytes=268_435_456),
        )
    )

    sos = signal.butter(4, (10_000.0, 50_000.0), btype="bandpass", fs=sample_rate_hz, output="sos")
    response = np.asarray(
        signal.sosfreqz(
            sos,
            worN=np.array([2.0 * np.pi * carrier_hz / sample_rate_hz]),
        )[1],
        dtype=np.complex128,
    )
    expected = float(np.abs(response[0]) ** 2)
    supported = [chunk for chunk in chunks if chunk.values is not None]
    assert supported
    for chunk in supported:
        assert chunk.values is not None
        assert chunk.values.dtype == np.complex128
        # Local finite Hilbert transforms are checked against gain, not global equality.
        assert np.allclose(np.abs(chunk.values), expected, rtol=2e-5, atol=2e-5)


def test_raw_analytic_recovers_known_am_envelope_without_phase() -> None:
    sample_rate_hz = 128_000.0
    times = np.arange(1_048_576, dtype=np.float64) / sample_rate_hz
    expected = 1.0 + 0.3 * np.cos(2.0 * np.pi * 20.0 * times)
    samples = expected * np.cos(2.0 * np.pi * 24_000.0 * times)
    band = resolve_characterization_bands(_recipe(), sample_rate_hz)[1]

    chunks = list(
        stream_band_analytic(
            samples,
            band,
            sample_rate_hz=sample_rate_hz,
            filter_order=4,
            resources=_resources(hard_chunk=1_048_576, work_bytes=268_435_456),
            detrend=True,
        )
    )

    supported_count = 0
    for chunk in chunks:
        assert 0 <= chunk.start_sample < chunk.stop_sample <= samples.size
        if chunk.values is not None:
            supported_count += 1
            assert np.allclose(
                np.abs(chunk.values),
                expected[chunk.start_sample : chunk.stop_sample],
                rtol=4e-4,
                atol=4e-4,
            )
    assert supported_count > 0


def test_missing_phase_blocks_residuals_but_not_raw_analytic_stream() -> None:
    sample_rate_hz = 128_000.0
    times = np.arange(65_536, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 24_000.0 * times)
    recipe = _recipe()
    band = resolve_characterization_bands(recipe, sample_rate_hz)[1]

    raw = list(
        stream_band_analytic(
            samples,
            band,
            sample_rate_hz=sample_rate_hz,
            filter_order=4,
            resources=_resources(),
        )
    )
    prepared = prepare_band_envelopes(
        samples,
        _phase(samples.size, sample_rate_hz, available=False),
        recipe,
        sample_rate_hz=sample_rate_hz,
    )
    residuals = list(prepared.stream_residuals(1))

    assert raw
    expected_reasons = {None, "filter_support_too_short", "filter_context_unstable"}
    assert all(chunk.reason_code in expected_reasons for chunk in raw)
    assert residuals
    assert all(not np.any(chunk.valid) for chunk in residuals)
    assert {chunk.reason_code for chunk in residuals} == {"phase_reference_unavailable"}


def test_phase_locked_envelopes_are_centered_once_per_bin_and_query_is_aligned() -> None:
    sample_rate_hz = 512_000.0
    sample_count = 327_680
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    mains = 2.0 * np.pi * 50.0 * times
    samples = (
        (1.0 + 0.25 * np.cos(mains)) * np.cos(2.0 * np.pi * 6_000.0 * times)
        + (0.7 + 0.15 * np.sin(mains)) * np.cos(2.0 * np.pi * 24_000.0 * times)
        + (0.4 + 0.1 * np.cos(2.0 * mains)) * np.cos(2.0 * np.pi * 80_000.0 * times)
    )
    phase = _phase(sample_count, sample_rate_hz)
    prepared = prepare_band_envelopes(
        samples,
        phase,
        _recipe(),
        sample_rate_hz=sample_rate_hz,
    )

    assert len(prepared.bands) == 3
    assert all(item.phase_means.means_v.shape == (64,) for item in prepared.bands)
    assert all(item.phase_means.counts.shape == (64,) for item in prepared.bands)
    for band_index, item in enumerate(prepared.bands):
        if item.phase_means.status is not Status.AVAILABLE:
            assert item.phase_means.reason_code == "insufficient_phase_support"
            continue
        sums = np.zeros(64, dtype=np.float64)
        counts = np.zeros(64, dtype=np.int64)
        for chunk in prepared.stream_residuals(band_index):
            assert chunk.values.dtype == np.float64
            assert chunk.valid.dtype == np.bool_
            expected_shape = (chunk.stop_sample - chunk.start_sample,)
            assert chunk.values.shape == chunk.valid.shape == expected_shape
            indices, phase_valid = phase_bins(phase, chunk.start_sample, chunk.stop_sample, 64)
            valid = chunk.valid & phase_valid
            sums += np.bincount(indices[valid], weights=chunk.values[valid], minlength=64)
            counts += np.bincount(indices[valid], minlength=64)
        assert np.all(counts > 0)
        assert np.allclose(sums, 0.0, rtol=0.0, atol=2e-11)

    requested = prepared.residual(1, 20_000, 22_000)
    assert (requested.start_sample, requested.stop_sample) == (20_000, 22_000)
    assert requested.values.shape == requested.valid.shape == (2_000,)
    assert requested.reason_code is not None or np.any(requested.valid)


def test_unsupported_high_band_does_not_hide_valid_bands_and_state_is_bounded() -> None:
    sample_rate_hz = 100_000.0
    sample_count = 30_000
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 6_000.0 * times) + np.cos(2.0 * np.pi * 24_000.0 * times)

    prepared = prepare_band_envelopes(
        samples,
        _phase(sample_count, sample_rate_hz),
        _recipe(),
        sample_rate_hz=sample_rate_hz,
    )

    assert prepared.bands[0].resolved.effective is not None
    assert prepared.bands[1].resolved.effective is not None
    assert prepared.bands[2].resolved.reason_code == "band_above_nyquist"
    assert prepared.bands[2].phase_means.reason_code == "band_above_nyquist"
    # The fixed A=16384 Hilbert context cannot fit into a 30k record, so the
    # first two supported bands report filter support shortage, not phase lack.
    assert prepared.bands[0].phase_means.status is Status.UNAVAILABLE
    assert prepared.bands[0].phase_means.reason_code == "filter_support_too_short"
    assert prepared.bands[1].phase_means.status is Status.UNAVAILABLE
    assert prepared.bands[1].phase_means.reason_code == "filter_support_too_short"
    assert not np.any(prepared.bands[2].phase_means.valid_bins)
    retained_cells = sum(
        item.phase_means.means_v.size
        + item.phase_means.counts.size
        + item.phase_means.valid_bins.size
        for item in prepared.bands
    )
    assert retained_cells == 3 * 64 * 3


def test_input_is_unchanged_and_checkpoint_exceptions_propagate() -> None:
    sample_rate_hz = 128_000.0
    times = np.arange(32_768, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 24_000.0 * times).astype(np.float32)
    original = samples.copy()
    recipe = _recipe()
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        prepare_band_envelopes(
            samples,
            _phase(samples.size, sample_rate_hz),
            recipe,
            sample_rate_hz=sample_rate_hz,
            checkpoint=cancel,
        )
    assert caught.value is error
    assert np.array_equal(samples, original)


def test_oversized_residual_span_raises_input_error() -> None:
    sample_rate_hz = 512_000.0
    sample_count = 327_680
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 6_000.0 * times)
    recipe = _recipe()
    tight = replace(
        recipe,
        resource_limits=replace(recipe.resource_limits, max_work_bytes=262_144),
    )
    prepared = prepare_band_envelopes(
        samples,
        _phase(sample_count, sample_rate_hz),
        tight,
        sample_rate_hz=sample_rate_hz,
    )
    # Span is inside the record but exceeds min(hard_max, work_bytes//64).
    with pytest.raises(InputError):
        prepared.residual(0, 0, 5_000)
    with pytest.raises(ValueError, match="outside the sample record"):
        prepared.residual(0, 0, prepared.sample_count + 1)


def test_always_raising_checkpoint_propagates_by_identity_before_unsupported() -> None:
    sample_rate_hz = 100_000.0
    sample_count = 30_000
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 6_000.0 * times)
    prepared = prepare_band_envelopes(
        samples,
        _phase(sample_count, sample_rate_hz),
        _recipe(),
        sample_rate_hz=sample_rate_hz,
    )
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        list(prepared.stream_residuals(2, checkpoint=cancel))
    assert caught.value is error


def test_always_raising_checkpoint_propagates_before_unavailable_phase_replay() -> None:
    sample_rate_hz = 128_000.0
    times = np.arange(65_536, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 24_000.0 * times)
    prepared = prepare_band_envelopes(
        samples,
        _phase(samples.size, sample_rate_hz, available=False),
        _recipe(),
        sample_rate_hz=sample_rate_hz,
    )
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        list(prepared.stream_residuals(1, checkpoint=cancel))
    assert caught.value is error


def test_cancellation_enabled_after_first_unavailable_chunk_raises_next() -> None:
    sample_rate_hz = 100_000.0
    sample_count = 30_000
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 6_000.0 * times)
    prepared = prepare_band_envelopes(
        samples,
        _phase(sample_count, sample_rate_hz),
        _recipe(),
        sample_rate_hz=sample_rate_hz,
    )
    states: list[bool] = [False]
    error = RuntimeError("cancel")

    def gate() -> None:
        if states[0]:
            raise error

    stream = prepared.stream_residuals(2, checkpoint=gate)
    next(stream)
    states[0] = True
    with pytest.raises(RuntimeError) as caught:
        next(stream)
    assert caught.value is error


def test_prepare_with_unavailable_phase_and_raising_checkpoint_propagates() -> None:
    sample_rate_hz = 128_000.0
    times = np.arange(32_768, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 24_000.0 * times).astype(np.float32)
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        prepare_band_envelopes(
            samples,
            _phase(samples.size, sample_rate_hz, available=False),
            _recipe(),
            sample_rate_hz=sample_rate_hz,
            checkpoint=cancel,
        )
    assert caught.value is error


def test_deficient_phase_bins_report_insufficient_phase_support() -> None:
    sample_rate_hz = 512_000.0
    sample_count = 327_680
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 6_000.0 * times)
    # One narrow valid cycle: analytic support exists mid-record, but every
    # bin stays below minimum_support_per_bin=20.
    narrow_phase = PhaseCycles(
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        cycle_start_samples=np.array([200_000.0]),
        cycle_end_samples=np.array([201_000.0]),
        cycle_valid=np.array([True]),
        status=Status.AVAILABLE,
        reason_code=None,
    )
    prepared = prepare_band_envelopes(
        samples,
        narrow_phase,
        _recipe(),
        sample_rate_hz=sample_rate_hz,
    )
    assert prepared.bands[0].phase_means.status is Status.UNAVAILABLE
    assert prepared.bands[0].phase_means.reason_code == "insufficient_phase_support"
