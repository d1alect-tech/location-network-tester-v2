from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from lnt.catalog.connection import writer_transaction
from lnt.catalog.migrations import apply_migrations
from lnt.simulate import simulate_session
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


def test_startup_indexes_manifest_id_for_context_read_and_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    root = tmp_path / "sessions"
    session = simulate_session(
        out_dir=root / "demo-b",
        profile="quiet",
        duration_s=0.05,
        sample_rate_hz=20_000.0,
        seed=6023,
    )

    with TestClient(
        create_app(
            root=root,
            catalog_db=tmp_path / "catalog.sqlite3",
            index_catalog=True,
        )
    ) as client:
        listed = client.get("/api/catalog/sessions")
        initial = client.get("/api/context/syn-quiet-seed6023")
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        updated = client.put(
            "/api/context/syn-quiet-seed6023",
            json={"expected_revision": initial.json()["revision"], "notes": "checked"},
            headers=headers,
        )
        stale = client.put(
            "/api/context/syn-quiet-seed6023",
            json={"expected_revision": initial.json()["revision"], "notes": "stale"},
            headers=headers,
        )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == ["syn-quiet-seed6023"]
    assert initial.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["revision"] == initial.json()["revision"] + 1
    assert stale.status_code == 409
    assert updated.json()["session_id"] == "syn-quiet-seed6023"
    assert (session / "context.json").is_file()
    assert not (root / "syn-quiet-seed6023").exists()
    assert session.name == "demo-b"


def test_stale_catalog_path_cannot_authorize_context_outside_root(
    tmp_path: Path,
) -> None:
    database = tmp_path / "catalog.sqlite3"
    apply_migrations(database)
    outside = tmp_path / "outside"
    outside.mkdir()
    with writer_transaction(database) as connection:
        connection.execute(
            """INSERT INTO catalog_sessions(storage_path, session_id, path_fingerprint,
            health, base_health) VALUES (?, 'outside-id', 'fp', 'ok', 'ok')""",
            (str(outside),),
        )

    with TestClient(
        create_app(root=tmp_path / "sessions", catalog_db=database),
    ) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        read = client.get("/api/context/outside-id")
        write = client.put(
            "/api/context/outside-id",
            json={"expected_revision": 0, "notes": "must not write"},
            headers=headers,
        )

    assert read.status_code == 404
    assert write.status_code == 404
    assert not (outside / "context.json").exists()
    assert not (outside / "context.events.jsonl").exists()


def test_stale_catalog_path_cannot_authorize_replacement_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    original = root / "original"
    replacement = root / "replacement"
    original.mkdir(parents=True)
    replacement.mkdir()
    database = tmp_path / "catalog.sqlite3"
    apply_migrations(database)
    with writer_transaction(database) as connection:
        connection.execute(
            """INSERT INTO catalog_sessions(storage_path, session_id, path_fingerprint,
            health, base_health) VALUES (?, 'replacement', 'fp', 'ok', 'ok')""",
            (str(original),),
        )

    with TestClient(create_app(root=root, catalog_db=database)) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        read = client.get("/api/context/replacement")
        write = client.put(
            "/api/context/replacement",
            json={"expected_revision": 0, "notes": "must not write"},
            headers=headers,
        )

    assert read.status_code == 404
    assert write.status_code == 404
    assert not (replacement / "context.json").exists()
    assert not (replacement / "context.events.jsonl").exists()
