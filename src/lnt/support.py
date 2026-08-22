"""Сборник поддержки: ZIP-диагностика без секретов, захватов и приватных заметок.

Состав членов фиксирован allowlist'ом; каждый член сопровождается SHA-256 в
manifest.json. В config-член попадает только версия схемы: значения конфигурации
могут содержать пользовательские пути и токены, поэтому не выгружаются вовсе.
Сырые захваты не включаются никогда; приватные заметки и хвост журнала — только
явным выбором через ``BundleOptions``.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from typing import TYPE_CHECKING, Final

from lnt.config.model import CONFIG_SCHEMA_VERSION
from lnt.device_diagnostics import DeviceDiagnostic, DeviceProbe, diagnose_device_state
from lnt.errors import InputError

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.app_paths import AppPaths

SUPPORT_BUNDLE_SCHEMA_VERSION: Final = 1
DEFAULT_TAIL_LINES: Final = 200
_DEPENDENCY_NAMES: Final = ("lnt", "numpy", "scipy", "fastapi", "uvicorn")
_ZIP_SUFFIX: Final = ".zip"


class SupportBundleError(InputError):
    """Ожидаемая ошибка сборки или записи сборника поддержки."""

    path: Path
    reason: str

    def __init__(self, path: Path, reason: str) -> None:
        """Фиксирует путь назначения и причину сбоя."""
        super().__init__(f"не удалось собрать сборник поддержки {path}: {reason}")
        self.path = path
        self.reason = reason


@dataclass(frozen=True, slots=True, kw_only=True)
class BundleOptions:
    """Явный выбор необязательных членов сборника."""

    include_private_notes: bool = False
    include_recent_logs: bool = True


@dataclass(frozen=True, slots=True)
class SupportBundleResult:
    """Итог сборки: путь архива и список членов без manifest.json."""

    path: Path
    member_names: tuple[str, ...]


def build_support_bundle(  # noqa: PLR0913 - явные инъекции путей/пробов/версий для тестов
    out_path: Path,
    *,
    paths: AppPaths,
    options: BundleOptions,
    probe: DeviceProbe | None,
    tail_lines: int = DEFAULT_TAIL_LINES,
    dependency_versions: dict[str, str] | None = None,
    now: datetime | None = None,
) -> SupportBundleResult:
    """Собирает ZIP с диагностикой; члены и их SHA-256 фиксируются в manifest.json."""
    members: dict[str, bytes] = {
        "config.json": _json_bytes({"schema_version": CONFIG_SCHEMA_VERSION}),
        "device.json": _json_bytes(_device_payload(probe)),
        "build.json": _json_bytes(_build_payload()),
        "dependencies.json": _json_bytes(
            _dependency_payload(
                dependency_versions if dependency_versions is not None else _installed_versions(),
            ),
        ),
    }
    if options.include_recent_logs:
        members["logs/recent.jsonl"] = _log_tail(paths.log_dir, tail_lines)
    manifest = {
        "schema_version": SUPPORT_BUNDLE_SCHEMA_VERSION,
        "created_utc": (now or datetime.now(UTC)).isoformat(),
        "options": {
            "include_private_notes": options.include_private_notes,
            "include_recent_logs": options.include_recent_logs,
        },
        "members": [
            {
                "path": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
            for name, content in sorted(members.items())
        ],
    }
    members["manifest.json"] = _json_bytes(manifest)
    ordered = dict(sorted(members.items()))
    _write_zip(out_path, ordered)
    names = tuple(name for name in ordered if name != "manifest.json")
    return SupportBundleResult(path=out_path, member_names=names)


def _device_payload(probe: DeviceProbe | None) -> dict[str, object]:
    """Диагностическая сводка устройства без строк драйвера с путями машины."""
    if probe is None:
        return {"probed": False}
    diagnostic: DeviceDiagnostic = diagnose_device_state(probe)
    return {
        "probed": True,
        "state": diagnostic.state.value,
        "detected_vid": diagnostic.detected_vid,
    }


def _build_payload() -> dict[str, object]:
    from lnt.analysis_store.identity import CodeIdentity  # noqa: PLC0415

    identity = CodeIdentity.current()
    return {
        "code_identity": identity.identity_string,
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }


def _installed_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _DEPENDENCY_NAMES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return versions


def _dependency_payload(versions: dict[str, str]) -> list[dict[str, str]]:
    """Возвращает стабильный список имя/версия без источников и хешей окружения."""
    return [{"name": name, "version": versions[name]} for name in sorted(versions)]


def _log_tail(log_dir: Path, tail_lines: int) -> bytes:
    """Последние строки журнала; битые байты заменяются, а не роняют сборку."""
    candidates = sorted(log_dir.glob("*.jsonl")) if log_dir.is_dir() else []
    if not candidates:
        return b""
    raw = candidates[-1].read_bytes()
    lines = raw.decode(encoding="utf-8", errors="replace").splitlines()
    selected = lines[-tail_lines:] if len(lines) > tail_lines else lines
    return ("\n".join(selected) + "\n").encode(encoding="utf-8")


def _json_bytes(payload: object) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    return text.encode("utf-8") + b"\n"


def _write_zip(out_path: Path, members: dict[str, bytes]) -> None:
    """Атомарно пишет ZIP: временный файл + os.replace, как для конфигурации."""
    if out_path.suffix != _ZIP_SUFFIX:
        raise SupportBundleError(out_path, f"ожидается суффикс {_ZIP_SUFFIX}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(f".{out_path.name}.partial-{uuid.uuid4().hex[:8]}")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        os.replace(temporary, out_path)  # noqa: PTH105 - единый патчируемый атомарный seam
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise SupportBundleError(out_path, str(error)) from error
