from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from lnt.catalog.connection import writer_transaction
from lnt.catalog.migrations import apply_migrations
from lnt.ui.app import create_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    database = local / "LNT" / "catalog.sqlite3"
    apply_migrations(database)
    session = tmp_path / "sessions" / "known"
    session.mkdir(parents=True)
    with writer_transaction(database) as connection:
        connection.execute(
            """INSERT INTO catalog_sessions(storage_path, session_id, path_fingerprint,
            health, base_health) VALUES (?, 'known', 'fp', 'ok', 'ok')""",
            (str(session),),
        )
    return TestClient(create_app(root=tmp_path / "sessions", catalog_db=database))


def test_context_update_conflict_and_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path, monkeypatch) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        initial = client.get("/api/context/known")
        updated = client.put(
            "/api/context/known",
            json={"expected_revision": 0, "tags": ["night"], "notes": "проверено"},
            headers=headers,
        )
        stale = client.put(
            "/api/context/known",
            json={"expected_revision": 0, "notes": "устарело"},
            headers=headers,
        )
        history = client.get("/api/context/known/history")

    assert initial.json()["revision"] == 0
    assert updated.status_code == 200
    assert updated.json()["revision"] == 1
    assert stale.status_code == 409
    assert stale.json()["current_revision"] == 1
    assert "конфликт" in stale.json()["detail"]
    assert [item["revision"] for item in history.json()["items"]] == [1]


def test_context_maps_unknown_traversal_and_invalid_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path, monkeypatch) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        missing = client.get("/api/context/missing")
        traversal = client.get("/api/context/..%5C..")
        invalid = client.put(
            "/api/context/known",
            json={"expected_revision": -1},
            headers=headers,
        )

    assert missing.status_code == 404
    assert traversal.status_code in {404, 422}
    assert invalid.status_code == 422
    assert all(
        "сесс" in response.json()["detail"] or "некоррект" in response.json()["detail"]
        for response in (missing, traversal, invalid)
    )
