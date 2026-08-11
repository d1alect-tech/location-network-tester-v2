from __future__ import annotations

import json
import re
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
        "GPL-3.0-or-later",
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
