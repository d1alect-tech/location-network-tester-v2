from pathlib import Path

from fastapi.testclient import TestClient

from lnt.ui.app import create_app


def test_v2_route_serves_index_and_assets(tmp_path: Path) -> None:
    app = create_app(root=tmp_path)
    with TestClient(app) as client:
        # Test /v2/ route
        response = client.get("/v2/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<title>LNT v2 Workbench</title>" in response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Content-Security-Policy"]
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"

        # Test /v2 redirect/alias
        response_alias = client.get("/v2")
        assert response_alias.status_code == 200
        assert "text/html" in response_alias.headers["content-type"]

        # Test static assets
        # Let's find a JS asset from the built directory
        static_v2_dir = Path(__file__).parent.parent / "src" / "lnt" / "ui" / "static" / "v2"
        assets_dir = static_v2_dir / "assets"
        js_files = list(assets_dir.glob("*.js"))
        assert js_files, "No JS files found in static/v2/assets"
        js_filename = js_files[0].name

        response_asset = client.get(f"/static/v2/assets/{js_filename}")
        assert response_asset.status_code == 200
        assert "javascript" in response_asset.headers["content-type"]
        # Hashed assets should have long-cache headers
        assert "Cache-Control" in response_asset.headers
        cache_ctrl = response_asset.headers["Cache-Control"]
        assert "max-age=31536000" in cache_ctrl or "no-store" not in cache_ctrl
