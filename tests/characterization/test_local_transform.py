from __future__ import annotations

import dataclasses
from itertools import pairwise
from typing import TYPE_CHECKING, NoReturn, override

import numpy as np
import pytest
from scipy import signal

if TYPE_CHECKING:
    from numpy.typing import NDArray

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.local_transform import (
    TransformChunk,
    TransformSpec,
    required_sos_halo,
    stream_local_transform,
)


def _resources(
    *, chunk: int = 128, hard_chunk: int = 1024, work_bytes: int = 1_048_576
) -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=chunk,
        hard_max_chunk_samples=hard_chunk,
        max_work_bytes=work_bytes,
        max_artifact_bytes=1024,
        max_stored_trajectories=1,
        max_surrogates=1,
        deterministic_seed=6022,
    )


def _identity_spec(*, analytic: bool = False, detrend: bool = False) -> TransformSpec:
    return TransformSpec(
        sos=np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float64),
        analytic=analytic,
        detrend=detrend,
    )


def _supported(chunks: list[TransformChunk]) -> NDArray[np.float64]:
    values = [chunk.values for chunk in chunks if chunk.values is not None]
    assert values
    return np.concatenate(values).astype(np.float64)


def _assert_exact_coverage(chunks: list[TransformChunk], size: int, chunk_limit: int) -> None:
    assert chunks[0].start_sample == 0
    assert chunks[-1].stop_sample == size
    assert all(left.stop_sample == right.start_sample for left, right in pairwise(chunks))
    assert all(0 < chunk.stop_sample - chunk.start_sample <= chunk_limit for chunk in chunks)


def test_identity_sos_has_mathematical_pad_halo_and_exact_supported_values() -> None:
    samples = np.linspace(-1.0, 1.0, 83, dtype=np.float32)
    original = samples.copy()
    spec = _identity_spec()

    chunks = list(stream_local_transform(samples, spec=spec, resources=_resources(chunk=17)))

    assert required_sos_halo(spec.sos) == 6
    _assert_exact_coverage(chunks, samples.size, 17)
    assert chunks[0] == TransformChunk(0, 12, None, 12, "filter_support_too_short")
    assert chunks[-1] == TransformChunk(71, 83, None, 12, "filter_support_too_short")
    for chunk in chunks:
        if chunk.values is not None:
            assert chunk.reason_code is None
            assert chunk.halo_samples == 12
            assert np.array_equal(chunk.values, samples[chunk.start_sample : chunk.stop_sample])
    assert np.array_equal(samples, original)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.__setattr__("analytic", True)


def test_zero_phase_lowpass_matches_squared_frequency_response_in_qualified_interior() -> None:
    sample_rate_hz = 2_000.0
    frequency_hz = 50.0
    sample_count = 20_000
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    samples = np.sin(2.0 * np.pi * frequency_hz * times)
    sos = signal.butter(4, 200.0, btype="lowpass", fs=sample_rate_hz, output="sos")
    spec = TransformSpec(sos=np.asarray(sos, dtype=np.float64))

    chunks = list(
        stream_local_transform(
            samples,
            spec=spec,
            resources=_resources(chunk=1024, hard_chunk=4096, work_bytes=4_194_304),
        )
    )
    supported = [chunk for chunk in chunks if chunk.values is not None]
    omega = 2.0 * np.pi * frequency_hz / sample_rate_hz
    _, response = signal.sosfreqz(sos, worN=np.array([omega]))
    expected_gain = float(np.abs(np.asarray(response)[0]) ** 2)

    assert supported
    for chunk in supported:
        expected = expected_gain * samples[chunk.start_sample : chunk.stop_sample]
        assert chunk.values is not None
        assert np.allclose(chunk.values, expected, rtol=2e-6, atol=2e-8)


def test_short_record_covers_every_span_once_and_repeats_deterministically() -> None:
    samples = np.arange(61, dtype=np.float64)
    resources = _resources(chunk=10, hard_chunk=10_000)

    first = list(stream_local_transform(samples, spec=_identity_spec(), resources=resources))
    second = list(stream_local_transform(samples, spec=_identity_spec(), resources=resources))

    _assert_exact_coverage(first, samples.size, resources.chunk_samples)
    assert len(first) == len(second)
    for left, right in zip(first, second, strict=True):
        assert (left.start_sample, left.stop_sample, left.halo_samples, left.reason_code) == (
            right.start_sample,
            right.stop_sample,
            right.halo_samples,
            right.reason_code,
        )
        if left.values is None:
            assert right.values is None
        else:
            assert right.values is not None
            assert np.array_equal(left.values, right.values)


def test_analytic_local_transform_is_complex_with_exact_bin_carrier_envelope() -> None:
    # Period four divides both initial FFT lengths, avoiding spectral leakage in this local check.
    samples = np.cos(0.5 * np.pi * np.arange(512, dtype=np.float64))
    chunks = list(
        stream_local_transform(
            samples,
            spec=_identity_spec(analytic=True),
            resources=_resources(chunk=64, hard_chunk=1024, work_bytes=1_048_576),
        )
    )

    supported = [chunk for chunk in chunks if chunk.values is not None]
    assert supported
    assert all(
        chunk.values is not None and chunk.values.dtype == np.complex128 for chunk in supported
    )
    envelope = np.abs(
        np.concatenate([chunk.values for chunk in supported if chunk.values is not None])
    )
    assert np.allclose(envelope, 1.0, rtol=0.0, atol=2e-14)


def test_detrend_is_applied_before_filtering() -> None:
    samples = np.full(100, 7.5, dtype=np.float64)
    chunks = list(
        stream_local_transform(
            samples,
            spec=_identity_spec(detrend=True),
            resources=_resources(chunk=25),
        )
    )

    assert np.array_equal(_supported(chunks), np.zeros(76, dtype=np.float64))


def test_initial_geometry_refusal_does_not_read_or_transform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReadGuard(np.ndarray):
        @override
        def __getitem__(self, key: object) -> NoReturn:
            raise AssertionError(f"unexpected read: {key!r}")

    samples = np.arange(40, dtype=np.float32).view(ReadGuard)

    def unexpected_transform(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("unexpected transform")

    monkeypatch.setattr(
        "lnt.characterization.local_transform.signal.sosfiltfilt", unexpected_transform
    )
    chunks = list(
        stream_local_transform(
            samples,
            spec=_identity_spec(),
            resources=_resources(chunk=8, hard_chunk=16, work_bytes=1024),
        )
    )

    _assert_exact_coverage(chunks, samples.size, 8)
    assert all(chunk.values is None for chunk in chunks)
    assert {chunk.reason_code for chunk in chunks} == {"filter_support_too_short"}


def test_context_refinement_stops_at_cap_with_stable_unavailable_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples = np.arange(100, dtype=np.float64)

    def context_dependent(
        sos: NDArray[np.float64], values: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        del sos
        return np.full(values.shape, float(values.size), dtype=np.float64)

    monkeypatch.setattr(
        "lnt.characterization.local_transform.signal.sosfiltfilt", context_dependent
    )
    chunks = list(
        stream_local_transform(
            samples,
            spec=_identity_spec(),
            resources=_resources(chunk=10, hard_chunk=58, work_bytes=1_048_576),
        )
    )

    _assert_exact_coverage(chunks, samples.size, 10)
    interior = [chunk for chunk in chunks if chunk.start_sample >= 12 and chunk.stop_sample <= 88]
    assert interior
    assert all(chunk.values is None for chunk in interior)
    assert {chunk.reason_code for chunk in interior} == {"filter_context_unstable"}


def test_nonfinite_gap_is_explicit_and_never_leaks_into_supported_output() -> None:
    samples = np.arange(120, dtype=np.float64)
    samples[52:55] = np.nan

    chunks = list(
        stream_local_transform(
            samples,
            spec=_identity_spec(),
            resources=_resources(chunk=11),
        )
    )

    _assert_exact_coverage(chunks, samples.size, 11)
    assert any(chunk.reason_code == "nonfinite_input" for chunk in chunks)
    for chunk in chunks:
        if chunk.values is not None:
            assert chunk.stop_sample <= 40 or chunk.start_sample >= 67
            assert np.array_equal(chunk.values, samples[chunk.start_sample : chunk.stop_sample])


def test_checkpoint_exceptions_propagate_by_identity_before_work_and_at_end() -> None:
    samples = np.arange(30, dtype=np.float64)
    initial_error = RuntimeError("cancel before work")

    def cancel_immediately() -> None:
        raise initial_error

    with pytest.raises(RuntimeError) as initial_caught:
        list(
            stream_local_transform(
                samples,
                spec=_identity_spec(),
                resources=_resources(),
                checkpoint=cancel_immediately,
            )
        )
    assert initial_caught.value is initial_error

    final_error = RuntimeError("cancel at end")
    calls = 0

    def cancel_at_end() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise final_error

    with pytest.raises(RuntimeError) as final_caught:
        list(
            stream_local_transform(
                np.empty(0, dtype=np.float64),
                spec=_identity_spec(),
                resources=_resources(),
                checkpoint=cancel_at_end,
            )
        )
    assert final_caught.value is final_error


def test_200_hz_lowpass_halo_at_5_mhz_fits_locked_initial_geometry() -> None:
    sos = signal.butter(4, 200.0, btype="lowpass", fs=5_000_000.0, output="sos")
    halo = required_sos_halo(np.asarray(sos, dtype=np.float64))

    assert halo == 143_644
    assert 4 * halo + 262_144 <= 1_048_576


def test_5_mhz_phase_lowpass_retains_substantial_nonzero_interior() -> None:
    sample_rate_hz = 5_000_000.0
    sample_count = 1_200_000
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    samples = np.sin(2.0 * np.pi * 50.0 * times).astype(np.float32)
    original = samples.copy()
    sos = signal.butter(4, 200.0, btype="lowpass", fs=sample_rate_hz, output="sos")

    chunks = list(
        stream_local_transform(
            samples,
            spec=TransformSpec(np.asarray(sos, dtype=np.float64)),
            resources=_resources(
                chunk=262_144,
                hard_chunk=1_048_576,
                work_bytes=268_435_456,
            ),
        )
    )

    supported = [chunk for chunk in chunks if chunk.values is not None]
    assert sum(chunk.stop_sample - chunk.start_sample for chunk in supported) >= 500_000
    peak = max(
        float(np.max(np.abs(chunk.values))) for chunk in supported if chunk.values is not None
    )
    assert peak > 0.1
    _assert_exact_coverage(chunks, sample_count, 262_144)
    assert np.array_equal(samples, original)


def test_fixed_analytic_halo_recovers_declared_am_envelope_below_one_percent() -> None:
    sample_rate_hz = 1_000_000.0
    sample_count = 300_000
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    expected = 1.0 + 0.3 * np.cos(2.0 * np.pi * 20.0 * times)
    samples = (expected * np.cos(2.0 * np.pi * 20_000.0 * times)).astype(np.float32)
    original = samples.copy()
    sos = signal.butter(
        4,
        (10_000.0, 50_000.0),
        btype="bandpass",
        fs=sample_rate_hz,
        output="sos",
    )
    analytic_halo = 16_384

    chunks = list(
        stream_local_transform(
            samples,
            spec=TransformSpec(
                np.asarray(sos, dtype=np.float64),
                analytic=True,
                analytic_halo_samples=analytic_halo,
            ),
            resources=_resources(
                chunk=65_536,
                hard_chunk=262_144,
                work_bytes=67_108_864,
            ),
        )
    )

    supported = [chunk for chunk in chunks if chunk.values is not None]
    assert sum(chunk.stop_sample - chunk.start_sample for chunk in supported) >= 100_000
    for chunk in supported:
        assert chunk.values is not None
        error = np.abs(np.abs(chunk.values) - expected[chunk.start_sample : chunk.stop_sample])
        assert float(np.max(error)) < 0.01
    _assert_exact_coverage(chunks, sample_count, 65_536)
    assert np.array_equal(samples, original)


def test_analytic_halo_must_be_nonnegative() -> None:
    with pytest.raises(ValueError, match="analytic_halo_samples"):
        TransformSpec(_identity_spec().sos, analytic=True, analytic_halo_samples=-1)
