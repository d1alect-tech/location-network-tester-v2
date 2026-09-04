"""CLI LNT: simulate / capture / analyze / compare / selftest (exit 0/2/3).

Коды выхода: 0 — успех; 2 — некорректный вход/данные (InputError, AnalysisError);
3 — устройство недоступно (DeviceNotFoundError); 1 — провал selftest.
Пользовательские ошибки печатаются одной строкой в stderr, без traceback.

Команды simulate/capture/compare живут в ``lnt.cli_simulate``,
``lnt.cli_capture`` и ``lnt.cli_compare``; здесь — парсер, analyze/ui/support-bundle/selftest.
"""

import argparse
import math
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Never, cast, override

from lnt._cli_capture import add_capture_arguments
from lnt.analysis import (
    LineQualityAnalysis,
    render_line_quality_analysis,
    write_line_quality_analysis,
)
from lnt.app_paths import resolve_app_paths
from lnt.archive import ArchiveError
from lnt.archive.cli import configure_archive_parser
from lnt.catalog.automation_cli import configure_automation_parsers
from lnt.catalog.cli import configure_catalog_parser
from lnt.cli_capture import cmd_capture as _cmd_capture
from lnt.cli_compare import cmd_compare as _cmd_compare
from lnt.cli_experiments import configure_research_parsers
from lnt.cli_simulate import cmd_simulate as _cmd_simulate
from lnt.cm_dm.dispatch import (
    analyze_routed_session,
    write_and_render_analysis,
)
from lnt.errors import AnalysisError, DeviceNotFoundError, InputError
from lnt.selftest import run_selftest
from lnt.signals import PROFILES

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
    except (InputError, AnalysisError, ArchiveError) as error:
        print(f"Ошибка: {error.message}", file=sys.stderr)
        return EXIT_INPUT
    except (KeyError, FileNotFoundError) as error:
        print(f"Ошибка: объект не найден: {error}", file=sys.stderr)
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
    archive = subparsers.add_parser("archive", help="проверенные экспорт, backup и restore")
    configure_archive_parser(archive)
    configure_automation_parsers(subparsers.add_parser)
    configure_research_parsers(subparsers.add_parser)

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

    support_bundle = subparsers.add_parser(
        "support-bundle",
        help="ZIP-диагностика для поддержки (без секретов и захватов)",
    )
    support_bundle.add_argument("out", help="путь к создаваемому .zip")
    support_bundle.add_argument(
        "--include-private-notes",
        action="store_true",
        help="явно пометить выгрузку приватных заметок (сейчас членов с заметками нет)",
    )
    support_bundle.add_argument(
        "--no-logs",
        action="store_true",
        help="не включать хвост структурного журнала",
    )
    support_bundle.set_defaults(handler=_cmd_support_bundle)

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


def _cmd_analyze(args: argparse.Namespace) -> int:
    session_dir = Path(cast("str", args.session))
    result = analyze_routed_session(session_dir)
    if isinstance(result, LineQualityAnalysis):
        metrics_path = write_line_quality_analysis(session_dir, result)
        print(render_line_quality_analysis(result))
        print(f"Артефакты: {metrics_path.name}")
        return EXIT_OK
    print(write_and_render_analysis(session_dir, result))
    return EXIT_OK


def _cmd_ui(args: argparse.Namespace) -> int:
    from lnt.ui.launcher import run_ui  # noqa: PLC0415

    return run_ui(root=Path(args.root), port=args.port, open_browser=not args.no_browser)


def _cmd_support_bundle(args: argparse.Namespace) -> int:
    from lnt.support import BundleOptions, build_support_bundle  # noqa: PLC0415

    paths = resolve_app_paths()
    result = build_support_bundle(
        Path(cast("str", args.out)),
        paths=paths,
        options=BundleOptions(
            include_private_notes=bool(args.include_private_notes),
            include_recent_logs=not bool(args.no_logs),
        ),
        probe=None,
    )
    print(f"Сборник поддержки: {result.path}")
    print(f"Члены: {', '.join(result.member_names)}")
    return EXIT_OK


def _cmd_selftest(_args: argparse.Namespace) -> int:
    result = run_selftest()
    print(result.message)
    return EXIT_OK if result.ok else EXIT_SELFTEST_FAIL
