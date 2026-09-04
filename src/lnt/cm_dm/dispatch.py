"""T8: маршрутизация CM/DM-сессий на точках диспетчеризации анализа.

Точки входа панели (``LntBackend.analyze_and_write``) и CLI (``_cmd_analyze``)
выбирают анализатор по ``session_type`` манифеста: probe-pair записи уходят в
CM/DM-анализатор, остальные — в канонический анализ v1 без изменений. Запись
артефактов и человекочитаемая сводка тоже диспетчеризуются по виду результата,
чтобы вызывающий модуль оставался линейным.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from lnt.analysis import (
    AnalysisResult,
    LineQualityAnalysis,
    analyze_session,
    render_analysis,
    write_analysis,
)
from lnt.cm_dm.analysis import (
    CM_DM_SPECTRUM_FILENAME,
    CmDmAnalysis,
    analyze_cm_dm_session,
    write_cm_dm_analysis,
)
from lnt.errors import InputError
from lnt.manifest import manifest_from_json
from lnt.session_store import MANIFEST_FILENAME
from lnt.spectrum_hold import write_hold_spectrum
from lnt.types import SessionType

if TYPE_CHECKING:
    from pathlib import Path

type RoutedAnalysis = AnalysisResult | LineQualityAnalysis | CmDmAnalysis

_RENDERED_CM_DM_PEAKS = 5


def is_cm_dm_session(session_dir: Path) -> bool:
    """Читает только манифест: True для cm_dm и калибровочных cm_dm-сессий."""
    try:
        manifest_text = (session_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise InputError("manifest.json: файл должен быть в кодировке UTF-8") from error
    session_type = manifest_from_json(manifest_text).session_type
    return session_type in (SessionType.CM_DM, SessionType.CM_DM_CALIBRATION)


def analyze_routed_session(session_dir: Path) -> RoutedAnalysis:
    """Диспетчеризует анализ по типу сессии из манифеста.

    Калибровочная сессия уходит в CM/DM-анализатор сознательно: он отвергает её
    ``InputError`` вместо молчаливой обработки как обычной измерительной записи.
    """
    if is_cm_dm_session(session_dir):
        return analyze_cm_dm_session(session_dir)
    return analyze_session(session_dir)


def render_cm_dm_analysis(result: CmDmAnalysis) -> str:
    """Компактная человекочитаемая сводка CM/DM-анализа для stdout CLI."""
    calibration_text = "применена" if result.calibration is not None else "не найдена"
    lines = [
        f"Сессия: {result.session_id}",
        f"Источник: {result.source.value} / {result.session_type.value}",
        f"Запись: fs={result.sample_rate_hz:.0f} Гц, длительность {result.duration_s:.2f} с",
        (
            f"Полоса CM/DM: {result.band_low_hz:.0f}-{result.band_high_hz:.0f} Гц, "
            f"сегментов: {result.segment_count}, nperseg: {result.nperseg}"
        ),
        f"Калибровка пары пробников: {calibration_text}",
        "Пики спектра:",
    ]
    if result.peaks:
        lines.extend(
            f"  {peak.frequency_hz:9.0f} Гц  {peak.mode.upper()}: {peak.psd_v2_per_hz:.3e} В²/Гц"
            for peak in result.peaks[:_RENDERED_CM_DM_PEAKS]
        )
    else:
        lines.append("  (выраженных пиков не найдено)")
    return "\n".join(lines)


def write_and_render_analysis(session_dir: Path, result: AnalysisResult | CmDmAnalysis) -> str:
    """Пишет артефакты анализа и возвращает полный текст для stdout CLI.

    Виды v1 проходят через функции v1 без изменений; CmDmAnalysis пишет
    metrics.json с секцией ``cm_dm`` плюс cm_dm_spectrum.csv.
    """
    match result:
        case AnalysisResult():
            metrics_path, spectrum_path = write_analysis(session_dir, result)
            write_hold_spectrum(session_dir, result.spectrum)
            rendered = render_analysis(result)
            artifacts = f"{metrics_path.name}, {spectrum_path.name}"
            return f"{rendered}\nАртефакты: {artifacts}"
        case CmDmAnalysis():
            metrics_path = write_cm_dm_analysis(session_dir, result)
            rendered = render_cm_dm_analysis(result)
            artifacts = f"{metrics_path.name}, {CM_DM_SPECTRUM_FILENAME}"
            return f"{rendered}\nАртефакты: {artifacts}"
    assert_never(result)
