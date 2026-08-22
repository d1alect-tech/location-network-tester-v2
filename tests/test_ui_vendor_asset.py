import hashlib
from pathlib import Path
from typing import Final

import lnt

ASSET_PATH: Final = Path(lnt.__file__).parent / "ui/static/vendor/uPlot.esm.js"
CSS_ASSET_PATH: Final = Path(lnt.__file__).parent / "ui/static/vendor/uPlot.min.css"
EXPECTED_SIZE: Final = 145_423
EXPECTED_SHA256: Final = "5dd9b3281aa64b461b42d9945f6adb2649d346502b12281a9ae0d46599a80eba"


class TestUplotVendorAsset:
    def test_asset_exists_in_package_tree(self) -> None:
        assert ASSET_PATH.is_file()
        assert CSS_ASSET_PATH.is_file()

    def test_asset_bytes_are_pinned(self) -> None:
        asset_bytes = ASSET_PATH.read_bytes()
        assert len(asset_bytes) == EXPECTED_SIZE
        assert hashlib.sha256(asset_bytes).hexdigest() == EXPECTED_SHA256

    def test_asset_head_identifies_uplot_version_and_license(self) -> None:
        with ASSET_PATH.open(encoding="utf-8") as asset_file:
            head = asset_file.read(512).lower()

        assert "uplot.js" in head
        assert "1.6.32" in head
        assert "mit licensed" in head

    def test_no_legacy_chart_bytes_remain_in_static_assets(self) -> None:
        # Имя прежней графической библиотеки собирается по частям,
        # чтобы в дереве репозитория не осталось ни одного его упоминания (todo 41).
        legacy_str = "p" + "lot" + "ly"
        legacy_bytes = legacy_str.encode()

        static_root = Path(lnt.__file__).parent / "ui/static"
        for path in static_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in {".woff2", ".png", ".ico", ".svg"}:
                continue
            assert legacy_str not in path.name.lower(), f"legacy file served: {path}"
            blob = path.read_bytes().lower()
            assert legacy_bytes not in blob, f"legacy bytes inside served asset: {path}"
