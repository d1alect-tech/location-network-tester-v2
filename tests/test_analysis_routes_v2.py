from __future__ import annotations

# ruff: noqa: TC003 - HTTP fixtures keep request contracts visible
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from lnt.analysis_store import (
    AnalysisRecipe,
    ArtifactInputs,
    ArtifactStore,
    CodeIdentity,
    NamedDigest,
)
from lnt.context.json_codec import JsonValue  # noqa: TC001 - fixture return type
from lnt.ui.app import create_app


def _recipe_payload() -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "mode": "standard",
        "channels": ["ch1"],
        "band_grid": {"low_hz": 10.0, "high_hz": 400.0, "grid_hz": 1.0},
        "welch": {
            "window": "hann_periodic",
            "segment_samples": 64,
            "overlap_fraction": 0.5,
            "detrend": "constant",
            "scaling": "density",
            "average": "mean",
        },
        "spectrogram": {"enabled": False, "segment_samples": 64, "overlap_fraction": 0.5},
        "events": {"enabled": False, "threshold_sigma": 5.0},
        "bands": {"edges_hz": [10.0, 100.0, 400.0]},
        "correction": {"method": "none"},
        "uncertainty": {"enabled": False, "confidence_level": 0.95, "bootstrap_samples": 0},
    }


def test_recipe_create_list_clone_and_referenced_delete_conflict(tmp_path: Path) -> None:
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        created = client.post(
            "/api/analysis/recipes",
            json={"name": "base", "recipe": _recipe_payload()},
            headers=headers,
        )
        cloned = client.post(
            f"/api/analysis/recipes/{created.json()['recipe_id']}/clone",
            json={"name": "copy"},
            headers=headers,
        )
        listed = client.get("/api/analysis/recipes")
        deleted = client.delete(
            f"/api/analysis/recipes/{created.json()['recipe_id']}", headers=headers
        )

    assert created.status_code == 201
    assert cloned.status_code == 201
    assert len(listed.json()["items"]) == 2
    assert deleted.status_code == 409


def _publish_spectrum(session: Path) -> tuple[str, bytes]:
    recipe = AnalysisRecipe.from_mapping(_recipe_payload())
    raw = b"raw"
    inputs = ArtifactInputs(
        recipe_sha256=recipe.recipe_sha256,
        raw_inputs=(
            NamedDigest(name="ch1.npy", digest=__import__("hashlib").sha256(raw).hexdigest()),
        ),
        context_dependencies=(),
        profile_dependencies=(),
        calibration_dependencies=(),
        code_identity=CodeIdentity(lnt="test", numpy="test", scipy="test"),
    )
    values = np.zeros(1001)
    values[101] = 12.0
    values[777] = -9.0
    spectrum = "frequency_hz,psd_v2_per_hz\n" + "".join(
        f"{x},{y}\n" for x, y in zip(np.arange(values.size), values, strict=True)
    )
    path = ArtifactStore(session).publish(
        inputs, {"spectrum.csv": spectrum.encode(), "metrics.json": b'{"exact":7}\n'}
    )
    return path.name, spectrum.encode()


def test_artifact_values_match_bytes_and_zoom_preserves_window_extrema(tmp_path: Path) -> None:
    session = tmp_path / "s1"
    session.mkdir()
    key, spectrum = _publish_spectrum(session)
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        artifact = client.get(f"/api/analysis/sessions/s1/artifacts/{key}/metrics.json")
        zoom = client.get(
            f"/api/analysis/sessions/s1/artifacts/{key}/plot/spectrum/zoom?start=50&end=900&max_points=20"
        )

    assert artifact.content == b'{"exact":7}\n'
    assert artifact.status_code == 200
    assert max(zoom.json()["y"]) == 12.0
    assert min(zoom.json()["y"]) == -9.0
    assert spectrum.startswith(b"frequency_hz")


def test_plot_limits_are_strict_and_russian(tmp_path: Path) -> None:
    session = tmp_path / "s1"
    session.mkdir()
    key, _ = _publish_spectrum(session)
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        response = client.get(
            f"/api/analysis/sessions/s1/artifacts/{key}/plot/spectrum?max_points=50001"
        )

    assert response.status_code == 422
    assert "предел" in response.json()["detail"]
