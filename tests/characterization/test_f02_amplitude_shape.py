"""F02 template_gain_delay_least_squares RED analytic tests (Wave 1 todo 11)."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from lnt.characterization.event_models import RootEvent
from lnt.characterization.f01_phase_cycle import compute_f01_phase_cycle
from lnt.characterization.f02_amplitude_shape import (
    COARSE_DELAY_METHOD,
    DELAY_REFINEMENT,
    MAXIMUM_EVENTS,
    METHOD,
    MINIMUM_EVENT_SNR_DB,
    RESIDUAL_FRACTION_MAX,
    SUBSAMPLE_DIVISOR,
    TEMPLATE_FAMILY_ID,
    TEMPLATE_FIELD,
    F02Result,
    compute_f02_amplitude_time_shape,
    resample_cycle_template,
)
from lnt.characterization.records import Status
from lnt.events.models import Polarity

FS_HZ = 500000.0
TEMPLATE_SAMPLES = 1000
_EVENT_AMPS = {1: 6.0, 3: 0.6, 5: 0.3, 7: 0.15}
_EVENT_PHASES = {1: 0.4, 3: -0.7, 5: 1.1, 7: 0.2}

type Float64Array = NDArray[np.float64]


def _build_template() -> Float64Array:
    """Synthesize one unit-cycle shape from harmonic cosines (F01 template idea)."""
    theta = np.linspace(0.0, 2.0 * np.pi, TEMPLATE_SAMPLES, endpoint=False)
    out = np.zeros(TEMPLATE_SAMPLES, dtype=np.float64)
    for order, amp in _EVENT_AMPS.items():
        out += 2.0 * amp * np.cos(float(order) * theta + _EVENT_PHASES[order])
    return out


def _embed(
    template: Float64Array,
    amplitude: float,
    delay_samples: int,
    noise_sigma: float,
    seed: int,
) -> Float64Array:
    """Build a [pre | span | post] record; span holds a0 * v(t - tau0) + noise."""
    span = int(template.size)
    rng = np.random.default_rng(seed)
    record = rng.standard_normal(3 * span) * noise_sigma
    delayed = np.zeros(span, dtype=np.float64)
    delayed[delay_samples:] = amplitude * template[: span - delay_samples]
    record[span : 2 * span] += delayed
    return record


def _event(
    start_sample: int,
    end_sample: int,
    snr_ratio: float,
    boundary: bool = False,
) -> RootEvent:
    """Construct one RootEvent record directly (never via the legacy detector)."""
    peak_sample = (start_sample + end_sample) // 2
    return RootEvent(
        ordinal=0,
        timeline_segment=0,
        start_sample=start_sample,
        end_sample=end_sample,
        peak_sample=peak_sample,
        start_time_s=start_sample / FS_HZ,
        end_time_s=end_sample / FS_HZ,
        peak_time_s=peak_sample / FS_HZ,
        peak_value_v=20.0,
        polarity=Polarity.POSITIVE,
        snr_ratio=snr_ratio,
        excess_v2_s=0.0,
        v2_s=0.0,
        clipped=False,
        dominant_band=None,
        dominant_band_reason_code=None,
        boundary=boundary,
    )


def _assert_no_bare_values(result: F02Result) -> None:
    """Rejected fits must carry no plausible single a/tau pair."""
    assert all(value is None for value in result.amplitudes)
    assert all(value is None for value in result.delays_s)


def test_locked_parameters_match_contract() -> None:
    assert METHOD == "template_gain_delay_least_squares"
    assert TEMPLATE_FAMILY_ID == "f01_phase_cycle"
    assert TEMPLATE_FIELD == "x_template_v"
    assert COARSE_DELAY_METHOD == "fft_cross_correlation"
    assert DELAY_REFINEMENT == "parabolic"
    assert SUBSAMPLE_DIVISOR == 64
    assert pytest.approx(10.0) == MINIMUM_EVENT_SNR_DB
    assert pytest.approx(0.25) == RESIDUAL_FRACTION_MAX
    assert MAXIMUM_EVENTS == 4096


def test_scaled_shifted_event_recovers_gain_and_delay() -> None:
    template = _build_template()
    record = _embed(template, amplitude=1.7, delay_samples=37, noise_sigma=0.05, seed=6022)
    event = _event(TEMPLATE_SAMPLES, 2 * TEMPLATE_SAMPLES - 1, snr_ratio=100.0)
    result = compute_f02_amplitude_time_shape(record, template, (event,), sample_rate_hz=FS_HZ)
    assert isinstance(result, F02Result)
    assert result.status is Status.AVAILABLE
    assert pytest.approx(1.7, abs=0.01) == result.amplitudes[0]
    assert pytest.approx(37.0 / FS_HZ, abs=1.0 / (64.0 * FS_HZ)) == result.delays_s[0]
    assert result.residual_fractions[0] is not None
    assert result.residual_fractions[0] < 0.02


def test_pure_shift_recovers_unit_gain_exactly() -> None:
    template = _build_template()
    record = _embed(template, amplitude=1.0, delay_samples=50, noise_sigma=0.0, seed=7)
    event = _event(TEMPLATE_SAMPLES, 2 * TEMPLATE_SAMPLES - 1, snr_ratio=100.0)
    result = compute_f02_amplitude_time_shape(record, template, (event,), sample_rate_hz=FS_HZ)
    assert result.status is Status.AVAILABLE
    assert pytest.approx(1.0, abs=1e-6) == result.amplitudes[0]
    assert pytest.approx(50.0 / FS_HZ) == result.delays_s[0]
    assert result.residual_fractions[0] is not None
    assert result.residual_fractions[0] < 1e-9


def test_overlapping_events_trip_overlapping_events() -> None:
    template = _build_template()
    record = _embed(template, amplitude=1.7, delay_samples=37, noise_sigma=0.05, seed=6022)
    first = _event(TEMPLATE_SAMPLES, 2 * TEMPLATE_SAMPLES - 1, snr_ratio=100.0)
    second = _event(
        TEMPLATE_SAMPLES + TEMPLATE_SAMPLES // 2,
        2 * TEMPLATE_SAMPLES + TEMPLATE_SAMPLES // 2 - 1,
        snr_ratio=100.0,
    )
    result = compute_f02_amplitude_time_shape(
        record, template, (first, second), sample_rate_hz=FS_HZ
    )
    assert "overlapping_events" in result.reason_codes
    assert result.status is Status.UNAVAILABLE
    _assert_no_bare_values(result)


def test_missing_template_is_unavailable_not_zero_gain() -> None:
    template = _build_template()
    record = _embed(template, amplitude=1.7, delay_samples=37, noise_sigma=0.05, seed=6022)
    event = _event(TEMPLATE_SAMPLES, 2 * TEMPLATE_SAMPLES - 1, snr_ratio=100.0)
    result = compute_f02_amplitude_time_shape(record, None, (event,), sample_rate_hz=FS_HZ)
    assert "template_unavailable" in result.reason_codes
    assert result.status is Status.UNAVAILABLE
    _assert_no_bare_values(result)


def test_event_at_record_edge_trips_event_truncated() -> None:
    template = _build_template()
    record = _embed(template, amplitude=1.7, delay_samples=37, noise_sigma=0.05, seed=6022)
    event = _event(2 * TEMPLATE_SAMPLES, 3 * TEMPLATE_SAMPLES + 10, snr_ratio=100.0, boundary=True)
    result = compute_f02_amplitude_time_shape(record, template, (event,), sample_rate_hz=FS_HZ)
    assert "event_truncated" in result.reason_codes
    assert result.status is Status.UNAVAILABLE
    _assert_no_bare_values(result)


def test_low_snr_event_trips_below_snr() -> None:
    template = _build_template()
    record = _embed(template, amplitude=1.7, delay_samples=37, noise_sigma=0.05, seed=6022)
    event = _event(TEMPLATE_SAMPLES, 2 * TEMPLATE_SAMPLES - 1, snr_ratio=1.5)
    result = compute_f02_amplitude_time_shape(record, template, (event,), sample_rate_hz=FS_HZ)
    assert "below_snr" in result.reason_codes
    assert result.status is Status.UNAVAILABLE
    _assert_no_bare_values(result)


def test_event_without_baseline_window_trips_baseline_unavailable() -> None:
    template = _build_template()
    span = TEMPLATE_SAMPLES
    rng = np.random.default_rng(6022)
    record = rng.standard_normal(2 * span) * 0.05
    record[:span] += 1.7 * template
    event = _event(0, span - 1, snr_ratio=100.0, boundary=True)
    result = compute_f02_amplitude_time_shape(record, template, (event,), sample_rate_hz=FS_HZ)
    assert "baseline_unavailable" in result.reason_codes
    assert result.status is Status.UNAVAILABLE
    _assert_no_bare_values(result)


def test_shape_mismatch_rejects_residual_above_quarter() -> None:
    template = _build_template()
    span = TEMPLATE_SAMPLES
    rng = np.random.default_rng(6022)
    record = rng.standard_normal(3 * span) * 0.05
    alien = np.sin(2.0 * np.pi * 13.0 * np.arange(span) / span)
    record[span : 2 * span] += 8.0 * alien
    event = _event(span, 2 * span - 1, snr_ratio=100.0)
    result = compute_f02_amplitude_time_shape(record, template, (event,), sample_rate_hz=FS_HZ)
    assert result.status is not Status.AVAILABLE
    _assert_no_bare_values(result)


def test_event_count_caps_at_maximum_events_with_accounting() -> None:
    template = _build_template()
    record = np.zeros(2 * (MAXIMUM_EVENTS + 1), dtype=np.float64)
    events = tuple(
        _event(2 * index, 2 * index + 1, snr_ratio=100.0) for index in range(MAXIMUM_EVENTS + 1)
    )
    result = compute_f02_amplitude_time_shape(record, template, events, sample_rate_hz=FS_HZ)
    assert result.evaluated_event_count == MAXIMUM_EVENTS
    assert result.omitted_event_count == 1


def test_declared_snr_gate_rejects_a_fit_the_default_gate_accepts() -> None:
    template = _build_template()
    record = _embed(template, amplitude=1.7, delay_samples=37, noise_sigma=0.05, seed=6022)
    event = _event(TEMPLATE_SAMPLES, 2 * TEMPLATE_SAMPLES - 1, snr_ratio=100.0)
    accepted = compute_f02_amplitude_time_shape(record, template, (event,), sample_rate_hz=FS_HZ)
    rejected = compute_f02_amplitude_time_shape(
        record, template, (event,), sample_rate_hz=FS_HZ, minimum_event_snr_db=200.0
    )
    assert accepted.status is Status.AVAILABLE
    assert rejected.status is Status.UNAVAILABLE
    assert rejected.reason_codes == ("below_snr",)


def test_declared_residual_ceiling_rejects_a_fit_the_default_ceiling_accepts() -> None:
    template = _build_template()
    record = _embed(template, amplitude=1.7, delay_samples=37, noise_sigma=0.05, seed=6022)
    event = _event(TEMPLATE_SAMPLES, 2 * TEMPLATE_SAMPLES - 1, snr_ratio=100.0)
    accepted = compute_f02_amplitude_time_shape(record, template, (event,), sample_rate_hz=FS_HZ)
    rejected = compute_f02_amplitude_time_shape(
        record, template, (event,), sample_rate_hz=FS_HZ, residual_fraction_max=1e-9
    )
    assert accepted.status is Status.AVAILABLE
    assert rejected.status is Status.UNAVAILABLE
    assert rejected.reason_codes == ("below_snr",)


def test_declared_maximum_events_caps_the_evaluated_inventory() -> None:
    template = _build_template()
    span = TEMPLATE_SAMPLES
    record = _embed(template, amplitude=1.7, delay_samples=37, noise_sigma=0.05, seed=6022)
    events = (_event(span, 2 * span - 1, snr_ratio=100.0), _event(2 * span, 3 * span - 1, 100.0))
    capped = compute_f02_amplitude_time_shape(
        record, template, events, sample_rate_hz=FS_HZ, maximum_events=1
    )
    assert capped.evaluated_event_count == 1
    assert capped.omitted_event_count == 1
    assert len(capped.amplitudes) == 2
    assert capped.amplitudes[1] is None


def test_empty_event_inventory_is_unavailable_without_fabricated_values() -> None:
    # The declared F02 vocabulary (method-notes-families-1-9.md:145-146) lists five
    # codes and none of them names "the detector delimited no event at all". With no
    # event there is no pair of flanking event-length intervals to take a median of,
    # so the baseline the method requires does not exist: of the five declared codes
    # only baseline_unavailable stays true. below_snr would claim a measurement that
    # never happened. Spec gap, surfaced to the owner rather than papered over.
    template = _build_template()
    record = _embed(template, amplitude=1.7, delay_samples=37, noise_sigma=0.05, seed=6022)
    result = compute_f02_amplitude_time_shape(record, template, (), sample_rate_hz=FS_HZ)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("baseline_unavailable",)
    assert result.evaluated_event_count == 0
    assert result.omitted_event_count == 0
    _assert_no_bare_values(result)


def test_declared_subsample_divisor_sets_the_lattice_step() -> None:
    template = _build_template()
    record = _embed(template, amplitude=1.0, delay_samples=50, noise_sigma=0.0, seed=7)
    event = _event(TEMPLATE_SAMPLES, 2 * TEMPLATE_SAMPLES - 1, snr_ratio=100.0)
    for divisor in (1, SUBSAMPLE_DIVISOR):
        result = compute_f02_amplitude_time_shape(
            record, template, (event,), sample_rate_hz=FS_HZ, subsample_divisor=divisor
        )
        assert result.status is Status.AVAILABLE
        # The delay must land on the declared lattice: an integer number of
        # 1/divisor steps, whatever the divisor is.
        delay_s = result.delays_s[0]
        assert delay_s is not None
        steps = delay_s * FS_HZ * divisor
        assert steps == pytest.approx(round(steps), abs=1e-6)
        assert delay_s == pytest.approx(50.0 / FS_HZ)


def test_resample_cycle_template_maps_one_cycle_onto_the_record_grid() -> None:
    # The F01 template is one cycle on a 1000-point theta grid, independent of fs.
    # An event span lives on the record grid, where one cycle is fs / f1 samples,
    # so v(t) must be resampled before any correlation means anything.
    template = _build_template()
    resampled = resample_cycle_template(template, f1_hz=50.0, sample_rate_hz=FS_HZ)
    assert resampled.size == round(FS_HZ / 50.0)
    assert resampled[0] == pytest.approx(template[0])
    quarter = resampled.size // 4
    assert resampled[quarter] == pytest.approx(template[250], rel=1e-3)
    assert float(np.max(np.abs(resampled))) == pytest.approx(
        float(np.max(np.abs(template))), rel=1e-2
    )


def test_resample_cycle_template_is_deterministic_and_finite() -> None:
    template = _build_template()
    first = resample_cycle_template(template, f1_hz=50.0, sample_rate_hz=FS_HZ)
    second = resample_cycle_template(template, f1_hz=50.0, sample_rate_hz=FS_HZ)
    assert np.array_equal(first, second)
    assert np.all(np.isfinite(first))


def test_f01_template_grid_is_endpoint_false_on_the_real_producer() -> None:
    """Допущение resample_cycle_template прибито к выходу F01, не к локальному шаблону.

    ``x_template_v`` — один цикл на сетке ``theta`` с ``endpoint=False``
    (`f01_phase_cycle.py:191`), поэтому период равен ровно ``size`` точкам, и
    wrap-around повторяет первый отсчёт. Смена сетки у продюсера молча сдвинула
    бы каждую задержку F02 на один отсчёт.
    """
    n = round(FS_HZ * 3.0)
    t = np.arange(n, dtype=np.float64) / FS_HZ
    sync = (6.0 * np.sin(2.0 * np.pi * 50.0 * t + 0.4)).astype(np.float32)
    result = compute_f01_phase_cycle(sync, sample_rate_hz=FS_HZ, sync_reference=sync)
    template = result.x_template_v
    f1_hz = result.f1_hz
    assert template is not None
    assert f1_hz is not None
    # endpoint=True дал бы дубликат точки 2pi: последний отсчёт равен первому.
    seam = abs(float(template[0] - template[-1]))
    interior = float(np.max(np.abs(np.diff(template))))
    assert seam > 0.0
    assert seam <= interior * 1.5
    resampled = resample_cycle_template(template, f1_hz=float(f1_hz), sample_rate_hz=FS_HZ)
    assert resampled.size == round(FS_HZ / float(f1_hz))
