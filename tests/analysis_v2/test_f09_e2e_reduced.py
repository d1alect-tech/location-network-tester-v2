"""F09 E2E-reduced через реальный seam: инвентарь событий даёт переходы и ожидание.

Истина аналитическая, не из движка: профиль ``bad`` объявляет асинхронный поток
``async_rate_hz=120`` (``src/lnt/signals.py``), поэтому событий много, инвентарь
детектора отклоняет часть кандидатов мёртвым временем (``dead_time_overlap``) и
вся пачка лежит в одном кластере (``single_cycle_record``). Ряд ожиданий ``dt``
обязан быть непустым и неотрицательным, а матрица переходов — публиковаться
таблицей. Граница вывода закреплена: циклы одной записи не независимые повторы,
популяционный вывод отклонён (``method-notes-families-1-9.md:456-459``).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.context.json_codec import decode_object
from lnt.simulate import simulate_session

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 500000.0
_DURATION_S = 2.4
_SEED = 6022
_F09_INDEX = 8
_TABLE_ID = "f09_transitions"
_ARRAY_IDS = (
    "f09_dt_s",
    "f09_polarity_run_lengths",
    "f09_cluster_start_s",
    "f09_cluster_spread_s",
    "f09_cluster_sizes",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f09 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _session(root: Path) -> Path:
    return simulate_session(
        out_dir=root / "syn-bad-seed6022",
        profile="bad",
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


def test_dense_event_record_publishes_ordering_with_withheld_inference(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (first.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f09 = loaded.bundle.families[_F09_INDEX]

    assert first.cache_hit is False
    assert f09.family_id == "f09_event_ordering"
    assert f09.status is Status.PARTIAL
    # Мёртвое время и один кластер объявлены кодами, а не подменены значениями.
    assert "dead_time_overlap" in f09.reason_codes
    assert "single_cycle_record" in f09.reason_codes
    assert {reference.array_id for reference in f09.array_refs} == set(_ARRAY_IDS)
    assert f09.signal_plane == "ch1_scope_input"
    assert f09.window.kind == "record"

    dt = loaded.arrays["f09_dt_s"]
    assert dt.size > 0
    assert bool(np.all(dt >= 0.0))
    assert bool(np.all(np.isfinite(dt)))

    # Матрица переходов публикуется таблицей с объявленными колонками.
    assert _TABLE_ID in loaded.tables
    table = loaded.tables[_TABLE_ID]
    column_names = {column.name for column in table.columns}
    assert {"source_label", "target_label", "n_ij"} <= column_names

    # Граница вывода закреплена в артефакте: популяционный вывод отклонён.
    assert f09.inference.population_inference == "withheld"
    assert f09.inference.estimate_scope == "single_session_descriptive"

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert _raw_hashes(session) == before
