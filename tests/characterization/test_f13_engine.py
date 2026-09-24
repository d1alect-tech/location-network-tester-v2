"""Аналитические тесты движка F13 band-envelope coactivity."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.bands import ResolvedBand, resolve_characterization_bands
from lnt.characterization.envelope_models import BandEnvelope, BandEnvelopes, EnvelopeChunk
from lnt.characterization.envelopes import prepare_band_envelopes
from lnt.characterization.f13_engine import compute_f13_band_envelope_coactivity
from lnt.characterization.f13_math import declared_lag_samples, select_peak_lag
from lnt.characterization.f13_result import (
    BAND_ABOVE_NYQUIST,
    BANDS_HZ,
    FILTER_CONTEXT_UNSTABLE,
    FILTER_SUPPORT_TOO_SHORT,
    INSUFFICIENT_ACTIVITY,
    LAG_SUPPORT_TOO_SHORT,
    MIXED_UNAVAILABLE_SUPPORT,
    NONFINITE_INPUT,
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_ZERO,
    F13Declarations,
    F13Result,
)
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

FS_HZ = 1_000.0
BAND_NAMES = ("band_0001", "band_0002", "band_0003")
_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=4_096,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4_096,
        max_surrogates=19,
        deterministic_seed=6_022,
    )


def _resolved_bands() -> tuple[ResolvedBand, ...]:
    recipe = parse_analysis_recipe(
        decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    )
    assert isinstance(recipe, CharacterizationRecipe)
    return resolve_characterization_bands(recipe, 1_000_000.0)


def _declarations() -> F13Declarations:
    return F13Declarations(
        bands_hz=BANDS_HZ,
        filter="butterworth_sos",
        filter_order=4,
        filter_phase="zero",
        filter_edge_guard_fraction=0.01,
        phase_bins=64,
        activity_threshold_mad=5.0,
        lag_low_s=-0.008,
        lag_high_s=0.008,
        maximum_lag_points=17,
        lag_tie_break="minimum_absolute_then_negative",
        minimum_active_samples=20,
    )


def _phase_means() -> PhaseMeans:
    return PhaseMeans(
        means_v=np.zeros(64, dtype=np.float64),
        counts=np.full(64, 20, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _source(
    residuals: np.ndarray,
    *,
    valid: np.ndarray | None = None,
    reasons: tuple[str | None, ...] | None = None,
    chunk_size: int = 128,
) -> BandEnvelopes:
    values = np.asarray(residuals, dtype=np.float64)
    assert values.shape == (3, values.shape[1])
    qualified = (
        np.ones(values.shape, dtype=np.bool_)
        if valid is None
        else np.asarray(valid, dtype=np.bool_)
    )
    assert qualified.shape == values.shape
    resolved = _resolved_bands()
    bands = tuple(BandEnvelope(resolved[index], 4, _phase_means()) for index in range(3))

    def factory(band_index: int, checkpoint: Callable[[], None] | None) -> Iterator[EnvelopeChunk]:
        for start in range(0, values.shape[1], chunk_size):
            if checkpoint is not None:
                checkpoint()
            stop = min(values.shape[1], start + chunk_size)
            reason = None if reasons is None else reasons[band_index]
            yield EnvelopeChunk(
                start,
                stop,
                values[band_index, start:stop].copy(),
                qualified[band_index, start:stop].copy(),
                reason,
            )

    return BandEnvelopes(
        bands=bands,
        sample_count=values.shape[1],
        sample_rate_hz=FS_HZ,
        _stream_factory=factory,
        _max_residual_samples=values.shape[1],
    )


def _delayed_residuals() -> np.ndarray:
    """Вторая полоса — точная копия первой, сдвинутая на два отсчёка."""
    sample_count = 512
    rng = np.random.default_rng(6_022)
    first = rng.uniform(-1.0, 1.0, sample_count)
    pulse = (np.arange(sample_count) % 32) < 4
    first[pulse] += 10.0
    second = np.roll(first, 2)
    third = rng.uniform(-1.0, 1.0, sample_count)
    third[np.roll(pulse, 3)] += 10.0
    return np.asarray((first, second, third), dtype=np.float64)


def test_two_millisecond_delayed_envelopes_recover_exact_lag_and_lift() -> None:
    """Известный сдвиг 2 мс даёт lag=+2 и lift выше единицы."""
    source = _source(_delayed_residuals())

    result = compute_f13_band_envelope_coactivity(
        source,
        _declarations(),
        _resolved_bands(),
        resources=_resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.qualified_sample_count == source.sample_count
    assert result.active_sample_count.tolist() == [64, 64, 64]
    assert result.activity_fraction[0] == pytest.approx(0.125)
    assert result.coincidence_probability[0, 1] == pytest.approx(0.0625)
    assert result.lift[0, 1] == pytest.approx(4.0)
    assert result.maximum_lag_s[0, 1] == pytest.approx(0.002)
    assert result.maximum_lag_correlation[0, 1] > 0.9


def _run(
    source: BandEnvelopes,
    declarations: F13Declarations | None = None,
    bands: tuple[ResolvedBand, ...] | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> F13Result:
    return compute_f13_band_envelope_coactivity(
        source,
        declarations or _declarations(),
        bands or _resolved_bands(),
        resources=_resources(),
        checkpoint=checkpoint,
    )


@pytest.mark.parametrize(
    "code",
    [
        PHASE_REFERENCE_UNAVAILABLE,
        BAND_ABOVE_NYQUIST,
        FILTER_SUPPORT_TOO_SHORT,
        FILTER_CONTEXT_UNSTABLE,
        NONFINITE_INPUT,
    ],
)
def test_machine_reason_without_common_support_stays_exact(code: str) -> None:
    """Машинная причина shared-root не маскируется выдуманной фазовой ошибкой."""
    valid = np.zeros((3, 128), dtype=np.bool_)
    source = _source(np.zeros((3, 128)), valid=valid, reasons=(code,) * 3)

    result = _run(source)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (code,)
    assert result.qualified_sample_count == 0
    assert result.maximum_lag_s.size == 0


def test_heterogeneous_unavailable_chunks_publish_mixed_support_code() -> None:
    """Два разных transform-отказа сворачиваются в объявленный mixed-код."""
    valid = np.zeros((3, 128), dtype=np.bool_)
    source = _source(
        np.zeros((3, 128)),
        valid=valid,
        reasons=(FILTER_SUPPORT_TOO_SHORT, FILTER_CONTEXT_UNSTABLE, FILTER_SUPPORT_TOO_SHORT),
    )

    result = _run(source)

    assert result.reason_codes == (
        FILTER_CONTEXT_UNSTABLE,
        FILTER_SUPPORT_TOO_SHORT,
        MIXED_UNAVAILABLE_SUPPORT,
    )


def test_partial_common_support_keeps_measurements_and_transform_reasons() -> None:
    """Смешанный поток даёт PARTIAL, не выбрасывая измеренный общий.support."""
    residuals = _delayed_residuals()
    valid = np.ones_like(residuals, dtype=np.bool_)
    valid[2, -10:] = False
    source = _source(
        residuals,
        valid=valid,
        reasons=(FILTER_SUPPORT_TOO_SHORT, FILTER_CONTEXT_UNSTABLE, None),
    )

    result = _run(source)

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (
        FILTER_CONTEXT_UNSTABLE,
        FILTER_SUPPORT_TOO_SHORT,
        MIXED_UNAVAILABLE_SUPPORT,
    )
    assert result.qualified_sample_count == source.sample_count - 10
    assert result.zero_lag_correlation.shape == (3, 3)


def test_zero_envelope_mad_is_scale_zero_not_substituted_scale() -> None:
    """Нулевая MAD полосы запрещает семейство без нулевой активности."""
    source = _source(np.ones((3, 128), dtype=np.float64))

    result = _run(source)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (SCALE_ZERO,)
    assert result.activity_fraction.size == 0


def test_nineteen_active_samples_are_insufficient_activity() -> None:
    """Граница 20 достижима: 19 активных отсчётов не публикуют lift."""
    rng = np.random.default_rng(6_022)
    base = rng.uniform(-1.0, 1.0, 512)
    residuals = np.repeat(base[None, :], 3, axis=0)
    residuals[:, :19] += 10.0
    source = _source(residuals)

    result = _run(source)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (INSUFFICIENT_ACTIVITY,)
    assert result.coincidence_probability.size == 0


def test_activity_threshold_is_strictly_above_five_mad() -> None:
    """Ровно 5*MAD не активно; 20 значений 6*MAD активны при locked минимуме."""
    base = np.concatenate(
        (
            -np.ones(50),
            np.ones(29),
            np.full(20, 6.0),
            np.asarray([5.0]),
        )
    )
    source = _source(np.asarray((base, np.roll(base, -2), np.roll(base, -4))))

    result = _run(source)

    assert result.status is Status.AVAILABLE
    assert result.active_sample_count.tolist() == [20, 20, 20]


def test_short_qualified_spans_fail_lag_support_without_bridging_gaps() -> None:
    """Короткие спаны не склеиваются через gap ради искусственного lag."""
    rng = np.random.default_rng(6_022)
    base = rng.uniform(-1.0, 1.0, 40)
    base[:22] += 10.0
    residuals = np.repeat(base[None, :], 3, axis=0)
    valid = np.repeat(((np.arange(40) % 9) < 8)[None, :], 3, axis=0)
    source = _source(residuals, valid=valid)

    result = _run(source)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (LAG_SUPPORT_TOO_SHORT,)
    assert result.qualified_sample_count == 0


def test_lag_cap_thins_the_grid_without_shrinking_the_declared_range() -> None:
    """При 500 кГц кэп 2049 прореживает сетку, но границы остаются ±20 мс.

    Диапазон `[-0.02, +0.02] s` заморожен рецептом, а кап ограничивает только число
    точек. Обрезка по краям дала бы ±2.048 мс — при 50 Гц меньше половины периода
    сети — и результат заявлял бы `lag_high_s`, которого в сетке нет.
    """
    lags = declared_lag_samples(-0.02, 0.02, 500_000.0, 2_049)

    assert lags.size <= 2_049
    assert (int(lags[0]), int(lags[-1])) == (-10_000, 10_000)
    assert int(lags[-1]) / 500_000.0 == 0.02
    assert int(lags[0]) / 500_000.0 == -0.02
    step = int(np.diff(lags)[0])
    assert step == 10
    assert np.all(np.diff(lags) == step)
    assert 0 in {int(value) for value in lags}


def test_lag_grid_keeps_sample_spacing_when_the_range_fits_the_cap() -> None:
    """Диапазон, умещающийся в кэп, остаётся плотным с шагом 1/fs и без прореживания."""
    lags = declared_lag_samples(-0.002, 0.002, 500_000.0, 2_049)

    assert lags.size == 2_001
    assert (int(lags[0]), int(lags[-1])) == (-1_000, 1_000)
    assert np.all(np.diff(lags) == 1)


def test_lag_peak_tie_prefers_smallest_absolute_then_negative() -> None:
    """Locked tie-break разрешает ничью по abs корреляции без данных о фазе."""
    lags = np.asarray((-2, -1, 0, 1), dtype=np.int64)
    correlations = np.asarray((0.9, -0.9, 0.8, 0.9), dtype=np.float64)

    assert select_peak_lag(correlations, lags) == 1


def test_independent_seeded_envelopes_have_lift_one_and_no_stable_peak() -> None:
    """Независимые активности дают P(both)=P(A)P(B), а выбранный lag не фиксирован."""
    peaks: set[float] = set()
    for seed in (6_022, 6_023, 6_024, 6_025):
        rng = np.random.default_rng(seed)
        count = 2_048
        first_values = rng.uniform(-1.0, 1.0, count)
        second_values = rng.uniform(-1.0, 1.0, count)
        third_values = rng.uniform(-1.0, 1.0, count)
        first_active = rng.choice(count, 64, replace=False)
        outside_first = np.setdiff1d(np.arange(count), first_active, assume_unique=True)
        second_active = rng.choice(outside_first, 64, replace=False)
        second_active[:2] = first_active[:2]
        third_active = rng.choice(count, 64, replace=False)
        first_values[first_active] += 10.0
        second_values[second_active] += 10.0
        third_values[third_active] += 10.0
        source = _source(np.asarray((first_values, second_values, third_values)))

        result = _run(source)

        assert result.coincidence_probability[0, 1] == pytest.approx(2 / count)
        assert result.lift[0, 1] == pytest.approx(1.0)
        assert abs(result.maximum_lag_correlation[0, 1]) < 0.35
        peaks.add(float(result.maximum_lag_s[0, 1]))
    assert len(peaks) > 1


def test_checkpoint_cancellation_propagates_by_identity() -> None:
    """Cancellation внутри bounded residual replay не превращается в QC-код."""
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as raised:
        _run(_source(_delayed_residuals()), checkpoint=cancel)

    assert raised.value is error


def test_f13_declarations_reject_overlap_and_wrong_locked_vocabulary() -> None:
    """Пересекающиеся полосы и чужой method vocabulary не доходят до движка."""
    with pytest.raises(ValueError, match="bands"):
        replace(_declarations(), bands_hz=((3_000.0, 11_000.0), *BANDS_HZ[1:]))
    with pytest.raises(ValueError, match="locked"):
        replace(_declarations(), filter="other")


def test_engine_rejects_band_envelope_root_not_matching_resolved_bands() -> None:
    """Движок не принимает чужой или пересобранный общий band-envelope корень."""
    bands = _resolved_bands()
    mismatched = (replace(bands[0], reason_code="band_above_nyquist"), *bands[1:])

    with pytest.raises(ValueError, match="band-envelope root"):
        _run(_source(_delayed_residuals()), bands=mismatched)


def test_realistic_shared_filter_am_fixture_reaches_activity_and_two_ms_lag() -> None:
    """Реальный путь Butterworth+Hilbert на разреженных AM-burst даёт lag в 1 сэмпл."""
    sample_rate_hz = 500_000.0
    sample_count = 131_072
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    sample_indices = np.arange(sample_count)
    first_burst = ((sample_indices % 18_500) < 2_000).astype(np.float64)
    delayed_burst = (((sample_indices - 1_000) % 18_500) < 2_000).astype(np.float64)
    third_burst = (((sample_indices + 500) % 20_500) < 1_500).astype(np.float64)
    first_envelope = 0.4 + 0.02 * np.sin(2.0 * np.pi * 1_730.0 * times) + 0.9 * first_burst
    second_envelope = 0.4 + 0.02 * np.sin(2.0 * np.pi * 1_730.0 * times) + 0.9 * delayed_burst
    third_envelope = 0.35 + 0.02 * np.cos(2.0 * np.pi * 2_110.0 * times) + 0.7 * third_burst
    samples = (
        first_envelope * np.cos(2.0 * np.pi * 8_500.0 * times)
        + second_envelope * np.cos(2.0 * np.pi * 14_000.0 * times + 5.0 * np.pi / 4.0)
        + third_envelope * np.cos(2.0 * np.pi * 80_000.0 * times)
    )
    mains_period = sample_rate_hz / 50.0
    boundaries = np.arange(0.0, sample_count + mains_period, mains_period, dtype=np.float64)
    boundaries = boundaries[boundaries <= sample_count]
    phase = PhaseCycles(
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        cycle_start_samples=boundaries[:-1],
        cycle_end_samples=boundaries[1:],
        cycle_valid=np.ones(boundaries.size - 1, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )
    recipe = parse_analysis_recipe(
        decode_object(_EXAMPLE.read_text(encoding="utf-8"), "realistic F13 recipe")
    )
    assert isinstance(recipe, CharacterizationRecipe)
    source = prepare_band_envelopes(
        samples,
        phase,
        recipe,
        sample_rate_hz=sample_rate_hz,
    )
    declarations = replace(
        _declarations(), lag_low_s=-0.02, lag_high_s=0.02, maximum_lag_points=2_049
    )

    result = _run(source, declarations, resolve_characterization_bands(recipe, sample_rate_hz))

    assert result.status in {Status.AVAILABLE, Status.PARTIAL}
    assert np.all(result.active_sample_count >= declarations.minimum_active_samples)
    assert result.lift[0, 1] > 1.0
    assert abs(result.maximum_lag_s[0, 1] - 0.002) <= 1.0 / sample_rate_hz
