from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from lnt.catalog.connection import writer_transaction
from lnt.catalog.migrations import apply_migrations
from lnt.context.model import ContextField, ContextSnapshot
from lnt.context.store import ContextStore, ContextUpdate
from lnt.ripple.adapter_declaration import AdapterDeclaration, declaration_fields
from lnt.simulate import simulate_session
from lnt.types import ComponentValuesBasis
from lnt.ui.app import create_app
from lnt.ui.models_context import ContextFieldModel

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import pytest

_CAPTURED_AT = "2026-10-23T08:00:00.000Z"


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


def _seed_adapter_declaration(tmp_path: Path, session_id: str = "known") -> ContextSnapshot:
    """Кладёт write-once декларацию так же, как lnt.capture при захвате."""
    declaration = AdapterDeclaration(
        cap_nf=100.0,
        series_r_ohm=470.0,
        preconnected=True,
        component_values_basis=ComponentValuesBasis.OPERATOR_MEASURED,
    )
    fields = declaration_fields(declaration, _CAPTURED_AT)
    snapshot = ContextSnapshot(
        schema_version=1,
        session_id=session_id,
        revision=1,
        fields=fields,
        tags=(),
        notes=None,
        profile_snapshots=(),
    )
    ContextStore(tmp_path / "sessions" / session_id, session_id).update(
        ContextUpdate(
            expected_revision=0,
            snapshot=snapshot,
            actor="lnt.capture",
            changed_keys=tuple(sorted(fields)),
            occurred_at=_CAPTURED_AT,
            event_id=f"initial-{session_id}",
        ),
    )
    return snapshot


def _field_payloads(fields: Mapping[str, ContextField]) -> dict[str, dict[str, object]]:
    """Поля контекста в JSON-форме тела PUT: byte-faithful round-trip."""
    return {
        key: ContextFieldModel.model_validate(field, from_attributes=True).model_dump(mode="json")
        for key, field in fields.items()
    }


def test_put_keeps_unchanged_adapter_keys_and_edits_notes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path, monkeypatch) as client:
        seeded = _seed_adapter_declaration(tmp_path)
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        response = client.put(
            "/api/context/known",
            json={
                "expected_revision": seeded.revision,
                "fields": _field_payloads(seeded.fields),
                "notes": "проверено",
            },
            headers=headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == 2
    assert body["notes"] == "проверено"
    assert set(body["fields"]) == set(seeded.fields)
    assert body["fields"]["adapter.cap_nf"]["value"] == 100.0


def test_put_changing_adapter_field_is_409_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path, monkeypatch) as client:
        seeded = _seed_adapter_declaration(tmp_path)
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        payloads = _field_payloads(seeded.fields)
        payloads["adapter.cap_nf"]["value"] = 200.0
        response = client.put(
            "/api/context/known",
            json={"expected_revision": seeded.revision, "fields": payloads},
            headers=headers,
        )
        current = client.get("/api/context/known")

    assert response.status_code == 409
    assert response.json()["reason"] == "adapter_declaration_immutable"
    assert "декларация адаптера" in response.json()["detail"]
    assert current.json()["revision"] == seeded.revision
    assert current.json()["fields"]["adapter.cap_nf"]["value"] == 100.0


def test_put_removing_adapter_key_is_409_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path, monkeypatch) as client:
        seeded = _seed_adapter_declaration(tmp_path)
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        payloads = _field_payloads(seeded.fields)
        del payloads["adapter.preconnected"]
        response = client.put(
            "/api/context/known",
            json={"expected_revision": seeded.revision, "fields": payloads},
            headers=headers,
        )

    assert response.status_code == 409
    assert response.json()["reason"] == "adapter_declaration_immutable"
    assert "декларация адаптера" in response.json()["detail"]


def test_put_adding_adapter_keys_without_declaration_is_409_capture_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path, monkeypatch) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        declaration = AdapterDeclaration(
            cap_nf=100.0,
            series_r_ohm=470.0,
            preconnected=True,
            component_values_basis=ComponentValuesBasis.NOMINAL,
        )
        response = client.put(
            "/api/context/known",
            json={
                "expected_revision": 0,
                "fields": _field_payloads(declaration_fields(declaration, _CAPTURED_AT)),
            },
            headers=headers,
        )

    assert response.status_code == 409
    assert response.json()["reason"] == "adapter_declaration_capture_only"
    assert "только в момент захвата" in response.json()["detail"]


def test_legacy_session_without_declaration_accepts_other_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path, monkeypatch) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        response = client.put(
            "/api/context/known",
            json={
                "expected_revision": 0,
                "fields": {
                    "session.label": {
                        "kind": "string",
                        "value": "лаборатория",
                        "unit": None,
                        "uncertainty": None,
                        "source": "user",
                        "collection_status": "collected",
                        "collection_reason": None,
                        "captured_at": _CAPTURED_AT,
                    }
                },
            },
            headers=headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == 1
    assert body["fields"]["session.label"]["value"] == "лаборатория"


def test_put_adds_label_alongside_unchanged_declaration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path, monkeypatch) as client:
        seeded = _seed_adapter_declaration(tmp_path)
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        payloads = _field_payloads(seeded.fields)
        payloads["session.label"] = {
            "kind": "string",
            "value": "стенд 3",
            "unit": None,
            "uncertainty": None,
            "source": "user",
            "collection_status": "collected",
            "collection_reason": None,
            "captured_at": _CAPTURED_AT,
        }
        response = client.put(
            "/api/context/known",
            json={"expected_revision": seeded.revision, "fields": payloads, "tags": ["ripple"]},
            headers=headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == 2
    assert body["tags"] == ["ripple"]
    assert body["fields"]["session.label"]["value"] == "стенд 3"
    assert body["fields"]["adapter.cap_nf"]["value"] == 100.0


def test_put_stale_revision_with_declaration_is_still_409_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path, monkeypatch) as client:
        seeded = _seed_adapter_declaration(tmp_path)
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        stale = client.put(
            "/api/context/known",
            json={
                "expected_revision": 0,
                "fields": _field_payloads(seeded.fields),
                "notes": "устарело",
            },
            headers=headers,
        )

    assert stale.status_code == 409
    assert stale.json()["current_revision"] == seeded.revision
    assert "конфликт" in stale.json()["detail"]
