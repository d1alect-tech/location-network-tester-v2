"""F12 E2E-reduced: сквозное измерение declared-scale куртозиса по qualified span.

F12 (``f12_spectral_kurtosis``, slot 11) меряет спектральную куртозису по longest
phase-qualified span записи. Корень фазы из ``compute_phase_cycles`` не покрывает
запись целиком: низкочастотный halo фильтра фазы съедает по три периода сети у
каждого края. ``sample_count`` публикует всю запись, ``qualified_sample_count`` —
измеренный span, а ``qualified_spans`` исключает из span ещё и root-event gaps,
поэтому F12 не сшивает разрыв и не вносит в record-spectrum null выдуманное
содержание.

Первый тест доказывает измерение на стандартном профиле bad, у которого замок фазы
наступает на период позже, второй — на чистой сильной ссылке 50 Гц. Оба идут
через реальный seam и публикуют воспроизводимый артефакт. Тесты не выводят
калибровку, соответствие стандарту, неопределённость GUM или причинность;
структурное отсутствие несёт код причины, никогда ноль или NaN.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, characterization_bundle, load_bundle
from lnt.characterization.f12_arrays import decode_f12_result
from lnt.characterization.f12_bundle import build_f12_family
from lnt.characterization.f12_contract import (
    F12_ID,
    F12_INDEX,
    METHOD,
    MINIMUM_FRAMES,
    NO_SIGNIFICANT_BIN,
    OVERLAP_FRACTION,
    PHASE_REFERENCE_UNAVAILABLE,
    SEGMENT_SAMPLES,
    SURROGATE_COUNT,
)
from lnt.characterization.phase import compute_phase_cycles
from lnt.context.json_codec import decode_object
from lnt.simulate import simulate_session
from lnt.types import SyntheticTruth
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    import pytest

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.analysis_v2.types import AnalysisRunResult
    from lnt.characterization.bundle_codec import LoadedCharacterization
    from lnt.characterization.f12_result import F12Result
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.records import Band
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_F12_METHOD_VERSION = 1
_F12_ARRAY_PREFIX = "f12_"
_FS_HZ = 500_000.0
_DURATION_S = 2.4
_SEED = 6022
# Длина записи: 500 000 отсчётов/с × 2,4 с — ровно 120 периодов сети.
_RECORD_SAMPLES = 1_200_000
_CYCLE_SAMPLES = 10_000
_NOMINAL_CYCLES = 120
# Низкочастотный halo фильтра фазы съедает по три периода у каждого края, так
# что квалифицированный span чистой ссылки равен 114 полным циклам = 1 140 000.
_HALO_CYCLES = 3
_CLEAN_RETAINED_CYCLES = _NOMINAL_CYCLES - 2 * _HALO_CYCLES
_CLEAN_QUALIFIED_SAMPLES = _CLEAN_RETAINED_CYCLES * _CYCLE_SAMPLES
# У профиля bad сама 50-герцевая ссылка CH2 возмущена событием, поэтому замок фазы
# наступает на один период позже: 113 удержанных циклов, а не 114.
_BAD_RETAINED_CYCLES = _CLEAN_RETAINED_CYCLES - 1
_BAD_QUALIFIED_SAMPLES = _BAD_RETAINED_CYCLES * _CYCLE_SAMPLES
_REFERENCE_HZ = 50.0
_REFERENCE_AMPLITUDE_V = 6.0
_REFERENCE_PHASE_RAD = 0.2
_TONE_HZ = 1_000.0
# У чистых синусов нет иголок, кольца, асинхронной части и огибающей, поэтому
# объявленная истина — нули во всех полях SyntheticTruth: клиппирование
# неприменимо по происхождению, и F12 не отказывает по CLIPPED до гарда.
_TRUTH_FIELDS = tuple(field.name for field in fields(SyntheticTruth))
# Три объявленных scale-оси F12: измеренный результат несёт все три, даже когда
# ни один significant bin не выжил.
_SCALE_AXES = ("segment_samples", "frame_count", "scale_available")


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f12 e2e reduced")
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


def _publish_twice(
    recipe: CharacterizationRecipe, session: Path, channels: tuple[np.ndarray, np.ndarray]
) -> tuple[AnalysisRunResult, AnalysisRunResult, LoadedCharacterization, dict[str, bytes]]:
    first = run_characterization(recipe, session, channels, _FS_HZ)
    files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(files)
    second = run_characterization(recipe, session, channels, _FS_HZ)
    return first, second, loaded, files


def _write_reference_session(path: Path, ch1: np.ndarray, ch2: np.ndarray) -> Path:
    """Записать сессию с объявленной synthetic_truth и двумя каналами."""
    write_manifest(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest["synthetic_truth"] = dict.fromkeys(_TRUTH_FIELDS, 0.0)
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    np.save(path / "ch1.npy", ch1.astype(np.float32))
    np.save(path / "ch2.npy", ch2.astype(np.float32))
    return path


def _clean_record() -> tuple[np.ndarray, np.ndarray]:
    """Ссылка 50 Гц на CH2 плюс тихий тон 1 кГц на CH1."""
    angle = 2.0 * np.pi * np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ
    return (
        0.1 * np.sin(_TONE_HZ * angle),
        _REFERENCE_AMPLITUDE_V * np.sin(_REFERENCE_HZ * angle + _REFERENCE_PHASE_RAD),
    )


def _capture_f12(monkeypatch: pytest.MonkeyPatch) -> list[F12Result]:
    measured: list[F12Result] = []
    persist = build_f12_family

    def capture(
        result: F12Result,
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

    monkeypatch.setattr(characterization_bundle, "build_f12_family", capture)
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


def _expected_frames(qualified: int) -> list[int]:
    """Полные STFT frames каждого declared scale: 1 + (N - L) // hop при 50 % overlap."""
    return [
        1 + (qualified - segment) // round(segment * (1.0 - OVERLAP_FRACTION))
        for segment in SEGMENT_SAMPLES
    ]


def _assert_envelope(
    f12: FamilyResult,
    declared: CharacterizationFamily,
    loaded: LoadedCharacterization,
    qualified: int,
) -> None:
    """Конверт F12: объявленная идентичность, измеренный status, полный support."""
    assert f12.family_id == declared.id == F12_ID == "f12_spectral_kurtosis"
    assert f12.method == declared.method == METHOD
    assert f12.method_version == declared.method_version == _F12_METHOD_VERSION
    assert f12.signal_plane == "ch1_scope_input"
    assert f12.status is not Status.UNAVAILABLE
    assert PHASE_REFERENCE_UNAVAILABLE not in f12.reason_codes
    assert f12.qc.reason_codes == f12.reason_codes
    assert f12.window.kind == "record"
    assert f12.window.duration_s == _DURATION_S
    assert f12.window.overlap_fraction == 0.0
    assert len(loaded.bundle.families) == 18
    assert f12.table_refs
    assert any(name.startswith(_F12_ARRAY_PREFIX) for name in (*loaded.arrays, *loaded.tables))
    # Support публикует всю запись и ровно измеренный qualified span.
    assert f12.support.sample_count == _RECORD_SAMPLES
    assert f12.support.observation_count == qualified
    assert f12.support.missing_count == _RECORD_SAMPLES - qualified
    assert f12.support.stored_count == qualified
    # Персистентная форма восстанавливается в engine-результат без потерь.
    assert decode_f12_result(f12, loaded.arrays, loaded.tables).status is f12.status


def _assert_measured(result: F12Result, qualified: int) -> None:
    """Движок меряет по qualified span; отсутствие bin объявлено, а не выдумано."""
    assert result.status is not Status.UNAVAILABLE
    assert PHASE_REFERENCE_UNAVAILABLE not in result.reason_codes
    assert result.sample_count == _RECORD_SAMPLES
    assert result.qualified_sample_count == qualified
    # Полные frames выведены из объявленных scales и длины измеренного span.
    assert result.segment_samples.tolist() == list(SEGMENT_SAMPLES)
    assert result.frame_count.tolist() == _expected_frames(qualified)
    # Даже самый короткий declared scale набирает minimum_frames, поэтому
    # поддержку получают все четыре, а не усечённый поднабор.
    assert min(result.frame_count.tolist()) >= MINIMUM_FRAMES
    assert result.scale_available.tolist() == [True] * len(SEGMENT_SAMPLES)
    assert result.analyzed_scale_count == len(SEGMENT_SAMPLES)
    assert result.surrogate_count == SURROGATE_COUNT
    # Ни один significant bin не выжил: четыре домена пусты по объявленной
    # причине, а не заполнены нулями, и полоса не выдумана.
    axes = ("segment_samples", "frame_count", "scale_available")
    assert [getattr(result, name).size for name in axes] == [len(SEGMENT_SAMPLES)] * 3
    bins = ("frequencies_hz", "scale_index", "spectral_kurtosis", "adjusted_p_value")
    assert [getattr(result, name).size for name in bins] == [0, 0, 0, 0]
    assert result.reason_codes == (NO_SIGNIFICANT_BIN,)
    assert result.candidate_count > 0
    assert result.significant_bin_count == 0
    assert result.stored_significant_bin_count == 0
    assert result.maximum_spectral_kurtosis is not None
    assert result.maximum_spectral_kurtosis > 0.0
    assert result.selected_scale_index is None


def _assert_halo_limits_the_span(
    ch2: np.ndarray, recipe: CharacterizationRecipe, retained: int
) -> None:
    """Корень фазы валиден целиком, но удерживает меньше периодов, чем запись."""
    phase = compute_phase_cycles(
        ch2, sample_rate_hz=_FS_HZ, settings=recipe.phase, resources=recipe.resource_limits
    )
    assert phase.status is Status.AVAILABLE
    assert phase.reason_code is None
    assert bool(np.all(phase.cycle_valid))
    assert phase.cycle_start_samples.size == retained
    assert float(phase.cycle_start_samples[0]) > 0.0
    assert float(phase.cycle_end_samples[-1]) < _RECORD_SAMPLES


def _measure_through_seam(
    session: Path,
    monkeypatch: pytest.MonkeyPatch,
    qualified: int,
    retained: int,
) -> None:
    """Прогнать реальный seam дважды и сверить F12 с analytic qualified span."""
    before = _raw_hashes(session)
    recipe = _recipe()
    channels = _load(session)
    measured = _capture_f12(monkeypatch)
    first, second, loaded, files = _publish_twice(recipe, session, channels)

    _assert_cache_and_source(first, second, files, session, before)
    f12 = loaded.bundle.families[F12_INDEX]
    _assert_envelope(f12, recipe.families[F12_INDEX], loaded, qualified)
    assert len(measured) == 1
    _assert_measured(measured[0], qualified)
    _assert_halo_limits_the_span(channels[1], recipe, retained)


def test_standard_profile_measures_f12_over_the_qualified_span(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Синтетика 500 кГц: F12 меряет, домены опубликованы, артефакт воспроизводим."""
    session = simulate_session(
        out_dir=tmp_path / "syn-bad-500k",
        profile="bad",
        duration_s=_DURATION_S,
        sample_rate_hz=_FS_HZ,
        seed=_SEED,
    )

    _measure_through_seam(session, monkeypatch, _BAD_QUALIFIED_SAMPLES, _BAD_RETAINED_CYCLES)


def test_clean_fifty_hertz_reference_measures_the_full_retained_span(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Чистая сильная ссылка 50 Гц меряет все 114 удержанных периодов сети."""
    session = _write_reference_session(tmp_path / "syn-clean-reference", *_clean_record())

    _measure_through_seam(session, monkeypatch, _CLEAN_QUALIFIED_SAMPLES, _CLEAN_RETAINED_CYCLES)
