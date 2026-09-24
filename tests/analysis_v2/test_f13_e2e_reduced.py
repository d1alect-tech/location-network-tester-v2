"""F13 E2E-reduced через реальный seam: slot 12 и общий band-envelope поток.

На синтетике 500 кГц и 2,4 с профили ``bad`` и ``quiet`` измеряют общий
qualified support 1 130 000 из 1 200 000 отсчётов. Граничные analytic-ядра
преобразования сохраняют ``filter_support_too_short``, слабый CH2-корень фазы
нормализуется в ``phase_reference_unavailable``, а несколько причин добавляют
``mixed_unavailable_support``. Поэтому оба результата честно PARTIAL, хотя
измерения, оси и матрицы публикуются.

Геометрия проверяется из замороженного рецепта, а не из согласия движка с
собой: три полосы, 64 фазовых бина, диапазон лагов ±0,02 с и кэп 2049 точек.
``leakage_ambiguous`` не провоцируется: в спецификации нет band-power
статистики или предиката (открытый F13-1).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
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
_F13_INDEX = 12
_F13_ID = "f13_band_envelope_coactivity"
_F13_METHOD = "phase_residual_hilbert_envelope_coactivity"
_F13_METHOD_VERSION = 1
_PHASE_BINS = 64
_BAND_COUNT = 3
_MAXIMUM_LAG_POINTS = 2049
_LAG_LOW_S = -0.02
_LAG_HIGH_S = 0.02
_LAG_SAMPLES = 10_000
_LAG_STEP = 10
_LAG_POINT_COUNT = 2_001
_F13_REASON_CODES = (
    "filter_support_too_short",
    "mixed_unavailable_support",
    "phase_reference_unavailable",
)
_BAND_NAMES = ("band_0001", "band_0002", "band_0003")
_BANDS_HZ = ((3_000.0, 10_000.0), (10_000.0, 50_000.0), (50_000.0, 200_000.0))
_ARRAY_IDS = (
    "f13_band_index",
    "f13_band_low_hz",
    "f13_band_high_hz",
    "f13_lag_s",
    "f13_activity_fraction",
    "f13_active_sample_count",
    "f13_zero_lag_correlation",
    "f13_coincidence_probability",
    "f13_lift",
    "f13_maximum_lag_s",
    "f13_maximum_lag_correlation",
)
_PAIR_ARRAY_IDS = (
    "f13_zero_lag_correlation",
    "f13_coincidence_probability",
    "f13_lift",
    "f13_maximum_lag_s",
    "f13_maximum_lag_correlation",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f13 e2e reduced")
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


def _assert_f13_common(
    f13: FamilyResult,
    loaded: LoadedCharacterization,
    declared: CharacterizationFamily,
) -> None:
    assert f13.family_id == declared.id == _F13_ID
    assert f13.method == declared.method == _F13_METHOD
    assert f13.method_version == declared.method_version == _F13_METHOD_VERSION
    assert f13.status is Status.PARTIAL
    assert f13.reason_codes == _F13_REASON_CODES
    assert "phase_reference_unavailable" in f13.reason_codes
    assert not PHASE_ROOT_REASON_CODES.intersection(f13.reason_codes)
    assert f13.signal_plane == "ch1_scope_input"
    assert f13.window.kind == "record"
    assert f13.window.duration_s == _DURATION_S
    assert f13.window.overlap_fraction == 0.0
    assert f13.support.sample_count == round(_FS_HZ * _DURATION_S) == 1_200_000
    assert f13.support.observation_count > 0
    assert f13.n == f13.support.observation_count
    assert tuple(reference.array_id for reference in f13.array_refs) == _ARRAY_IDS
    assert all(
        reference.validity_mask_id == f"{reference.array_id}_valid" for reference in f13.array_refs
    )
    assert tuple((reference.table_id, reference.role) for reference in f13.table_refs) == (
        ("f13_band_metadata", "band_metadata"),
    )

    summaries = {item.name: float(item.value) for item in f13.comparison_summary}
    assert summaries["f13_phase_bins"] == float(_PHASE_BINS)
    assert summaries["f13_maximum_lag_points"] == float(_MAXIMUM_LAG_POINTS)
    assert summaries["f13_lag_low_s"] == _LAG_LOW_S
    assert summaries["f13_lag_high_s"] == _LAG_HIGH_S
    assert summaries["f13_stored_lag_count"] == float(_LAG_POINT_COUNT)
    assert summaries["f13_sample_count"] == float(f13.support.sample_count)
    assert summaries["f13_qualified_sample_count"] == float(f13.support.observation_count)
    assert len(loaded.bundle.families) == 18


def _assert_f13_geometry(f13: FamilyResult, loaded: LoadedCharacterization) -> None:
    arrays = loaded.arrays
    assert arrays["f13_band_index"].tolist() == [0, 1, 2]
    assert arrays["f13_band_low_hz"].tolist() == [3000.0, 10000.0, 50000.0]
    assert arrays["f13_band_high_hz"].tolist() == [10000.0, 50000.0, 200000.0]
    metadata = loaded.tables["f13_band_metadata"]
    assert metadata.row_count == 3
    assert metadata.rows == tuple(
        (index, name, low, high)
        for index, (name, (low, high)) in enumerate(zip(_BAND_NAMES, _BANDS_HZ, strict=True))
    )

    lag = arrays["f13_lag_s"]
    # 500 кГц × 0,02 с = 10 000 отсчётов. При кэпе 2049 минимальный
    # симметричный целый шаг равен 10, поэтому сетка содержит 2 001 точку.
    assert round(_LAG_HIGH_S * _FS_HZ) == _LAG_SAMPLES
    assert _LAG_STEP == 10
    assert _LAG_SAMPLES % _LAG_STEP == 0
    assert _LAG_POINT_COUNT == 2 * (_LAG_SAMPLES // _LAG_STEP) + 1
    assert lag.shape == (_LAG_POINT_COUNT,)
    assert lag.size <= _MAXIMUM_LAG_POINTS
    assert lag[0] == _LAG_LOW_S
    assert lag[-1] == _LAG_HIGH_S
    assert lag[lag.size // 2] == 0.0
    assert bool(np.all(np.diff(lag) > 0.0))

    activity = arrays["f13_activity_fraction"]
    counts = arrays["f13_active_sample_count"]
    assert activity.shape == (_BAND_COUNT,)
    assert counts.shape == (_BAND_COUNT,)
    assert bool(np.all(np.isfinite(activity)))
    assert bool(np.all((activity >= 0.0) & (activity <= 1.0)))
    assert np.issubdtype(counts.dtype, np.integer)
    assert bool(np.all(counts >= 0))
    assert bool(np.all(counts <= f13.support.observation_count))

    for name in _PAIR_ARRAY_IDS:
        matrix = arrays[name]
        assert matrix.shape == (3, 3)
        assert bool(np.all(np.isfinite(matrix)))
        assert np.array_equal(matrix, matrix.T)


def test_bad_profile_publishes_f13_geometry_and_declared_partial(tmp_path: Path) -> None:
    """Плотный профиль сохраняет F13-измерения; PARTIAL объявляет измеренные потери."""
    session = _session(tmp_path, "syn-bad-500k", "bad")
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    first_files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(first_files)
    f13 = loaded.bundle.families[_F13_INDEX]
    declared = recipe.families[_F13_INDEX]

    assert first.cache_hit is False
    _assert_f13_common(f13, loaded, declared)
    _assert_f13_geometry(f13, loaded)

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert _artifact_bytes(second.artifact_dir) == first_files
    assert _raw_hashes(session) == before


def test_quiet_profile_keeps_f13_measurements_with_same_declared_reasons(tmp_path: Path) -> None:
    """Тихая запись не фабрикует AVAILABLE: те же потери фазы и фильтра сохраняются."""
    session = _session(tmp_path, "syn-quiet-500k", "quiet")
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    first_files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(first_files)
    f13 = loaded.bundle.families[_F13_INDEX]
    declared = recipe.families[_F13_INDEX]

    assert first.cache_hit is False
    _assert_f13_common(f13, loaded, declared)
    _assert_f13_geometry(f13, loaded)

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert _artifact_bytes(second.artifact_dir) == first_files
    assert _raw_hashes(session) == before
