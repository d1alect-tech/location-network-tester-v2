"""Команда ``lnt compare``: таблица дельт двух сессий (B - A).

Быстрый путь: метрики иголок и пики читаются из ``metrics.json``, полный PSD
для интерполяции уровней — из ``spectrum.csv``; повторный прогон сырого
анализа не выполняется. При отсутствии/порче артефактов — откат на
``analyze_session`` (поведение и коды выхода 0/1/2/3 неизменны).

Оговорка точности: ``spectrum.csv`` хранит PSD в формате ``%.9g``, поэтому
дельты на последнем знаке могут отличаться от полного пересчёта; рендер CLI
(0.1 дБ) бит-в-бит совпадает.
"""
# ruff: noqa: TC003 - CLI-хендлеры держат argparse-контракт видимым

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

import numpy as np

from lnt.analysis import (
    ANALYSIS_SCHEMA_VERSION,
    AnalysisResult,
    LineQualityAnalysis,
    analyze_session,
)
from lnt.compare import compare_analyses, ensure_comparable, render_comparison
from lnt.needles import NeedleMetrics, SyncSource
from lnt.spectrum import BandSpectrum, SpectrumPeak
from lnt.types import SessionSource, SessionType

EXIT_OK = 0
_TABLE_NDIM = 2
_PSD_COLUMNS = 2


def cmd_compare(args: argparse.Namespace) -> int:
    """Обработчик ``lnt compare``: дельты B - A по артефактам сессий."""
    result_a = ensure_comparable(_load_comparable(Path(cast("str", args.session_a))))
    result_b = ensure_comparable(_load_comparable(Path(cast("str", args.session_b))))
    print(render_comparison(compare_analyses(result_a, result_b)))
    return EXIT_OK


def _load_comparable(session_dir: Path) -> AnalysisResult | LineQualityAnalysis:
    """Грузит результат из артефактов; при их отсутствии — считает заново."""
    try:
        return _load_from_artifacts(session_dir)
    except (OSError, ValueError, KeyError, TypeError):
        return analyze_session(session_dir)


def _load_from_artifacts(session_dir: Path) -> AnalysisResult | LineQualityAnalysis:
    """Реконструирует результат анализа из metrics.json + spectrum.csv."""
    payload = json.loads((session_dir / "metrics.json").read_text(encoding="utf-8"))
    if payload["schema_version"] != ANALYSIS_SCHEMA_VERSION:
        raise ValueError("metrics.json: несовместимая schema_version")
    if payload.get("line_quality") is not None or payload.get("needle") is None:
        # Line-quality и чужие (cm_dm) формы — через полный анализ,
        # чтобы ветка отказа ensure_comparable осталась бит-в-бит.
        return analyze_session(session_dir)
    table = np.loadtxt(session_dir / "spectrum.csv", delimiter=",", skiprows=1)
    if table.ndim != _TABLE_NDIM or table.shape[1] != _PSD_COLUMNS or table.shape[0] == 0:
        raise ValueError("spectrum.csv: пустая или битая таблица PSD")
    needle_payload = payload["needle"]
    spectrum_payload = payload["spectrum"]
    return AnalysisResult(
        session_id=payload["session_id"],
        profile=payload["profile"],
        source=SessionSource(payload["source"]),
        session_type=SessionType(payload["session_type"]),
        sample_rate_hz=payload["sample_rate_hz"],
        duration_s=payload["duration_s"],
        needle=NeedleMetrics(
            sync_source=SyncSource(needle_payload["sync_source"]),
            cycles_analyzed=needle_payload["cycles_analyzed"],
            line_frequency_hz=needle_payload["line_frequency_hz"],
            needle_mean_v=needle_payload["needle_mean_v"],
            needle_sigma_ratio=needle_payload["needle_sigma_ratio"],
            sync_power_v2=needle_payload["sync_power_v2"],
            async_power_v2=needle_payload["async_power_v2"],
            async_sync_ratio=needle_payload["async_sync_ratio"],
            lf_envelope_cv=needle_payload["lf_envelope_cv"],
        ),
        spectrum=BandSpectrum(
            frequencies_hz=np.ascontiguousarray(table[:, 0], dtype=np.float64),
            psd_v2_per_hz=np.ascontiguousarray(table[:, 1], dtype=np.float64),
            resolution_hz=spectrum_payload["resolution_hz"],
            band_low_hz=spectrum_payload["band_low_hz"],
            band_high_hz=spectrum_payload["band_high_hz"],
            peaks=tuple(
                SpectrumPeak(
                    frequency_hz=peak["frequency_hz"],
                    level_db=peak["level_db"],
                    prominence_db=peak["prominence_db"],
                    q_factor=peak["q_factor"],
                )
                for peak in spectrum_payload["peaks"]
            ),
            window=spectrum_payload["window"],
            enbw_hz=spectrum_payload["enbw_hz"],
        ),
    )


# Совместимость: прежнее приватное имя из ``lnt.cli``.
_cmd_compare = cmd_compare
