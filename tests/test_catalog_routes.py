from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from lnt.catalog.connection import writer_transaction
from lnt.catalog.migrations import apply_migrations
from lnt.ui.app import create_app

if TYPE_CHECKING:
    from pathlib import Path


def _database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    database = local / "LNT" / "catalog.sqlite3"
    apply_migrations(database)
    return database


def _insert(database: Path, session_id: str, created: str, **values: str) -> None:
    storage = values.pop("storage_path", f"C:/private/{session_id}")
    with writer_transaction(database) as connection:
        connection.execute(
            """INSERT INTO catalog_sessions(
            storage_path, session_id, path_fingerprint, health, base_health,
            created_utc, source, session_type, profile, label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                storage,
                session_id,
                f"fp-{session_id}",
                values.get("health", "ok"),
                values.get("health", "ok"),
                created,
                values.get("source", "capture"),
                values.get("session_type", "measurement"),
                values.get("profile", "lab"),
                values.get("label", session_id),
            ),
        )
        for tag in values.get("tags", "").split(","):
            if tag:
                connection.execute(
                    "INSERT INTO catalog_context_tags(storage_path, tag) VALUES (?, ?)",
                    (storage, tag),
                )


def test_catalog_cursor_is_stable_and_hides_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _database(tmp_path, monkeypatch)
    _insert(database, "b", "2026-01-02T00:00:00Z")
    _insert(database, "c", "2026-01-01T00:00:00Z")

    with TestClient(create_app(root=tmp_path / "sessions", catalog_db=database)) as client:
        first = client.get("/api/catalog/sessions", params={"page_size": 1}).json()
        _insert(database, "a", "2026-01-03T00:00:00Z")
        second = client.get(
            "/api/catalog/sessions",
            params={"page_size": 2, "cursor": first["next_cursor"]},
        ).json()

    assert [item["id"] for item in first["items"] + second["items"]] == ["b", "c"]
    assert "storage_path" not in first["items"][0]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ({"health": "corrupt_manifest"}, "broken"),
        ({"session_type": "self_noise"}, "noise"),
        ({"source": "simulate"}, "synthetic"),
        ({"profile": "field"}, "profiled"),
        ({"label": "ИГОЛ"}, "labelled"),
        ({"tag": "night"}, "tagged"),
        ({"created_from": "2026-02-01T00:00:00Z"}, "recent"),
        ({"created_to": "2025-12-31T23:59:59Z"}, "old"),
    ],
)
def test_catalog_supports_each_typed_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    query: dict[str, str],
    expected: str,
) -> None:
    database = _database(tmp_path, monkeypatch)
    fixtures = {
        "broken": {"health": "corrupt_manifest"},
        "noise": {"session_type": "self_noise"},
        "synthetic": {"source": "simulate"},
        "profiled": {"profile": "field"},
        "labelled": {"label": "до Иголки"},
        "tagged": {"tags": "night"},
        "recent": {},
        "old": {},
    }
    for session_id, values in fixtures.items():
        created = "2026-02-02T00:00:00Z" if session_id == "recent" else "2025-01-01T00:00:00Z"
        _insert(database, session_id, created, **values)

    with TestClient(create_app(root=tmp_path / "sessions", catalog_db=database)) as client:
        response = client.get("/api/catalog/sessions", params=query)

    assert response.status_code == 200
    assert expected in {item["id"] for item in response.json()["items"]}


def test_catalog_facets_validation_unavailable_and_docs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _database(tmp_path, monkeypatch)
    _insert(database, "broken", "2026-01-01T00:00:00Z", health="corrupt_manifest")
    with TestClient(create_app(root=tmp_path / "sessions", catalog_db=database)) as client:
        facets = client.get("/api/catalog/health-facets")
        oversized = client.get("/api/catalog/sessions", params={"page_size": 201})
        docs = [client.get(path).status_code for path in ("/docs", "/redoc", "/openapi.json")]
    database.unlink()
    with TestClient(create_app(root=tmp_path / "other", catalog_db=database)) as client:
        unavailable = client.get("/api/catalog/sessions")

    assert facets.json() == {"counts": {"corrupt_manifest": 1}}
    assert oversized.status_code == 422
    assert "некоррект" in oversized.json()["detail"]
    assert docs == [404, 404, 404]
    assert unavailable.status_code == 503
    assert "каталог" in unavailable.json()["detail"]


def test_catalog_10k_query_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database(tmp_path, monkeypatch)
    rows = [
        (
            f"C:/private/{index}",
            f"s-{index:05d}",
            f"fp-{index}",
            "ok",
            "ok",
            f"2026-01-{(index % 28) + 1:02d}T00:00:00Z",
            "capture",
            "measurement",
            "lab",
            "row",
        )
        for index in range(10_000)
    ]
    with writer_transaction(database) as connection:
        connection.executemany(
            """INSERT INTO catalog_sessions(storage_path, session_id, path_fingerprint,
            health, base_health, created_utc, source, session_type, profile, label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    with TestClient(create_app(root=tmp_path / "sessions", catalog_db=database)) as client:
        started = time.perf_counter()
        response = client.get("/api/catalog/sessions", params={"page_size": 50})
        measured_ms = (time.perf_counter() - started) * 1000

    assert response.status_code == 200
    assert len(response.json()["items"]) == 50
    assert measured_ms < 1000, f"10k catalog query: {measured_ms:.1f} ms"


def test_create_app_root_does_not_read_default_global_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_database = _database(tmp_path / "global", monkeypatch)
    _insert(global_database, "global-only", "2026-01-01T00:00:00Z")
    root = tmp_path / "isolated-sessions"
    scoped_database = root / ".lnt" / "catalog.sqlite3"
    apply_migrations(scoped_database)
    _insert(scoped_database, "scoped-only", "2026-01-02T00:00:00Z")

    with TestClient(create_app(root=root)) as client:
        response = client.get("/api/catalog/sessions")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["scoped-only"]
