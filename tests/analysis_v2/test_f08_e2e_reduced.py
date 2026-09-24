"""F08 E2E-reduced через реальный seam: затухающий синус профиля даёт f_d/tau/zeta.

Истина аналитическая, не из движка: профиль ``bad-damped`` объявляет
``ring_f0_hz=22400`` и ``ring_q=16`` (``src/lnt/signals.py``), поэтому частота
звона обязана лечь на 22400 Гц, постоянная затухания — на ``q/(pi*f0)``, а
коэффициент затухания — на ``1/(2q)``. Тихий профиль не даёт ни одного
подогнанного события: FAMILY UNAVAILABLE объявленными кодами, без выдуманных
параметров фита.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, Unit, load_bundle
from lnt.context.json_codec import decode_object
from lnt.simulate import simulate_session

if TYPE_CHECKING:
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 500000.0
_DURATION_S = 2.4
_SEED = 6022
_F08_INDEX = 7
_RING_F0_HZ = 22400.0
_RING_Q = 16.0
_FITTED_IDS = (
    "f08_t_rise_s",
    "f08_v_peak_v",
    "f08_v2_s",
    "f08_n_zc",
    "f08_f_d_hz",
    "f08_tau_d_s",
    "f08_zeta",
    "f08_residual_fraction",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f08 e2e reduced")
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


def _summaries(family: FamilyResult) -> dict[str, float]:
    return {item.name: float(item.value) for item in family.comparison_summary}


def test_damped_profile_recovers_ringing_truth(tmp_path: Path) -> None:
    session = _session(tmp_path, "syn-bad-damped", "bad-damped")
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (first.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f08 = loaded.bundle.families[_F08_INDEX]

    assert first.cache_hit is False
    assert f08.family_id == "f08_transient_morphology"
    assert f08.status is Status.PARTIAL
    assert f08.reason_codes
    assert {reference.array_id for reference in f08.array_refs} == set(_FITTED_IDS)
    assert f08.signal_plane == "ch1_scope_input"
    assert f08.window.kind == "record"

    fitted = loaded.arrays["f08_f_d_hz"]
    taus = loaded.arrays["f08_tau_d_s"]
    zetas = loaded.arrays["f08_zeta"]
    assert fitted.size > 0
    assert fitted.shape == taus.shape == zetas.shape
    # Аналитическая истина профиля: f_d -> ring_f0, tau -> q/(pi*f0), zeta -> 1/(2q).
    assert abs(float(np.median(fitted)) - _RING_F0_HZ) / _RING_F0_HZ <= 0.02
    expected_tau = _RING_Q / (math.pi * _RING_F0_HZ)
    assert abs(float(np.median(taus)) - expected_tau) / expected_tau <= 0.05
    expected_zeta = 1.0 / (2.0 * _RING_Q)
    assert abs(float(np.median(zetas)) - expected_zeta) / expected_zeta <= 0.10
    for array_id in ("f08_v2_s",):
        unit = next(r.unit for r in f08.array_refs if r.array_id == array_id)
        assert unit is Unit.V2_S

    summaries = _summaries(f08)
    assert summaries["f08_fitted_event_count"] == float(fitted.size)
    assert summaries["f08_evaluated_event_count"] >= summaries["f08_fitted_event_count"]

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert _raw_hashes(session) == before


def test_quiet_profile_publishes_refusal_without_fitted_parameters(
    tmp_path: Path,
) -> None:
    """Тихая запись не даёт подогнанных событий: отказ кодами, без выдуманных параметров."""
    session = _session(tmp_path, "syn-quiet", "quiet")
    recipe = _recipe()
    ch1, ch2 = _load(session)

    result = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f08 = loaded.bundle.families[_F08_INDEX]

    assert result.cache_hit is False
    assert f08.status is Status.UNAVAILABLE
    assert f08.reason_codes
    declared = {
        "multimode",
        "single_exponential_poor",
        "too_few_samples",
        "below_snr",
        "clipped",
        "overlapping_events",
    }
    assert all(code in declared for code in f08.reason_codes)
    assert not any(name.startswith("f08_f_d_hz") for name in loaded.arrays)
