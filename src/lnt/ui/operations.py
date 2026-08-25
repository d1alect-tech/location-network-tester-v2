"""Типизированный адаптер запросов панели к доменным операциям LNT."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lnt.acquire import capture_session
from lnt.analysis import (
    AnalysisResult,
    LineQualityAnalysis,
    analyze_session,
    write_analysis,
    write_line_quality_analysis,
)
from lnt.cm_dm.analysis import (
    CmDmAnalysis,
    analyze_cm_dm_session,
    write_cm_dm_analysis,
)
from lnt.cm_dm.dispatch import is_cm_dm_session
from lnt.compare import ComparisonResult, compare_analyses, ensure_comparable
from lnt.scope_io import NEVER_CANCELLED, CancellationToken, CancelledResult
from lnt.selftest import SelftestResult, run_selftest
from lnt.simulate import simulate_session
from lnt.types import ChannelMode, SeriesPosition, SessionType
from lnt.ui.device import DeviceStatus, diagnose_device
from lnt.ui.models import CaptureRequest, SimulateRequest


class JobBackend(Protocol):
    """Контракт доменных операций для обработчика задач панели."""

    def simulate_one(
        self,
        request: SimulateRequest,
        out_dir: Path,
        series: SeriesPosition | None,
    ) -> Path:
        """Создаёт одну синтетическую сессию."""
        ...

    def capture_one(
        self,
        request: CaptureRequest,
        out_dir: Path,
        series: SeriesPosition | None,
        cancellation_token: CancellationToken,
    ) -> Path | CancelledResult:
        """Захватывает одну сессию с устройства."""
        ...

    def analyze_and_write(
        self,
        session_dir: Path,
    ) -> AnalysisResult | LineQualityAnalysis | CmDmAnalysis:
        """Анализирует сессию и записывает артефакты анализа."""
        ...

    def compare(self, session_a: Path, session_b: Path) -> ComparisonResult:
        """Сравнивает результаты анализа двух сессий."""
        ...

    def selftest(self) -> SelftestResult:
        """Запускает синтетическую самопроверку LNT."""
        ...

    def device_check(self) -> DeviceStatus:
        """Диагностирует доступность устройства захвата."""
        ...


def _channel_mode(channels: int) -> ChannelMode:
    return ChannelMode.CH1_ONLY if channels == 1 else ChannelMode.DUAL


def _session_type(request: CaptureRequest) -> SessionType:
    if request.input == "transformer":
        return SessionType.LINE_QUALITY
    if request.self_noise:
        return SessionType.SELF_NOISE
    return SessionType.MEASUREMENT


@dataclass(frozen=True, slots=True)
class LntBackend:
    """Делегирует задачи панели производственным доменным функциям LNT."""

    def simulate_one(
        self,
        request: SimulateRequest,
        out_dir: Path,
        series: SeriesPosition | None,
    ) -> Path:
        """Создаёт синтетическую сессию с позицией в серии."""
        seed = request.seed + series.index - 1 if series is not None else request.seed
        return simulate_session(
            out_dir=out_dir,
            profile=request.profile,
            duration_s=request.duration_s,
            sample_rate_hz=request.sample_rate_hz,
            seed=seed,
            label=request.label,
            series=series,
            channel_mode=_channel_mode(request.channels),
        )

    def capture_one(
        self,
        request: CaptureRequest,
        out_dir: Path,
        series: SeriesPosition | None,
        cancellation_token: CancellationToken = NEVER_CANCELLED,
    ) -> Path | CancelledResult:
        """Захватывает сессию с параметрами запроса панели."""
        session_type = _session_type(request)
        baseline = (
            f"../{request.baseline_session}" if request.baseline_session is not None else None
        )
        return capture_session(
            out_dir=out_dir,
            duration_s=request.duration_s,
            sample_rate_hz=request.sample_rate_hz,
            session_type=session_type,
            ch1_range_v=request.range_v,
            label=request.label,
            series=series,
            baseline_session=baseline,
            channel_mode=_channel_mode(request.channels),
            cancellation_token=cancellation_token,
        )

    def analyze_and_write(
        self,
        session_dir: Path,
    ) -> AnalysisResult | LineQualityAnalysis | CmDmAnalysis:
        """Анализирует сессию, записывает артефакты и возвращает результат."""
        if is_cm_dm_session(session_dir):
            cm_dm_result = analyze_cm_dm_session(session_dir)
            write_cm_dm_analysis(session_dir, cm_dm_result)
            return cm_dm_result
        result = analyze_session(session_dir)
        if isinstance(result, LineQualityAnalysis):
            write_line_quality_analysis(session_dir, result)
            return result
        write_analysis(session_dir, result)
        return result

    def compare(self, session_a: Path, session_b: Path) -> ComparisonResult:
        """Анализирует и сравнивает две сессии в порядке A, B."""
        return compare_analyses(
            ensure_comparable(analyze_session(session_a)),
            ensure_comparable(analyze_session(session_b)),
        )

    def selftest(self) -> SelftestResult:
        """Возвращает результат производственной самопроверки."""
        return run_selftest()

    def device_check(self) -> DeviceStatus:
        """Возвращает результат диагностики устройства."""
        return diagnose_device()
