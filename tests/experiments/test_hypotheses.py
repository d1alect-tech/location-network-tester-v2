import json
from pathlib import Path

import pytest

from lnt.research import (
    EvidenceReference,
    ExpectedDirection,
    Hypothesis,
    HypothesisConflictError,
    HypothesisStatus,
    HypothesisStore,
    LinkedEstimand,
    Revision,
    hypothesis_status_label,
)


def _hypothesis(
    *, revision: int = 1, status: HypothesisStatus = HypothesisStatus.DRAFT
) -> Hypothesis:
    return Hypothesis(
        schema_version=1,
        hypothesis_id="network_load",
        revision=revision,
        statement="Рост нагрузки связан с ростом измеряемой задержки.",
        expected_direction=ExpectedDirection.INCREASE,
        mechanism="Общая нагрузка может менять расписание обработки.",
        linked_estimands=(
            LinkedEstimand(experiment_id="exp-1", estimand="latency_ms: loaded - idle"),
        ),
        confounds=("time_of_day", "location"),
        evidence_for=(
            EvidenceReference(result_id="corr-1", result_kind="descriptive_exploratory"),
        ),
        evidence_against=(
            EvidenceReference(result_id="corr-2", result_kind="descriptive_exploratory"),
        ),
        status=status,
        revision_history=(
            Revision(
                revision=revision,
                occurred_at="2026-01-01T00:00:00Z",
                actor="user:kirill",
                reason="user_edit",
            ),
        ),
    )


def test_hypothesis_round_trip_and_append_only_audit(tmp_path: Path) -> None:
    # Given
    store = HypothesisStore(tmp_path / "sessions")
    original = _hypothesis()

    # When
    store.save(original, expected_revision=0)
    edited = original.model_copy(
        update={
            "revision": 2,
            "mechanism": "Обновлённый пользовательский механизм.",
            "revision_history": (
                *original.revision_history,
                Revision(
                    revision=2,
                    occurred_at="2026-01-02T00:00:00Z",
                    actor="user:kirill",
                    reason="user_edit",
                ),
            ),
        },
    )
    store.save(edited, expected_revision=1)

    # Then
    assert store.load("network_load") == edited
    assert store.history("network_load") == (original, edited)
    assert store.root == tmp_path / "hypotheses"
    event_lines = (
        (store.root / "network_load" / "hypothesis.events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert [json.loads(line)["revision"] for line in event_lines] == [1, 2]


def test_status_changes_only_through_explicit_user_revision(tmp_path: Path) -> None:
    # Given
    store = HypothesisStore(tmp_path / "sessions")
    original = _hypothesis()
    store.save(original, expected_revision=0)

    # When
    implicit = original.model_copy(update={"status": HypothesisStatus.TESTING, "revision": 2})

    # Then
    with pytest.raises(HypothesisConflictError, match="revision_history"):
        store.save(implicit, expected_revision=1)
    assert store.load("network_load").status is HypothesisStatus.DRAFT


def test_evidence_links_and_noncausal_status_labels_round_trip(tmp_path: Path) -> None:
    # Given
    store = HypothesisStore(tmp_path / "sessions")
    hypothesis = _hypothesis(status=HypothesisStatus.CONSISTENT_WITH_OBSERVATIONS)

    # When
    store.save(hypothesis, expected_revision=0)
    restored = store.load(hypothesis.hypothesis_id)

    # Then
    assert restored.evidence_for[0].result_id == "corr-1"
    assert restored.evidence_against[0].result_id == "corr-2"
    labels = tuple(hypothesis_status_label(status) for status in HypothesisStatus)
    assert hypothesis_status_label(HypothesisStatus.CONSISTENT_WITH_OBSERVATIONS) == (
        "согласуется с наблюдениями"
    )
    assert all("подтверждено" not in label.casefold() for label in labels)
