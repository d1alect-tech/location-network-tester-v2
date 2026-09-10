"""Build a deterministic LNT Corresponding Source archive from committed HEAD."""

from __future__ import annotations

import argparse
import io
import json
import shutil
import stat
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
import zlib
from collections.abc import Container, Iterable  # noqa: TC003
from hashlib import sha1, sha256
from pathlib import Path, PurePosixPath

BUILDING = """# Building LNT from Corresponding Source

`project/` is the exact source. `SHA256SUMS` verifies every listed file,
including files under generated or dependency directories. During the
additional-file inventory, `-SourceArchive` ignores only known generated,
dependency, and Python cache directories.

From this archive's root, prepare the locked Python and frontend dependencies,
build the frontend, then run the package build:

```powershell
uv sync --locked --python 3.12 --all-extras --project project
npm --prefix project/frontend ci
npm --prefix project/frontend run build
powershell -File project/packaging/build.ps1 -Clean -Evidence evidence -SourceArchive `
  -HantekSource sources/hantek/hantek.git
```

These preparation commands install locked dependencies and build the frontend.
They do not rebuild every bundled native component from source; component
source archives, pins, and build paths are recorded in `SOURCE-MANIFEST.json`.
"""

GIT = shutil.which("git") or "git"


class SourceError(Exception):
    """Report an invalid or incomplete Corresponding Source build."""


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(  # noqa: S603
        [GIT, *args], cwd=root, capture_output=True, check=False
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise SourceError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _safe_member(raw: str) -> str:
    normalized = raw.replace("\\", "/")
    raw_parts = normalized.rstrip("/").split("/")
    parts = PurePosixPath(normalized.rstrip("/")).parts
    if any(part in {"", ".", ".."} for part in raw_parts) or (
        not normalized or normalized.startswith("/") or ":" in normalized
    ):
        raise SourceError(f"unsafe archive member: {raw!r}")
    return "/".join(parts)


def _check_tar_link(name: str, link: str | None, regular: set[str]) -> None:
    if not link or PurePosixPath(link).is_absolute() or ":" in link:
        raise SourceError(f"unsafe archive link target: {name}")
    target = list(PurePosixPath(name).parent.parts)
    for part in PurePosixPath(link).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if len(target) <= 1:
                raise SourceError(f"unsafe archive link target: {name}")
            target.pop()
        else:
            target.append(part)
    if "/".join(target) not in regular:
        raise SourceError(f"unsafe archive link target: {name}")


def _validate_archive(data: bytes, record: dict[str, object]) -> None:
    expects_zip = str(record["url"]).split("?", 1)[0].lower().endswith(".zip")
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [
                (info.filename, not info.is_dir(), stat.S_IFMT(info.external_attr >> 16), None)
                for info in archive.infolist()
            ]
            safe = {0, stat.S_IFREG, stat.S_IFDIR}
            if record["kind"] == "hantek":
                safe.add(stat.S_IFLNK)
            _check_archive_members(members, record, safe)
        return
    if expects_zip:
        raise SourceError(f"source ZIP/member mismatch for {record['name']}")
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            members = [(item.name, item.isfile(), item.type, item.linkname) for item in archive]
            _check_archive_members(
                members,
                record,
                {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE, tarfile.SYMTYPE},
            )
    except tarfile.TarError as exc:
        raise SourceError(f"source ZIP/member mismatch for {record['name']}") from exc


def _check_archive_members(
    members: Iterable[tuple[str, bool, object, str | None]],
    record: dict[str, object],
    safe: Container[object],
) -> None:
    files = 0
    root = str(record["archive_root"])
    seen: set[str] = set()
    normalized = [
        (_safe_member(name), is_file, member_type, link)
        for name, is_file, member_type, link in members
    ]
    regular = {
        name
        for name, _, member_type, _ in normalized
        if member_type in {tarfile.REGTYPE, tarfile.AREGTYPE}
    }
    for name, is_file, member_type, link in normalized:
        key = name if record["kind"] == "hantek" else name.casefold()
        if key in seen:
            raise SourceError(f"duplicate archive member: {name}")
        seen.add(key)
        if member_type not in safe:
            raise SourceError(f"unsafe archive member type: {name}")
        if member_type == tarfile.SYMTYPE:
            _check_tar_link(name, link, regular)
        files += int(is_file)
        if PurePosixPath(name).parts[0] != root:
            raise SourceError(f"archive root mismatch for {record['name']}: {name}")
    if not files:
        raise SourceError(f"source ZIP/member mismatch for {record['name']}")


def _runtime_records(root: Path, seen: set[str]) -> list[dict[str, object]]:
    dependencies = _load_json(root / "dependency-manifest.json")
    if not isinstance(dependencies, list):
        raise SourceError("dependency-manifest.json must be an array")
    records: list[dict[str, object]] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict) or dependency.get("scope") != "runtime":
            continue
        name = str(dependency.get("name", ""))
        digest = str(dependency.get("hash", ""))
        if name.casefold() in seen or not digest.startswith("sha256:"):
            continue
        url = str(dependency.get("source_url", ""))
        root_name = Path(url).name.split(".tar.")[0].removesuffix(".tgz").removesuffix(".zip")
        records.append(
            {
                "name": name,
                "kind": "runtime",
                "url": url,
                "sha256": digest.removeprefix("sha256:"),
                "archive_root": root_name,
            }
        )
        seen.add(name.casefold())
    return records


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(root: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    raw = _load_json(root / "release-source-inputs.json")
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise SourceError("invalid release-source-inputs.json schema")
    inputs = raw.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise SourceError("release-source-inputs.json inputs must be a non-empty array")
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict):
            raise SourceError("source input must be an object")
        if any(
            not isinstance(item.get(field), str) or not item[field]
            for field in ("name", "kind", "url", "sha256", "archive_root")
        ):
            raise SourceError("source input fields must be non-empty strings")
        name = str(item["name"])
        if name.casefold() in seen or len(str(item["sha256"])) != 64:  # noqa: PLR2004
            raise SourceError(f"invalid or duplicate source input: {name}")
        commit = item.get("commit")
        if commit is not None and (
            not isinstance(commit, str) or len(commit) != 40  # noqa: PLR2004
        ):
            raise SourceError(f"invalid source commit: {name}")
        seen.add(name.casefold())
        records.append(item)
    records.extend(_runtime_records(root, seen))
    _check_coverage(root, raw, {str(item["name"]): item for item in records})
    return raw, records


def _check_required(
    manifest: dict[str, object], field: str, available: set[object], message: str
) -> None:
    required = manifest.get(field)
    if not isinstance(required, list):
        raise SourceError(f"{field} must be an array")
    for name in required:
        if name not in available:
            raise SourceError(f"{message}: {name}")


def _check_coverage(
    root: Path, manifest: dict[str, object], records: dict[str, dict[str, object]]
) -> None:
    dependencies = _load_json(root / "dependency-manifest.json")
    if not isinstance(dependencies, list):
        raise SourceError("dependency-manifest.json must be an array")
    for dependency in dependencies:
        if not isinstance(dependency, dict) or dependency.get("scope") != "runtime":
            continue
        name = str(dependency.get("name", ""))
        record = records.get(name)
        expected_hash = str(dependency.get("hash", ""))
        valid = record is not None and (
            expected_hash == f"sha256:{record['sha256']}"
            or expected_hash == f"git-commit:{record.get('commit', '')}"
        )
        source_matches = record is not None and (
            record["url"] == dependency.get("source_url") or "commit" in record
        )
        if not valid or not source_matches:
            raise SourceError(f"missing runtime sdist: {name}")
    dependency_names: set[object] = {
        item["name"]
        for item in dependencies
        if isinstance(item, dict) and item.get("scope") == "runtime" and "name" in item
    }
    runtime_available = dependency_names & records.keys()
    _check_required(manifest, "required_runtime", runtime_available, "missing runtime sdist")
    _check_required(manifest, "required_native", set(records), "missing required native source")
    _check_required(manifest, "required_frontend", set(records), "missing frontend source archive")


def _fetch(record: dict[str, object], cache: Path | None) -> bytes:
    digest = str(record["sha256"])
    cached = cache / digest if cache else None
    if cached and cached.is_file():
        data = cached.read_bytes()
    else:
        try:
            with urllib.request.urlopen(str(record["url"]), timeout=60) as response:  # noqa: S310
                data = response.read()
        except OSError as exc:
            raise SourceError(f"download failed for {record['name']}: {exc}") from exc
    actual = sha256(data).hexdigest()
    if actual != digest:
        raise SourceError(f"sha256 mismatch for {record['name']}: {actual}")
    _validate_archive(data, record)
    if cached and not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
    return data


def _project_files(root: Path) -> tuple[str, str, dict[str, bytes]]:
    commit = _git(root, "rev-parse", "HEAD").decode().strip()
    project = tomllib.loads(_git(root, "show", "HEAD:pyproject.toml").decode())["project"]
    version = str(project["version"])
    files: dict[str, bytes] = {}
    names: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(_git(root, "archive", "--format=zip", "HEAD"))) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = _safe_member(info.filename)
            if stat.S_IFMT(info.external_attr >> 16) not in {0, stat.S_IFREG}:
                raise SourceError(f"symlink/reparse project entry rejected: {name}")
            path = f"project/{name}"
            key = path.casefold()
            if key in names:
                raise SourceError(f"duplicate project archive member: {name}")
            names.add(key)
            files[path] = archive.read(info)
    if "project/packaging/hantek-6022be.patch" not in files:
        raise SourceError("required tracked patch missing: packaging/hantek-6022be.patch")
    return commit, version, files


def _input_path(record: dict[str, object]) -> str:
    name = str(record["name"])
    filename = Path(str(record["url"]).split("?", 1)[0]).name
    filename = filename if filename.lower().startswith(name.lower()) else f"{name}-{filename}"
    return f"sources/{record['kind']}/{filename}"


def _git_object(kind: str, data: bytes) -> tuple[str, bytes]:
    object_data = f"{kind} {len(data)}\0".encode() + data
    return sha1(object_data, usedforsecurity=False).hexdigest(), zlib.compress(object_data)


def _hantek_repository(data: bytes, record: dict[str, object]) -> dict[str, bytes]:
    commit = str(record.get("commit", ""))
    commit_data = record.get("git_commit_object")
    if not isinstance(commit_data, str):
        raise SourceError("Hantek source requires git_commit_object metadata")
    commit_bytes = commit_data.encode()
    commit_hash, compressed_commit = _git_object("commit", commit_bytes)
    if commit_hash != commit:
        raise SourceError("Hantek git commit object does not match pinned commit")
    entries: list[tuple[tuple[str, ...], str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            parts = PurePosixPath(_safe_member(info.filename)).parts
            archive_mode = info.external_attr >> 16
            mode = (
                "120000"
                if stat.S_IFMT(archive_mode) == stat.S_IFLNK
                else "100755"
                if archive_mode & 0o111
                else "100644"
            )
            entries.append((parts[1:], mode, archive.read(info)))

    objects: dict[str, bytes] = {}

    def write_object(kind: str, content: bytes) -> str:
        digest, compressed = _git_object(kind, content)
        objects[f"objects/{digest[:2]}/{digest[2:]}"] = compressed
        return digest

    def write_tree(prefix: tuple[str, ...]) -> str:
        children = {parts[len(prefix)] for parts, _, _ in entries if parts[: len(prefix)] == prefix}
        tree_entries: list[tuple[bytes, bytes]] = []
        for name in children:
            path = (*prefix, name)
            file = next((item for item in entries if item[0] == path), None)
            if file is None:
                mode = "40000"
                digest = write_tree(path)
                sort_key = f"{name}/".encode()
            else:
                mode = file[1]
                digest = write_object("blob", file[2])
                sort_key = name.encode()
            tree_entries.append((sort_key, f"{mode} {name}\0".encode() + bytes.fromhex(digest)))
        return write_object("tree", b"".join(entry for _, entry in sorted(tree_entries)))

    tree = write_tree(())
    expected_tree = commit_data.partition("\n")[0].removeprefix("tree ")
    if tree != expected_tree:
        raise SourceError(f"Hantek codeload tree does not match commit: {tree}")
    objects[f"objects/{commit[:2]}/{commit[2:]}"] = compressed_commit
    return {
        **objects,
        "HEAD": b"ref: refs/heads/source\n",
        "config": (b"[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n\tbare = true\n"),
        "refs/heads/source": f"{commit}\n".encode("ascii"),
        "shallow": f"{commit}\n".encode("ascii"),
    }


def _write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)


def _publish(artifact: Path, files: dict[str, bytes]) -> None:
    sidecar = artifact.with_name(f"{artifact.name}.sha256")
    temporary = artifact.with_suffix(".zip.tmp")
    temporary_sidecar = sidecar.with_suffix(".sha256.tmp")
    for path in (artifact, sidecar, temporary, temporary_sidecar):
        path.unlink(missing_ok=True)
    try:
        _write_zip(temporary, files)
        digest = sha256(temporary.read_bytes()).hexdigest()
        temporary_sidecar.write_text(f"{digest}  {artifact.name}\n", encoding="ascii", newline="\n")
        temporary_sidecar.replace(sidecar)
        temporary.replace(artifact)
    except Exception:
        artifact.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
        temporary_sidecar.unlink(missing_ok=True)


def build(root: Path, out_dir: Path, cache: Path | None, *, release: bool) -> Path:
    """Build and publish a Corresponding Source ZIP and SHA-256 sidecar."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("LNT-*-corresponding-source.zip*"):
        if stale.is_file():
            stale.unlink()
    if release and _git(root, "status", "--porcelain", "--untracked-files=normal").strip():
        raise SourceError("release requires clean committed HEAD")
    manifest, records = _records(root)
    commit, version, files = _project_files(root)
    artifact = out_dir / f"LNT-{version}-corresponding-source.zip"
    if version != manifest.get("project_version"):
        raise SourceError(f"project version mismatch: HEAD={version}")
    source_inputs: list[dict[str, object]] = []
    paths = {name.casefold() for name in files}
    for record in records:
        path = _input_path(record)
        if path.casefold() in paths:
            raise SourceError(f"source path collision: {path}")
        data = _fetch(record, cache)
        paths.add(path.casefold())
        files[path] = data
        source_input = {**record, "path": path}
        if record["kind"] == "hantek":
            build_path = "sources/hantek/hantek.git"
            for name, content in _hantek_repository(data, record).items():
                repository_path = f"{build_path}/{name}"
                if repository_path.casefold() in paths:
                    raise SourceError(f"source path collision: {repository_path}")
                paths.add(repository_path.casefold())
                files[repository_path] = content
            source_input["build_path"] = build_path
        source_inputs.append(source_input)
    files["BUILDING.md"] = BUILDING.encode()
    project = {"name": "LNT", "version": version, "commit": commit, "path": "project/"}
    source_manifest: dict[str, object] = {
        "schema_version": 1,
        "project": project,
        "inputs": source_inputs,
        "conveyed_artifact": manifest.get("conveyed_artifact"),
    }
    files["SOURCE-MANIFEST.json"] = (
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    files["SHA256SUMS"] = "".join(
        f"{sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items())
    ).encode("ascii")
    _publish(artifact, files)
    return artifact


def main(argv: list[str] | None = None) -> int:
    """Run the Corresponding Source builder CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--out-dir", type=Path, default=Path("dist"))
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args(argv)
    try:
        artifact = build(
            args.root.resolve(), args.out_dir.resolve(), args.cache_dir, release=args.release
        )
    except SourceError as exc:
        sys.stderr.write(f"SOURCE ERROR: {exc}\n")
        return 2
    sys.stdout.write(f"{artifact}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
