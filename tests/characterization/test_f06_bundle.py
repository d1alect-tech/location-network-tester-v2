"""F06 bundle assembly: mapped F06 beside unchanged F01, F02 and F05 families."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization import (
    FAMILY_IDS,
    Filter,
    Status,
    Unit,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.event_models import RootEvent
from lnt.characterization.f01_bundle import build_f01_bundle
from lnt.characterization.f01_phase_cycle import F01Result, compute_f01_phase_cycle
from lnt.characterization.f02_amplitude_shape import (
    F02Result,
    compute_f02_amplitude_time_shape,
)
from lnt.characterization.f05_bundle import build_f01_f02_f05_bundle
from lnt.characterization.f05_phase_stats import (
    F05Result,
    compute_f05_phase_conditioned_statistics,
)
from lnt.characterization.f06_bundle import build_f01_f02_f05_f06_bundle
from lnt.characterization.f06_modulation import F06Result
from lnt.characterization.phase_model import PhaseCycles
from lnt.context.json_codec import decode_object
from lnt.events.models import Polarity

if TYPE_CHECKING:
    from lnt.characterization.models import CharacterizationBundle
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 8000.0
_BINS = 64
_TEMPLATE_SAMPLES = 1000
_AMPS = {1: 6.0, 3: 0.6, 5: 0.3, 7: 0.15}
_PHASES = {1: 0.4, 3: -0.7, 5: 1.1, 7: 0.2}
_F05_INDEX = 4
_F06_INDEX = 5
_RECORD_SAMPLES = 1024
_RECORD_S = _RECORD_SAMPLES / _FS_HZ
_SPAN_SAMPLES = 256
_START_SAMPLE = 64
_STORED = 32
_TRAJECTORY_IDS = ("f06_envelope_v", "f06_phase_rad", "f06_frequency_hz")


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _comb(duration_s: float = 2.4) -> np.ndarray:
    n = round(_FS_HZ * duration_s)
    t = np.arange(n, dtype=np.float64) / _FS_HZ
    signal = np.zeros(n, dtype=np.float64)
    for order in range(1, 41):
        signal += (6.0 / order) * np.sin(2.0 * np.pi * 50.0 * order * t)
    return signal


def _f01_result() -> F01Result:
    signal = _comb()
    result = compute_f01_phase_cycle(signal, sample_rate_hz=_FS_HZ, sync_reference=signal)
    assert result.status is Status.AVAILABLE
    return result


def _template() -> np.ndarray:
    theta = np.linspace(0.0, 2.0 * np.pi, _TEMPLATE_SAMPLES, endpoint=False)
    out = np.zeros(_TEMPLATE_SAMPLES, dtype=np.float64)
    for order, amp in _AMPS.items():
        out += 2.0 * amp * np.cos(float(order) * theta + _PHASES[order])
    return out


def _event(start: int, end: int | None = None, *, ordinal: int = 1) -> RootEvent:
    if end is None:
        end = start + 8
    peak = (start + end) // 2
    return RootEvent(
        ordinal=ordinal,
        timeline_segment=0,
        start_sample=start,
        end_sample=end,
        peak_sample=peak,
        start_time_s=start / _FS_HZ,
        end_time_s=end / _FS_HZ,
        peak_time_s=peak / _FS_HZ,
        peak_value_v=20.0,
        polarity=Polarity.POSITIVE,
        snr_ratio=100.0,
        excess_v2_s=0.0,
        v2_s=0.0,
        clipped=False,
        dominant_band=None,
        dominant_band_reason_code=None,
        boundary=False,
    )


def _f02_result() -> F02Result:
    template = _template()
    span = _TEMPLATE_SAMPLES
    rng = np.random.default_rng(6022)
    record = rng.standard_normal(3 * span) * 0.05
    delayed = np.zeros(span, dtype=np.float64)
    delayed[37:] = 1.7 * template[: span - 37]
    record[span : 2 * span] += delayed
    result = compute_f02_amplitude_time_shape(
        record, template, (_event(span, 2 * span - 1),), sample_rate_hz=_FS_HZ
    )
    assert result.status is Status.AVAILABLE
    return result


def _cycles(starts: list[float], ends: list[float], sample_count: int) -> PhaseCycles:
    return PhaseCycles(
        sample_rate_hz=_FS_HZ,
        sample_count=sample_count,
        cycle_start_samples=np.array(starts, dtype=np.float64),
        cycle_end_samples=np.array(ends, dtype=np.float64),
        cycle_valid=np.array([True] * len(starts), dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _f05_result() -> F05Result:
    phase = _cycles([0.0, 64.0], [64.0, 128.0], 128)
    samples = np.tile(np.arange(_BINS, dtype=np.float64) / 16.0, 2)
    result = compute_f05_phase_conditioned_statistics(
        samples, phase, (_event(10), _event(74)), phase_bins=_BINS, minimum_support_per_bin=2
    )
    assert result.status is Status.AVAILABLE
    return result


def _f06_result() -> F06Result:
    """Траектория собирается руками: сам движок проверяется своим файлом тестов."""
    indices = (
        np.floor(np.arange(_STORED) * _SPAN_SAMPLES / _STORED).astype(np.int64) + _START_SAMPLE
    )
    times = indices.astype(np.float64) / _FS_HZ
    return F06Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        stored_indices=indices,
        amplitudes_v=1.0 + 0.5 * np.cos(2.0 * np.pi * 50.0 * times),
        phases_rad=2.0 * np.pi * 30_000.0 * times,
        frequencies_hz=np.full(_STORED, 30_000.0, dtype=np.float64),
        start_sample=_START_SAMPLE,
        stop_sample=_START_SAMPLE + _SPAN_SAMPLES,
        observation_count=_SPAN_SAMPLES,
        missing_count=_RECORD_SAMPLES - _SPAN_SAMPLES,
        stored_count=_STORED,
        snr_db=40.0,
        components=1,
    )


def _unavailable_f06_result() -> F06Result:
    empty = np.empty(0, dtype=np.float64)
    return F06Result(
        status=Status.UNAVAILABLE,
        reason_codes=("multiple_components",),
        stored_indices=np.empty(0, dtype=np.int64),
        amplitudes_v=empty,
        phases_rad=empty.copy(),
        frequencies_hz=empty.copy(),
        start_sample=0,
        stop_sample=0,
        observation_count=0,
        missing_count=_RECORD_SAMPLES,
        stored_count=0,
        snr_db=None,
        components=2,
    )


def _build(
    result: F06Result,
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    return build_f01_f02_f05_f06_bundle(
        _f01_result(),
        _f02_result(),
        _f05_result(),
        result,
        _recipe(),
        sample_rate_hz=_FS_HZ,
        record_duration_s=_RECORD_S,
    )


def test_bundle_keeps_eighteen_families_with_f06_in_its_declared_slot() -> None:
    bundle, _arrays, _tables = _build(_f06_result())

    assert len(bundle.families) == 18
    assert [family.family_id for family in bundle.families] == list(FAMILY_IDS)
    assert bundle.families[_F06_INDEX].family_id == "f06_modulation_trajectories"
    untouched = (*bundle.families[2:4], *bundle.families[_F06_INDEX + 1 :])
    assert all(family.status is Status.UNAVAILABLE for family in untouched)
    assert all(family.reason_codes == ("not_computed",) for family in untouched)


def test_f01_f02_and_f05_envelopes_match_the_three_family_bundle() -> None:
    """F06 не сдвигает уже опубликованные семейства ни в одном поле."""
    recipe = _recipe()
    three, three_arrays, _tables = build_f01_f02_f05_bundle(
        _f01_result(), _f02_result(), _f05_result(), recipe, record_duration_s=_RECORD_S
    )
    four, four_arrays, _tables2 = build_f01_f02_f05_f06_bundle(
        _f01_result(),
        _f02_result(),
        _f05_result(),
        _f06_result(),
        recipe,
        sample_rate_hz=_FS_HZ,
        record_duration_s=_RECORD_S,
    )

    for index in range(_F06_INDEX):
        assert four.families[index] == three.families[index]
    for array_id, values in three_arrays.items():
        assert np.array_equal(four_arrays[array_id], values)
    lone, _lone_arrays, _lone_tables = build_f01_bundle(_f01_result(), recipe)
    assert four.families[0] == lone.families[0]


def test_available_f06_publishes_three_trajectories_over_the_record_span() -> None:
    bundle, arrays, _tables = _build(_f06_result())
    f06 = bundle.families[_F06_INDEX]

    assert f06.status is Status.AVAILABLE
    assert f06.reason_codes == ()
    assert {reference.array_id for reference in f06.array_refs} == set(_TRAJECTORY_IDS)
    assert all(reference.validity_mask_id is None for reference in f06.array_refs)
    assert all(reference.shape == (_STORED,) for reference in f06.array_refs)
    for array_id in _TRAJECTORY_IDS:
        assert np.all(np.isfinite(arrays[array_id]))
    assert f06.units == (Unit.V, Unit.RAD, Unit.HZ)
    assert f06.comparison_summary == ()
    assert f06.support.sample_count == _RECORD_SAMPLES
    assert f06.support.observation_count == _SPAN_SAMPLES
    assert f06.support.missing_count == _RECORD_SAMPLES - _SPAN_SAMPLES
    assert f06.support.stored_count == _STORED
    assert f06.support.selection_rule == "even_floor_index"
    assert f06.support.start_s == _START_SAMPLE / _FS_HZ
    assert f06.support.end_s == (_START_SAMPLE + _SPAN_SAMPLES) / _FS_HZ
    assert math.isclose(f06.support.duration_s, _SPAN_SAMPLES / _FS_HZ, rel_tol=1e-12)
    assert f06.n == _SPAN_SAMPLES


def test_declared_filter_and_record_window_are_persisted() -> None:
    """F06 фильтрует полосу, поэтому объявленный фильтр обязан попасть в конверт."""
    family = _recipe().families[_F06_INDEX]
    order = family.value("filter_order")
    assert isinstance(order, int)
    bundle, _arrays, _tables = _build(_f06_result())
    f06 = bundle.families[_F06_INDEX]

    assert f06.filter == Filter(
        kind=str(family.value("filter")), order=order, phase=str(family.value("filter_phase"))
    )
    assert f06.filter.kind == "butterworth_sos"
    assert f06.filter.phase == "zero"
    assert f06.window.kind == "record"
    assert f06.window.duration_s == _RECORD_S


def test_unavailable_f06_publishes_no_output_and_the_declared_code() -> None:
    bundle, arrays, _tables = _build(_unavailable_f06_result())
    f06 = bundle.families[_F06_INDEX]

    assert f06.status is Status.UNAVAILABLE
    assert f06.reason_codes == ("multiple_components",)
    assert f06.array_refs == ()
    assert f06.comparison_summary == ()
    assert f06.support.observation_count == 0
    assert not any(name.startswith("f06_") for name in arrays)


def test_f06_family_round_trips_through_the_codec() -> None:
    bundle, arrays, tables = _build(_f06_result())
    files = encode_bundle(
        bundle, arrays, tables, max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes
    )

    loaded = load_bundle(files)

    assert loaded.bundle.families[_F06_INDEX] == bundle.families[_F06_INDEX]
    for array_id in _TRAJECTORY_IDS:
        assert np.array_equal(loaded.arrays[array_id], arrays[array_id])
    assert loaded.bundle.families[_F06_INDEX].filter == bundle.families[_F06_INDEX].filter
