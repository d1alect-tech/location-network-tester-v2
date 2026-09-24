"""F11 E2E-reduced через реальный seam: phase × band × F15-mode сетка.

Профиль ``bad`` проходит через F10 → F15 → F11 и даёт частичный, но содержательный
результат: события есть, однако часть корневого инвентаря не имеет фазы, метки
полосы или сохранённой моды. Рецепт объявляет 16 фаз, 3 полосы и 4 моды, поэтому
публикуются ровно 192 ячейки; три измеримые величины имеют 129-точечные pooled
CDF-сетки. ``dominant_frequency_hz`` структурно отсутствует в корневом событии:
в каждой ячейке это явный UNAVAILABLE с ``missing_count=support_count``, но не
причина семейного PARTIAL. Тихая запись делает F15 недоступным, поэтому F11
корректно деградирует до ``mode_unavailable``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.context.json_codec import decode_object
from lnt.simulate import simulate_session

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.bundle_codec import LoadedCharacterization
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 500000.0
_DURATION_S = 2.4
_SEED = 6022
_F11_INDEX = 10
_F15_INDEX = 14
_F11_ID = "f11_conditional_distributions"
_F11_METHOD = "fixed_phase_band_f15_mode_empirical_distributions"
_F11_METHOD_VERSION = 1
_PHASE_BINS = 16
_BAND_COUNT = 3
_MODE_COUNT = 4
_CELL_COUNT = _PHASE_BINS * _BAND_COUNT * _MODE_COUNT
_CDF_POINTS = 129
_MINIMUM_SUPPORT = 20


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f11 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _session(root: Path, name: str, profile: str) -> Path:
    return simulate_session(
        out_dir=root / name,
        profile=profile,
        duration_s=_DURATION_S,
        sample_rate_hz=_FS_HZ,
        seed=_SEED,
    )


def _load(session: Path) -> tuple[np.ndarray, np.ndarray]:
    ch1 = np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False)
    ch2 = np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False)
    return ch1, ch2


def _raw_hashes(session: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((session / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "ch2.npy", "manifest.json")
    }


def _artifact_bytes(artifact_dir: Path) -> dict[str, bytes]:
    return {name: (artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}


def _assert_f11_envelope(
    f11: FamilyResult, f15: FamilyResult, declared: CharacterizationFamily
) -> None:
    assert f11.family_id == declared.id == _F11_ID
    assert f11.method == declared.method == _F11_METHOD
    assert f11.method_version == declared.method_version == _F11_METHOD_VERSION
    assert f15.family_id == "f15_interpretable_modes"
    assert f15.status is Status.AVAILABLE
    assert f11.status is Status.PARTIAL
    assert f11.reason_codes == (
        "dominant_band_unavailable",
        "mode_assignment_unavailable",
        "phase_reference_unavailable",
    )
    assert f11.signal_plane == "ch1_scope_input"
    assert f11.window.kind == "record"
    assert f11.window.duration_s == _DURATION_S
    assert f11.window.overlap_fraction == 0.0
    assert f11.table_refs[0].table_id == "f11_cells"


def _assert_f11_summary(f11: FamilyResult) -> None:
    summaries = {item.name: float(item.value) for item in f11.comparison_summary}
    assert summaries["f11_event_count"] == float(f11.support.sample_count)
    assert summaries["f11_evaluated_event_count"] == summaries["f11_event_count"]
    assert summaries["f11_omitted_event_count"] == 0.0
    assert summaries["f11_n_mode_missing"] > 0.0
    assert summaries["f11_n_dominant_band_unavailable"] > 0.0
    assert summaries["f11_n_phase_unavailable"] > 0.0
    assert f11.n == f11.support.observation_count
    assert f11.support.missing_count == f11.support.sample_count - f11.n


def _assert_f11_geometry(loaded: LoadedCharacterization) -> None:
    arrays = loaded.arrays
    support = arrays["f11_cell_support_count"]
    assert support.shape == (_PHASE_BINS, _BAND_COUNT, _MODE_COUNT)
    assert arrays["f11_phase_bin"].shape == (_PHASE_BINS,)
    assert arrays["f11_band_index"].shape == (_BAND_COUNT,)
    assert arrays["f11_mode_index"].shape == (_MODE_COUNT,)
    assert arrays["f11_cdf_probability"].shape == (_CDF_POINTS,)
    assert np.array_equal(arrays["f11_cdf_probability"], np.linspace(0.0, 1.0, _CDF_POINTS))
    assert arrays["f11_absolute_peak_v"].shape == (_CELL_COUNT, 6)
    assert arrays["f11_duration_s"].shape == (_CELL_COUNT, 6)
    assert arrays["f11_v2_s"].shape == (_CELL_COUNT, 6)
    assert arrays["f11_cdf_absolute_peak_v"].shape == (_CELL_COUNT, _CDF_POINTS)
    assert arrays["f11_cdf_duration_s"].shape == (_CELL_COUNT, _CDF_POINTS)
    assert arrays["f11_cdf_v2_s"].shape == (_CELL_COUNT, _CDF_POINTS)
    assert arrays["f11_cdf_grid_absolute_peak_v"].shape == (_CDF_POINTS,)
    assert arrays["f11_cdf_grid_duration_s"].shape == (_CDF_POINTS,)
    assert arrays["f11_cdf_grid_v2_s"].shape == (_CDF_POINTS,)
    assert bool(np.all(np.isfinite(arrays["f11_cdf_grid_absolute_peak_v"])))
    assert bool(np.all(np.isfinite(arrays["f11_cdf_grid_duration_s"])))
    assert bool(np.all(np.isfinite(arrays["f11_cdf_grid_v2_s"])))
    assert arrays["f11_cdf_grid_dominant_frequency_hz"].shape == (0,)
    assert arrays["f11_cdf_dominant_frequency_hz"].shape == (_CELL_COUNT, 0)
    assert int(np.count_nonzero(arrays["f11_dominant_frequency_hz_valid"])) == 0


def _assert_frequency_absence(loaded: LoadedCharacterization) -> None:
    table = loaded.tables["f11_cells"]
    assert len(table.rows) == _CELL_COUNT
    columns = {column.name: index for index, column in enumerate(table.columns)}
    required = {
        "support_count",
        "status",
        "f11_dominant_frequency_observed_count",
        "f11_dominant_frequency_missing_count",
        "f11_dominant_frequency_status",
        "f11_dominant_frequency_reason_code",
        "f11_absolute_peak_status",
        "f11_duration_status",
        "f11_v2_s_status",
    }
    assert required <= columns.keys()
    supported = []
    for row in table.rows:
        cell_support = row[columns["support_count"]]
        assert isinstance(cell_support, int)
        assert row[columns["f11_dominant_frequency_observed_count"]] == 0
        assert row[columns["f11_dominant_frequency_missing_count"]] == cell_support
        assert row[columns["f11_dominant_frequency_status"]] == Status.UNAVAILABLE.value
        assert row[columns["f11_dominant_frequency_reason_code"]] == "insufficient_support"
        if cell_support >= _MINIMUM_SUPPORT:
            supported.append(row)
    assert supported
    assert all(row[columns["status"]] == Status.AVAILABLE.value for row in supported)
    for column in ("f11_absolute_peak_status", "f11_duration_status", "f11_v2_s_status"):
        assert all(row[columns[column]] == Status.AVAILABLE.value for row in supported)


def test_bad_profile_publishes_full_conditional_grid_without_frequency_fabrication(
    tmp_path: Path,
) -> None:
    """F11 публикует 192 ячейки и три измеримые CDF, не подменяя отсутствующую частоту."""
    session = _session(tmp_path, "syn-bad-500k", "bad")
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    first_files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(first_files)
    f11 = loaded.bundle.families[_F11_INDEX]
    f15 = loaded.bundle.families[_F15_INDEX]
    declared = recipe.families[_F11_INDEX]

    assert first.cache_hit is False
    _assert_f11_envelope(f11, f15, declared)
    _assert_f11_summary(f11)
    _assert_f11_geometry(loaded)
    _assert_frequency_absence(loaded)
    assert "insufficient_support" not in f11.reason_codes

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert _artifact_bytes(second.artifact_dir) == first_files
    assert _raw_hashes(session) == before


def test_quiet_profile_degrades_when_f15_modes_are_unavailable(tmp_path: Path) -> None:
    """Без доступных F15-режимов F11 не фабрикует ячейки, а объявляет mode_unavailable."""
    session = _session(tmp_path, "syn-quiet-500k", "quiet")
    recipe = _recipe()
    ch1, ch2 = _load(session)

    result = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    loaded = load_bundle(_artifact_bytes(result.artifact_dir))
    f11 = loaded.bundle.families[_F11_INDEX]
    f15 = loaded.bundle.families[_F15_INDEX]
    declared = recipe.families[_F11_INDEX]

    assert result.cache_hit is False
    assert f11.family_id == declared.id == _F11_ID
    assert f11.method == declared.method == _F11_METHOD
    assert f11.method_version == declared.method_version == _F11_METHOD_VERSION
    assert f15.status is Status.UNAVAILABLE
    assert f15.reason_codes == ("feature_scale_zero",)
    assert f11.status is Status.UNAVAILABLE
    assert f11.reason_codes == ("mode_unavailable",)
    assert f11.array_refs == ()
    assert f11.table_refs == ()
    assert f11.comparison_summary == ()
    assert not any(name.startswith("f11_") for name in loaded.arrays)
