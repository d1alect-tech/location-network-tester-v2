"""Verify locked dependencies for the reproducible-release quality gate.

Cross-checks ``dependency-manifest.json`` against the real sources of truth:
``uv.lock`` for Python packages, ``frontend/package-lock.json`` for the vendored
uPlot pin and ``src/lnt/ui/static/fonts/manifest.json`` for the vendored IBM
Plex WOFF2 files (SHA-256 recomputed from disk).  Optionally compares the
canonical fingerprint of ``frontend/package-lock.json`` against a freshly
regenerated copy to prove the lock is not stale versus ``package.json``.

Emits a strict JSON verdict consumed by ``scripts/quality.ps1``.
Exit codes: 0 verified; 1 semantic mismatch; 2 malformed input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

HASH_PATTERN: Final = re.compile(r"^(sha256:[0-9a-f]{64}|git-commit:[0-9a-f]{40})$")
REQUIRED_FIELDS: Final = ("name", "version", "license", "source_url", "hash", "scope")
VALID_SCOPES: Final = frozenset({"runtime", "dev", "vendored"})
FONT_FAMILIES: Final = {"sans": "Sans", "mono": "Mono"}
FONT_WEIGHTS: Final = {"regular": "Regular", "medium": "Medium", "semibold": "SemiBold"}
PLEX_PACKAGE_NAMES: Final = {"sans": "@ibm/plex-sans", "mono": "@ibm/plex-mono"}
UPLOT_LOCK_KEY: Final = "node_modules/uplot"
EXIT_OK: Final = 0
EXIT_MISMATCH: Final = 1
EXIT_MALFORMED: Final = 2


class LockCheckError(Exception):
    """Malformed input: the gate must stop before any semantic comparison."""


def _load_json(path: Path) -> object:
    """Read and parse a JSON file, mapping every failure to a typed error."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"unreadable input {path}: {exc}"
        raise LockCheckError(msg) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"malformed JSON in {path}: {exc}"
        raise LockCheckError(msg) from exc


def _canonical_sha256(value: object) -> str:
    """Stable fingerprint: sorted keys, compact separators, UTF-8 bytes."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _str_field(entry: object, field: str, where: str, errors: list[str]) -> str | None:
    if not isinstance(entry, dict):
        errors.append(f"{where}: entry is not an object")
        return None
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: field '{field}' must be a non-empty string")
        return None
    return value


def _validate_manifest(root: Path, errors: list[str]) -> list[dict[str, str]]:
    """Strict schema validation of dependency-manifest.json."""
    raw = _load_json(root / "dependency-manifest.json")
    if not isinstance(raw, list):
        errors.append("dependency-manifest.json: top level must be an array")
        return []
    seen: set[tuple[str, str]] = set()
    entries: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        where = f"dependency-manifest.json[{index}]"
        fields: dict[str, str] = {}
        for field in REQUIRED_FIELDS:
            value = _str_field(item, field, where, errors)
            if value is None:
                continue
            fields[field] = value
        if len(fields) != len(REQUIRED_FIELDS):
            continue
        if fields["scope"] not in VALID_SCOPES:
            errors.append(f"{where}: unknown scope '{fields['scope']}'")
            continue
        if HASH_PATTERN.match(fields["hash"]) is None:
            errors.append(f"{where}: hash must be sha256:<64 hex> or git-commit:<40 hex>")
            continue
        key = (fields["name"], fields["scope"])
        if key in seen:
            errors.append(f"{where}: duplicate name/scope '{fields['name']}'")
            continue
        seen.add(key)
        entries.append(fields)
    return entries


def _uv_versions(root: Path, errors: list[str]) -> dict[str, str]:
    """Name -> version map of every package locked in uv.lock."""
    try:
        data = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"malformed uv.lock: {exc}"
        raise LockCheckError(msg) from exc
    packages = data.get("package")
    if not isinstance(packages, list):
        errors.append("uv.lock: missing [[package]] table array")
        return {}
    versions: dict[str, str] = {}
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            errors.append(f"uv.lock[package:{index}]: entry is not a table")
            continue
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            errors.append(f"uv.lock[package:{index}]: name/version must be strings")
            continue
        versions.setdefault(name, version)
    return versions


def _fonts_manifest(root: Path, errors: list[str]) -> dict[str, object]:
    """Read fonts/manifest.json or return an empty mapping with recorded errors."""
    raw = _load_json(root / "src/lnt/ui/static/fonts/manifest.json")
    if not isinstance(raw, dict):
        errors.append("fonts/manifest.json: top level must be an object")
        return {}
    return raw


def _font_file_hash(root: Path, name: str, errors: list[str]) -> str | None:
    """Recompute the SHA-256 of a vendored WOFF2 file named like the manifest entry."""
    parts = name.removeprefix("ibm-plex-").split("-")
    family_key, weight_key = parts[0], "-".join(parts[1:])
    family = FONT_FAMILIES.get(family_key)
    weight = FONT_WEIGHTS.get(weight_key)
    if family is None or weight is None:
        errors.append(f"vendored font '{name}': cannot map to IBM Plex file name")
        return None
    path = root / "src/lnt/ui/static/fonts" / f"IBMPlex{family}-{weight}.woff2"
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        errors.append(f"vendored font '{name}': file missing on disk: {path.name}")
        return None
    return digest


def _check_vendored(
    root: Path,
    entries: Iterable[dict[str, str]],
    fonts: dict[str, object],
    errors: list[str],
) -> dict[str, str]:
    """Verify vendored pins against package-lock.json and on-disk font hashes."""
    packages = fonts.get("packages")
    font_packages: dict[str, dict[str, object]] = {}
    if isinstance(packages, list):
        for package in packages:
            if isinstance(package, dict) and isinstance(package.get("name"), str):
                font_packages[str(package["name"])] = package
    else:
        errors.append("fonts/manifest.json: 'packages' must be an array")
    checked: dict[str, str] = {}
    for entry in entries:
        name = entry["name"]
        if name == "uplot":
            checked[name] = entry["version"]
            continue
        if not name.startswith("ibm-plex-"):
            errors.append(f"vendored entry '{name}': unknown vendored component")
            continue
        family_key = name.removeprefix("ibm-plex-").split("-")[0]
        package = font_packages.get(PLEX_PACKAGE_NAMES.get(family_key, ""))
        if package is None:
            errors.append(f"vendored font '{name}': package absent from fonts/manifest.json")
            continue
        version = package.get("version")
        if version != entry["version"]:
            errors.append(f"vendored font '{name}': manifest {entry['version']} != fonts {version}")
        expected = _font_file_hash(root, name, errors)
        if expected is not None and f"sha256:{expected}" != entry["hash"]:
            errors.append(f"vendored font '{name}': recorded hash differs from file on disk")
        checked[name] = entry["version"]
    return checked


def verify(root: Path, npm_regen_dir: Path | None) -> dict[str, object]:
    """Run every lock cross-check and return the verdict payload."""
    errors: list[str] = []
    manifest = _validate_manifest(root, errors)
    uv = _uv_versions(root, errors)
    fonts = _fonts_manifest(root, errors)

    runtime = [e for e in manifest if e["scope"] == "runtime"]
    dev = [e for e in manifest if e["scope"] == "dev"]
    vendored = [e for e in manifest if e["scope"] == "vendored"]
    for entry in runtime + dev:
        locked = uv.get(entry["name"])
        if locked is None:
            errors.append(f"{entry['scope']} '{entry['name']}' is absent from uv.lock")
        elif locked != entry["version"]:
            errors.append(
                f"{entry['scope']} '{entry['name']}': manifest {entry['version']}"
                f" != uv.lock {locked}"
            )
    vendored_checked = _check_vendored(root, vendored, fonts, errors)

    lock_path = root / "frontend/package-lock.json"
    fingerprint = _canonical_sha256(_load_json(lock_path))
    if npm_regen_dir is not None:
        regen = _canonical_sha256(_load_json(npm_regen_dir / "package-lock.json"))
        if regen != fingerprint:
            errors.append(
                "frontend/package-lock.json is stale versus frontend/package.json"
                " (regenerated lock differs)"
            )

    uplot_version = vendored_checked.get("uplot", "")
    return {
        "ok": not errors,
        "errors": sorted(errors),
        "checked": {
            "manifest_entries": len(manifest),
            "runtime": len(runtime),
            "dev": len(dev),
            "vendored": len(vendored),
            "uv_packages": len(uv),
        },
        "entries": sorted(manifest, key=lambda e: (e["scope"], e["name"])),
        "uplot_version": uplot_version,
        "npm_lock_fingerprint": fingerprint,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse args, verify, write verdict JSON, exit coded."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="repository root directory")
    parser.add_argument("--out", required=True, help="path of the JSON verdict to write")
    parser.add_argument(
        "--npm-regen-dir",
        help="directory holding a freshly regenerated package-lock.json copy",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    out_path = Path(args.out)
    regen = Path(args.npm_regen_dir) if args.npm_regen_dir else None
    try:
        verdict = verify(root, regen)
        exit_code = EXIT_OK if verdict["ok"] else EXIT_MISMATCH
    except LockCheckError as exc:
        verdict = {"ok": False, "errors": [str(exc)]}
        exit_code = EXIT_MALFORMED
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    for error in verdict["errors"]:
        sys.stderr.write(f"LOCKCHECK ERROR: {error}\n")
    sys.stderr.write(f"LOCKCHECK EXIT_CODE={exit_code}\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
