"""Строгий JSON-паттерн manifest.json: parse на границе, типы внутри."""

import os.path
from pathlib import Path

from lnt import _manifest_ch1_setup
from lnt._manifest_json import JsonValue, decode_json_object, encode_json
from lnt._manifest_schema import manifest_from_mapping, manifest_to_mapping
from lnt.errors import InputError
from lnt.types import Ch1Setup, SessionManifest


def manifest_to_json(manifest: SessionManifest) -> str:
    """Сериализует манифест в человекочитаемый JSON (schema v1)."""
    return encode_json(manifest_to_mapping(manifest))


def manifest_from_json(text: str) -> SessionManifest:
    """Строго разбирает manifest.json; любое отклонение -> InputError."""
    return manifest_from_mapping(decode_json_object(text))


def ch1_setup_mapping(setup: Ch1Setup | None) -> dict[str, JsonValue] | None:
    """Публичная сериализация CH1 setup для производных артефактов анализа."""
    if setup is None:
        return None
    return _manifest_ch1_setup.serialize_ch1_setup(setup)


def resolve_baseline_path(
    session_dir: Path,
    manifest: SessionManifest,
) -> Path | None:
    """Разрешает baseline_session относительно каталога сессии (лексически)."""
    if manifest.baseline_session is None:
        return None
    return Path(os.path.normpath(session_dir / manifest.baseline_session))


def validated_label(label: str | None) -> str | None:
    """Нормализует метку сессии для parameters["label"]; пустая -> InputError."""
    if label is None:
        return None
    stripped = label.strip()
    if not stripped:
        raise InputError("метка сессии (--label) не должна быть пустой")
    return stripped
