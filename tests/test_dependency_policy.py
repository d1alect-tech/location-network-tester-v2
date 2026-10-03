from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Final, TypedDict
from urllib.parse import urlparse

import pytest

ROOT: Final = Path(__file__).resolve().parent.parent
MANIFEST: Final = ROOT / "dependency-manifest.json"
STATIC_ROOT: Final = ROOT / "src" / "lnt" / "ui" / "static"

APPROVED_LICENSES: Final = frozenset(
    {
        "Apache-2.0",
        "Apache-2.0 OR BSD-2-Clause",
        "Apache-2.0 OR BSD-3-Clause",
        "Apache-2.0 OR GPL-2.0-or-later",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
        "GPL-2.0-or-later WITH Bootloader-exception",
        "GPL-3.0-only",
        "LGPL-2.1-or-later",
        "MIT",
        "MIT-CMU",
        "OFL-1.1",
        "PSF-2.0",
        "PSF-based",
    }
)
HTML_REMOTE_ASSET = re.compile(
    r"<(?:script|link|img|source)\b[^>]*\b(?:src|href)\s*=\s*[\"'](https?://[^\"']+)",
    re.IGNORECASE,
)
JS_REMOTE_FETCH = re.compile(
    r"(?:fetch|importScripts|import)\s*\(\s*[\"'](https?://[^\"']+)",
)


class Dependency(TypedDict):
    name: str
    version: str
    license: str
    source_url: str
    hash: str
    scope: str


def _load_manifest(path: Path) -> list[Dependency]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _policy_errors(entries: list[Dependency]) -> list[str]:
    errors: list[str] = []
    for entry in entries:
        name = entry.get("name", "<unnamed>")
        if entry.get("license") not in APPROVED_LICENSES:
            errors.append(f"{name}: unapproved or missing license")
        if not entry.get("source_url"):
            errors.append(f"{name}: missing source URL")
        if not entry.get("hash"):
            errors.append(f"{name}: missing hash")
    return errors


def _is_external(url: str) -> bool:
    hostname = urlparse(url).hostname
    return hostname not in {"127.0.0.1", "localhost", "::1"}


def test_dependency_manifest_satisfies_allowlist_and_provenance_policy() -> None:
    entries = _load_manifest(MANIFEST)

    errors = _policy_errors(entries)

    assert errors == []


def test_hantek_patch_marks_retained_modified_files() -> None:
    patch = (ROOT / "packaging" / "hantek-6022be.patch").read_text(encoding="utf-8")
    notice = (
        "+# Modified by LNT contributors on 2026-09-10 to restrict the packaged runtime "
        "to Hantek 6022BE."
    )
    retained_paths = ("PyHT6022/Firmware/__init__.py", "PyHT6022/LibUsbScope.py")

    missing = []
    for path in retained_paths:
        section = patch.split(f"diff --git a/{path} b/{path}\n", maxsplit=1)[1].split(
            "\ndiff --git ", maxsplit=1
        )[0]
        if notice not in section.splitlines():
            missing.append(path)

    assert missing == []


def test_project_license_is_consistent_across_release_metadata() -> None:
    license_id = "GPL-3.0-only"
    manifest = _load_manifest(MANIFEST)
    hantek = next(entry for entry in manifest if entry["name"] == "hantek6022api")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert (ROOT / "LICENSE").read_bytes() == (ROOT / "LICENSES" / "GPL-3.0.txt").read_bytes()
    assert project["license"] == license_id
    assert license_id in readme
    assert hantek["license"] == license_id


def test_public_release_policy_contract() -> None:
    expected_assets = {
        "LNT-0.1.0-win64.zip",
        "LNT-0.1.0-win64.zip.sha256",
        "LNT-0.1.0-corresponding-source.zip",
        "LNT-0.1.0-corresponding-source.zip.sha256",
    }
    policy_paths = (
        ROOT / "AGENTS.md",
        ROOT / "README.md",
        ROOT / "docs" / "distribution-policy.md",
        ROOT / "docs" / "packaging-notices.md",
    )
    notice_path = ROOT / "packaging" / "SOURCE.txt"
    policy_texts = [path.read_text(encoding="utf-8") for path in policy_paths]
    notice_text = notice_path.read_text(encoding="utf-8")
    audit_text = (ROOT / "scripts" / "audit-scope.ps1").read_text(encoding="utf-8-sig")
    packager_text = (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8-sig")
    source_builder_text = (ROOT / "scripts" / "release_sources.py").read_text(encoding="utf-8")
    spec_text = (ROOT / "packaging" / "lnt.spec").read_text(encoding="utf-8")
    release_policy_text = "\n".join([*policy_texts, notice_text, audit_text])

    assert all("GPL-3.0-only" in text for text in [*policy_texts, notice_text])
    assert "GPL-3.0-or-later" not in release_policy_text
    assert "public" in packager_text.lower()
    assert '$zipName = "LNT-$projectVersion-win64.zip"' in packager_text
    assert 'f"LNT-{version}-corresponding-source.zip"' in source_builder_text
    assert all(
        expected_assets <= set(re.findall(r"LNT-0\.1\.0-[\w.-]+", text)) for text in policy_texts
    )
    assert "PRIVATE-USE" not in release_policy_text
    assert "private_one_folder_windows_package" not in release_policy_text
    assert "private_use_label_present" not in release_policy_text
    assert "private-use.zip" not in release_policy_text.lower()
    assert not (ROOT / "packaging" / "PRIVATE-USE.txt").exists()
    assert (ROOT / "LICENSE").is_file()
    assert '(str(ROOT / "LICENSE"), ".")' in spec_text


def test_source_notice_names_the_current_release_assets() -> None:
    """SOURCE.txt ships inside the release it describes, so it tracks the live version."""
    version: str = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    text = (ROOT / "packaging" / "SOURCE.txt").read_text(encoding="utf-8")
    expected_assets = {
        f"LNT-{version}-win64.zip",
        f"LNT-{version}-win64.zip.sha256",
        f"LNT-{version}-corresponding-source.zip",
        f"LNT-{version}-corresponding-source.zip.sha256",
    }

    assert expected_assets <= set(re.findall(rf"LNT-{re.escape(version)}-[\w.-]+", text))
    assert f"/releases/tag/v{version}" in text
    assert text.startswith(f"Исходники Windows-релиза LNT {version}")


def test_dependency_policy_rejects_dependency_without_license(tmp_path: Path) -> None:
    entries = _load_manifest(MANIFEST)
    copied_manifest = tmp_path / "dependency-manifest.json"
    entries.append(
        {
            "name": "fixture-without-license",
            "version": "1.0.0",
            "license": "",
            "source_url": "https://example.invalid/source.tar.gz",
            "hash": "sha256:fixture",
            "scope": "dev",
        }
    )
    copied_manifest.write_text(json.dumps(entries), encoding="utf-8")

    errors = _policy_errors(_load_manifest(copied_manifest))

    assert errors == ["fixture-without-license: unapproved or missing license"]


@pytest.mark.parametrize("suffix", [".html", ".js"])
def test_static_assets_do_not_fetch_remote_runtime_resources(suffix: str) -> None:
    violations: list[str] = []
    pattern = HTML_REMOTE_ASSET if suffix == ".html" else JS_REMOTE_FETCH
    for path in STATIC_ROOT.rglob(f"*{suffix}"):
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)}: {url}" for url in pattern.findall(text) if _is_external(url)
        )

    assert violations == []
