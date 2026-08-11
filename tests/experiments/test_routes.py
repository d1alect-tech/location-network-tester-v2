from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from lnt.experiments import ExperimentStore, Member, Revision
from lnt.research import ExpectedDirection, HypothesisStatus
from lnt.ui.app import create_app
from tests.experiments.factories import make_experiment

if TYPE_CHECKING:
    from pathlib import Path


def _headers(client: TestClient) -> dict[str, str]:
    nonce = client.get("/api/config").json()["mutation_nonce"]
    return {"X-LNT-Mutation-Nonce": nonce, "Origin": "http://127.0.0.1"}


def _create(client: TestClient, *, members: int = 2) -> dict[str, object]:
    experiment = make_experiment()
    if members != 2:
        generated = tuple(
            Member(
                session_id=f"session-{index:05d}",
                storage_ref=f"session-{index:05d}",
                role="measurement",
                condition_id="condition-a" if index % 2 else "condition-b",
                order=index,
                block_key=f"block-{index // 2}",
                pairing_key=f"pair-{index // 2}",
            )
            for index in range(1, members + 1)
        )
        experiment = experiment.model_copy(update={"members": generated})
    response = client.post(
        "/api/v2/experiments",
        headers=_headers(client),
        json={"experiment": experiment.model_dump(mode="json"), "expected_revision": 0},
    )
    assert response.status_code == 201
    return response.json()


def test_experiment_crud_revision_and_stable_member_cursor(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        created = _create(client)
        experiment = make_experiment()
        generated = tuple(
            Member(
                session_id=f"session-{index:05d}",
                storage_ref=f"session-{index:05d}",
                role="measurement",
                condition_id="condition-a" if index % 2 else "condition-b",
                order=index,
                block_key=f"block-{index // 2}",
                pairing_key=f"pair-{index // 2}",
            )
            for index in range(1, 10_001)
        )
        ExperimentStore(tmp_path / "sessions").save(
            experiment.model_copy(
                update={
                    "revision": 2,
                    "members": generated,
                    "revision_history": (
                        *experiment.revision_history,
                        Revision(
                            revision=2,
                            occurred_at="2026-08-11T11:00:00.000Z",
                            actor="tester",
                            reason="Большая когорта",
                        ),
                    ),
                }
            ),
            expected_revision=1,
        )
        listing = client.get("/api/v2/experiments", params={"page_size": 1})
        first = client.get(
            "/api/v2/experiments/latency-study/members", params={"page_size": 37}
        ).json()
        second = client.get(
            "/api/v2/experiments/latency-study/members",
            params={"page_size": 37, "cursor": first["next_cursor"]},
        ).json()
        stale = client.put(
            "/api/v2/experiments/latency-study",
            headers=_headers(client),
            json={"experiment": created, "expected_revision": 0},
        )

    assert listing.status_code == 200
    assert listing.json()["items"][0]["experiment_id"] == "latency-study"
    assert len(first["items"]) == len(second["items"]) == 37
    assert first["items"][-1]["order"] < second["items"][0]["order"]
    assert stale.status_code == 409
    assert stale.json()["code"] == "experiment_revision_conflict"


def test_experiment_routes_validate_bounds_and_inherit_nonce(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        rejected = client.post("/api/v2/experiments", json={})
        oversized = client.get("/api/v2/experiments", params={"page_size": 201})
        malformed = client.get("/api/v2/experiments", params={"cursor": "not-a-cursor"})

    assert rejected.status_code == 403
    assert rejected.json()["code"] == "mutation_nonce_invalid"
    assert oversized.status_code == 422
    assert malformed.status_code == 422
    assert "cursor" in malformed.json()["detail"]


def test_simulator_protocol_run_and_status_contract(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        _create(client)
        started = client.post(
            "/api/v2/experiments/latency-study/runs",
            headers=_headers(client),
            json={"run_id": "run-1", "mode": "simulator"},
        )
        confirmed = client.post(
            "/api/v2/protocol-runs/run-1/confirm",
            headers=_headers(client),
            json={"actor": "user:tester", "auto_confirm": False},
        )
        status = client.get("/api/v2/protocol-runs/run-1")

    assert started.status_code == 201
    assert started.json()["status"] == "completed"
    assert confirmed.status_code == 200
    assert status.json()["completed_members"][0]["confirmation"]["actor"] == "simulator"


def test_real_protocol_rejects_auto_confirmation_with_typed_russian_error(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        _create(client)
        client.post(
            "/api/v2/experiments/latency-study/runs",
            headers=_headers(client),
            json={"run_id": "real-1", "mode": "real"},
        )
        response = client.post(
            "/api/v2/protocol-runs/real-1/confirm",
            headers=_headers(client),
            json={"actor": "user:tester", "auto_confirm": True},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "real_intervention_auto_confirmation_forbidden"
    assert "нельзя" in response.json()["detail"]


def test_statistics_submit_poll_and_metadata_snapshot(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        _create(client)
        submitted = client.post(
            "/api/v2/experiments/latency-study/statistics-runs",
            headers=_headers(client),
            json={
                "kind": "ab",
                "estimand": "latency_s",
                "units": "s",
                "pairs": [
                    {"unit_id": f"u-{index}", "value_a": index, "value_b": index + 0.5}
                    for index in range(12)
                ],
                "seed": 7,
            },
        )
        assert submitted.status_code == 202
        job_id = submitted.json()["job_id"]
        deadline = time.monotonic() + 3
        result = client.get(f"/api/v2/statistics-runs/{job_id}/result")
        while result.status_code == 202 and time.monotonic() < deadline:
            time.sleep(0.01)
            result = client.get(f"/api/v2/statistics-runs/{job_id}/result")

    assert result.status_code == 200
    payload = result.json()
    assert payload["result_kind"] == "effect"
    assert payload["metadata"] == {
        "units": "s",
        "sampling_unit": "subject",
        "hierarchy": ["site_id", "subject_id"],
        "n": 12,
        "missing_count": 0,
        "exclusions": [],
        "estimator": "paired_difference",
        "interval_method": "seeded_block_bootstrap_percentile_95",
        "provenance": {
            "experiment_id": "latency-study",
            "experiment_revision": 1,
            "estimand": "latency_s",
            "job_id": job_id,
        },
    }


def test_trends_and_hypothesis_audited_contracts(tmp_path: Path) -> None:
    hypothesis = {
        "schema_version": 1,
        "hypothesis_id": "lower-latency",
        "revision": 1,
        "statement": "B связано с меньшей задержкой",
        "expected_direction": ExpectedDirection.DECREASE,
        "mechanism": "Меньше буферизация",
        "linked_estimands": [{"experiment_id": "latency-study", "estimand": "latency_s"}],
        "confounds": ["temperature"],
        "evidence_for": [],
        "evidence_against": [],
        "status": HypothesisStatus.DRAFT,
        "revision_history": [
            {
                "revision": 1,
                "occurred_at": "2026-08-11T10:00:00.000Z",
                "actor": "user:tester",
                "reason": "Создание",
            }
        ],
    }
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        trend = client.post(
            "/api/v2/trends/query",
            headers=_headers(client),
            json={
                "observations": [
                    {
                        "observation_id": f"o-{index}",
                        "timestamp": f"2026-08-{index + 1:02d}T10:00:00+00:00",
                        "source_offset": str(index),
                        "location": "lab",
                        "condition": "a",
                        "predictor": float(index),
                        "outcome": float(index + 1),
                        "metadata": [],
                    }
                    for index in range(5)
                ],
                "minimum_n": 5,
                "max_lag": 2,
                "bootstrap_samples": 100,
                "seed": 1,
                "units": "s",
            },
        )
        created = client.post(
            "/api/v2/hypotheses",
            headers=_headers(client),
            json={"hypothesis": hypothesis, "expected_revision": 0},
        )
        listing = client.get("/api/v2/hypotheses", params={"status": "draft"})

    assert trend.status_code == 200
    assert trend.json()["metadata"]["units"] == "s"
    assert trend.json()["metadata"]["estimator"] == "descriptive_longitudinal"
    assert created.status_code == 201
    assert listing.json()["items"][0]["status_label"] == "черновик"
