"""F11 seam adapter tests: retained-row F15 data expands onto the shared window grid."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2.characterization_slices_conditional import (
    build_f11_event_inventory,
    build_f15_mode_source,
)
from lnt.analysis_v2.characterization_slices_extended import _compute_f11
from lnt.characterization.bands import resolve_characterization_bands
from lnt.characterization.event_models import RootEvent, RootEvents, RootEventSettings
from lnt.characterization.f11_modes import assign_mode, build_mode_model
from lnt.characterization.f15_modes import fit_f15_pam
from lnt.characterization.f15_result import F15Result, F15Settings
from lnt.characterization.phase_model import PhaseCycles
from lnt.characterization.records import Status
from lnt.characterization.sync_grid import complete_window_count, nominal_window_samples
from lnt.context.json_codec import decode_object
from lnt.events.models import Polarity
from lnt.scope_io import NEVER_CANCELLED

if TYPE_CHECKING:
    from collections.abc import Iterator

    from lnt.characterization.event_models import RootTimelineItem

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 1000.0
_SAMPLE_COUNT = 2000
_WINDOWS = complete_window_count(_SAMPLE_COUNT, nominal_window_samples(0.02, _FS_HZ))


def _recipe() -> CharacterizationRecipe:
    recipe = parse_analysis_recipe(
        decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    )
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _f15_result() -> F15Result:
    centres = np.asarray(
        [
            (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
            (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0),
            (2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0),
            (3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0),
        ],
        dtype=np.float64,
    )
    return fit_f15_pam(
        np.tile(centres, (20, 1)),
        np.arange(80, dtype=np.int64),
        settings=F15Settings.locked(),
        source_window_count=_WINDOWS,
    )


def _root_event() -> RootEvent:
    return RootEvent(
        ordinal=7,
        timeline_segment=1,
        start_sample=100,
        end_sample=103,
        peak_sample=101,
        start_time_s=100 / _FS_HZ,
        end_time_s=103 / _FS_HZ,
        peak_time_s=101 / _FS_HZ,
        peak_value_v=-2.5,
        polarity=Polarity.NEGATIVE,
        snr_ratio=12.0,
        excess_v2_s=3.0,
        v2_s=4.25,
        clipped=False,
        dominant_band="band_0002",
        dominant_band_reason_code=None,
        boundary=False,
    )


def _replay(_: object) -> Iterator[RootTimelineItem]:
    return iter(())


def _root_events() -> RootEvents:
    return RootEvents(
        sample_rate_hz=_FS_HZ,
        sample_count=_SAMPLE_COUNT,
        events=(_root_event(),),
        gaps=(),
        exclusions=(),
        candidate_count=1,
        snr_rejected_count=0,
        accepted_count=1,
        omitted_count=0,
        dead_time_rejected_count=0,
        gap_count=2,
        omitted_gap_count=3,
        omitted_exclusion_count=0,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=RootEventSettings(
            recipe_sha256="0" * 64,
            detector="test",
            noise_window_samples=1,
            noise_step_samples=1,
            minimum_noise_samples=1,
            threshold_sigma=5.0,
            max_gap_samples=1,
            minimum_event_samples=1,
            minimum_snr_db=1.0,
            minimum_snr_ratio=1.0,
            dead_time_s=0.0,
            dead_time_samples=0,
            chunk_samples=1,
            fft_max_samples=4096,
            clipping_low_v=None,
            clipping_high_v=None,
            clipping_reason_code=None,
            dead_time_handling="exclude_intervals",
            gap_handling="exclude_waiting_intervals",
        ),
        status=Status.AVAILABLE,
        reason_codes=(),
        _replay_factory=_replay,
    )


def _phase() -> PhaseCycles:
    return PhaseCycles(
        sample_rate_hz=_FS_HZ,
        sample_count=_SAMPLE_COUNT,
        cycle_start_samples=np.asarray([0.0]),
        cycle_end_samples=np.asarray([float(_SAMPLE_COUNT)]),
        cycle_valid=np.asarray([True], dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def test_f15_adapter_expands_retained_rows_to_complete_window_labels() -> None:
    f15 = _f15_result()
    source = build_f15_mode_source(
        f15, sample_count=_SAMPLE_COUNT, sample_rate_hz=_FS_HZ, overlap_fraction=0.0
    )
    model = build_mode_model(source, sample_rate_hz=_FS_HZ)
    assert model is not None
    assert source.canonical_labels == ("mode_0", "mode_1", "mode_2", "mode_3")
    assert source.window_features == (None,) * _WINDOWS
    assert source.window_labels[79] == f"mode_{int(f15.labels[79])}"
    assert source.window_labels[80:] == (None,) * 20
    assert assign_mode(model, 79 * 20) == source.window_labels[79]
    assert assign_mode(model, 80 * 20) is None
    assert source.canonical_standardized_features == tuple(
        tuple(float(value) for value in f15.standardized_features[_row_of(f15, int(window))])
        for window in f15.medoid_indices
    )


def _row_of(result: F15Result, window_index: int) -> int:
    """Номер компактной строки F15 по индексу окна полной сетки."""
    rows = {int(window): row for row, window in enumerate(result.window_indices)}
    return rows[window_index]


def _f15_result_high_indices() -> F15Result:
    """F15, сохранивший только окна 80..159: индекс сетки больше номера строки."""
    centres = np.asarray(
        [
            (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
            (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0),
            (2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0),
            (3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0),
        ],
        dtype=np.float64,
    )
    return fit_f15_pam(
        np.tile(centres, (20, 1)),
        np.arange(80, 160, dtype=np.int64),
        settings=F15Settings.locked(),
        source_window_count=160,
    )


def test_adapter_maps_medoid_grid_indices_onto_compact_retained_rows() -> None:
    """Given retained windows late in the grid, medoid indices must not index the row matrix.

    `F15Result.medoid_indices` holds COMPLETE-GRID window indices while
    `standardized_features` holds only the retained rows. When qualification drops
    early windows the two numbering spaces diverge, and indexing rows by a grid
    index raises `IndexError` on real profiles such as `async-heavy`. This pins the
    mapping through `window_indices` instead.
    """
    f15 = _f15_result_high_indices()
    retained = f15.standardized_features.shape[0]
    assert retained == 80
    assert int(f15.medoid_indices.min()) >= retained, "fixture must diverge from row numbering"

    source = build_f15_mode_source(
        f15, sample_count=160 * 20, sample_rate_hz=_FS_HZ, overlap_fraction=0.0
    )

    assert source.canonical_standardized_features == tuple(
        tuple(float(value) for value in f15.standardized_features[_row_of(f15, int(window))])
        for window in f15.medoid_indices
    )
    assert len(source.window_labels) == 160
    assert source.window_labels[:80] == (None,) * 80
    assert source.window_labels[159] == f"mode_{int(f15.labels[-1])}"


def test_event_adapter_preserves_root_fields_and_accounts_for_gaps() -> None:
    source = build_f11_event_inventory(_root_events(), sample_rate_hz=_FS_HZ)

    assert len(source.events) == 1
    event = source.events[0]
    assert (event.ordinal, event.peak_sample, event.peak_time_s) == (7, 101, 101 / _FS_HZ)
    assert (event.polarity, event.absolute_peak_v) == (Polarity.NEGATIVE, 2.5)
    assert (event.duration_s, event.dominant_band, event.v2_s) == (4 / _FS_HZ, "band_0002", 4.25)
    assert (source.gap_count, source.omitted_gap_count) == (2, 3)


def test_f11_slice_degrades_when_f15_is_unavailable() -> None:
    unavailable = fit_f15_pam(
        np.zeros((4, 7), dtype=np.float64),
        np.arange(4, dtype=np.int64),
        settings=replace(F15Settings.locked(), minimum_windows=4),
    )
    result = _compute_f11(
        _phase(),
        _root_events(),
        unavailable,
        resolve_characterization_bands(_recipe(), _FS_HZ),
        _SAMPLE_COUNT,
        _FS_HZ,
        _recipe(),
        NEVER_CANCELLED,
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("mode_unavailable",)
    assert result.cells == ()
