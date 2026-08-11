"""CLI LNT: simulate / capture / analyze / compare / selftest (exit 0/2/3).

Коды выхода: 0 — успех; 2 — некорректный вход/данные (InputError, AnalysisError);
3 — устройство недоступно (DeviceNotFoundError); 1 — провал selftest.
Пользовательские ошибки печатаются одной строкой в stderr, без traceback.
"""

import argparse
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Never, cast, override

from lnt._cli_capture import CaptureSetupOptions, add_capture_arguments, build_capture_setup
from lnt.acquire import capture_session
from lnt.analysis import (
    LineQualityAnalysis,
    analyze_session,
    render_analysis,
    render_line_quality_analysis,
    write_analysis,
    write_line_quality_analysis,
)
from lnt.catalog.cli import configure_catalog_parser
from lnt.compare import compare_analyses, ensure_comparable, render_comparison
from lnt.errors import AnalysisError, DeviceNotFoundError, InputError
from lnt.selftest import run_selftest
from lnt.series import run_series, series_dirs
from lnt.signals import PROFILES
from lnt.simulate import simulate_session
from lnt.types import ChannelMode, SeriesPosition, SessionType

EXIT_OK = 0
EXIT_SELFTEST_FAIL = 1
EXIT_INPUT = 2
EXIT_DEVICE = 3

SIM_DEFAULT_DURATION_S = 2.4
SIM_DEFAULT_RATE_HZ = 500_000.0
CAPTURE_DEFAULT_DURATION_S = 2.4
CAPTURE_DEFAULT_RATE_HZ = 8_000_000.0
DEFAULT_SEED = 6022

Handler = Callable[[argparse.Namespace], int]
_SessionWriter = Callable[[Path, SeriesPosition, SeriesPosition | None], Path]


@dataclass(frozen=True, slots=True, kw_only=True)
class _SeriesRun:
    out_dir: Path
    repeat: int
    interval_s: float


class _InputArgumentParser(argparse.ArgumentParser):
    @override
    def error(self, message: str) -> Never:
        sanitized = " ".join(message.splitlines())
        raise InputError(f"аргументы: {sanitized}")


def _finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("ожидается число") from error
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("ожидается конечное число")
    return parsed


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("ожидается целое число") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("ожидается неотрицательное целое число")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа console script ``lnt``; возвращает код выхода."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        handler = cast("Handler", args.handler)
        return handler(args)
    except (InputError, AnalysisError) as error:
        print(f"Ошибка: {error.message}", file=sys.stderr)
        return EXIT_INPUT
    except DeviceNotFoundError as error:
        print(f"Устройство: {error.message}", file=sys.stderr)
        return EXIT_DEVICE


def _build_parser() -> argparse.ArgumentParser:
    parser = _InputArgumentParser(
        prog="lnt",
        description="Location Network Tester: захват и анализ сетевых помех (Hantek 6022BE)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    simulate = subparsers.add_parser("simulate", help="синтетическая сессия по профилю")
    simulate.add_argument("--profile", required=True, choices=sorted(PROFILES))
    simulate.add_argument("--out", required=True, help="каталог новой сессии")
    simulate.add_argument("--duration", type=_finite_float, default=SIM_DEFAULT_DURATION_S)
    simulate.add_argument("--rate", type=_finite_float, default=SIM_DEFAULT_RATE_HZ)
    simulate.add_argument("--seed", type=_non_negative_int, default=DEFAULT_SEED)
    _add_channels_argument(simulate)
    _add_label_argument(simulate)
    _add_series_arguments(simulate)
    simulate.set_defaults(handler=_cmd_simulate)

    capture = subparsers.add_parser("capture", help="захват с Hantek 6022BE")
    add_capture_arguments(capture, finite_float=_finite_float)
    _add_channels_argument(capture)
    _add_label_argument(capture)
    _add_series_arguments(capture)
    capture.set_defaults(handler=_cmd_capture)

    analyze = subparsers.add_parser("analyze", help="анализ сессии: metrics.json + spectrum.csv")
    analyze.add_argument("session", help="каталог сессии")
    analyze.set_defaults(handler=_cmd_analyze)

    compare = subparsers.add_parser("compare", help="таблица дельт двух сессий (B - A)")
    compare.add_argument("session_a", help="каталог сессии A (база)")
    compare.add_argument("session_b", help="каталог сессии B")
    compare.set_defaults(handler=_cmd_compare)

    ui = subparsers.add_parser("ui", help="локальный веб-дашборд (localhost)")
    ui.add_argument(
        "--root",
        default=Path.home() / "lnt-sessions",
        metavar="DIR",
        help="каталог сессий",
    )
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument(
        "--no-browser",
        action="store_true",
        help="не открывать браузер автоматически",
    )
    ui.set_defaults(handler=_cmd_ui)

    selftest = subparsers.add_parser("selftest", help="синтетическая самопроверка пайплайна")
    selftest.set_defaults(handler=_cmd_selftest)
    catalog = subparsers.add_parser("catalog", help="обслуживание каталога сессий")
    configure_catalog_parser(catalog)
    return parser


def _add_channels_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--channels",
        type=int,
        choices=(1, 2),
        default=2,
        help="1 — только CH1 (один пробник, без фазовой привязки); 2 — CH1+CH2 (по умолчанию)",
    )


def _channel_mode(args: argparse.Namespace) -> ChannelMode:
    return ChannelMode.CH1_ONLY if cast("int", args.channels) == 1 else ChannelMode.DUAL


def _add_label_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--label",
        default=None,
        help="метка сессии (до/после, нагрузка) -> parameters['label'] манифеста",
    )


def _add_series_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="число сессий серии: каталоги <out>-001..-NNN",
    )
    command.add_argument(
        "--interval",
        type=_finite_float,
        default=0.0,
        dest="interval_s",
        help="период между стартами сессий серии, с (сетка t0 + i*interval)",
    )


def _run_session_series(run: _SeriesRun, write_session: _SessionWriter) -> int:
    dirs = series_dirs(run.out_dir, run.repeat)

    def start(position: SeriesPosition) -> Path:
        series = position if run.repeat > 1 else None
        path = write_session(dirs[position.index - 1], position, series)
        print(f"Сессия записана: {path}")
        return path

    run_series(repeat=run.repeat, interval_s=run.interval_s, start_session=start)
    return EXIT_OK


def _cmd_simulate(args: argparse.Namespace) -> int:
    run = _SeriesRun(
        out_dir=Path(cast("str", args.out)),
        repeat=cast("int", args.repeat),
        interval_s=cast("float", args.interval_s),
    )

    def write_session(
        out_dir: Path,
        position: SeriesPosition,
        series: SeriesPosition | None,
    ) -> Path:
        return simulate_session(
            out_dir=out_dir,
            profile=cast("str", args.profile),
            duration_s=cast("float", args.duration),
            sample_rate_hz=cast("float", args.rate),
            seed=cast("int", args.seed) + position.index - 1,
            label=cast("str | None", args.label),
            series=series,
            channel_mode=_channel_mode(args),
        )

    return _run_session_series(run, write_session)


def _cmd_capture(args: argparse.Namespace) -> int:
    session_type = _capture_session_type(args)
    setup = build_capture_setup(
        session_type=session_type,
        options=CaptureSetupOptions(
            baseline_session=cast("str | None", args.baseline),
            resistance_ohm=cast("float | None", args.rc_r_ohm),
            c1_nf=cast("float | None", args.rc_c1_nf),
            c2_nf=cast("float | None", args.rc_c2_nf),
            component_values_basis=cast("str | None", args.component_values_basis),
            termination_ohm=cast("float | None", args.termination_ohm),
            probe_multiplier=cast("float | None", args.probe_multiplier),
        ),
    )
    run = _SeriesRun(
        out_dir=Path(cast("str", args.out)),
        repeat=cast("int", args.repeat),
        interval_s=cast("float", args.interval_s),
    )

    def write_session(
        out_dir: Path,
        _position: SeriesPosition,
        series: SeriesPosition | None,
    ) -> Path:
        return capture_session(
            out_dir=out_dir,
            duration_s=cast("float", args.duration),
            sample_rate_hz=cast("float", args.rate),
            session_type=session_type,
            ch1_range_v=cast("float", args.range_v),
            label=cast("str | None", args.label),
            series=series,
            ch1_setup=setup,
            baseline_session=cast("str | None", args.baseline),
            channel_mode=(
                ChannelMode.CH1_ONLY
                if session_type is SessionType.LINE_QUALITY
                else _channel_mode(args)
            ),
        )

    return _run_session_series(run, write_session)


def _capture_session_type(args: argparse.Namespace) -> SessionType:
    self_noise = cast("bool", args.self_noise)
    line_quality = cast("bool", args.line_quality)
    if self_noise and line_quality:
        raise InputError("--self-noise и --line-quality взаимоисключающие")
    if line_quality:
        return SessionType.LINE_QUALITY
    if self_noise:
        return SessionType.SELF_NOISE
    return SessionType.MEASUREMENT


def _cmd_analyze(args: argparse.Namespace) -> int:
    session_dir = Path(cast("str", args.session))
    result = analyze_session(session_dir)
    if isinstance(result, LineQualityAnalysis):
        metrics_path = write_line_quality_analysis(session_dir, result)
        print(render_line_quality_analysis(result))
        print(f"Артефакты: {metrics_path.name}")
        return EXIT_OK
    metrics_path, spectrum_path = write_analysis(session_dir, result)
    print(render_analysis(result))
    print(f"Артефакты: {metrics_path.name}, {spectrum_path.name}")
    return EXIT_OK


def _cmd_compare(args: argparse.Namespace) -> int:
    result_a = ensure_comparable(analyze_session(Path(cast("str", args.session_a))))
    result_b = ensure_comparable(analyze_session(Path(cast("str", args.session_b))))
    print(render_comparison(compare_analyses(result_a, result_b)))
    return EXIT_OK


def _cmd_ui(args: argparse.Namespace) -> int:
    from lnt.ui.launcher import run_ui  # noqa: PLC0415

    return run_ui(root=Path(args.root), port=args.port, open_browser=not args.no_browser)


def _cmd_selftest(_args: argparse.Namespace) -> int:
    result = run_selftest()
    print(result.message)
    return EXIT_OK if result.ok else EXIT_SELFTEST_FAIL
