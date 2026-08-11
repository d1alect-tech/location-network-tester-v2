import hashlib
from pathlib import Path
from typing import Final

import lnt

ASSET_PATH: Final = Path(lnt.__file__).parent / "ui/static/vendor/plotly-gl2d-3.7.0.min.js"
EXPECTED_SIZE: Final = 1_594_705
EXPECTED_SHA256: Final = "d396c0d59e2844a167dc4aca8469fe1653060cb105f4d7cbd47b3c7788b1e750"


class TestPlotlyVendorAsset:
    def test_asset_exists_in_package_tree(self) -> None:
        assert ASSET_PATH.is_file()

    def test_asset_bytes_are_pinned(self) -> None:
        asset_bytes = ASSET_PATH.read_bytes()
        assert len(asset_bytes) == EXPECTED_SIZE
        assert hashlib.sha256(asset_bytes).hexdigest() == EXPECTED_SHA256

    def test_asset_head_identifies_plotly_version(self) -> None:
        with ASSET_PATH.open(encoding="utf-8") as asset_file:
            head = asset_file.read(512).lower()

        assert "plotly.js" in head
        assert "3.7.0" in head
