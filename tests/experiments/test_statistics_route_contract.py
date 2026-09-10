from __future__ import annotations

import time
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient

from lnt.experiments import ExperimentStore, Protocol
from lnt.runtime.store import JobStore
from lnt.ui.app import create_app
from tests.experiments.factories import make_experiment

if TYPE_CHECKING:
    from pathlib import Path


def _headers(client: TestClient) -> dict[str, str]:
    nonce = client.get("/api/config").json()["mutation_nonce"]
    return {"X-LNT-Mutation-Nonce": nonce, "Origin": "http://127.0.0.1"}


def _result(client: TestClient, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 3
    response = client.get(f"/api/v2/statistics-runs/{job_id}/result")
    while response.status_code == 202 and time.monotonic() < deadline:
        time.sleep(0.01)
        response = client.get(f"/api/v2/statistics-runs/{job_id}/result")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "ab", "estimand": "latency_s", "units": "s", "pairs": []},
        {"kind": "aba", "estimand": "latency_s", "units": "s", "aba_units": []},
        {
            "kind": "ab",
            "estimand": "latency_s",
            "units": "s",
            "pairs": [{"unit_id": "u-1", "value_a": "NaN", "value_b": 1.0}],
        },
        {
            "kind": "ab",
            "estimand": "latency_s",
            "units": "s",
            "pairs": [{"unit_id": "u-1", "value_a": 0.0, "value_b": "Infinity"}],
        },
        {
            "kind": "ab",
            "estimand": "latency_s",
            "units": "s",
            "pairs": [{"unit_id": "u-1", "value_a": 0.0, "value_b": 1.0}],
            "aba_units": [{"unit_id": "u-1", "value_a1": 0.0, "value_b": 1.0, "value_a2": 0.0}],
        },
        {
            "kind": "aba",
            "estimand": "latency_s",
            "units": "s",
            "pairs": [{"unit_id": "u-1", "value_a": 0.0, "value_b": 1.0}],
            "aba_units": [{"unit_id": "u-1", "value_a1": 0.0, "value_b": 1.0, "value_a2": 0.0}],
        },
        {
            "kind": "aba",
            "estimand": "latency_s",
            "units": "s",
            "pairs": [{"unit_id": "u-1", "value_a": 0.0, "value_b": 1.0}],
        },
        {
            "kind": "repeated_blocks",
            "estimand": "latency_s",
            "units": "s",
            "pairs": [{"unit_id": "u-1", "value_a": 0.0, "value_b": 1.0}],
        },
    ],
)
def test_invalid_statistics_inputs_are_rejected_before_job_submission(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    sessions = tmp_path / "sessions"
    runtime_db = tmp_path / "runtime.sqlite3"
    ExperimentStore(sessions).save(make_experiment(), expected_revision=0)

    with TestClient(create_app(root=sessions, runtime_db=runtime_db)) as client:
        response = client.post(
            "/api/v2/experiments/latency-study/statistics-runs",
            headers=_headers(client),
            json=payload,
        )

    assert response.status_code == 422
    assert JobStore(runtime_db).list_snapshots(page_size=10) == ()


@pytest.mark.parametrize("count", [1, 2])
def test_low_n_ab_result_is_flat_descriptive_effect(tmp_path: Path, count: int) -> None:
    sessions = tmp_path / "sessions"
    ExperimentStore(sessions).save(make_experiment(), expected_revision=0)

    with TestClient(create_app(root=sessions, runtime_db=tmp_path / "runtime.sqlite3")) as client:
        submitted = client.post(
            "/api/v2/experiments/latency-study/statistics-runs",
            headers=_headers(client),
            json={
                "kind": "ab",
                "estimand": "latency_s",
                "units": "s",
                "pairs": [
                    {"unit_id": f"u-{index}", "value_a": float(index), "value_b": index + 0.5}
                    for index in range(count)
                ],
            },
        )
        payload = _result(client, submitted.json()["job_id"])

    assert payload["result_kind"] == "descriptive"
    result = cast("dict[str, object]", payload["result"])
    metadata = cast("dict[str, object]", payload["metadata"])
    assert result["mean_effect"] == 0.5
    assert result["interval"] is None
    assert metadata["n"] == count


@pytest.mark.parametrize(
    ("kind", "protocol", "estimator"),
    [
        ("ab", Protocol.AB, "paired_difference"),
        ("repeated_blocks", Protocol.REPEATED_BLOCKS, "block_paired"),
    ],
)
def test_inferential_paired_result_wraps_effect_for_ui_consumers(
    tmp_path: Path,
    kind: str,
    protocol: Protocol,
    estimator: str,
) -> None:
    sessions = tmp_path / "sessions"
    ExperimentStore(sessions).save(make_experiment(protocol), expected_revision=0)

    with TestClient(create_app(root=sessions, runtime_db=tmp_path / "runtime.sqlite3")) as client:
        submitted = client.post(
            "/api/v2/experiments/latency-study/statistics-runs",
            headers=_headers(client),
            json={
                "kind": kind,
                "estimand": "latency_s",
                "units": "s",
                "pairs": [
                    {"unit_id": f"u-{index}", "value_a": float(index), "value_b": index + 0.5}
                    for index in range(3)
                ],
                "seed": 7,
            },
        )
        payload = _result(client, submitted.json()["job_id"])

    assert payload["result_kind"] == "effect"
    result = cast("dict[str, object]", payload["result"])
    effect = cast("dict[str, object]", result["effect"])
    metadata = cast("dict[str, object]", payload["metadata"])
    assert effect["mean_effect"] == 0.5
    assert effect["interval"] == {
        "low": 0.5,
        "high": 0.5,
        "confidence_level": 0.95,
    }
    assert metadata["estimator"] == estimator


@pytest.mark.parametrize(
    ("value_a2", "result_kind"),
    [(0.0, "effect"), (0.4, "refusal")],
)
def test_aba_result_preserves_qualified_effect_or_refusal(
    tmp_path: Path,
    value_a2: float,
    result_kind: str,
) -> None:
    sessions = tmp_path / "sessions"
    ExperimentStore(sessions).save(make_experiment(Protocol.ABA), expected_revision=0)

    with TestClient(create_app(root=sessions, runtime_db=tmp_path / "runtime.sqlite3")) as client:
        submitted = client.post(
            "/api/v2/experiments/latency-study/statistics-runs",
            headers=_headers(client),
            json={
                "kind": "aba",
                "estimand": "latency_s",
                "units": "s",
                "aba_units": [
                    {
                        "unit_id": f"u-{index}",
                        "value_a1": 0.0,
                        "value_b": 0.2,
                        "value_a2": value_a2,
                    }
                    for index in range(3)
                ],
                "seed": 11,
            },
        )
        payload = _result(client, submitted.json()["job_id"])

    assert payload["result_kind"] == result_kind
    result = cast("dict[str, object]", payload["result"])
    if result_kind == "effect":
        effect = cast("dict[str, object]", result["effect"])
        drift = cast("dict[str, object]", result["drift"])
        assert effect["mean_effect"] == pytest.approx(0.2)
        assert drift["mean_effect"] == 0.0
    else:
        assert result["reason_code"] == "a_drift_exceeds_half_effect_or_two_sd"
        assert result["drift_effect"] == pytest.approx(0.4)
