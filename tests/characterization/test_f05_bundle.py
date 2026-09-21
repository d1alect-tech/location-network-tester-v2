"""F05 bundle assembly: mapped F05 beside an unchanged F01 and F02 family."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization import (
    FAMILY_IDS,
    Status,
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
from lnt.characterization.f02_bundle import build_f01_f02_bundle
from lnt.characterization.f05_bundle import build_f01_f02_f05_bundle
from lnt.characterization.f05_phase_stats import (
    F05Result,
    compute_f05_phase_conditioned_statistics,
)
from lnt.characterization.phase_model import PhaseCycles
from lnt.characterization.records import Unit
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
_F05_MASK = "f05_bins_valid"
_RECORD_S = 128 / _FS_HZ


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
    """Два полных цикла: все бины набраны, семейство доступно."""
    phase = _cycles([0.0, 64.0], [64.0, 128.0], 128)
    samples = np.tile(np.arange(_BINS, dtype=np.float64) / 16.0, 2)
    result = compute_f05_phase_conditioned_statistics(
        samples, phase, (_event(10), _event(74)), phase_bins=_BINS, minimum_support_per_bin=2
    )
    assert result.status is Status.AVAILABLE
    return result


def _partial_f05_result() -> F05Result:
    """Второй цикл короче: половина бинов набрана дважды, половина один раз."""
    phase = _cycles([0.0, 64.0], [64.0, 96.0], 128)
    result = compute_f05_phase_conditioned_statistics(
        np.ones(128, dtype=np.float64),
        phase,
        (_event(10),),
        phase_bins=_BINS,
        minimum_support_per_bin=2,
    )
    assert result.status is Status.PARTIAL
    return result


def _unavailable_f05_result() -> F05Result:
    phase = PhaseCycles(
        sample_rate_hz=_FS_HZ,
        sample_count=128,
        cycle_start_samples=np.array([], dtype=np.float64),
        cycle_end_samples=np.array([], dtype=np.float64),
        cycle_valid=np.array([], dtype=np.bool_),
        status=Status.UNAVAILABLE,
        reason_code=None,
    )
    result = compute_f05_phase_conditioned_statistics(
        np.ones(128, dtype=np.float64), phase, (), phase_bins=_BINS
    )
    assert result.status is Status.UNAVAILABLE
    return result


def _build(
    result: F05Result,
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Окно F05 это вся запись, а не окно F01: длительность берётся у записи."""
    return build_f01_f02_f05_bundle(
        _f01_result(), _f02_result(), result, _recipe(), record_duration_s=_RECORD_S
    )


def test_bundle_keeps_eighteen_families_with_f05_in_its_declared_slot() -> None:
    bundle, _arrays, _tables = _build(_f05_result())

    assert len(bundle.families) == 18
    assert [family.family_id for family in bundle.families] == list(FAMILY_IDS)
    assert bundle.families[_F05_INDEX].family_id == "f05_phase_conditioned_statistics"
    untouched = (bundle.families[2], bundle.families[3], *bundle.families[_F05_INDEX + 1 :])
    assert all(family.status is Status.UNAVAILABLE for family in untouched)
    assert all(family.reason_codes == ("not_computed",) for family in untouched)


def test_f01_and_f02_envelopes_match_the_two_family_bundle() -> None:
    """F05 не сдвигает уже опубликованные семейства ни в одном поле."""
    recipe = _recipe()
    two, two_arrays, _tables = build_f01_f02_bundle(_f01_result(), _f02_result(), recipe)
    three, three_arrays, _tables2 = build_f01_f02_f05_bundle(
        _f01_result(), _f02_result(), _f05_result(), recipe, record_duration_s=_RECORD_S
    )

    assert three.families[0] == two.families[0]
    assert three.families[1] == two.families[1]
    for array_id, values in two_arrays.items():
        assert np.array_equal(three_arrays[array_id], values)
    # Одинокая сборка F01 остаётся ровно тем же конвертом.
    lone, _lone_arrays, _lone_tables = build_f01_bundle(_f01_result(), recipe)
    assert three.families[0] == lone.families[0]


def test_available_f05_publishes_five_bin_arrays_and_the_bin_population() -> None:
    bundle, arrays, _tables = _build(_f05_result())
    f05 = bundle.families[_F05_INDEX]

    assert f05.status is Status.AVAILABLE
    assert f05.reason_codes == ()
    assert {reference.array_id for reference in f05.array_refs} == {
        "f05_mu_v",
        "f05_sigma2_v2",
        "f05_ms_v2",
        "f05_p_event",
        "f05_n_b",
    }
    assert all(reference.validity_mask_id is None for reference in f05.array_refs)
    assert all(reference.shape == (_BINS,) for reference in f05.array_refs)
    for array_id in ("f05_mu_v", "f05_sigma2_v2", "f05_ms_v2", "f05_p_event", "f05_n_b"):
        assert np.all(np.isfinite(arrays[array_id]))
    assert f05.support.sample_count == _BINS
    assert f05.support.observation_count == _BINS
    assert f05.support.missing_count == 0
    assert f05.support.stored_count == _BINS
    assert f05.support.selection_rule == "all"
    assert f05.n == _BINS


def test_partial_f05_carries_a_mask_on_every_array() -> None:
    """PARTIAL обязан объявить невалидные бины маской, а не выдать их за измерение."""
    bundle, arrays, _tables = _build(_partial_f05_result())
    f05 = bundle.families[_F05_INDEX]

    assert f05.status is Status.PARTIAL
    assert f05.reason_codes == ("insufficient_support",)
    for reference in f05.array_refs:
        assert reference.validity_mask_id == _F05_MASK
        mask = arrays[_F05_MASK]
        assert mask.dtype == np.uint8
        assert mask.shape == reference.shape
        assert set(np.unique(mask).tolist()) <= {0, 1}
    assert int(np.count_nonzero(arrays[_F05_MASK])) == _BINS // 2
    assert f05.support.observation_count == _BINS // 2
    assert f05.support.missing_count == _BINS - _BINS // 2
    # Невалидные бины не выдают значение за измерение.
    assert np.all(arrays["f05_mu_v"][arrays[_F05_MASK] == 0] == 0.0)


def test_event_phase_resultant_and_direction_are_published_with_their_units() -> None:
    bundle, _arrays, _tables = _build(_f05_result())
    summaries = {item.name: item for item in bundle.families[_F05_INDEX].comparison_summary}

    resultant = summaries["f05_event_phase_resultant"]
    direction = summaries["f05_event_phase_mean_rad"]
    assert resultant.unit is Unit.RATIO
    assert resultant.circular is False
    assert 0.0 <= resultant.value <= 1.0
    assert direction.unit is Unit.RAD
    assert direction.circular is True
    assert Unit.RAD in bundle.families[_F05_INDEX].units


def test_unavailable_f05_publishes_no_output_and_the_declared_code() -> None:
    bundle, arrays, _tables = _build(_unavailable_f05_result())
    f05 = bundle.families[_F05_INDEX]

    assert f05.status is Status.UNAVAILABLE
    assert f05.reason_codes == ("phase_reference_unavailable",)
    assert f05.array_refs == ()
    assert f05.comparison_summary == ()
    assert not any(name.startswith("f05_") for name in arrays)


def test_f05_family_round_trips_through_the_codec() -> None:
    bundle, arrays, tables = _build(_partial_f05_result())
    files = encode_bundle(
        bundle, arrays, tables, max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes
    )

    loaded = load_bundle(files)

    assert loaded.bundle.families[_F05_INDEX] == bundle.families[_F05_INDEX]
    assert np.array_equal(loaded.arrays["f05_mu_v"], arrays["f05_mu_v"])
    assert np.array_equal(loaded.arrays[_F05_MASK], arrays[_F05_MASK])
