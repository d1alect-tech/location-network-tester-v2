from __future__ import annotations

import hashlib
import sqlite3
from typing import TYPE_CHECKING

from lnt import session_projection
from lnt.analysis import analyze_measurement_session, write_analysis
from lnt.catalog import CatalogRepositories, open_catalog_reader
from lnt.simulate import simulate_session

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_analysis_projects_legacy_default_artifact_after_files_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    database = local / "LNT" / "catalog.sqlite3"
    session = simulate_session(
        out_dir=tmp_path / "sessions" / "synthetic",
        profile="quiet",
        duration_s=2.1,
        sample_rate_hz=20_000.0,
        seed=9,
    )
    result = analyze_measurement_session(session)

    # When
    metrics_path, spectrum_path = write_analysis(session, result)

    # Then
    assert metrics_path.is_file()
    assert spectrum_path.is_file()
    with open_catalog_reader(database) as connection:
        recipes = CatalogRepositories(connection).artifacts.for_session(result.session_id)
    assert len(recipes) == 1
    assert recipes[0].artifact_key == "legacy-default"
    assert recipes[0].storage_ref == str(session.resolve())
    expected = hashlib.sha256(b"lnt:legacy-default-analysis:v2").hexdigest()
    assert recipes[0].recipe_sha256 == expected


def test_analysis_catalog_failure_keeps_legacy_files_and_marks_reconcile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    session = simulate_session(
        out_dir=tmp_path / "sessions" / "synthetic",
        profile="quiet",
        duration_s=2.1,
        sample_rate_hz=20_000.0,
        seed=10,
    )
    result = analyze_measurement_session(session)

    def fail_projection(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(session_projection, "project_analysis_artifact", fail_projection)

    # When
    metrics_path, spectrum_path = write_analysis(session, result)

    # Then
    assert metrics_path.is_file()
    assert spectrum_path.is_file()
    assert (session / ".reconcile-needed").is_file()
