from __future__ import annotations

import hashlib
import io
import json
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/release_sources.py"
BUILD_SCRIPT = Path(__file__).parents[1] / "packaging/build.ps1"
SOURCE_NOTICE = Path(__file__).parents[1] / "packaging/SOURCE.txt"
GIT = shutil.which("git") or "git"
POWERSHELL = shutil.which("powershell")
NODE = shutil.which("node")
NPM = shutil.which("npm")
CMD = shutil.which("cmd")


def _git(root: Path, *args: str) -> None:
    subprocess.run([GIT, *args], cwd=root, check=True, capture_output=True)


def _git_output(root: Path, *args: str) -> bytes:
    return subprocess.run(
        [GIT, *args],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout


def _archive(path: Path, member: str = "source/file.c", data: bytes = b"source") -> str:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, data)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tar_archive(
    path: Path,
    linkname: str = "../CONTRIBUTING.md",
    *,
    link_type: bytes = tarfile.SYMTYPE,
    target_is_link: bool = False,
) -> str:
    with tarfile.open(path, "w:gz") as archive:
        target = tarfile.TarInfo("pyparsing-3.3.2/CONTRIBUTING.md")
        if target_is_link:
            target.type = tarfile.SYMTYPE
            target.linkname = "LICENSE"
            archive.addfile(target)
        else:
            target.size = len(b"contribute\n")
            archive.addfile(target, io.BytesIO(b"contribute\n"))
        link = tarfile.TarInfo("pyparsing-3.3.2/docs/CONTRIBUTING.md")
        link.type = link_type
        link.linkname = linkname
        archive.addfile(link)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object_hash(kind: str, data: bytes) -> str:
    return hashlib.sha1(f"{kind} {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()


def _hantek_archive(path: Path) -> tuple[str, str, str]:
    files = {
        "CHANGELOG": ("100644", b"upper-case path\n"),
        "changelog": ("100644", b"lower-case path\n"),
        "examples/PyHT6022": ("120000", b"../PyHT6022"),
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, (mode, data) in files.items():
            info = zipfile.ZipInfo(f"source/{name}")
            info.external_attr = (
                (stat.S_IFLNK | 0o777) if mode == "120000" else (stat.S_IFREG | 0o644)
            ) << 16
            archive.writestr(info, data)
    examples_tree = _object_hash(
        "tree",
        b"120000 PyHT6022\0" + bytes.fromhex(_object_hash("blob", files["examples/PyHT6022"][1])),
    )
    tree_object = b"".join(
        [
            b"100644 CHANGELOG\0" + bytes.fromhex(_object_hash("blob", files["CHANGELOG"][1])),
            b"100644 changelog\0" + bytes.fromhex(_object_hash("blob", files["changelog"][1])),
            b"40000 examples\0" + bytes.fromhex(examples_tree),
        ]
    )
    tree = _object_hash("tree", tree_object)
    commit_object = (
        f"tree {tree}\nauthor Test <test@example.invalid> 0 +0000\n"
        "committer Test <test@example.invalid> 0 +0000\n\nfixture\n"
    )
    commit = _object_hash("commit", commit_object.encode())
    return hashlib.sha256(path.read_bytes()).hexdigest(), commit, commit_object


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    inputs = tmp_path / "inputs"
    out = tmp_path / "out"
    root.mkdir()
    inputs.mkdir()
    (root / "packaging").mkdir()
    shutil.copy2(BUILD_SCRIPT, root / "packaging/build.ps1")
    shutil.copy2(SOURCE_NOTICE, root / "packaging/SOURCE.txt")
    (root / "packaging/hantek-6022be.patch").write_text("patch\n", encoding="utf-8", newline="\n")
    (root / "frontend").mkdir()
    (root / "frontend/package.json").write_text(
        json.dumps({"scripts": {"build:check": 'node -e "process.exit(23)"'}}),
        encoding="utf-8",
    )
    (root / "build").mkdir()
    (root / "build/listed.txt").write_text("listed\n", encoding="utf-8", newline="\n")
    (root / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    (root / "tracked.txt").write_text("committed\n", encoding="utf-8", newline="\n")
    runtime_digest = _archive(inputs / "runtime.zip")
    frontend_digest = _archive(inputs / "frontend.zip")
    native_digest = _archive(inputs / "native.zip")
    hantek_digest, hantek_commit, hantek_commit_object = _hantek_archive(inputs / "hantek.zip")
    manifest = {
        "schema_version": 1,
        "project_version": "0.1.0",
        "conveyed_artifact": {
            "name": "LNT-0.1.0-win64.zip",
            "relationship": "built from the project and all inputs in this manifest",
        },
        "required_runtime": ["runtime"],
        "required_native": ["native"],
        "required_frontend": ["frontend"],
        "inputs": [
            {
                "name": "runtime",
                "kind": "runtime",
                "url": (inputs / "runtime.zip").as_uri(),
                "sha256": runtime_digest,
                "archive_root": "source",
            },
            {
                "name": "frontend",
                "kind": "frontend",
                "url": (inputs / "frontend.zip").as_uri(),
                "sha256": frontend_digest,
                "archive_root": "source",
            },
            {
                "name": "native",
                "kind": "native",
                "url": (inputs / "native.zip").as_uri(),
                "sha256": native_digest,
                "archive_root": "source",
            },
            {
                "name": "hantek",
                "kind": "hantek",
                "url": (inputs / "hantek.zip").as_uri(),
                "sha256": hantek_digest,
                "commit": hantek_commit,
                "git_commit_object": hantek_commit_object,
                "archive_root": "source",
            },
        ],
    }
    (root / "release-source-inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "dependency-manifest.json").write_text(
        json.dumps(
            [
                {
                    "name": "runtime",
                    "scope": "runtime",
                    "source_url": (inputs / "runtime.zip").as_uri(),
                    "hash": f"sha256:{runtime_digest}",
                }
            ]
        ),
        encoding="utf-8",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    return root, inputs, out


def _run(root: Path, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--out-dir", str(out), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def _extracted_source_archive(tmp_path: Path) -> Path:
    root, _, out = _repo(tmp_path)
    result = _run(root, out, "--release")
    assert result.returncode == 0, result.stderr
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(out / "LNT-0.1.0-corresponding-source.zip") as archive:
        archive.extractall(extracted)  # noqa: S202
    return extracted


@pytest.mark.skipif(
    POWERSHELL is None or NODE is None or NPM is None,
    reason="Windows PowerShell, Node.js, or npm is unavailable",
)
def test_extracted_source_archive_passes_integrity_and_reaches_frontend_check(
    tmp_path: Path,
) -> None:
    assert POWERSHELL is not None
    extracted = _extracted_source_archive(tmp_path)
    evidence = extracted / "evidence"
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(extracted / "project/packaging/build.ps1"),
            "-Clean",
            "-Evidence",
            str(evidence),
            "-SourceArchive",
        ],
        cwd=extracted,
        capture_output=True,
        text=True,
        check=False,
    )
    transcript = (evidence / "build-transcript.txt").read_text(encoding="utf-8-sig")
    assert result.returncode == 20
    assert "STEP source-archive-integrity EXIT_CODE=0" in transcript
    assert "STEP git-worktree-clean EXIT_CODE=0 :: not-enforced-for-SourceArchive" in transcript
    assert "STEP clean EXIT_CODE=0" in transcript
    assert "STEP frontend-build-check EXIT_CODE=23" in transcript


@pytest.mark.skipif(
    POWERSHELL is None or NODE is None or NPM is None,
    reason="Windows PowerShell, Node.js, or npm is unavailable",
)
def test_prepared_source_archive_allows_repeated_clean_builds(tmp_path: Path) -> None:
    assert POWERSHELL is not None
    extracted = _extracted_source_archive(tmp_path)
    project = extracted / "project"
    preserved = [
        project / "build/listed.txt",
        project / ".venv/pyvenv.cfg",
        project / "frontend/node_modules/package/package.json",
        project / "src/package/__pycache__/module.cpython-312.pyc",
        project / "frontend/test-results/result.txt",
        project / "frontend/playwright-report/index.html",
        project / "frontend/dist/assets/app.js",
    ]
    for path in preserved[1:]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("dependency or cache\n", encoding="utf-8")

    for run in (1, 2):
        stale = [
            project / "build/pyinstaller/work/Analysis-00.toc",
            project / "dist/LNT-0.1.0-win64.zip",
            project / "dist/LNT-0.1.0-win64.zip.sha256",
        ]
        for path in stale:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"stale {run}\n", encoding="utf-8")
        evidence = tmp_path / f"evidence-{run}"
        result = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(project / "packaging/build.ps1"),
                "-Clean",
                "-Evidence",
                str(evidence),
                "-SourceArchive",
            ],
            cwd=extracted,
            capture_output=True,
            text=True,
            check=False,
        )
        transcript = (evidence / "build-transcript.txt").read_text(encoding="utf-8-sig")
        assert result.returncode == 20
        assert "STEP source-archive-integrity EXIT_CODE=0" in transcript
        assert "STEP clean EXIT_CODE=0" in transcript
        assert "STEP frontend-build-check EXIT_CODE=23" in transcript
        assert all(not path.exists() for path in stale)
        assert all(path.is_file() for path in preserved)


@pytest.mark.skipif(
    POWERSHELL is None or CMD is None,
    reason="Windows PowerShell or cmd.exe is unavailable",
)
def test_source_archive_rejects_junction_before_pruning(tmp_path: Path) -> None:
    assert POWERSHELL is not None
    assert CMD is not None
    extracted = _extracted_source_archive(tmp_path)
    project = extracted / "project"
    target = tmp_path / "junction-target"
    target.mkdir()
    junction = project / ".venv"
    created = subprocess.run(
        [CMD, "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode:
        pytest.skip(f"cannot create test junction: {created.stderr.strip()}")

    evidence = extracted / "evidence"
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project / "packaging/build.ps1"),
            "-Clean",
            "-Evidence",
            str(evidence),
            "-SourceArchive",
        ],
        cwd=extracted,
        capture_output=True,
        text=True,
        check=False,
    )
    transcript = (evidence / "build-transcript.txt").read_text(encoding="utf-8-sig")
    assert result.returncode == 10
    assert "STEP source-archive-integrity EXIT_CODE=10" in transcript
    assert "reparse/symlink-like project entry rejected:" in transcript
    assert str(junction) in transcript
    assert "frontend-build-check" not in transcript


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("altered", "SHA-256 mismatch: project/tracked.txt"),
        ("missing", "SHA256SUMS file is missing: project/tracked.txt"),
        ("unlisted", "unlisted project file: project/src/unlisted.py"),
        ("altered_ignored", "SHA-256 mismatch: project/build/listed.txt"),
    ],
)
@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_extracted_source_archive_rejects_invalid_project_before_build_work(
    tmp_path: Path, mutation: str, reason: str
) -> None:
    assert POWERSHELL is not None
    extracted = _extracted_source_archive(tmp_path)
    project = extracted / "project"
    if mutation == "altered":
        (project / "tracked.txt").write_text("tampered\n", encoding="utf-8")
    elif mutation == "missing":
        (project / "tracked.txt").unlink()
    elif mutation == "unlisted":
        (project / "src").mkdir()
        (project / "src/unlisted.py").write_text("unlisted\n", encoding="utf-8")
    else:
        (project / "build/listed.txt").write_text("tampered\n", encoding="utf-8")
    evidence = extracted / "evidence"
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(extracted / "project/packaging/build.ps1"),
            "-Clean",
            "-Evidence",
            str(evidence),
            "-SourceArchive",
        ],
        cwd=extracted,
        capture_output=True,
        text=True,
        check=False,
    )
    transcript = (evidence / "build-transcript.txt").read_text(encoding="utf-8-sig")
    assert result.returncode == 10
    assert "STEP source-archive-integrity EXIT_CODE=10" in transcript
    assert reason in transcript
    assert "git-worktree-clean" not in transcript
    assert "frontend-build-check" not in transcript
    assert "hantek-clone" not in transcript
    assert "pyinstaller" not in transcript
    assert not (extracted / "project/dist").exists()


def test_cli_builds_deterministic_source_zip_from_head(tmp_path: Path) -> None:
    root, _, out = _repo(tmp_path)
    first = _run(root, out, "--release")
    assert first.returncode == 0, first.stderr
    artifact = out / "LNT-0.1.0-corresponding-source.zip"
    first_bytes = artifact.read_bytes()
    assert (out / f"{artifact.name}.sha256").read_text(encoding="ascii") == (
        f"{hashlib.sha256(first_bytes).hexdigest()}  {artifact.name}\n"
    )
    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        assert not any(name.endswith("/") for name in names)
        assert "project/tracked.txt" in names
        assert "project/packaging/hantek-6022be.patch" in names
        assert {
            "sources/runtime/runtime.zip",
            "sources/frontend/frontend.zip",
            "sources/native/native.zip",
            "sources/hantek/hantek.zip",
        } <= set(names)
        source_manifest = json.loads(archive.read("SOURCE-MANIFEST.json"))
        assert source_manifest["project"]["version"] == "0.1.0"
        assert source_manifest["project"]["commit"]
        assert source_manifest["inputs"]
        assert source_manifest["conveyed_artifact"] == {
            "name": "LNT-0.1.0-win64.zip",
            "relationship": "built from the project and all inputs in this manifest",
        }
        sums = archive.read("SHA256SUMS").decode("ascii")
        assert "SOURCE-MANIFEST.json" in sums
        building = archive.read("BUILDING.md")
        assert building.startswith(b"# Building LNT")
        assert b"-SourceArchive" in building
        assert b"uv sync --locked --python 3.12 --all-extras --project project" in building
        assert b"npm --prefix project/frontend ci" in building
        assert b"npm --prefix project/frontend run build" in building
    artifact.unlink()
    assert _run(root, out, "--release").returncode == 0
    assert artifact.read_bytes() == first_bytes


def test_hantek_source_preserves_case_distinct_paths_in_cloneable_repository(
    tmp_path: Path,
) -> None:
    root, _, out = _repo(tmp_path)
    result = _run(root, out, "--release")
    assert result.returncode == 0, result.stderr
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(out / "LNT-0.1.0-corresponding-source.zip") as archive:
        archive.extractall(extracted)  # noqa: S202
        source_manifest = json.loads(archive.read("SOURCE-MANIFEST.json"))
    hantek = next(item for item in source_manifest["inputs"] if item["kind"] == "hantek")
    source = extracted / hantek["build_path"]
    assert (
        _git_output(source, "rev-parse", f"{hantek['commit']}^{{commit}}").decode().strip()
        == (hantek["commit"])
    )
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "--no-checkout", "--", str(source), str(clone))
    assert _git_output(clone, "show", f"{hantek['commit']}:CHANGELOG") == b"upper-case path\n"
    assert _git_output(clone, "show", f"{hantek['commit']}:changelog") == b"lower-case path\n"
    assert _git_output(clone, "show", f"{hantek['commit']}:examples/PyHT6022") == b"../PyHT6022"
    assert _git_output(clone, "ls-tree", hantek["commit"], "examples/PyHT6022").startswith(
        b"120000 blob "
    )
    building = (extracted / "BUILDING.md").read_text(encoding="utf-8")
    assert "-SourceArchive" in building
    assert "-HantekSource sources/hantek/hantek.git" in building


def test_cli_exports_committed_bytes_and_release_rejects_dirty_repo(tmp_path: Path) -> None:
    root, _, out = _repo(tmp_path)
    (root / "tracked.txt").write_text("working tree\n", encoding="utf-8")
    assert _run(root, out, "--release").returncode == 2
    (root / "tracked.txt").write_text("committed\n", encoding="utf-8")
    (root / "untracked.txt").write_text("no\n", encoding="utf-8")
    assert _run(root, out, "--release").returncode == 2
    assert _run(root, out).returncode == 0
    with zipfile.ZipFile(out / "LNT-0.1.0-corresponding-source.zip") as archive:
        assert archive.read("project/tracked.txt").replace(b"\r\n", b"\n") == b"committed\n"
        assert "project/untracked.txt" not in archive.namelist()


def test_failed_rebuild_removes_stale_zip_and_sidecar(tmp_path: Path) -> None:
    root, inputs, out = _repo(tmp_path)
    assert _run(root, out, "--release").returncode == 0
    artifact = out / "LNT-0.1.0-corresponding-source.zip"
    sidecar = out / f"{artifact.name}.sha256"
    assert artifact.exists()
    assert sidecar.exists()
    (inputs / "runtime.zip").write_bytes(b"changed")
    failed = _run(root, out, "--release")
    assert failed.returncode == 2
    assert not artifact.exists()
    assert not sidecar.exists()


@pytest.mark.parametrize("collision", ["duplicate", "case_collision"])
def test_cli_rejects_duplicate_archive_members(tmp_path: Path, collision: str) -> None:
    root, inputs, out = _repo(tmp_path)
    manifest_path = root / "release-source-inputs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependency_path = root / "dependency-manifest.json"
    dependencies = json.loads(dependency_path.read_text(encoding="utf-8"))
    bad = inputs / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("source/file.c", b"one")
        archive.writestr("source/file.c" if collision == "duplicate" else "SOURCE/FILE.C", b"two")
    digest = hashlib.sha256(bad.read_bytes()).hexdigest()
    manifest["inputs"][0].update(url=bad.as_uri(), sha256=digest)
    dependencies[0].update(source_url=bad.as_uri(), hash=f"sha256:{digest}")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    dependency_path.write_text(json.dumps(dependencies), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "mutate")
    result = _run(root, out, "--release")
    assert result.returncode == 2
    assert "duplicate archive member" in result.stderr


def test_cli_rejects_exact_duplicate_hantek_archive_members(tmp_path: Path) -> None:
    root, inputs, out = _repo(tmp_path)
    manifest_path = root / "release-source-inputs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bad = inputs / "hantek-duplicate.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("source/file.c", b"one")
        archive.writestr("source/file.c", b"two")
    manifest["inputs"][3].update(
        url=bad.as_uri(), sha256=hashlib.sha256(bad.read_bytes()).hexdigest()
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "mutate")

    result = _run(root, out, "--release")

    assert result.returncode == 2
    assert "duplicate archive member: source/file.c" in result.stderr


def test_cli_still_rejects_symlink_in_generic_source_archive(tmp_path: Path) -> None:
    root, inputs, out = _repo(tmp_path)
    manifest_path = root / "release-source-inputs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependency_path = root / "dependency-manifest.json"
    dependencies = json.loads(dependency_path.read_text(encoding="utf-8"))
    bad = inputs / "runtime-symlink.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        info = zipfile.ZipInfo("source/link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"target")
    digest = hashlib.sha256(bad.read_bytes()).hexdigest()
    manifest["inputs"][0].update(url=bad.as_uri(), sha256=digest)
    dependencies[0].update(source_url=bad.as_uri(), hash=f"sha256:{digest}")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    dependency_path.write_text(json.dumps(dependencies), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "mutate")

    result = _run(root, out, "--release")

    assert result.returncode == 2
    assert "unsafe archive member type: source/link" in result.stderr


def test_cli_accepts_safe_pyparsing_tar_symlink(tmp_path: Path) -> None:
    root, inputs, out = _repo(tmp_path)
    manifest_path = root / "release-source-inputs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependency_path = root / "dependency-manifest.json"
    dependencies = json.loads(dependency_path.read_text(encoding="utf-8"))
    source = inputs / "pyparsing-3.3.2.tar.gz"
    digest = _tar_archive(source)
    manifest["inputs"][0].update(url=source.as_uri(), sha256=digest, archive_root="pyparsing-3.3.2")
    dependencies[0].update(source_url=source.as_uri(), hash=f"sha256:{digest}")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    dependency_path.write_text(json.dumps(dependencies), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "mutate")

    result = _run(root, out, "--release")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("linkname", "link_type", "target_is_link", "message"),
    [
        ("/CONTRIBUTING.md", tarfile.SYMTYPE, False, "unsafe archive link target"),
        ("../../outside", tarfile.SYMTYPE, False, "unsafe archive link target"),
        ("../missing.md", tarfile.SYMTYPE, False, "unsafe archive link target"),
        ("../CONTRIBUTING.md", tarfile.SYMTYPE, True, "unsafe archive link target"),
        ("../CONTRIBUTING.md", tarfile.LNKTYPE, False, "unsafe archive member type"),
        ("", tarfile.CHRTYPE, False, "unsafe archive member type"),
    ],
)
def test_cli_rejects_unsafe_tar_links(
    tmp_path: Path,
    linkname: str,
    link_type: bytes,
    target_is_link: bool,
    message: str,
) -> None:
    root, inputs, out = _repo(tmp_path)
    manifest_path = root / "release-source-inputs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependency_path = root / "dependency-manifest.json"
    dependencies = json.loads(dependency_path.read_text(encoding="utf-8"))
    source = inputs / "unsafe.tar.gz"
    digest = _tar_archive(source, linkname, link_type=link_type, target_is_link=target_is_link)
    manifest["inputs"][0].update(url=source.as_uri(), sha256=digest, archive_root="pyparsing-3.3.2")
    dependencies[0].update(source_url=source.as_uri(), hash=f"sha256:{digest}")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    dependency_path.write_text(json.dumps(dependencies), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "mutate")

    result = _run(root, out, "--release")

    assert result.returncode == 2
    assert message in result.stderr


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("hash", "sha256 mismatch"),
        ("missing", "download failed"),
        ("traversal", "unsafe archive member"),
        ("root", "archive root mismatch"),
        ("format", "source ZIP/member mismatch"),
        ("native", "missing required native source"),
        ("runtime", "missing runtime sdist"),
        ("frontend", "missing frontend source archive"),
        ("patch", "required tracked patch missing"),
    ],
)
def test_cli_fails_closed_for_invalid_or_incomplete_inputs(
    tmp_path: Path, mutation: str, message: str
) -> None:
    root, inputs, out = _repo(tmp_path)
    manifest_path = root / "release-source-inputs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependency_path = root / "dependency-manifest.json"
    dependencies = json.loads(dependency_path.read_text(encoding="utf-8"))
    if mutation == "hash":
        (inputs / "runtime.zip").write_bytes(b"changed")
    elif mutation == "missing":
        manifest["inputs"][0]["url"] = (inputs / "absent.zip").as_uri()
        dependencies[0]["source_url"] = manifest["inputs"][0]["url"]
    elif mutation in {"traversal", "root"}:
        bad = inputs / "bad.zip"
        digest = _archive(bad, "../evil" if mutation == "traversal" else "wrong/file.c")
        manifest["inputs"][0].update(url=bad.as_uri(), sha256=digest)
        dependencies[0].update(source_url=bad.as_uri(), hash=f"sha256:{digest}")
    elif mutation == "format":
        bad = inputs / "bad.zip"
        bad.write_bytes(b"not an archive")
        digest = hashlib.sha256(bad.read_bytes()).hexdigest()
        manifest["inputs"][0].update(url=bad.as_uri(), sha256=digest)
        dependencies[0].update(source_url=bad.as_uri(), hash=f"sha256:{digest}")
    elif mutation == "native":
        manifest["inputs"] = [item for item in manifest["inputs"] if item["name"] != "native"]
    elif mutation == "runtime":
        dependencies.clear()
    elif mutation == "frontend":
        manifest["inputs"] = [item for item in manifest["inputs"] if item["name"] != "frontend"]
    elif mutation == "patch":
        _git(root, "rm", "-q", "packaging/hantek-6022be.patch")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    dependency_path.write_text(json.dumps(dependencies), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--allow-empty", "-qm", "mutate")
    result = _run(root, out, "--release")
    assert result.returncode == 2
    assert message in result.stderr
    if out.exists():
        assert not list(out.glob("*.zip"))


def test_cli_rejects_case_colliding_generated_source_paths(tmp_path: Path) -> None:
    root, _, out = _repo(tmp_path)
    manifest_path = root / "release-source-inputs.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    duplicate = dict(manifest["inputs"][3])
    duplicate["name"] = "hantek.zip"
    manifest["inputs"].append(duplicate)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "mutate")
    result = _run(root, out, "--release")
    assert result.returncode == 2
    assert "source path collision" in result.stderr
