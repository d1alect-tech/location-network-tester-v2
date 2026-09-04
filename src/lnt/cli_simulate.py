"""Команда ``lnt simulate``: серии синтетических сессий по профилю.

Общие хелперы серии (``_SeriesRun``/``_run_session_series``/``_channel_mode``)
живут здесь и переиспользуются командой capture; поверхность CLI, коды
выхода 0/1/2/3 и тексты stdout/stderr неизменны.
"""
# ruff: noqa: TC003 - CLI-хендлеры держат argparse-контракт видимым

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from lnt.series import run_series, series_dirs
from lnt.simulate import simulate_session
from lnt.types import ChannelMode, SeriesPosition

EXIT_OK = 0

_HandlerWriter = Callable[[Path, SeriesPosition, SeriesPosition | None], Path]


@dataclass(frozen=True, slots=True, kw_only=True)
class SeriesRun:
    """Параметры серии сессий: корневой каталог, повторы, интервал стартов."""

    out_dir: Path
    repeat: int
    interval_s: float


def channel_mode(args: argparse.Namespace) -> ChannelMode:
    """Режим каналов из ``--channels``: 1 — только CH1, иначе CH1+CH2."""
    return ChannelMode.CH1_ONLY if cast("int", args.channels) == 1 else ChannelMode.DUAL


def run_session_series(run: SeriesRun, write_session: _HandlerWriter) -> int:
    """Пишет серию сессий по сетке t0 + i*interval; возвращает код выхода."""
    dirs = series_dirs(run.out_dir, run.repeat)

    def start(position: SeriesPosition) -> Path:
        series = position if run.repeat > 1 else None
        path = write_session(dirs[position.index - 1], position, series)
        print(f"Сессия записана: {path}")
        return path

    run_series(repeat=run.repeat, interval_s=run.interval_s, start_session=start)
    return EXIT_OK


def cmd_simulate(args: argparse.Namespace) -> int:
    """Обработчик ``lnt simulate``: синтетика по профилю с серией повторов."""
    run = SeriesRun(
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
            channel_mode=channel_mode(args),
        )

    return run_session_series(run, write_session)


# Совместимость: прежние приватные имена из ``lnt.cli``.
_SeriesRun = SeriesRun
_run_session_series = run_session_series
_channel_mode = channel_mode
_cmd_simulate = cmd_simulate
