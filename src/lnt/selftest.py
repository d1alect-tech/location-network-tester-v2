"""Синтетическая самопроверка пайплайна LNT."""

# ПРИМЕЧАНИЕ О ВОССТАНОВЛЕНИИ: исходник утрачен при сбое диска; файл
# восстановлен 1:1 по дизассемблированному байткоду (selftest.cpython-312.pyc).

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lnt.analysis import AnalysisResult, analyze_measurement_session
from lnt.simulate import simulate_session

SELFTEST_PROFILE: Final = "bad"
SELFTEST_DURATION_S: Final = 2.4
SELFTEST_SAMPLE_RATE_HZ: Final = 500_000.0
SELFTEST_SEED: Final = 6022
SELFTEST_RING_F0_HZ: Final = 22_400.0
SELFTEST_TOLERANCE_BINS: Final = 2.0


@dataclass(frozen=True, slots=True, kw_only=True)
class SelftestResult:
    """Результат самопроверки для отображения через CLI."""

    ok: bool
    message: str
    frequency_hz: float | None
    cycles_analyzed: int | None


def evaluate_selftest(result: AnalysisResult) -> SelftestResult:
    """Проверяет наличие и частоту главного спектрального пика."""
    if not result.spectrum.peaks:
        return SelftestResult(
            ok=False,
            message="SELFTEST FAIL: пиков не найдено",
            frequency_hz=None,
            cycles_analyzed=None,
        )
    top = result.spectrum.peaks[0]
    tolerance_hz = SELFTEST_TOLERANCE_BINS * result.spectrum.resolution_hz
    if abs(top.frequency_hz - SELFTEST_RING_F0_HZ) > tolerance_hz:
        return SelftestResult(
            ok=False,
            message=(
                f"SELFTEST FAIL: пик {top.frequency_hz:.0f} Гц вместо {SELFTEST_RING_F0_HZ:.0f} Гц"
            ),
            frequency_hz=top.frequency_hz,
            cycles_analyzed=None,
        )
    return SelftestResult(
        ok=True,
        message=(
            f"SELFTEST OK: пик {top.frequency_hz:.0f} Гц, циклов {result.needle.cycles_analyzed}"
        ),
        frequency_hz=top.frequency_hz,
        cycles_analyzed=result.needle.cycles_analyzed,
    )


def run_selftest() -> SelftestResult:
    """Симулирует, анализирует и оценивает эталонную сессию во временном каталоге."""
    with tempfile.TemporaryDirectory(prefix="lnt-selftest-") as tmp:
        session_dir = simulate_session(
            out_dir=Path(tmp) / "selftest",
            profile=SELFTEST_PROFILE,
            duration_s=SELFTEST_DURATION_S,
            sample_rate_hz=SELFTEST_SAMPLE_RATE_HZ,
            seed=SELFTEST_SEED,
        )
        result = analyze_measurement_session(session_dir)
    return evaluate_selftest(result)
