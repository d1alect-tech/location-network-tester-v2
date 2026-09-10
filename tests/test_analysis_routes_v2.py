from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from lnt.analysis_store import (
    AnalysisRecipe,
    ArtifactCorruptError,
    ArtifactInputs,
    ArtifactStore,
    CodeIdentity,
    NamedDigest,
)
from lnt.context.json_codec import JsonValue  # noqa: TC001 - fixture return type
from lnt.ui.app import create_app
from tests.test_ui_sessions import write_manifest


def _make_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607
            check=True,
            capture_output=True,
        )
    else:
        link.symlink_to(target, target_is_directory=True)


def _remove_directory_link(link: Path) -> None:
    if os.name == "nt":
        link.rmdir()
    else:
        link.unlink()


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


def _create_recipe(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/analysis/recipes",
        json={"name": "base", "recipe": _recipe_payload()},
        headers=headers,
    )
    assert response.status_code == 201
    return str(response.json()["recipe_id"])


def test_run_rejects_traversal_before_job_or_external_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    write_manifest(outside)

    def fake_run(_self: object, session_dir: Path, *_args: object, **_kwargs: object) -> object:
        (session_dir / "analyses").mkdir(parents=True)
        return SimpleNamespace(artifact_key="a" * 64)

    monkeypatch.setattr("lnt.ui.routes_analysis_v2.AnalysisOrchestrator.run", fake_run)
    app = create_app(root=root, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        recipe_id = _create_recipe(client, headers)
        response = client.post(
            "/api/analysis/runs",
            json={"session": "../outside", "recipe_id": recipe_id, "make_default": True},
            headers=headers,
        )

    assert response.status_code == 422
    assert not (root / ".lnt" / "analysis-jobs").exists()
    assert not (outside / "analyses").exists()
    assert not (outside / ".lnt-default-analysis.json").exists()


def test_run_rejects_ambiguous_session_without_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    write_manifest(root / "shared", session_id="direct-id")
    write_manifest(root / "other", session_id="shared")

    def fake_run(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(artifact_key="a" * 64)

    monkeypatch.setattr("lnt.ui.routes_analysis_v2.AnalysisOrchestrator.run", fake_run)
    app = create_app(root=root, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        recipe_id = _create_recipe(client, headers)
        response = client.post(
            "/api/analysis/runs",
            json={"session": "shared", "recipe_id": recipe_id, "make_default": True},
            headers=headers,
        )

    assert response.status_code == 409
    assert not (root / ".lnt" / "analysis-jobs").exists()
    assert not (root / "shared" / ".lnt-default-analysis.json").exists()
    assert not (root / "other" / ".lnt-default-analysis.json").exists()


def test_run_uses_manifest_alias_resolved_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    target = root / "directory-name"
    write_manifest(target, session_id="public-id")
    used: list[Path] = []

    def fake_run(_self: object, session_dir: Path, *_args: object, **_kwargs: object) -> object:
        used.append(session_dir)
        artifact_key, _ = _publish_spectrum(session_dir)
        return SimpleNamespace(artifact_key=artifact_key)

    monkeypatch.setattr("lnt.ui.routes_analysis_v2.AnalysisOrchestrator.run", fake_run)
    app = create_app(root=root, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        recipe_id = _create_recipe(client, headers)
        response = client.post(
            "/api/analysis/runs",
            json={"session": "public-id", "recipe_id": recipe_id, "make_default": True},
            headers=headers,
        )

    assert response.status_code == 202
    assert used == [target]
    assert (target / ".lnt-default-analysis.json").is_file()
    assert not (root / "public-id").exists()


def test_artifact_file_must_be_listed_in_verified_manifest(tmp_path: Path) -> None:
    session = tmp_path / "s1"
    session.mkdir()
    key, _ = _publish_spectrum(session)
    (session / "analyses" / key / "secret.txt").write_text("outside manifest", encoding="utf-8")
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")

    with TestClient(app) as client:
        response = client.get(f"/api/analysis/sessions/s1/artifacts/{key}/secret.txt")

    assert response.status_code == 404


def test_default_pointer_get_requires_verified_artifact(tmp_path: Path) -> None:
    session = tmp_path / "s1"
    session.mkdir()
    key, _ = _publish_spectrum(session)
    recipe_id = AnalysisRecipe.from_mapping(_recipe_payload()).recipe_sha256
    pointer = {"recipe_id": recipe_id, "artifact_key": key}
    (session / ".lnt-default-analysis.json").write_text(
        json.dumps(pointer) + "\n", encoding="utf-8"
    )
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")

    with TestClient(app) as client:
        valid = client.get("/api/analysis/sessions/s1/.lnt-default-analysis.json")
        (session / "analyses" / key / "metrics.json").write_bytes(b"tampered")
        corrupt = client.get("/api/analysis/sessions/s1/.lnt-default-analysis.json")

    assert valid.status_code == 200
    assert valid.json() == pointer
    assert corrupt.status_code == 409


def test_default_pointer_rejects_recipe_mismatch(tmp_path: Path) -> None:
    session = tmp_path / "s1"
    session.mkdir()
    key, _ = _publish_spectrum(session)
    (session / ".lnt-default-analysis.json").write_text(
        json.dumps({"recipe_id": "b" * 64, "artifact_key": key}) + "\n", encoding="utf-8"
    )
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")

    with TestClient(app) as client:
        response = client.get("/api/analysis/sessions/s1/.lnt-default-analysis.json")

    assert response.status_code == 409


def test_missing_recipe_is_rejected_before_job_creation(tmp_path: Path) -> None:
    write_manifest(tmp_path / "s1")
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        response = client.post(
            "/api/analysis/runs",
            json={"session": "s1", "recipe_id": "a" * 64},
            headers=headers,
        )

    assert response.status_code == 404
    assert not (tmp_path / ".lnt" / "analysis-jobs").exists()


def test_linked_analysis_destination_is_rejected_before_job_or_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = tmp_path / "s1"
    external = tmp_path / "external"
    write_manifest(session)
    external.mkdir()
    (external / "keep.txt").write_text("keep", encoding="utf-8")
    link = session / "analyses"
    _make_directory_link(link, external)
    called = False

    def fake_run(*_args: object, **_kwargs: object) -> object:
        nonlocal called
        called = True
        return SimpleNamespace(artifact_key="a" * 64)

    monkeypatch.setattr("lnt.ui.routes_analysis_v2.AnalysisOrchestrator.run", fake_run)
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")
    try:
        with TestClient(app) as client:
            headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
            recipe_id = _create_recipe(client, headers)
            response = client.post(
                "/api/analysis/runs",
                json={"session": "s1", "recipe_id": recipe_id},
                headers=headers,
            )
    finally:
        _remove_directory_link(link)

    assert response.status_code == 422
    assert not called
    assert not (tmp_path / ".lnt" / "analysis-jobs").exists()
    assert (external / "keep.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    ("failure", "marker"),
    [
        (OSError("pointer denied"), "pointer denied"),
        (ArtifactCorruptError(Path("artifact"), "recipe_id_mismatch"), "recipe_id_mismatch"),
    ],
)
def test_pointer_publish_failure_records_failed_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception, marker: str
) -> None:
    session = tmp_path / "s1"
    write_manifest(session)

    def fake_run(_self: object, session_dir: Path, *_args: object, **_kwargs: object) -> object:
        artifact_key, _ = _publish_spectrum(session_dir)
        return SimpleNamespace(artifact_key=artifact_key)

    def fail_pointer(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr("lnt.ui.routes_analysis_v2.AnalysisOrchestrator.run", fake_run)
    monkeypatch.setattr("lnt.ui.routes_analysis_v2.write_default_pointer", fail_pointer)
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        recipe_id = _create_recipe(client, headers)
        response = client.post(
            "/api/analysis/runs",
            json={"session": "s1", "recipe_id": recipe_id, "make_default": True},
            headers=headers,
        )
        status = client.get(f"/api/analysis/runs/{response.json()['job_id']}")

    payload = response.json()
    job_path = tmp_path / ".lnt" / "analysis-jobs" / f"{payload['job_id']}.json"
    assert response.status_code == 202
    assert payload["status"] == "failed"
    assert marker in payload["error"]
    assert json.loads(job_path.read_text(encoding="utf-8"))["status"] == "failed"
    assert status.json()["status"] == "failed"


def test_tampered_recipe_identity_fails_listing_closed(tmp_path: Path) -> None:
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        recipe_id = _create_recipe(client, headers)
        path = tmp_path / ".lnt" / "analysis-recipes" / f"{recipe_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["recipe_id"] = "b" * 64
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        listed = client.get("/api/analysis/recipes")

    assert listed.status_code == 422


@pytest.mark.parametrize("tamper", ["payload", "canonical"])
def test_tampered_recipe_identity_is_rejected_before_run_or_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str
) -> None:
    write_manifest(tmp_path / "s1")
    called = False

    def fake_run(*_args: object, **_kwargs: object) -> object:
        nonlocal called
        called = True
        return SimpleNamespace(artifact_key="a" * 64)

    monkeypatch.setattr("lnt.ui.routes_analysis_v2.AnalysisOrchestrator.run", fake_run)
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        recipe_id = _create_recipe(client, headers)
        path = tmp_path / ".lnt" / "analysis-recipes" / f"{recipe_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if tamper == "payload":
            payload["recipe_id"] = "b" * 64
        else:
            payload["recipe"]["mode"] = "tampered"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        run = client.post(
            "/api/analysis/runs",
            json={"session": "s1", "recipe_id": recipe_id},
            headers=headers,
        )
        clone = client.post(
            f"/api/analysis/recipes/{recipe_id}/clone",
            json={"name": "copy"},
            headers=headers,
        )

    assert run.status_code == 422
    assert clone.status_code == 422
    assert not called
    assert not (tmp_path / ".lnt" / "analysis-jobs").exists()


@pytest.mark.parametrize(
    ("method", "url", "json_body"),
    [
        ("get", "/api/analysis/runs/not-a-job", None),
        ("post", "/api/analysis/recipes/not-a-recipe/clone", {"name": "copy"}),
        ("get", "/api/analysis/sessions/s1/artifacts/not-an-artifact/metrics.json", None),
    ],
)
def test_filesystem_backed_path_keys_require_exact_formats(
    tmp_path: Path, method: str, url: str, json_body: dict[str, str] | None
) -> None:
    (tmp_path / "s1").mkdir()
    app = create_app(root=tmp_path, runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        response = client.request(method, url, json=json_body, headers=headers)

    assert response.status_code == 422
