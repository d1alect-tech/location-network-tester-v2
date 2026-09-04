"""JSON-представления дисковых сессий для API панели мониторинга."""

import json
from pathlib import Path
from typing import Final

import numpy as np

from lnt.analysis import (
    METRICS_FILENAME,
    SPECTRUM_FILENAME,
    SPECTRUM_INPUT_REFERRED_FILENAME,
)
from lnt.errors import InputError
from lnt.manifest import manifest_from_json
from lnt.session_store import MANIFEST_FILENAME
from lnt.types import SessionManifest
from lnt.ui.decimation import decimate_spectrum, decimate_waveform
from lnt.ui.sessions import list_sessions, resolve_session_dir


class InputReferredSpectrumMissingError(InputError):
    """Файл input-referred спектра отсутствует (HTTP 404 на границе маршрутов)."""


class InputReferenceUnavailableError(InputError):
    """Квалификация input-reference недоступна (HTTP 409 на границе маршрутов)."""

    def __init__(self, message: str, *, reason_code: str | None) -> None:
        """Сохраняет machine-readable reason_code рядом с сообщением."""
        super().__init__(message)
        self.reason_code: str | None = reason_code


_WAVEFORM_CACHE_LIMIT: Final = 32
type WaveformCacheKey = tuple[str, str, int, int]
_WAVEFORM_CACHE: Final[dict[WaveformCacheKey, dict[str, object]]] = {}


def sessions_payload(root: Path) -> dict[str, object]:
    """Возвращает JSON-список сессий с краткими метаданными."""
    session_payloads: list[dict[str, object]] = []
    for entry in list_sessions(root):
        summary = entry.summary
        summary_payload: dict[str, object] | None = None
        if summary is not None:
            summary_payload = {
                "session_id": summary.session_id,
                "created_utc": summary.created_utc,
                "source": summary.source,
                "session_type": summary.session_type,
                "profile": summary.profile,
                "sample_rate_hz": summary.sample_rate_hz,
                "duration_s": summary.duration_s,
                "sample_count": summary.sample_count,
                "label": summary.label,
                "channels": summary.channels,
            }
        session_payloads.append(
            {
                "name": entry.name,
                "status": entry.status,
                "error": entry.error,
                "analyzed": entry.analyzed,
                "summary": summary_payload,
            },
        )
    return {"sessions": session_payloads}


def session_detail_payload(root: Path, name: str) -> dict[str, object]:
    """Возвращает манифест, анализ и доступность графиков сессии."""
    session_dir = resolve_session_dir(root, name)
    manifest_text, _manifest = _read_validated_manifest(session_dir)
    metrics_path = session_dir / METRICS_FILENAME
    analysis = (
        json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.is_file() else None
    )
    return {
        "name": name,
        "manifest": json.loads(manifest_text),
        "analysis": analysis,
        "spectrum_available": (session_dir / SPECTRUM_FILENAME).is_file(),
        "waveform_available": (session_dir / "ch1.npy").is_file(),
        "ch2_available": (session_dir / "ch2.npy").is_file(),
    }


def spectrum_payload(root: Path, name: str, *, max_points: int) -> dict[str, object]:
    """Возвращает ограниченный и безопасный для log-осей спектр сессии."""
    session_dir = resolve_session_dir(root, name)
    spectrum_path = session_dir / SPECTRUM_FILENAME
    if not spectrum_path.is_file():
        raise InputError("сессия не проанализирована: запустите анализ")
    spectrum_table = np.loadtxt(
        spectrum_path,
        delimiter=",",
        skiprows=1,
        dtype=np.float64,
        ndmin=2,
    )
    series = decimate_spectrum(
        spectrum_table[:, 0],
        spectrum_table[:, 1],
        max_points=max_points,
    )
    result: dict[str, object] = {
        "frequency_hz": list(series.x),
        "psd_v2_per_hz": list(series.y),
        "point_count": series.point_count,
    }
    # RBW-контракт шкалы: только ADD ключей, старые клиенты целы.
    result.update(_spectrum_meta(session_dir))
    return result


def input_referred_spectrum_payload(
    root: Path,
    name: str,
    *,
    max_points: int,
) -> dict[str, object]:
    """Возвращает ограниченный input-referred excess-PSD спектр CH1."""
    session_dir = resolve_session_dir(root, name)
    spectrum_path = session_dir / SPECTRUM_INPUT_REFERRED_FILENAME
    if not spectrum_path.is_file():
        raise InputReferredSpectrumMissingError(
            "input-referred спектр отсутствует: запустите анализ",
        )
    analysis = _read_analysis(session_dir)
    reference = analysis.get("ch1_input_reference")
    reference_map = reference if isinstance(reference, dict) else {}
    if reference_map.get("status") == "unavailable":
        reason_code = reference_map.get("reason_code")
        reason_text = reason_code if isinstance(reason_code, str) else "unknown"
        raise InputReferenceUnavailableError(
            f"input-reference недоступен: {reason_text}",
            reason_code=reason_code if isinstance(reason_code, str) else None,
        )
    try:
        spectrum_table = np.loadtxt(
            spectrum_path,
            delimiter=",",
            skiprows=1,
            dtype=np.float64,
            ndmin=2,
        )
    except (OSError, ValueError):
        spectrum_table = np.empty((0, 2), dtype=np.float64)
    if spectrum_table.size == 0:
        series = decimate_spectrum(
            np.empty(0, dtype=np.float64),
            np.empty(0, dtype=np.float64),
            max_points=max_points,
        )
    else:
        series = decimate_spectrum(
            spectrum_table[:, 0],
            spectrum_table[:, 1],
            max_points=max_points,
        )
    spectrum_meta = _spectrum_meta(session_dir)
    return {
        "frequency_hz": list(series.x),
        "input_referred_excess_psd_v2_per_hz": list(series.y),
        "point_count": series.point_count,
        "status": reference_map.get("status"),
        "reason_code": reference_map.get("reason_code"),
        "qualified_bin_count": reference_map.get("qualified_bin_count", 0),
        "total_bin_count": reference_map.get("total_bin_count", 0),
        "resolution_hz": spectrum_meta.get("resolution_hz"),
        "window": spectrum_meta.get("window"),
        "enbw_hz": spectrum_meta.get("enbw_hz"),
    }


def waveform_payload(
    root: Path,
    name: str,
    *,
    channel: str,
    max_points: int,
) -> dict[str, object]:
    """Возвращает ограниченную форму волны канала с кэшем по mtime файла."""
    if channel not in {"ch1", "ch2"}:
        raise InputError("канал должен быть ch1 или ch2")
    session_dir = resolve_session_dir(root, name)
    channel_path = session_dir / f"{channel}.npy"
    if not channel_path.is_file():
        raise InputError(f"файл канала не найден: {channel}")
    cache_key = (
        str(session_dir.resolve(strict=True)),
        channel,
        max_points,
        channel_path.stat().st_mtime_ns,
    )
    cached = _WAVEFORM_CACHE.get(cache_key)
    if cached is not None:
        return cached

    _manifest_text, manifest = _read_validated_manifest(session_dir)
    try:
        samples = np.load(channel_path, mmap_mode="r")
    except (OSError, ValueError) as error:
        raise InputError("повреждённый канал") from error
    if samples.ndim != 1 or samples.dtype != np.float32:
        raise InputError("повреждённый канал")
    series = decimate_waveform(
        samples,
        sample_rate_hz=manifest.sample_rate_hz,
        max_points=max_points,
    )
    result: dict[str, object] = {
        "channel": channel,
        "time_s": list(series.x),
        "voltage_v": list(series.y),
        "point_count": series.point_count,
    }
    if len(_WAVEFORM_CACHE) >= _WAVEFORM_CACHE_LIMIT:
        del _WAVEFORM_CACHE[next(iter(_WAVEFORM_CACHE))]
    _WAVEFORM_CACHE[cache_key] = result
    return result


def _read_analysis(session_dir: Path) -> dict[str, object]:
    """Читает metrics.json сессии; при отсутствии/порче возвращает пустой словарь."""
    metrics_path = session_dir / METRICS_FILENAME
    try:
        raw = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _spectrum_meta(session_dir: Path) -> dict[str, object]:
    """Возвращает RBW-метаданные шкалы из metrics.json (только известные ключи)."""
    analysis = _read_analysis(session_dir)
    spectrum = analysis.get("spectrum")
    if not isinstance(spectrum, dict):
        return {}
    meta: dict[str, object] = {}
    for key in ("resolution_hz", "band_low_hz", "band_high_hz", "enbw_hz"):
        value = spectrum.get(key)
        if isinstance(value, (int, float)):
            meta[key] = value
    window = spectrum.get("window")
    if isinstance(window, str):
        meta["window"] = window
    return meta


def _read_validated_manifest(session_dir: Path) -> tuple[str, SessionManifest]:
    manifest_text = (session_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    return manifest_text, manifest_from_json(manifest_text)
