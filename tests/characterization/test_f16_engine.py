"""Аналитические тесты движка F16 multiscale memory."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.event_models import (
    RootEvent,
    RootEvents,
    RootEventSettings,
    RootTimelineItem,
    TaggedEvent,
    TaggedGap,
)
from lnt.characterization.f16_contract import (
    ACF_AGGREGATION,
    ANALYZED_SEGMENT_CONVENTION,
    CLAIM_BOUNDARY,
    COUNT_WINDOW_CONVENTION,
    DECLARED_CODES,
    F16_ID,
    F16_INDEX,
    GAPS_PRESENT,
    INSUFFICIENT_COUNT_WINDOWS,
    INSUFFICIENT_PAIRS,
    LAG_ABOVE_SUPPORT,
    LAG_SAMPLE_CONVENTION,
    MAD_CONVENTION,
    METHOD,
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_ZERO,
    ZERO_EVENT_RATE,
)
from lnt.characterization.f16_engine import compute_f16_multiscale_memory
from lnt.characterization.f16_result import F16Declarations
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status
from lnt.events.models import Polarity, UnqualifiedGap

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_FS_HZ = 10_000.0


def _resources(chunk_samples: int = 4_096) -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=chunk_samples,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4_096,
        max_surrogates=19,
        deterministic_seed=6_022,
    )


def _phase(sample_count: int) -> PhaseCycles:
    starts = np.arange(0, sample_count + 1, 200, dtype=np.float64)
    if int(starts[-1]) != sample_count:
        starts = np.append(starts, sample_count)
    return PhaseCycles(
        sample_rate_hz=_FS_HZ,
        sample_count=sample_count,
        cycle_start_samples=starts[:-1],
        cycle_end_samples=starts[1:],
        cycle_valid=np.ones(starts.size - 1, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _means() -> PhaseMeans:
    return PhaseMeans(
        means_v=np.zeros(64, dtype=np.float64),
        counts=np.full(64, 200, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _event(sample: int, ordinal: int) -> RootEvent:
    return RootEvent(
        ordinal=ordinal,
        timeline_segment=0,
        start_sample=sample - 1,
        end_sample=sample + 1,
        peak_sample=sample,
        start_time_s=(sample - 1) / _FS_HZ,
        end_time_s=(sample + 1) / _FS_HZ,
        peak_time_s=sample / _FS_HZ,
        peak_value_v=1.0,
        polarity=Polarity.POSITIVE,
        snr_ratio=10.0,
        excess_v2_s=0.001,
        v2_s=0.002,
        clipped=False,
        dominant_band="band_0001",
        dominant_band_reason_code=None,
        boundary=False,
    )


def _inventory(
    sample_count: int,
    events: tuple[RootEvent, ...] = (),
    gaps: tuple[UnqualifiedGap, ...] = (),
) -> RootEvents:
    def replay(_: Callable[[], None] | None) -> Iterator[RootTimelineItem]:
        for event in events:
            yield TaggedEvent("event", event)
        for gap in gaps:
            yield TaggedGap("gap", gap)

    settings = RootEventSettings(
        recipe_sha256="test",
        detector="existing_event_inventory",
        noise_window_samples=2_048,
        noise_step_samples=1_024,
        minimum_noise_samples=1_024,
        threshold_sigma=5.0,
        max_gap_samples=4,
        minimum_event_samples=1,
        minimum_snr_db=10.0,
        minimum_snr_ratio=3.9810717055349722,
        dead_time_s=0.001,
        dead_time_samples=10,
        chunk_samples=4_096,
        fft_max_samples=1_048_576,
        clipping_low_v=None,
        clipping_high_v=None,
        clipping_reason_code="not_applicable",
        dead_time_handling="exclude_intervals",
        gap_handling="exclude_crossing_intervals",
    )
    return RootEvents(
        sample_rate_hz=_FS_HZ,
        sample_count=sample_count,
        events=events,
        gaps=gaps,
        exclusions=(),
        candidate_count=len(events),
        snr_rejected_count=0,
        accepted_count=len(events),
        omitted_count=0,
        dead_time_rejected_count=0,
        gap_count=len(gaps),
        omitted_gap_count=0,
        omitted_exclusion_count=0,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=settings,
        status=Status.AVAILABLE,
        reason_codes=(),
        _replay_factory=replay,
    )


def test_periodic_residual_reveals_exact_acf_and_recurrence() -> None:
    """Чередующийся остаток имеетAnalytically exact ACF и inclusive MAD recurrence."""
    sample_count = 100_000
    samples = np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0)

    result = compute_f16_multiscale_memory(
        samples,
        _phase(sample_count),
        _means(),
        _inventory(sample_count, (_event(100, 1),)),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.lag_s == pytest.approx(F16Declarations.locked().lags_s)
    assert result.autocorrelation == pytest.approx([-1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    expected_recurrence = np.ones((6, 3), dtype=np.float64)
    expected_recurrence[0, :2] = 0.0
    assert result.recurrence_rate == pytest.approx(expected_recurrence)
    assert result.pair_count.tolist() == [99_999, 99_990, 99_900, 99_800, 99_000, 95_000]
    assert np.all(result.lag_available)


def test_clustered_counts_recover_exact_sample_variance_fano() -> None:
    """Восемь событий в двух последних one-second windows дают Fano 32/9 при ddof=1."""
    sample_count = 100_000
    samples = np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0)
    peaks = (81_000, 82_000, 83_000, 89_000, 91_000, 92_000, 93_000, 99_000)
    events = tuple(_event(peak, index + 1) for index, peak in enumerate(peaks))

    result = compute_f16_multiscale_memory(
        samples,
        _phase(sample_count),
        _means(),
        _inventory(sample_count, events),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.count_window_count.tolist() == [500, 100, 20, 10]
    assert result.event_count == 8
    assert result.count_mean[-1] == pytest.approx(4 / 5)
    # Сумма=8, сумма(x²)=32, n=10: s²=(32-64/10)/9=128/45; Fano=(128/45)/(4/5)=32/9.
    assert result.count_variance[-1] == pytest.approx(128 / 45)
    assert result.fano_factor[-1] == pytest.approx(32 / 9)
    assert np.all(result.fano_available)


def test_exact_minimum_pairs_reaches_support_and_ninety_nine_does_not() -> None:
    """Ровно 100 пар доступны; 99 пар дают masked absence и точный QC code."""
    declarations = F16Declarations.locked()
    supported = compute_f16_multiscale_memory(
        np.resize(np.asarray([1.25, 0.75, 1.0], dtype=np.float64), 5_100),
        _phase(5_100),
        _means(),
        _inventory(5_100),
        declarations,
        _resources(),
    )
    sparse = compute_f16_multiscale_memory(
        np.resize(np.asarray([1.25, 0.75, 1.0], dtype=np.float64), 5_099),
        _phase(5_099),
        _means(),
        _inventory(5_099),
        declarations,
        _resources(),
    )

    assert int(supported.pair_count[-1]) == 100
    assert bool(supported.lag_available[-1])
    assert int(sparse.pair_count[-1]) == 99
    assert not bool(sparse.lag_available[-1])
    assert np.isnan(sparse.autocorrelation[-1])
    assert np.all(np.isnan(sparse.recurrence_rate[-1]))
    assert INSUFFICIENT_PAIRS in sparse.reason_codes


def test_nine_windows_leave_one_scale_masked_without_zero_fano() -> None:
    """Девять one-second windows не публикуют summary; меньшие scales измеримы."""
    sample_count = 90_000
    samples = np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0)
    events = (_event(100, 1),)

    result = compute_f16_multiscale_memory(
        samples,
        _phase(sample_count),
        _means(),
        _inventory(sample_count, events),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.PARTIAL
    assert INSUFFICIENT_COUNT_WINDOWS in result.reason_codes
    assert result.count_window_count.tolist() == [450, 90, 18, 9]
    assert result.count_window_available.tolist() == [True, True, True, False]
    assert np.all(np.isnan(result.count_mean[-1]))
    assert np.all(np.isnan(result.count_variance[-1]))
    assert np.all(np.isnan(result.fano_factor[-1]))
    assert not bool(result.fano_available[-1])
    assert not np.any(result.lag_available == 0)


def test_gap_splits_pair_support_and_discards_only_crossing_windows() -> None:
    """Gap не создаёт пары; count windows сохраняют global sample-zero alignment."""
    sample_count = 20_000
    samples = np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0)
    gap = UnqualifiedGap(
        start_sample=9_000,
        end_sample=9_999,
        start_time_s=0.9,
        end_time_s=0.9999,
    )

    result = compute_f16_multiscale_memory(
        samples,
        _phase(sample_count),
        _means(),
        _inventory(sample_count, (_event(10_100, 1),), (gap,)),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (
        GAPS_PRESENT,
        INSUFFICIENT_COUNT_WINDOWS,
    )
    assert result.qualified_sample_count == 19_000
    assert result.analyzed_segment_count == 2
    assert result.pair_count[-1] == 9_000
    assert result.count_window_count.tolist() == [95, 19, 3, 1]
    assert not np.any(result.lag_available == 0)


@pytest.mark.parametrize("code", sorted(PHASE_ROOT_REASON_CODES))
def test_phase_root_codes_normalize_without_leaking(code: str) -> None:
    """Upstream phase-root code всегда становится F16 reference-unavailable."""
    phase = replace(_phase(10_000), status=Status.UNAVAILABLE, reason_code=code)

    result = compute_f16_multiscale_memory(
        np.ones(10_000, dtype=np.float64),
        phase,
        _means(),
        _inventory(10_000),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    assert result.lag_s.size == 0
    assert result.recurrence_rate.size == 0
    assert result.count_window_s.size == 0


def test_locked_contract_and_claim_boundary_match_recipe() -> None:
    """Все F16 recipe values и явные запреты притязаний остаются frozen."""
    declarations = F16Declarations.locked()

    assert F16_ID == "f16_multiscale_memory"
    assert F16_INDEX == 15
    assert METHOD == "fft_acf_declared_recurrence_nonoverlap_fano"
    assert declarations.phase_bins == 64
    assert declarations.autocovariance == "unbiased_fft_linear"
    assert declarations.lags_s == (0.0001, 0.001, 0.01, 0.02, 0.1, 0.5)
    assert declarations.recurrence_radius_mad == (0.5, 1.0, 2.0)
    assert declarations.count_windows_s == (0.02, 0.1, 0.5, 1.0)
    assert declarations.count_window_overlap_fraction == 0.0
    assert declarations.partial_count_window_handling == "discard"
    assert declarations.fano_variance_ddof == 1
    assert declarations.minimum_pairs == 100
    assert declarations.minimum_count_windows == 10
    assert declarations.maximum_fft_segment_samples == 1_048_576
    assert DECLARED_CODES == (
        "phase_reference_unavailable",
        "scale_zero",
        "lag_above_support",
        "insufficient_pairs",
        "insufficient_count_windows",
        "zero_event_rate",
        "gaps_present",
    )
    assert LAG_SAMPLE_CONVENTION == "nearest_integer"
    assert MAD_CONVENTION == "population_median_absolute_deviation_per_analyzed_segment"
    assert ACF_AGGREGATION == "pair_weighted_unbiased_linear_covariance"
    assert ANALYZED_SEGMENT_CONVENTION == "gaps_then_nonoverlap_maximum_fft_input"
    assert COUNT_WINDOW_CONVENTION == "global_sample_zero_nonoverlap_discard_partial"
    assert "no calibration" in CLAIM_BOUNDARY
    assert "IEC 61000-4-30 compliance" in CLAIM_BOUNDARY
    assert "GUM-conformant" in CLAIM_BOUNDARY
    assert "unavailable is never fabricated" in CLAIM_BOUNDARY


def test_zero_mad_is_unavailable_with_every_domain_empty() -> None:
    """Нулевая raw MAD не заменяется масштабом и не публикует axes."""
    sample_count = 10_000
    result = compute_f16_multiscale_memory(
        np.ones(sample_count, dtype=np.float64),
        _phase(sample_count),
        _means(),
        _inventory(sample_count),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (SCALE_ZERO,)
    assert result.sample_count == sample_count
    assert result.qualified_sample_count == 0
    assert result.lag_s.size == 0
    assert result.autocorrelation.size == 0
    assert result.pair_count.size == 0
    assert result.recurrence_rate.size == 0
    assert result.count_window_s.size == 0
    assert result.fano_factor.size == 0


def test_zero_event_rate_masks_only_fano_without_degrading_acf() -> None:
    """Нулевая event rate оставляет exact count moments, но не публикует Fano."""
    sample_count = 100_000
    result = compute_f16_multiscale_memory(
        np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0),
        _phase(sample_count),
        _means(),
        _inventory(sample_count),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (ZERO_EVENT_RATE,)
    assert np.all(result.lag_available)
    assert np.all(result.count_window_available)
    assert np.all(result.count_mean == 0.0)
    assert np.all(result.count_variance == 0.0)
    assert not np.any(result.fano_available)
    assert np.all(np.isnan(result.fano_factor))


def test_partial_final_count_window_is_discarded_without_realignment() -> None:
    """Partial tail не входит в count windows; start остаётся кратен window size."""
    sample_count = 100_137
    result = compute_f16_multiscale_memory(
        np.resize(np.asarray([1.25, 0.75, 1.0], dtype=np.float64), sample_count),
        _phase(sample_count),
        _means(),
        _inventory(sample_count, (_event(100, 1),)),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.count_window_count.tolist() == [500, 100, 20, 10]
    assert result.count_window_s.tolist() == [0.02, 0.1, 0.5, 1.0]
    assert result.event_count == 1
    assert np.all(result.fano_available)


def test_lag_with_zero_pairs_is_explicit_scale_absence() -> None:
    """Lag ровно N не имеет linear pairs и остаётся masked, не получает zero ACF."""
    sample_count = 5_000
    result = compute_f16_multiscale_memory(
        np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0),
        _phase(sample_count),
        _means(),
        _inventory(sample_count, (_event(100, 1),)),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.PARTIAL
    assert LAG_ABOVE_SUPPORT in result.reason_codes
    assert int(result.pair_count[-1]) == 0
    assert not bool(result.lag_available[-1])
    assert np.isnan(result.autocorrelation[-1])
    assert np.all(np.isnan(result.recurrence_rate[-1]))


def test_fft_zero_padding_excludes_exact_linear_lag_product() -> None:
    """Импульс в sample zero даёт exact hand product 95099 при lag 5000, не wrap."""
    sample_count = 100_000
    samples = np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0)
    samples[0] = 100.0

    result = compute_f16_multiscale_memory(
        samples,
        _phase(sample_count),
        _means(),
        _inventory(sample_count, (_event(100, 1),)),
        F16Declarations.locked(),
        _resources(),
    )

    # Нулевая covariance=109999/100000. При k=5000 есть 95000 пар:
    # пара 0 даёт 100, остальные 94999 пар дают +1.
    expected = (95_099 / 95_000) / (109_999 / 100_000)
    assert result.autocorrelation[-1] == pytest.approx(expected, rel=1e-12)
    assert result.recurrence_rate[-1] == pytest.approx([94_999 / 95_000] * 3)


def test_phase_mean_is_removed_before_acf_and_recurrence() -> None:
    """Constant phase-bin mean удаляется до MAD, ACF и recurrence."""
    sample_count = 100_000
    residual = np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0)
    means = replace(_means(), means_v=np.full(64, 2.0, dtype=np.float64))
    result = compute_f16_multiscale_memory(
        residual + 2.0,
        _phase(sample_count),
        means,
        _inventory(sample_count, (_event(100, 1),)),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.autocorrelation == pytest.approx([-1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    assert result.recurrence_rate[0].tolist() == [0.0, 0.0, 1.0]


def test_locked_fft_cap_splits_long_segment_without_exceeding_pair_domain() -> None:
    """Continuous record делится на два bounded FFT inputs, cap не обрезает record."""
    sample_count = 1_100_000
    result = compute_f16_multiscale_memory(
        np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0),
        _phase(sample_count),
        _means(),
        _inventory(sample_count, (_event(100, 1),)),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.qualified_sample_count == sample_count
    assert result.analyzed_segment_count == 2
    assert result.pair_count[-1] == 1_090_000
    assert np.all(result.lag_available)


def test_checkpoint_cancellation_propagates_by_identity() -> None:
    """Cancellation не превращается в F16 QC code."""
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as raised:
        compute_f16_multiscale_memory(
            np.ones(10_000, dtype=np.float64),
            _phase(10_000),
            _means(),
            _inventory(10_000),
            F16Declarations.locked(),
            _resources(),
            checkpoint=cancel,
        )

    assert raised.value is error


def test_declarations_reject_alternate_ddof_and_partial_handling() -> None:
    """Нельзя silently переключить population/sample variance или partial tail."""
    with pytest.raises(ValueError, match="locked recipe"):
        replace(F16Declarations.locked(), fano_variance_ddof=0)
    with pytest.raises(ValueError, match="locked recipe"):
        replace(F16Declarations.locked(), partial_count_window_handling="include_partial")


def test_engine_rejects_nonfinite_input_before_measurement() -> None:
    """Finite-channel contract остаётся trust-boundary validation."""
    samples = np.zeros(10_000, dtype=np.float64)
    samples[100] = np.nan

    with pytest.raises(ValueError, match="finite"):
        compute_f16_multiscale_memory(
            samples,
            _phase(10_000),
            _means(),
            _inventory(10_000),
            F16Declarations.locked(),
            _resources(),
        )


def test_engine_uses_full_event_replay_instead_of_retained_prefix() -> None:
    """Persisted prefix не обнуляет complete event replay для Fano."""
    sample_count = 100_000
    events = tuple(_event(1_000 + index * 10_000, index + 1) for index in range(10))
    inventory = _inventory(sample_count, events)

    result = compute_f16_multiscale_memory(
        np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0),
        _phase(sample_count),
        _means(),
        replace(inventory, events=()),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.event_count == 10
    assert np.all(result.count_mean > 0.0)


def test_result_rejects_unknown_codes_and_nonempty_unavailable_domains() -> None:
    """F16Result fail-closed проверяет vocabulary и unavailable output invariant."""
    sample_count = 100_000
    available = compute_f16_multiscale_memory(
        np.where(np.arange(sample_count) % 2 == 0, 1.0, -1.0),
        _phase(sample_count),
        _means(),
        _inventory(sample_count),
        F16Declarations.locked(),
        _resources(),
    )
    unavailable = compute_f16_multiscale_memory(
        np.ones(sample_count, dtype=np.float64),
        _phase(sample_count),
        _means(),
        _inventory(sample_count),
        F16Declarations.locked(),
        _resources(),
    )

    with pytest.raises(CharacterizationError):
        replace(available, reason_codes=("invented",))
    with pytest.raises(CharacterizationError):
        replace(unavailable, lag_s=np.zeros(6, dtype=np.float64))
