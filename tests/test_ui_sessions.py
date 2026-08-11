# ПРИМЕЧАНИЕ О ВОССТАНОВЛЕНИИ: оригинальный файл тестов утрачен при сбое диска
# (битые сектора во всех копиях; остатки — в _recovery/corrupted_tests/).
# Восстановлен только хелпер write_manifest, который импортирует
# tests/test_ui_security.py; сами тесты сессий предстоит написать заново.

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def write_manifest(session_dir: Path) -> None:
    """Создаёт каталог сессии с валидным manifest.json (schema v1)."""
    session_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "session_id": session_dir.name,
        "created_utc": "2026-08-04T00:00:00Z",
        "completed_utc": "2026-08-04T00:00:02Z",
        "source": "synthetic",
        "session_type": "measurement",
        "sample_rate_hz": 500_000.0,
        "duration_s": 2.4,
        "sample_count": 1_200_000,
        "line_frequency_hz": 50.0,
        "profile": "quiet",
        "baseline_session": None,
        "parameters": {"seed": 7},
        "ch1": {
            "filename": "ch1.npy",
            "role": "hf_probe",
            "unit": "V",
            "front_end": "synthetic",
            "range_code": 1,
            "probe_multiplier": 1.0,
        },
        "ch2": {
            "filename": "ch2.npy",
            "role": "lf_transformer",
            "unit": "V",
            "front_end": "synthetic",
            "range_code": 1,
            "probe_multiplier": 1.0,
        },
        "acquisition_telemetry": None,
        "synthetic_truth": None,
    }
    (session_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
