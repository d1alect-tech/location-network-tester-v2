from pathlib import Path

import pytest
from starlette.testclient import TestClient

from lnt.ui.app import create_app


def _nonce(client: TestClient) -> str:
    value = client.get("/api/config").json()["mutation_nonce"]
    assert isinstance(value, str)
    return value


@pytest.mark.parametrize("headers", [{}, {"X-LNT-Mutation-Nonce": "wrong"}])
def test_mutation_requires_per_launch_nonce(tmp_path: Path, headers: dict[str, str]) -> None:
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.post("/api/jobs", headers=headers, json={"kind": "selftest"})

    assert response.status_code == 403
    assert response.json() == {
        "code": "mutation_nonce_invalid",
        "detail": "изменяющий запрос отклонён: неверный одноразовый nonce запуска",
    }


def test_old_constant_header_alone_is_rejected(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.post(
            "/api/jobs",
            headers={"X-LNT-Request": "ui"},
            json={"kind": "selftest"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "mutation_nonce_invalid"


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ({"host": "attacker.example"}, "host_not_loopback"),
        ({"origin": "https://attacker.example"}, "origin_not_loopback"),
    ],
)
def test_non_loopback_host_or_origin_is_rejected(
    tmp_path: Path,
    headers: dict[str, str],
    code: str,
) -> None:
    with TestClient(create_app(root=tmp_path), base_url="http://127.0.0.1") as client:
        request_headers = {"X-LNT-Mutation-Nonce": _nonce(client), **headers}
        response = client.post("/api/jobs", headers=request_headers, json={"kind": "selftest"})

    assert response.status_code == 403
    assert response.json()["code"] == code


def test_request_body_limit_is_enforced_before_validation(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.post(
            "/api/jobs",
            headers={"X-LNT-Mutation-Nonce": _nonce(client)},
            content=b"x" * 1_048_577,
        )

    assert response.status_code == 413
    assert response.json()["code"] == "request_body_too_large"


def test_security_headers_and_cache_contract(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path)) as client:
        index = client.get("/")
        config = client.get("/api/config").json()
        asset = client.get(config["static_assets"]["app"])

    assert index.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in index.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in index.headers["content-security-policy"]
    assert index.headers["x-content-type-options"] == "nosniff"
    assert index.headers["referrer-policy"] == "no-referrer"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert f".{config['static_asset_hash']}.js" in config["static_assets"]["app"]


def test_health_config_and_index_share_build_identity(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path)) as client:
        health = client.get("/api/health").json()
        config = client.get("/api/config").json()
        index = client.get("/").text

    assert health["build_id"] == config["build_id"]
    assert f'data-build-id="{config["build_id"]}"' in index


def test_page_size_limit_is_typed_validation_error(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.get("/api/jobs?page_size=101")

    assert response.status_code == 422
    assert "page_size" in response.json()["detail"]
