"""Серии сессий (``--repeat/--interval``): фиксированная сетка стартов.

Интервал считается от старта до старта (t0 + i*interval): расписание не
уползает от длительности захвата; сессия длиннее интервала — следующая
стартует сразу. Ошибка на i-й сессии обрывает серию, уже записанные
сессии остаются на диске (каждая атомарна).
"""

import math
import time
from collections.abc import Callable
from pathlib import Path

from lnt.errors import InputError
from lnt.types import SeriesPosition

Clock = Callable[[], float]
Sleep = Callable[[float], None]


def series_dirs(out_dir: Path, repeat: int) -> list[Path]:
    """Каталоги сессий серии: сам ``out_dir`` при repeat=1, иначе соседи -001..-NNN."""
    if repeat == 1:
        return [out_dir]
    return [out_dir.with_name(f"{out_dir.name}-{index:03d}") for index in range(1, repeat + 1)]


def run_series(
    *,
    repeat: int,
    interval_s: float,
    start_session: Callable[[SeriesPosition], Path],
    clock: Clock = time.monotonic,
    sleep: Sleep = time.sleep,
) -> list[Path]:
    """Запускает ``repeat`` сессий; старт i-й — в ``t0 + i*interval_s``."""
    _validate(repeat=repeat, interval_s=interval_s)
    t0 = clock()
    written: list[Path] = []
    for index in range(repeat):
        delay = t0 + index * interval_s - clock()
        if delay > 0.0:
            sleep(delay)
        position = SeriesPosition(index=index + 1, total=repeat, interval_s=interval_s)
        written.append(start_session(position))
    return written


def _validate(*, repeat: int, interval_s: float) -> None:
    if not math.isfinite(interval_s):
        raise InputError("--interval: интервал должен быть конечным")
    if repeat < 1:
        raise InputError("--repeat: число сессий серии должно быть >= 1")
    if interval_s < 0.0:
        raise InputError("--interval: интервал не может быть отрицательным")
    if repeat == 1 and interval_s > 0.0:
        raise InputError("--interval имеет смысл только вместе с --repeat > 1")
