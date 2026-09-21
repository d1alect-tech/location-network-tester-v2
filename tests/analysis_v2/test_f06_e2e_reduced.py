"""F06 E2E-reduced через реальный seam: аналитическая AM-истина, cache, raw-хеши.

Истина не выведена из движка: запись это AM с объявленными глубиной и темпом,
поэтому огибающая обязана лечь на 1 + m*cos(2*pi*fm*t), мгновенная частота — на
несущую, а развёрнутая фаза — расти. Позиции хранимых отсчётов восстановлены из
опубликованной поддержки и объявленного правила ``even_floor_index``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, Unit, load_bundle
from lnt.context.json_codec import decode_object
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 500_000.0
_DURATION_S = 0.5
_CARRIER_HZ = 30_000.0
_RATE_HZ = 500.0
_DEPTH = 0.5
_NOISE_V = 1e-4
_SEED = 6022
_F06_INDEX = 5
_RECORD_SAMPLES = round(_FS_HZ * _DURATION_S)
_TRAJECTORY_IDS = ("f06_envelope_v", "f06_phase_rad", "f06_frequency_hz")
_TONE_LOW_HZ = 20_000.0
_TONE_HIGH_HZ = 32_000.0


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f06 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _session(path: Path, measured: np.ndarray) -> Path:
    """Пишет сессию: измеренный канал задаёт тест, CH2 остаётся чистой опорой 50 Гц."""
    write_manifest(path)
    times = np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ
    np.save(path / "ch1.npy", measured.astype(np.float32))
    np.save(path / "ch2.npy", (6.0 * np.sin(2.0 * np.pi * 50.0 * times)).astype(np.float32))
    return path


def _am_record() -> np.ndarray:
    """AM: огибающая 1 + m*cos(2*pi*fm*t) на несущей 30 кГц плюс слабый белый шум."""
    times = np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ
    envelope = 1.0 + _DEPTH * np.cos(2.0 * np.pi * _RATE_HZ * times)
    noise = np.random.default_rng(_SEED).standard_normal(_RECORD_SAMPLES) * _NOISE_V
    return envelope * np.cos(2.0 * np.pi * _CARRIER_HZ * times) + noise


def _two_tone_record() -> np.ndarray:
    """Два тона в полосе: условие Бедросяна нарушено, огибающая бьётся разностной."""
    times = np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ
    return np.cos(2.0 * np.pi * _TONE_LOW_HZ * times) + np.cos(2.0 * np.pi * _TONE_HIGH_HZ * times)


def _load(session: Path) -> tuple[np.ndarray, np.ndarray]:
    ch1 = np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False)
    ch2 = np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False)
    return ch1, ch2


def _raw_hashes(session: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((session / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "ch2.npy", "manifest.json")
    }


def _stored_limit(recipe: CharacterizationRecipe) -> int:
    raw = recipe.families[_F06_INDEX].value("maximum_stored_samples")
    assert isinstance(raw, int)
    return raw


def _positions(family: FamilyResult, limit: int) -> np.ndarray:
    """Кандидаты объявленного правила, попавшие в опубликованный спан."""
    start = round(family.support.start_s * _FS_HZ)
    stop = round(family.support.end_s * _FS_HZ)
    candidates = np.floor(np.arange(limit) * _RECORD_SAMPLES / limit).astype(np.int64)
    return candidates[(candidates >= start) & (candidates < stop)]


def test_am_record_publishes_trajectories_matching_the_declared_law(tmp_path: Path) -> None:
    session = _session(tmp_path / "syn-am-seed6022", _am_record())
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (first.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f06 = loaded.bundle.families[_F06_INDEX]

    assert first.cache_hit is False
    assert f06.family_id == "f06_modulation_trajectories"
    assert f06.status is Status.AVAILABLE
    assert f06.reason_codes == ()
    assert {reference.array_id for reference in f06.array_refs} == set(_TRAJECTORY_IDS)
    assert f06.signal_plane == "ch1_scope_input"
    assert f06.filter.kind == "butterworth_sos"
    assert f06.filter.phase == "zero"
    assert f06.units == (Unit.V, Unit.RAD, Unit.HZ)
    assert f06.window.kind == "record"

    support = f06.support
    assert support.sample_count == _RECORD_SAMPLES
    start = round(support.start_s * _FS_HZ)
    stop = round(support.end_s * _FS_HZ)
    assert support.observation_count == stop - start
    assert support.missing_count == _RECORD_SAMPLES - support.observation_count
    assert 0 < support.stored_count < support.observation_count
    assert support.selection_rule == "even_floor_index"

    envelope = loaded.arrays["f06_envelope_v"]
    phases = loaded.arrays["f06_phase_rad"]
    frequencies = loaded.arrays["f06_frequency_hz"]
    assert envelope.shape == (support.stored_count,)
    assert phases.shape == envelope.shape
    assert frequencies.shape == envelope.shape

    positions = _positions(f06, _stored_limit(recipe))
    assert positions.size == support.stored_count
    times = positions.astype(np.float64) / _FS_HZ

    expected = 1.0 + _DEPTH * np.cos(2.0 * np.pi * _RATE_HZ * times)
    assert float(np.max(np.abs(envelope - expected))) <= 1e-3 * float(np.max(expected))
    assert float(np.max(np.abs(frequencies - _CARRIER_HZ))) <= 1e-4 * _CARRIER_HZ
    assert bool(np.all(np.diff(phases) > 0.0))
    increments = np.diff(phases) - 2.0 * np.pi * _CARRIER_HZ * np.diff(times)
    assert float(np.max(np.abs(increments))) <= 1e-2

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert _raw_hashes(session) == before


def test_two_tone_record_publishes_the_declared_refusal_without_arrays(tmp_path: Path) -> None:
    """Отказ обязан дойти до артефакта объявленным кодом, без выдуманных траекторий."""
    session = _session(tmp_path / "syn-two-tone", _two_tone_record())
    recipe = _recipe()
    ch1, ch2 = _load(session)

    result = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f06 = loaded.bundle.families[_F06_INDEX]

    assert result.cache_hit is False
    assert f06.status is Status.UNAVAILABLE
    assert f06.reason_codes == ("multiple_components",)
    assert f06.array_refs == ()
    assert f06.comparison_summary == ()
    assert f06.support.observation_count == 0
    assert not any(name.startswith("f06_") for name in loaded.arrays)
