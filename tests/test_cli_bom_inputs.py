"""DEF-003 regression: CLI принимает JSON с UTF-8 BOM (PowerShell 5.1 utf8)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from lnt.cli_experiments import (
    _hypothesis_file,  # pyright: ignore[reportPrivateUsage]
)
from lnt.cli_research import run_trends
from lnt.research import (
    EvidenceReference,
    ExpectedDirection,
    Hypothesis,
    HypothesisStatus,
    LinkedEstimand,
    Revision,
)

if TYPE_CHECKING:
    from pathlib import Path


BOM = b"\xef\xbb\xbf"


def _hypothesis_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "hypothesis_id": "bom-check",
        "revision": 1,
        "statement": "Гипотеза, сохранённая PowerShell 5.1 с BOM.",
        "expected_direction": ExpectedDirection.INCREASE.value,
        "mechanism": "Механизм описан пользователем.",
        "linked_estimands": [{"experiment_id": "exp-1", "estimand": "latency_ms"}],
        "confounds": ["time_of_day"],
        "evidence_for": [{"result_id": "corr-1", "result_kind": "descriptive_exploratory"}],
        "evidence_against": [],
        "status": HypothesisStatus.DRAFT.value,
        "revision_history": [
            {
                "revision": 1,
                "occurred_at": "2026-08-20T00:00:00Z",
                "actor": "user:kirill",
                "reason": "user_edit",
            }
        ],
    }


def test_hypothesis_add_accepts_utf8_bom(tmp_path: Path) -> None:
    # Given
    path = tmp_path / "hypothesis-bom.json"
    path.write_bytes(BOM + json.dumps(_hypothesis_payload(), ensure_ascii=False).encode("utf-8"))

    # When
    hypothesis = _hypothesis_file(path)

    # Then: BOM не искажает разбор и не даёт пустого списка полей.
    assert isinstance(hypothesis, Hypothesis)
    assert hypothesis.hypothesis_id == "bom-check"


def test_hypothesis_add_still_accepts_bom_free_payload(tmp_path: Path) -> None:
    # Given
    path = tmp_path / "hypothesis.json"
    path.write_bytes(json.dumps(_hypothesis_payload(), ensure_ascii=False).encode("utf-8"))

    # When
    hypothesis = _hypothesis_file(path)

    # Then
    assert hypothesis.status is HypothesisStatus.DRAFT
    assert isinstance(hypothesis.linked_estimands[0], LinkedEstimand)
    assert isinstance(hypothesis.revision_history[0], Revision)


def test_trends_accepts_utf8_bom_query(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    payload = {
        "observations": [
            {
                "observation_id": f"o{index}",
                "timestamp": None,
                "source_offset": f"+{index}s",
                "location": "L1",
                "condition": "A" if index % 2 == 0 else "B",
                "predictor": float(index),
                "outcome": float(index) / 2,
                "metadata": [],
            }
            for index in range(6)
        ],
        "minimum_n": 3,
        "max_lag": 2,
        "bootstrap_samples": 100,
        "seed": 7,
        "units": "V",
    }
    path = tmp_path / "trends-bom.json"
    path.write_bytes(BOM + json.dumps(payload).encode("utf-8"))

    # When
    exit_code = run_trends(path)

    # Then
    assert exit_code == 0
    captured = capsys.readouterr()
    assert '"estimator": "descriptive_longitudinal"' in captured.out


def test_evidence_reference_kind_contract_unchanged() -> None:
    # BOM-fix не ослабляет строгие модели: неизвестный kind отклоняется.
    with pytest.raises(ValidationError):
        EvidenceReference(result_id="x", result_kind="confirmed_result")
