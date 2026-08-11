from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lnt.ui.app import create_app


def test_profile_crud_preserves_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    payload = {
        "kind": "location",
        "data": {"alias": "стенд", "outlet": "A-3", "circuit": "lab"},
    }
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        created = client.post("/api/profiles/lab-main", json=payload, headers=headers)
        listed = client.get("/api/profiles")
        shown = client.get("/api/profiles/lab-main")
        updated_payload = {
            "kind": "location",
            "data": {"alias": "стенд 2", "outlet": "A-3", "circuit": "lab"},
        }
        updated = client.put("/api/profiles/lab-main", json=updated_payload, headers=headers)
        history = client.get("/api/profiles/lab-main/history")
        deleted = client.delete("/api/profiles/lab-main", headers=headers)
        missing = client.get("/api/profiles/lab-main")

    assert created.status_code == 201
    assert listed.json()["items"][0]["profile_id"] == "lab-main"
    assert shown.json()["revision"] == 1
    assert updated.json()["revision"] == 2
    assert [item["revision"] for item in history.json()["items"]] == [1, 2]
    assert deleted.status_code == 204
    assert missing.status_code == 404


def test_profile_rejects_traversal_and_invalid_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
        traversal = client.post(
            "/api/profiles/..%5C..",
            json={"kind": "location", "data": {}},
            headers=headers,
        )
        invalid = client.post(
            "/api/profiles/lab",
            json={"kind": "sql", "data": {}},
            headers=headers,
        )

    assert traversal.status_code in {404, 422}
    assert invalid.status_code == 422
    assert "некоррект" in invalid.json()["detail"]
