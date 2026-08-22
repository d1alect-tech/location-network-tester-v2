"""Тесты сборника поддержки: allowlist членов, хеши, секреты, явные флаги."""

import hashlib
import json
import zipfile
from pathlib import Path

from lnt.app_paths import AppPathOverrides, AppPaths, resolve_app_paths
from lnt.device_diagnostics import DeviceProbeSnapshot
from lnt.support import SUPPORT_BUNDLE_SCHEMA_VERSION, BundleOptions, build_support_bundle

_MEMBER_ALLOWLIST = {
    "config.json",
    "device.json",
    "build.json",
    "dependencies.json",
    "logs/recent.jsonl",
}
_ARCHIVE_MEMBERS = _MEMBER_ALLOWLIST | {"manifest.json"}


class _ReadyProbe:
    """Детерминированный проб: устройство готово."""

    def probe(self) -> DeviceProbeSnapshot:
        return DeviceProbeSnapshot(
            backend_available=True,
            driver_available=True,
            detected_vid="04B5",
            handle_opened=True,
            firmware_present=True,
        )


def _paths(tmp_path: Path) -> AppPaths:
    return resolve_app_paths(AppPathOverrides(test_root=tmp_path))


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, object]:
    payload = json.loads(archive.read("manifest.json"))
    assert isinstance(payload, dict)
    return payload


def test_members_are_allowlisted_and_hashes_match_content(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    out = tmp_path / "поддержка" / "bundle.zip"

    result = build_support_bundle(out, paths=paths, options=BundleOptions(), probe=_ReadyProbe())
    members = result.member_names

    assert members == tuple(sorted(_MEMBER_ALLOWLIST))
    with zipfile.ZipFile(out) as archive:
        assert tuple(sorted(archive.namelist())) == tuple(sorted(_ARCHIVE_MEMBERS))
        manifest = _read_manifest(archive)
        raw_members = manifest["members"]
        assert isinstance(raw_members, list)
        entries: dict[str, dict[str, object]] = {}
        for entry in raw_members:
            assert isinstance(entry, dict)
            entries[str(entry["path"])] = entry
        assert set(entries) == _MEMBER_ALLOWLIST
        for path, item in entries.items():
            content = archive.read(path)
            assert item["sha256"] == hashlib.sha256(content).hexdigest()
            assert item["bytes"] == len(content)


def test_config_member_carries_only_schema_version_even_when_secrets_present(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    paths.config_path.parent.mkdir(parents=True, exist_ok=True)
    paths.config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_root": r"C:\Users\секретарь\lnt-sessions",
                "api_key": "supersecret-token",
            },
        ),
        encoding="utf-8",
    )
    out = tmp_path / "bundle.zip"

    build_support_bundle(out, paths=paths, options=BundleOptions(), probe=None)

    with zipfile.ZipFile(out) as archive:
        config = json.loads(archive.read("config.json"))
        blob = b"".join(archive.read(name) for name in archive.namelist())
    assert config == {"schema_version": 1}
    assert b"supersecret-token" not in blob
    assert "секретарь".encode() not in blob


def test_device_member_reflects_probe_or_skipped_state(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    probed_out = tmp_path / "probed.zip"
    build_support_bundle(probed_out, paths=paths, options=BundleOptions(), probe=_ReadyProbe())
    skipped_out = tmp_path / "skipped.zip"
    build_support_bundle(skipped_out, paths=paths, options=BundleOptions(), probe=None)

    with zipfile.ZipFile(probed_out) as archive:
        device = json.loads(archive.read("device.json"))
    assert device == {
        "probed": True,
        "state": "ready",
        "detected_vid": "04B5",
    }
    with zipfile.ZipFile(skipped_out) as archive:
        device = json.loads(archive.read("device.json"))
    assert device == {"probed": False}


def test_log_tail_keeps_only_requested_recent_lines(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    lines = [f'{{"ts":"2026-01-01T00:00:{i:02d}Z","message":"строка {i}"}}' for i in range(300)]
    (paths.log_dir / "lnt.log.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "bundle.zip"

    build_support_bundle(
        out,
        paths=paths,
        options=BundleOptions(),
        probe=None,
        tail_lines=100,
    )

    with zipfile.ZipFile(out) as archive:
        tail = archive.read("logs/recent.jsonl").decode(encoding="utf-8").splitlines()
    assert len(tail) == 100
    assert json.loads(tail[-1])["message"] == "строка 299"
    assert json.loads(tail[0])["message"] == "строка 200"


def test_logs_excluded_when_not_explicitly_selected(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    (paths.log_dir / "lnt.log.jsonl").write_text('{"message":"x"}\n', encoding="utf-8")
    out = tmp_path / "bundle.zip"

    result = build_support_bundle(
        out,
        paths=paths,
        options=BundleOptions(include_recent_logs=False),
        probe=None,
    )

    assert "logs/recent.jsonl" not in result.member_names
    with zipfile.ZipFile(out) as archive:
        assert "logs/recent.jsonl" not in archive.namelist()


def test_private_notes_flag_is_recorded_but_never_adds_private_members(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    out = tmp_path / "bundle.zip"

    result = build_support_bundle(
        out,
        paths=paths,
        options=BundleOptions(include_private_notes=True),
        probe=None,
    )

    assert all(not name.startswith(("sessions/", "notes/")) for name in result.member_names)
    with zipfile.ZipFile(out) as archive:
        manifest = _read_manifest(archive)
    assert manifest["options"] == {"include_private_notes": True, "include_recent_logs": True}
    assert manifest["schema_version"] == SUPPORT_BUNDLE_SCHEMA_VERSION


def test_build_and_dependency_members_carry_identity_without_private_data(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    out = tmp_path / "bundle.zip"

    build_support_bundle(
        out,
        paths=paths,
        options=BundleOptions(),
        probe=None,
        dependency_versions={"numpy": "2.5.1", "scipy": "1.18.0"},
    )

    with zipfile.ZipFile(out) as archive:
        build_info = json.loads(archive.read("build.json"))
        dependencies = json.loads(archive.read("dependencies.json"))
    assert build_info["code_identity"].startswith("lnt=")
    assert dependencies == [
        {"name": "numpy", "version": "2.5.1"},
        {"name": "scipy", "version": "1.18.0"},
    ]


def test_corrupt_log_lines_do_not_crash_builder(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    raw = b"".join(
        (
            b'{"message":"ok"}\n',
            b"\xff\xfe\x00broken-bytes\n",
            b'{"message":"poslednyaya"}\n',
        ),
    )
    (paths.log_dir / "lnt.log.jsonl").write_bytes(raw)
    out = tmp_path / "bundle.zip"

    build_support_bundle(out, paths=paths, options=BundleOptions(), probe=None, tail_lines=10)

    with zipfile.ZipFile(out) as archive:
        tail = archive.read("logs/recent.jsonl").decode(encoding="utf-8").splitlines()
    assert len(tail) == 3
    assert json.loads(tail[-1])["message"] == "poslednyaya"
