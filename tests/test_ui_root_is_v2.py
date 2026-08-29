from pathlib import Path

from starlette.testclient import TestClient

from lnt.ui.app import create_app


def test_root_serves_v2_workbench_html_no_store(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "LNT v2 Workbench" in response.text
    assert response.headers["cache-control"] == "no-store"
