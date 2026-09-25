"""F14 E2E-reduced: измеренный отказ стандартных профилей и аналитический AVAILABLE.

Стандартная синтетика намеренно асимметрична: CH1 содержит иголки, а CH2 только
50 Гц. Поэтому обратный инвентарь CH2 пуст, а окна CH1 пересекают dead-time
исключения плотных иголок. ``bad`` и ``quiet`` честно UNAVAILABLE. Отдельная
пара последовательностей импульсов даёт 25 полных триггеров в каждом направлении.
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
from lnt.characterization.f14_bundle import build_f14_family
from lnt.context.json_codec import decode_object
from lnt.simulate import simulate_session
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.bundle_codec import LoadedCharacterization
    from lnt.characterization.f14_result import F14DirectionResult, F14Result
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.records import Band
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 500_000.0
_DURATION_S = 2.4
_SEED = 6022
_F14_INDEX = 13
_F14_ID = "f14_cross_channel_event_association"
_F14_METHOD = "bidirectional_event_triggered_cross_channel_association"
_METHOD_VERSION = 1
_STANDARD_REASONS = ("gaps_present", "insufficient_triggers", "window_truncated")
_LAG_SIGN_CONVENTION = "target_after_trigger_positive"
_CLAIM_BOUNDARY = (
    "temporal association only; physical lead, source, coupling, causality, and utility "
    "are not established"
)
_ARRAY_IDS = (
    "f14_direction_index",
    "f14_relative_time_s",
    "f14_cycle_shift_offsets",
    "f14_mean_waveform_v",
    "f14_event_probability",
    "f14_nearest_lag_s",
    "f14_baseline_probability",
    "f14_baseline_low",
    "f14_baseline_high",
)
_ANALYTIC_FS_HZ = 8_000.0
_ANALYTIC_SAMPLES = 19_200
_EVENT_COUNT = 25
_EVENT_START_S = 0.10
_EVENT_PERIOD_S = 0.08
_LAG_S = 0.003


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f14 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _session(root: Path, profile: str) -> Path:
    return simulate_session(
        out_dir=root / f"syn-{profile}-500k",
        profile=profile,
        duration_s=_DURATION_S,
        sample_rate_hz=_FS_HZ,
        seed=_SEED,
    )


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


def _direction_counts(direction: F14DirectionResult) -> tuple[int, ...]:
    # Всего, граница, gap, усечение, квалифицировано, сохранено, опущено.
    return (
        direction.total_event_count,
        direction.boundary_trigger_count,
        direction.gap_crossing_trigger_count,
        direction.window_truncated_count,
        direction.qualified_trigger_count,
        direction.stored_trigger_count,
        direction.omitted_trigger_count,
    )


def _write_paired_impulse_session(path: Path) -> tuple[np.ndarray, np.ndarray]:
    write_manifest(path)
    rng = np.random.default_rng(_SEED)
    time = np.arange(_ANALYTIC_SAMPLES, dtype=np.float64) / _ANALYTIC_FS_HZ
    ch1 = rng.normal(0.0, 0.01, _ANALYTIC_SAMPLES)
    ch2 = 6.0 * np.sin(2.0 * np.pi * 50.0 * time + 0.4)
    ch2 += rng.normal(0.0, 0.01, _ANALYTIC_SAMPLES)
    trigger_samples = np.rint(
        (_EVENT_START_S + np.arange(_EVENT_COUNT) * _EVENT_PERIOD_S) * _ANALYTIC_FS_HZ
    ).astype(np.int64)
    lag_samples = round(_LAG_S * _ANALYTIC_FS_HZ)
    ch1[trigger_samples] += 5.0
    ch2[trigger_samples + lag_samples] += 30.0
    ch1 = ch1.astype(np.float32)
    ch2 = ch2.astype(np.float32)
    np.save(path / "ch1.npy", ch1)
    np.save(path / "ch2.npy", ch2)
    return ch1, ch2


def _assert_f14_identity(f14: FamilyResult, declared: CharacterizationFamily) -> None:
    """Слот 13 сохраняет frozen ID, метод и версию рецепта."""
    assert f14.family_id == declared.id == _F14_ID
    assert f14.method == declared.method == _F14_METHOD
    assert f14.method_version == declared.method_version == _METHOD_VERSION
    assert f14.signal_plane == "cross_channel_measured_planes"


def _assert_available_f14_domains(loaded: LoadedCharacterization) -> None:
    """Проверить оси, направления, лаги и декларативную границу F14."""
    f14 = loaded.bundle.families[_F14_INDEX]
    assert f14.status is Status.AVAILABLE
    assert f14.reason_codes == ()
    assert tuple(reference.array_id for reference in f14.array_refs) == _ARRAY_IDS
    assert f14.table_refs[0].table_id == "f14_direction_metadata"

    summaries = {item.name: float(item.value) for item in f14.comparison_summary}
    assert summaries["f14_relative_time_bins"] == 401.0
    assert summaries["f14_cycle_shift_count"] == 32.0
    assert summaries["f14_maximum_triggers_per_direction"] == 4096.0
    assert summaries["f14_omitted_trigger_count"] == 0.0

    arrays = loaded.arrays
    axis = arrays["f14_relative_time_s"]
    assert axis.shape == (401,)
    assert np.array_equal(axis, np.linspace(-0.02, 0.02, 401, dtype=np.float64))
    assert axis[0] == -0.02
    assert axis[200] == 0.0
    assert np.array_equal(arrays["f14_cycle_shift_offsets"], np.arange(1, 33, dtype=np.int64))
    assert arrays["f14_direction_index"].shape == (2,)
    assert arrays["f14_mean_waveform_v"].shape == (2, 401)
    assert arrays["f14_event_probability"].shape == (2, 401)
    assert arrays["f14_baseline_probability"].shape == (2, 32, 401)
    assert np.max(arrays["f14_event_probability"]) == 1.0
    assert np.array_equal(arrays["f14_nearest_lag_offsets"], np.asarray([0, 25, 50]))
    lags = arrays["f14_nearest_lag_s"]
    expected_lag = np.full(_EVENT_COUNT, _LAG_S, dtype=np.float64)
    assert np.array_equal(lags[:_EVENT_COUNT], expected_lag)
    assert np.array_equal(lags[_EVENT_COUNT:], -expected_lag)

    table = loaded.tables["f14_direction_metadata"]
    columns = {column.name: index for index, column in enumerate(table.columns)}
    assert table.row_count == table.stored_count == 2
    identities = tuple(
        (row[columns["trigger_channel"]], row[columns["response_channel"]]) for row in table.rows
    )
    assert identities == (("ch1", "ch2"), ("ch2", "ch1"))
    for row in table.rows:
        assert row[columns["total_event_count"]] == _EVENT_COUNT
        assert row[columns["qualified_trigger_count"]] == _EVENT_COUNT
        assert row[columns["stored_trigger_count"]] == _EVENT_COUNT
        assert row[columns["omitted_trigger_count"]] == 0
        assert row[columns["boundary_trigger_count"]] == 0
        assert row[columns["gap_crossing_trigger_count"]] == 0
        assert row[columns["window_truncated_count"]] == 0
        assert row[columns["lag_sign_convention"]] == _LAG_SIGN_CONVENTION
        assert row[columns["claim_boundary"]] == _CLAIM_BOUNDARY

    # 401 временных центров дают шаг 100 мкс. При 8 кГц это 0,8 отсчёта на
    # центр; округлённое окно ±20 мс поэтому занимает 321 отсчёт, не 401.
    relative_bins = round((0.02 - (-0.02)) / 0.0001) + 1
    window_samples = 2 * round(0.02 * _ANALYTIC_FS_HZ) + 1
    event_period_samples = round(_EVENT_PERIOD_S * _ANALYTIC_FS_HZ)
    assert relative_bins == 401
    assert window_samples == 321
    assert event_period_samples == 640
    assert event_period_samples > window_samples
    assert _EVENT_COUNT >= 20


@pytest.mark.parametrize(
    ("profile", "expected_counts"),
    [
        ("bad", ((927, 1, 907, 18, 1, 0, 1), (0, 0, 0, 0, 0, 0, 0))),
        ("quiet", ((241, 0, 233, 5, 3, 0, 3), (0, 0, 0, 0, 0, 0, 0))),
    ],
    ids=("bad", "quiet"),
)
def test_standard_profiles_publish_exact_unavailable_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    expected_counts: tuple[tuple[int, ...], tuple[int, ...]],
) -> None:
    """Пустой CH2-инвентарь и плотные CH1-исключения дают точный UNAVAILABLE."""
    session = _session(tmp_path, profile)
    before = _raw_hashes(session)
    recipe = _recipe()
    channels = _load(session)
    measured: list[F14Result] = []
    persist = build_f14_family

    def capture(
        result: F14Result,
        family: CharacterizationFamily,
        band: Band,
        *,
        record_duration_s: float,
    ) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
        measured.append(result)
        return persist(result, family, band, record_duration_s=record_duration_s)

    monkeypatch.setattr(characterization_bundle, "build_f14_family", capture)
    first = run_characterization(recipe, session, channels, _FS_HZ)
    first_files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(first_files)
    f14 = loaded.bundle.families[_F14_INDEX]
    declared = recipe.families[_F14_INDEX]

    assert first.cache_hit is False
    assert first.failures == ()
    assert len(loaded.bundle.families) == 18
    _assert_f14_identity(f14, declared)
    assert f14.status is Status.UNAVAILABLE
    assert f14.reason_codes == _STANDARD_REASONS
    assert f14.array_refs == ()
    assert f14.table_refs == ()
    assert f14.comparison_summary == ()
    assert not any(name.startswith("f14_") for name in loaded.arrays)
    assert "f14_direction_metadata" not in loaded.tables

    assert len(measured) == 1
    in_memory = measured[0]
    assert in_memory.status is Status.UNAVAILABLE
    assert in_memory.reason_codes == _STANDARD_REASONS
    assert in_memory.relative_time_s.size == 0
    assert in_memory.sample_count == 1_200_000
    assert in_memory.qualified_cycle_count == 0
    assert tuple(_direction_counts(item) for item in in_memory.directions) == expected_counts
    for direction in in_memory.directions:
        assert direction.stored_trigger_count == 0
        assert direction.omitted_trigger_count == direction.qualified_trigger_count
        assert direction.mean_waveform_v.size == 0
        assert direction.event_probability.size == 0
        assert direction.nearest_lag_s.size == 0
        assert direction.baseline_probability.size == 0

    second = run_characterization(recipe, session, channels, _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert _artifact_bytes(second.artifact_dir) == first_files
    assert _raw_hashes(session) == before


def test_analytic_paired_impulses_publish_available_f14(tmp_path: Path) -> None:
    """Две изолированные 25-импульсные последовательности дают лаги ±3 мс."""
    session = tmp_path / "analytic-paired-impulses"
    channels = _write_paired_impulse_session(session)
    before = _raw_hashes(session)
    recipe = _recipe()

    first = run_characterization(recipe, session, channels, _ANALYTIC_FS_HZ)
    first_files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(first_files)
    f14 = loaded.bundle.families[_F14_INDEX]
    declared = recipe.families[_F14_INDEX]

    assert first.cache_hit is False
    assert first.failures == ()
    _assert_f14_identity(f14, declared)
    _assert_available_f14_domains(loaded)

    second = run_characterization(recipe, session, channels, _ANALYTIC_FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert _artifact_bytes(second.artifact_dir) == first_files
    assert _raw_hashes(session) == before
