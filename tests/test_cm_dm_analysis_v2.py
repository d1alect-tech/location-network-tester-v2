"""T9: CM/DM-ветвь analysis_v2 — диспетчеризация оркестратора, движок, проекция."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store import AnalysisRecipe, CodeIdentity
from lnt.analysis_v2 import (
    AnalysisOrchestrator,
    BranchContext,
    DefaultAnalysisEngine,
    SessionKind,
)
from lnt.cm_dm.analysis import (
    CM_DM_SPECTRUM_FILENAME,
    CSV_HEADER,
    analyze_cm_dm_session,
    cm_dm_analysis_to_payload,
)
from lnt.errors import InputError
from lnt.scope_io import NEVER_CANCELLED
from tests.cm_dm_fixtures import build_probe_pair_session

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_CANONICAL_KEYS = frozenset(
    {
        "schema_version",
        "session_id",
        "profile",
        "source",
        "session_type",
        "sample_rate_hz",
        "duration_s",
        "needle",
        "line_quality",
        "spectrum",
        "ch1_input_reference",
    }
)


def _recipe() -> AnalysisRecipe:
    return AnalysisRecipe.from_mapping(
        {
            "schema_version": 1,
            "mode": "standard",
            "channels": ["ch1", "ch2"],
            "band_grid": {"low_hz": 10.0, "high_hz": 400.0, "grid_hz": 1.0},
            "welch": {
                "window": "hann_periodic",
                "segment_samples": 64,
                "overlap_fraction": 0.5,
                "detrend": "constant",
                "scaling": "density",
                "average": "mean",
            },
            "spectrogram": {"enabled": True, "segment_samples": 64, "overlap_fraction": 0.5},
            "events": {"enabled": True, "threshold_sigma": 5.0},
            "bands": {"edges_hz": [10.0, 100.0, 400.0]},
            "correction": {"method": "none"},
            "uncertainty": {"enabled": False, "confidence_level": 0.95, "bootstrap_samples": 0},
        }
    )


def _rewrite_manifest(session_dir: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    path = session_dir / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _orchestrator() -> AnalysisOrchestrator:
    return AnalysisOrchestrator(
        engine=DefaultAnalysisEngine(),
        code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
    )


def test_orchestrator_dispatches_cm_dm_kind(tmp_path: Path) -> None:
    # Given: a synthetic probe-pair cm_dm session and the real v2 engine.
    session = build_probe_pair_session(tmp_path / "cm-dm", duration_s=0.05)

    # When: the orchestrator runs with legacy projection enabled.
    result = _orchestrator().run(session, _recipe())

    # Then: the artifact store holds metrics.json with the cm_dm section plus the csv.
    assert result.failures == ()
    payload = json.loads((result.artifact_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "cm_dm" in payload
    assert (result.artifact_dir / CM_DM_SPECTRUM_FILENAME).is_file()
    # And: projection lands both files at the session root like the v1 path.
    projected = json.loads((session / "metrics.json").read_text(encoding="utf-8"))
    assert "cm_dm" in projected
    assert (session / CM_DM_SPECTRUM_FILENAME).is_file()


def test_engine_cm_dm_branch_matches_v1_output(tmp_path: Path) -> None:
    # Given: a probe-pair session whose v1 reference payload fixes the contract keys.
    session = build_probe_pair_session(tmp_path / "engine", duration_s=0.05)
    reference = set(cm_dm_analysis_to_payload(analyze_cm_dm_session(session)))
    context = BranchContext(
        kind=SessionKind.CM_DM,
        session_dir=session,
        sample_rate_hz=2_000_000.0,
        channels=tuple(
            np.load(session / f"{name}.npy", mmap_mode="r", allow_pickle=False)
            for name in ("ch1", "ch2")
        ),
        recipe=_recipe(),
        cancellation=NEVER_CANCELLED,
    )

    # When: the engine runs the cm_dm branch.
    output = DefaultAnalysisEngine().run_branch("cm_dm", context)

    # Then: metrics.json parses to exactly the canonical contract plus the cm_dm section.
    emitted = json.loads(output.files["metrics.json"].decode(encoding="utf-8"))
    assert set(emitted) == _CANONICAL_KEYS | {"cm_dm"}
    assert set(emitted) == reference
    # And: the spectrum csv carries the same header as write_cm_dm_analysis writes.
    csv_lines = output.files[CM_DM_SPECTRUM_FILENAME].decode(encoding="utf-8").splitlines()
    assert csv_lines[0] == CSV_HEADER


def test_calibration_manifest_still_rejected(tmp_path: Path) -> None:
    # Given: a probe-pair session whose manifest declares the calibration type.
    session = build_probe_pair_session(tmp_path / "calibration", duration_s=0.05)
    _rewrite_manifest(
        session,
        lambda payload: payload.update({"session_type": "cm_dm_calibration"}),
    )

    # When / Then: rejection surfaces as the typed input error, not a raw ValueError.
    with pytest.raises(InputError, match="тип сессии"):
        _orchestrator().run(session, _recipe())
