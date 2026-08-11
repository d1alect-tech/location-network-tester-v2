from __future__ import annotations

# ruff: noqa: TC002
import json
from typing import TYPE_CHECKING

import pytest

from lnt.cli import main
from tests.experiments.factories import make_experiment

if TYPE_CHECKING:
    from pathlib import Path


def test_experiment_create_list_show_and_stats_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = tmp_path / "experiment.json"
    payload.write_text(make_experiment().model_dump_json(), encoding="utf-8")
    root = tmp_path / "sessions"

    created = main(["experiment", "create", str(payload), "--root", str(root)])
    listed = main(["experiment", "list", "--root", str(root)])
    shown = main(["experiment", "show", "latency-study", "--root", str(root)])
    stats = main(
        [
            "experiment",
            "stats",
            "latency-study",
            "--root",
            str(root),
            "--estimand",
            "latency_s",
            "--units",
            "s",
            "--pair",
            "u1:1:2",
        ]
    )

    output = capsys.readouterr().out
    assert (created, listed, shown, stats) == (0, 0, 0, 0)
    assert "latency-study" in output
    assert '"units": "s"' in output
    assert '"estimator"' in output


def test_experiment_cli_typed_failure_is_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["experiment", "show", "missing", "--root", str(tmp_path / "sessions")])

    error = capsys.readouterr().err
    assert code == 2
    assert "не найден" in error


def test_hypothesis_add_edit_and_status_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "sessions"
    payload = tmp_path / "hypothesis.json"
    hypothesis = {
        "schema_version": 1,
        "hypothesis_id": "lower-latency",
        "revision": 1,
        "statement": "B связано с меньшей задержкой",
        "expected_direction": "decrease",
        "mechanism": "Меньше буферизация",
        "linked_estimands": [],
        "confounds": [],
        "evidence_for": [],
        "evidence_against": [],
        "status": "draft",
        "revision_history": [
            {
                "revision": 1,
                "occurred_at": "2026-08-11T10:00:00.000Z",
                "actor": "user:tester",
                "reason": "Создание",
            }
        ],
    }
    payload.write_text(json.dumps(hypothesis, ensure_ascii=False), encoding="utf-8")

    added = main(["hypothesis", "add", str(payload), "--root", str(root)])
    status = main(["hypothesis", "status", "lower-latency", "--root", str(root)])

    output = capsys.readouterr().out
    assert (added, status) == (0, 0)
    assert "черновик" in output
