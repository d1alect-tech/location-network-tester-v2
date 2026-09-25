"""F16 E2E-reduced: реальный seam, finite artifact и маскированное отсутствие.

Проверка проходит через ``simulate_session``/синтетические ``.npy``,
``run_characterization``, опубликованный каталог и ``load_bundle``. In-memory
результат используется только как дополнительный witness: все числовые выводы
читаются из загруженного артефакта.

F16 описывает конечную запись на объявленных лагах и окнах. Тесты не выводят
калибровку, соответствие стандарту, долгую память, стационарность или причинность.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, characterization_bundle, load_bundle
from lnt.characterization.f16_bundle import MEMORY_TABLE_ID, build_f16_family, decode_f16_result
from lnt.characterization.f16_contract import (
    ACF_AGGREGATION,
    ANALYZED_SEGMENT_CONVENTION,
    AUTOCORRELATION_NAME,
    CLAIM_BOUNDARY,
    COUNT_MEAN_NAME,
    COUNT_VARIANCE_NAME,
    COUNT_WINDOW_CONVENTION,
    DECLARED_CODES,
    F16_ID,
    FANO_FACTOR_NAME,
    INSUFFICIENT_COUNT_WINDOWS,
    LAG_ABOVE_SUPPORT,
    LAG_SAMPLE_CONVENTION,
    LAGS_S,
    MAD_CONVENTION,
    METHOD,
    MINIMUM_COUNT_WINDOWS,
    MINIMUM_PAIRS,
    PHASE_REFERENCE_UNAVAILABLE,
    RECURRENCE_RATE_NAME,
)
from lnt.characterization.f16_validation import validate_f16_result
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.context.json_codec import decode_object
from lnt.simulate import simulate_session
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.analysis_v2.types import AnalysisRunResult
    from lnt.characterization.bundle_codec import LoadedCharacterization
    from lnt.characterization.f16_result import F16Result
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.records import Band
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_F16_INDEX = 15
_F16_METHOD_VERSION = 1
_SPARSE_FS_HZ = 8_000.0
_SPARSE_DURATION_S = 2.4
_ACF_FS_HZ = 6_400.0
_ACF_DURATION_S = 2.4
_LONG_FS_HZ = 10_000.0
_LONG_DURATION_S = 12.0
_SPARSE_SEAM_COUNT_WINDOWS = (112, 22, 3, 1)
_LONG_COUNT_WINDOWS = (593, 118, 22, 10)
_ARRAY_IDS = (
    "f16_lag_s",
    AUTOCORRELATION_NAME,
    "f16_pair_count",
    "f16_recurrence_radius_mad",
    RECURRENCE_RATE_NAME,
    "f16_count_window_s",
    "f16_count_window_count",
    COUNT_MEAN_NAME,
    COUNT_VARIANCE_NAME,
    FANO_FACTOR_NAME,
)
_STRUCTURAL_ARRAY_IDS = frozenset(
    {
        "f16_lag_s",
        "f16_pair_count",
        "f16_recurrence_radius_mad",
        "f16_count_window_s",
        "f16_count_window_count",
    }
)
_MEASUREMENT_MASKS = (
    ("autocorrelation", "f16_lag_valid"),
    ("recurrence_rate", "f16_recurrence_rate_valid"),
    ("count_mean", "f16_count_window_valid"),
    ("count_variance", "f16_count_window_valid"),
    ("fano_factor", "f16_fano_factor_valid"),
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f16 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _load(session: Path) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False),
        np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False),
    )


def _raw_hashes(session: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((session / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "ch2.npy", "manifest.json")
    }


def _artifact_bytes(artifact_dir: Path) -> dict[str, bytes]:
    return {name: (artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}


def _write_session(path: Path, ch1: np.ndarray, ch2: np.ndarray) -> Path:
    write_manifest(path)
    np.save(path / "ch1.npy", ch1.astype(np.float32))
    np.save(path / "ch2.npy", ch2.astype(np.float32))
    return path


def _reference(fs: float, samples: int) -> np.ndarray:
    times = np.arange(samples, dtype=np.float64) / fs
    return 6.0 * np.sin(2.0 * np.pi * 50.0 * times + 0.2)


def _smooth_record(fs: float, samples: int, peaks: tuple[float, ...] = ()) -> np.ndarray:
    times = np.arange(samples, dtype=np.float64) / fs
    result = 0.1 * np.sin(2.0 * np.pi * 1_000.0 * times)
    for peak_s in peaks:
        result[min(samples - 1, round(peak_s * fs))] += 5.0
    return result


def _publish_twice(
    recipe: CharacterizationRecipe,
    session: Path,
    channels: tuple[np.ndarray, np.ndarray],
    sample_rate_hz: float,
) -> tuple[AnalysisRunResult, AnalysisRunResult, LoadedCharacterization, dict[str, bytes]]:
    first = run_characterization(recipe, session, channels, sample_rate_hz)
    files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(files)
    second = run_characterization(recipe, session, channels, sample_rate_hz)
    return first, second, loaded, files


def _capture_f16(monkeypatch: pytest.MonkeyPatch) -> list[F16Result]:
    measured: list[F16Result] = []
    persist = build_f16_family

    def capture(
        result: F16Result,
        family: CharacterizationFamily,
        band: Band,
        *,
        measured_channel: str = "ch1",
        record_duration_s: float,
    ) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
        measured.append(result)
        return persist(
            result,
            family,
            band,
            measured_channel=measured_channel,
            record_duration_s=record_duration_s,
        )

    monkeypatch.setattr(characterization_bundle, "build_f16_family", capture)
    return measured


def _assert_cache_and_source(
    first: AnalysisRunResult,
    second: AnalysisRunResult,
    files: dict[str, bytes],
    session: Path,
    before: dict[str, str],
) -> None:
    assert first.cache_hit is False
    assert first.failures == ()
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert _artifact_bytes(second.artifact_dir) == files
    assert _raw_hashes(session) == before


def _assert_identity(
    f16: FamilyResult,
    declared: CharacterizationFamily,
    loaded: LoadedCharacterization,
) -> None:
    assert f16.family_id == declared.id == F16_ID == "f16_multiscale_memory"
    assert f16.method == declared.method == METHOD == "fft_acf_declared_recurrence_nonoverlap_fano"
    assert f16.method_version == declared.method_version == _F16_METHOD_VERSION
    assert f16.signal_plane == "ch1_scope_input"
    assert len(loaded.bundle.families) == 18
    if f16.status is not Status.UNAVAILABLE:
        assert len(f16.array_refs) == len(_ARRAY_IDS)
        assert tuple(reference.array_id for reference in f16.array_refs) == _ARRAY_IDS


def _assert_status_reason(f16: FamilyResult) -> None:
    if f16.status is Status.AVAILABLE:
        assert f16.reason_codes == ()
    else:
        assert f16.reason_codes
        assert set(f16.reason_codes) <= set(DECLARED_CODES)
    assert PHASE_ROOT_REASON_CODES.isdisjoint(f16.reason_codes)


def _assert_metadata(loaded: LoadedCharacterization) -> None:
    table = loaded.tables[MEMORY_TABLE_ID]
    values = dict(zip((column.name for column in table.columns), table.rows[0], strict=True))
    assert values["lag_sample_convention"] == LAG_SAMPLE_CONVENTION
    assert values["mad_convention"] == MAD_CONVENTION
    assert values["acf_aggregation"] == ACF_AGGREGATION
    assert values["analyzed_segment_convention"] == ANALYZED_SEGMENT_CONVENTION
    assert values["count_window_convention"] == COUNT_WINDOW_CONVENTION
    assert values["claim_boundary"] == CLAIM_BOUNDARY


def _assert_persisted_round_trip(
    loaded: LoadedCharacterization,
    f16: FamilyResult,
) -> F16Result:
    restored = decode_f16_result(f16, loaded.arrays, loaded.tables)
    validate_f16_result(restored)
    assert restored.status is f16.status
    assert restored.reason_codes == f16.reason_codes

    for reference in f16.array_refs:
        values = loaded.arrays[reference.array_id]
        assert values.dtype == np.dtype(reference.dtype)
        assert values.shape == reference.shape
        assert bool(np.all(np.isfinite(values)))
        if reference.validity_mask_id is not None:
            mask = loaded.arrays[reference.validity_mask_id]
            assert mask.dtype == np.dtype(np.uint8)
            assert mask.shape == values.shape
            valid = mask.astype(np.bool_)
            assert bool(np.all(np.isfinite(values[valid])))
            assert bool(np.all(values[~valid] == 0.0))
            if reference.array_id in _STRUCTURAL_ARRAY_IDS:
                assert bool(np.all(mask == 1))

    assert np.array_equal(restored.lag_available, loaded.arrays["f16_lag_valid"].astype(bool))
    for attribute, mask_id in _MEASUREMENT_MASKS:
        values = getattr(restored, attribute)
        mask = loaded.arrays[mask_id].astype(bool)
        assert bool(np.all(np.isfinite(values[mask])))
        assert bool(np.all(np.isnan(values[~mask])))
    return restored


def test_sparse_count_scales_stay_partial_in_published_artifact(tmp_path: Path) -> None:
    """2.4 s record masks only 0.5 s and 1.0 s; supported scales remain numeric."""
    session = simulate_session(
        out_dir=tmp_path / "syn-bad-8k",
        profile="bad",
        duration_s=_SPARSE_DURATION_S,
        sample_rate_hz=_SPARSE_FS_HZ,
        seed=6022,
    )
    before = _raw_hashes(session)
    first, second, loaded, files = _publish_twice(_recipe(), session, _load(session), _SPARSE_FS_HZ)
    f16 = loaded.bundle.families[_F16_INDEX]
    declared = _recipe().families[_F16_INDEX]

    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f16, declared, loaded)
    _assert_status_reason(f16)
    assert f16.status is Status.PARTIAL
    assert INSUFFICIENT_COUNT_WINDOWS in f16.reason_codes
    assert f16.window.kind == "record"
    assert f16.window.duration_s == pytest.approx(_SPARSE_DURATION_S)
    assert f16.window.overlap_fraction == 0.0
    _assert_metadata(loaded)

    arrays = loaded.arrays
    # Full-span F16-1 arithmetic gives [119, 23, 4, 2] for 2.4 s. The real seam
    # also removes low-pass phase halos, so this measured artifact has [112, 22, 3, 1].
    # Both are below ten only at the two long scales; no tolerance is widened.
    assert arrays["f16_count_window_count"].tolist() == list(_SPARSE_SEAM_COUNT_WINDOWS)
    assert arrays["f16_count_window_valid"].tolist() == [1, 1, 0, 0]
    assert max(arrays["f16_count_window_count"][2:]) < MINIMUM_COUNT_WINDOWS
    assert arrays["f16_fano_factor_valid"].tolist() == [1, 1, 0, 0]
    assert bool(np.all(np.isfinite(arrays[COUNT_MEAN_NAME][:2])))
    assert bool(np.all(np.isfinite(arrays[FANO_FACTOR_NAME][:2])))
    assert bool(np.all(arrays[COUNT_MEAN_NAME][2:] == 0.0))
    assert bool(np.all(arrays[FANO_FACTOR_NAME][2:] == 0.0))

    restored = _assert_persisted_round_trip(loaded, f16)
    assert bool(np.all(np.isnan(restored.count_mean[2:])))
    assert bool(np.all(np.isnan(restored.count_variance[2:])))
    assert bool(np.all(np.isnan(restored.fano_factor[2:])))


def test_alternating_residual_reproduces_supported_lags_and_masks_lag_above_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At 6.4 kHz, r[n]=(-1)^n gives -1/+1 ACF until 0.5 s exceeds support."""
    samples = round(_ACF_FS_HZ * _ACF_DURATION_S)
    times = np.arange(samples, dtype=np.float64) / _ACF_FS_HZ
    alternating = np.where(np.arange(samples) % 2 == 0, 1.0, -1.0)
    session = _write_session(
        tmp_path / "syn-alternating",
        alternating,
        _reference(_ACF_FS_HZ, samples),
    )
    before = _raw_hashes(session)
    measured = _capture_f16(monkeypatch)
    first, second, loaded, files = _publish_twice(_recipe(), session, _load(session), _ACF_FS_HZ)
    f16 = loaded.bundle.families[_F16_INDEX]
    declared = _recipe().families[_F16_INDEX]

    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f16, declared, loaded)
    _assert_status_reason(f16)
    assert f16.status is Status.PARTIAL
    assert LAG_ABOVE_SUPPORT in f16.reason_codes
    assert len(measured) == 1
    assert times[1] - times[0] == pytest.approx(1.0 / _ACF_FS_HZ)
    _assert_metadata(loaded)

    arrays = loaded.arrays
    # 6.4 kHz rounds declared lags to [1, 6, 64, 128, 640, 3200] samples.
    # A qualified segment of 1660 samples therefore has [1659, 1654, 1596,
    # 1532, 1020, 0] pairs. Products are -1 at odd lag 1 and +1 at even lags.
    assert arrays["f16_lag_s"].tolist() == list(LAGS_S)
    assert arrays["f16_pair_count"].tolist() == [1659, 1654, 1596, 1532, 1020, 0]
    assert min(arrays["f16_pair_count"][:5]) >= MINIMUM_PAIRS
    assert arrays["f16_lag_valid"].tolist() == [1, 1, 1, 1, 1, 0]
    np.testing.assert_allclose(
        arrays[AUTOCORRELATION_NAME][:5],
        [-1.0, 1.0, 1.0, 1.0, 1.0],
        rtol=0.0,
        atol=1e-12,
    )
    assert arrays[AUTOCORRELATION_NAME][5] == 0.0
    assert arrays["f16_recurrence_rate"][0].tolist() == [0.0, 0.0, 1.0]

    restored = _assert_persisted_round_trip(loaded, f16)
    np.testing.assert_allclose(restored.autocorrelation[:5], [-1.0, 1.0, 1.0, 1.0, 1.0], atol=1e-12)
    assert bool(np.isnan(restored.autocorrelation[5]))
    assert restored.pair_count[-1] == 0
    assert np.array_equal(restored.lag_available, measured[0].lag_available)


def test_long_record_supports_all_scales_and_reports_clustered_fano(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """12 s at 10 kHz reaches every count-window gate; clustered Fano is hand-derived."""
    samples = round(_LONG_FS_HZ * _LONG_DURATION_S)
    # Complete one-second windows are global indices 1..10. Their counts are
    # [5, 5, 1, 1, 1, 1, 1, 1, 1, 1], giving n=10, sum=18, sum(c²)=58.
    peaks = (
        1.30,
        1.31,
        1.32,
        1.33,
        1.34,
        2.30,
        2.31,
        2.32,
        2.33,
        2.34,
        3.20,
        4.20,
        5.20,
        6.20,
        7.20,
        8.20,
        9.20,
        10.20,
    )
    session = _write_session(
        tmp_path / "syn-clustered-fano",
        _smooth_record(_LONG_FS_HZ, samples, peaks),
        _reference(_LONG_FS_HZ, samples),
    )
    before = _raw_hashes(session)
    measured = _capture_f16(monkeypatch)
    first, second, loaded, files = _publish_twice(_recipe(), session, _load(session), _LONG_FS_HZ)
    f16 = loaded.bundle.families[_F16_INDEX]
    declared = _recipe().families[_F16_INDEX]

    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f16, declared, loaded)
    _assert_status_reason(f16)
    assert f16.status is Status.PARTIAL
    assert f16.reason_codes == ("gaps_present",)
    assert len(measured) == 1
    _assert_metadata(loaded)

    arrays = loaded.arrays
    # 10 kHz × 12 s supplies [593, 118, 22, 10] complete windows after the
    # declared phase-qualified support. All ten one-second windows clear 10.
    assert arrays["f16_count_window_count"].tolist() == list(_LONG_COUNT_WINDOWS)
    assert arrays["f16_count_window_valid"].tolist() == [1, 1, 1, 1]
    assert arrays["f16_fano_factor_valid"].tolist() == [1, 1, 1, 1]
    assert arrays["f16_lag_valid"].tolist() == [1, 1, 1, 1, 1, 1]
    assert int(np.min(arrays["f16_pair_count"])) >= MINIMUM_PAIRS
    # mean=18/10=9/5; s²=(58-10*(9/5)²)/9=128/45; Fano=(128/45)/(9/5)=128/81.
    assert arrays[COUNT_MEAN_NAME][-1] == pytest.approx(9.0 / 5.0)
    assert arrays[COUNT_VARIANCE_NAME][-1] == pytest.approx(128.0 / 45.0)
    assert arrays[FANO_FACTOR_NAME][-1] == pytest.approx(128.0 / 81.0)
    assert arrays[FANO_FACTOR_NAME][-1] > 1.0

    restored = _assert_persisted_round_trip(loaded, f16)
    assert restored.count_window_count.tolist() == list(_LONG_COUNT_WINDOWS)
    assert bool(np.all(restored.fano_available))
    assert restored.fano_factor[-1] == pytest.approx(128.0 / 81.0)


def test_poisson_like_window_counts_have_fano_near_one(tmp_path: Path) -> None:
    """Twelve occupied 0.1 s windows over 118 windows give hand-derived Fano 106/117."""
    samples = round(_LONG_FS_HZ * _LONG_DURATION_S)
    # One event in each of twelve distinct complete 0.1-s windows.
    peaks = tuple(0.5 + 0.8 * index for index in range(12))
    session = _write_session(
        tmp_path / "syn-poisson-fano",
        _smooth_record(_LONG_FS_HZ, samples, peaks),
        _reference(_LONG_FS_HZ, samples),
    )
    before = _raw_hashes(session)
    first, second, loaded, files = _publish_twice(_recipe(), session, _load(session), _LONG_FS_HZ)
    f16 = loaded.bundle.families[_F16_INDEX]
    declared = _recipe().families[_F16_INDEX]

    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f16, declared, loaded)
    _assert_status_reason(f16)
    assert f16.status is Status.PARTIAL
    assert f16.reason_codes == ("gaps_present",)
    _assert_metadata(loaded)

    arrays = loaded.arrays
    # For n=118 windows, twelve counts are 1 and 106 are 0. With ddof=1:
    # mean=12/118, s²=(12-118*(12/118)²)/117, Fano=s²/mean=106/117.
    assert arrays["f16_count_window_count"].tolist() == list(_LONG_COUNT_WINDOWS)
    assert arrays["f16_fano_factor_valid"].tolist() == [1, 1, 1, 1]
    assert arrays[FANO_FACTOR_NAME][1] == pytest.approx(106.0 / 117.0)
    assert arrays[FANO_FACTOR_NAME][1] == pytest.approx(0.905982905982906, abs=1e-12)

    restored = _assert_persisted_round_trip(loaded, f16)
    assert restored.fano_factor[1] == pytest.approx(106.0 / 117.0)


def test_unavailable_phase_root_publishes_empty_f16_domains(tmp_path: Path) -> None:
    """Constant CH2 removes phase reference; F16 publishes no arrays, table, or summaries."""
    samples = round(_SPARSE_FS_HZ * _SPARSE_DURATION_S)
    session = _write_session(
        tmp_path / "syn-no-phase",
        _smooth_record(_SPARSE_FS_HZ, samples),
        np.zeros(samples, dtype=np.float64),
    )
    before = _raw_hashes(session)
    first, second, loaded, files = _publish_twice(_recipe(), session, _load(session), _SPARSE_FS_HZ)
    f16 = loaded.bundle.families[_F16_INDEX]
    declared = _recipe().families[_F16_INDEX]

    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f16, declared, loaded)
    _assert_status_reason(f16)
    assert f16.status is Status.UNAVAILABLE
    assert f16.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    assert f16.array_refs == ()
    assert f16.table_refs == ()
    assert f16.comparison_summary == ()
    assert not any(name.startswith("f16_") for name in loaded.arrays)
    assert MEMORY_TABLE_ID not in loaded.tables
    assert f16.support.observation_count == 0
