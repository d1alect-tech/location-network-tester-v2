"""Хранилище, ссылки и catalog projection экспериментов."""

import sqlite3
from pathlib import Path

import pytest

from lnt.catalog.reconcile import reconcile_catalog
from lnt.experiments import ExperimentConflictError, ExperimentStore
from tests.experiments.factories import make_experiment


def test_store_uses_sibling_area_and_preserves_sessions(tmp_path: Path) -> None:
    # Given
    session_root = tmp_path / "sessions"
    session = session_root / "session-a"
    session.mkdir(parents=True)
    marker = session / "raw.bin"
    marker.write_bytes(b"raw")
    store = ExperimentStore(session_root)

    # When
    stored = store.save(make_experiment(), expected_revision=0)

    # Then
    assert stored == make_experiment()
    assert (tmp_path / "experiments/latency-study/experiment.json").is_file()
    assert (tmp_path / "experiments/latency-study/experiment.events.jsonl").is_file()
    assert marker.read_bytes() == b"raw"


def test_revision_conflict_has_no_partial_state(tmp_path: Path) -> None:
    # Given
    store = ExperimentStore(tmp_path / "sessions")
    initial = store.save(make_experiment(), expected_revision=0)
    changed = make_experiment(revision=2).model_copy(update={"title": "Новая версия"})

    # When / Then
    with pytest.raises(ExperimentConflictError) as raised:
        store.save(changed, expected_revision=0)
    assert raised.value.reason_code == "experiment_revision_conflict"
    assert store.load("latency-study") == initial
    assert len(store.history("latency-study")) == 1


def test_missing_member_remains_visible_as_broken_reference(tmp_path: Path) -> None:
    # Given
    session_root = tmp_path / "sessions"
    (session_root / "session-a").mkdir(parents=True)
    store = ExperimentStore(session_root)
    store.save(make_experiment(), expected_revision=0)

    # When
    view = store.resolve_members("latency-study")

    # Then
    assert [(item.member.session_id, item.health) for item in view] == [
        ("session-a", "ok"),
        ("missing-session", "broken_reference"),
    ]


def test_reindex_projects_experiment_and_membership(tmp_path: Path) -> None:
    # Given
    session_root = tmp_path / "sessions"
    (session_root / "session-a").mkdir(parents=True)
    database = tmp_path / "catalog.sqlite3"
    ExperimentStore(session_root).save(make_experiment(), expected_revision=0)

    # When
    reconcile_catalog(session_root, database, rebuild=True)

    # Then
    with sqlite3.connect(database) as connection:
        experiments = connection.execute(
            "SELECT id, title, protocol, revision FROM catalog_experiments",
        ).fetchall()
        members = connection.execute(
            (
                "SELECT session_id, condition_id, reference_health "
                "FROM catalog_experiment_members ORDER BY ordinal"
            ),
        ).fetchall()
    assert experiments == [("latency-study", "Задержка A/B", "ab", 1)]
    assert members == [
        ("session-a", "condition-a", "ok"),
        ("missing-session", "condition-b", "broken_reference"),
    ]
