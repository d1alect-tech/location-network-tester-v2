from __future__ import annotations

import importlib.util
import json
import re
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/release_lockcheck.py"
SPEC = importlib.util.spec_from_file_location("release_lockcheck", SCRIPT)
assert SPEC
assert SPEC.loader
LOCKCHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCKCHECK)
ROOT = SCRIPT.parents[1]


def _source_manifest() -> dict[str, object]:
    return json.loads((ROOT / "release-source-inputs.json").read_text(encoding="utf-8"))


def _source_records(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    inputs = manifest["inputs"]
    assert isinstance(inputs, list)
    records: dict[str, dict[str, object]] = {}
    for record in inputs:
        assert isinstance(record, dict)
        name = record.get("name")
        assert isinstance(name, str)
        records[name] = record
    return records


def test_source_input_schema_accepts_repository_manifest() -> None:
    errors: list[str] = []
    records = LOCKCHECK.validate_source_inputs(ROOT, errors)
    assert not errors
    assert {record["name"] for record in records} >= {
        "astral-python-build-standalone",
        "hantek6022api",
        "echarts",
        "fontsource-inter",
    }


def test_source_input_schema_rejects_wrong_required_pin(tmp_path: Path) -> None:
    manifest = _source_manifest()
    inputs = manifest["inputs"]
    assert isinstance(inputs, list)
    first_input = inputs[0]
    assert isinstance(first_input, dict)
    first_input["commit"] = "0" * 40
    (tmp_path / "release-source-inputs.json").write_text(json.dumps(manifest))
    errors: list[str] = []
    LOCKCHECK.validate_source_inputs(tmp_path, errors)
    assert "wrong commit for 'astral-python-build-standalone'" in "\n".join(errors)


def test_source_input_schema_checks_commit_and_archive_hash(tmp_path: Path) -> None:
    manifest = _source_manifest()
    records = _source_records(manifest)
    records["libffi"]["sha256"] = "0" * 64
    (tmp_path / "release-source-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
    errors: list[str] = []
    LOCKCHECK.validate_source_inputs(tmp_path, errors)
    assert "wrong sha256 for 'libffi'" in "\n".join(errors)


def test_libffi_pin_matches_pinned_windows_builder_recipe() -> None:
    manifest = _source_manifest()
    records = _source_records(manifest)
    builder = records["astral-python-build-standalone"]
    builder_archive = ROOT / "build/release-source-cache" / str(builder["sha256"])
    with zipfile.ZipFile(builder_archive) as archive:
        root = f"{builder['archive_root']}/"
        windows_recipe = archive.read(f"{root}cpython-windows/build.py").decode()
        downloads = archive.read(f"{root}pythonbuild/downloads.py").decode()

    build_libffi = windows_recipe.split("def build_libffi(", maxsplit=1)[1].split(
        "\ndef ", maxsplit=1
    )[0]
    checkout = re.search(r'"checkout",\s*"([0-9a-f]{40})"', build_libffi)
    assert checkout
    assert records["libffi"]["commit"] == checkout.group(1)
    assert 'DOWNLOADS["libffi"]' not in build_libffi
    assert '"version": "3.4.6"' in downloads

    source_archive = ROOT / "build/release-source-cache" / str(records["libffi"]["sha256"])
    with zipfile.ZipFile(source_archive) as archive:
        configure_name = next(name for name in archive.namelist() if name.endswith("/configure.ac"))
        configure = archive.read(configure_name).decode()
    assert "AC_INIT([libffi], [3.4.2]" in configure


def test_scipy_compiler_metadata_does_not_claim_unrelated_gcc_source() -> None:
    scipy_spec = importlib.util.find_spec("scipy")
    assert scipy_spec
    assert scipy_spec.origin
    scipy_config = Path(scipy_spec.origin).with_name("__config__.py").read_text(encoding="utf-8")
    compiler_versions = set(
        re.findall(r'"name": "gcc",\s+"linker":.*?\s+"version": "([^"]+)"', scipy_config)
    )
    assert compiler_versions == {"15.2.0"}
    assert '"name": "scipy-openblas"' in scipy_config
    assert '"version": "0.3.31.dev"' in scipy_config

    manifest = _source_manifest()
    records = _source_records(manifest)
    assert "gcc" not in records
    required_native = manifest["required_native"]
    assert isinstance(required_native, list)
    assert "gcc" not in required_native
