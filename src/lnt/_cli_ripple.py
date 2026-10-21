"""Подкоманда ``lnt ripple``: CLI-поверхность ripple-среза анализа v2.

Поверхность без математики: разрешение сессии (путь, имя каталога или
``session_id`` по семантике ``ui/sessions.resolve_session_dir``), типизированный
разбор флагов, вызов публичного ``run_ripple`` и однострочный свод в stdout.
CLI никогда не правит отсчёты, не пересчитывает вольты и не вычитает фон —
``--probe`` это проверка равенства против манифеста, фон публикуется рядом.
Внутренний отказ движка — exit 1 одной строкой stderr, без traceback.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from lnt.analysis_v2.engine_ripple import run_ripple
from lnt.analysis_v2.ripple_options import (
    BaselineAttachment,
    RippleRequest,
    SettlingDeclaration,
)
from lnt.errors import AnalysisError, InputError
from lnt.ripple.adapter import AdapterSpec
from lnt.session_store import load_session
from lnt.ui.sessions import resolve_session_dir

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Mapping

    from lnt.session_store import LoadedSession

EXIT_OK: Final = 0
EXIT_INTERNAL_ERROR: Final = 1

DEFAULT_ROOT: Final = Path.home() / "lnt-sessions"
DEFAULT_CAP_NF: Final = 100.0
DEFAULT_SERIES_R_OHM: Final = 0.0
DEFAULT_WINDOW_S: Final = 1.0

#: ``--probe`` — объявление пробника адаптера (1x/10x), не масштаб записи.
_PROBE_CHOICES: Final = ("1x", "10x")
_PROBE_MULTIPLIERS: Final[Mapping[str, int]] = {"1x": 1, "10x": 10}

_UNAVAILABLE: Final = "недоступно"


def configure_ripple_parser(
    command: argparse.ArgumentParser,
    *,
    finite_float: Callable[[str], float],
) -> None:
    """Регистрирует флаги ``lnt ripple`` (полоса обязательна, без молчаливых дефолтов)."""
    command.add_argument("session", help="каталог сессии, имя каталога или session_id")
    command.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        metavar="DIR",
        help="корень сессий для разрешения имени/session_id (по умолчанию ~/lnt-sessions)",
    )
    command.add_argument(
        "--band-low",
        type=finite_float,
        required=True,
        metavar="HZ",
        help="нижняя граница полосы риппла, Гц (>= 0, DC-бин исключён)",
    )
    command.add_argument(
        "--band-high",
        type=finite_float,
        required=True,
        metavar="HZ",
        help="верхняя граница полосы риппла, Гц (<= fs/2 сессии)",
    )
    command.add_argument(
        "--cap-nf",
        type=finite_float,
        default=DEFAULT_CAP_NF,
        metavar="NF",
        help="ёмкость последовательного конденсатора адаптера, нФ",
    )
    command.add_argument(
        "--series-r-ohm",
        type=finite_float,
        default=DEFAULT_SERIES_R_OHM,
        metavar="OHM",
        help="номинал последовательного резистора адаптера, Ом",
    )
    command.add_argument(
        "--probe",
        choices=_PROBE_CHOICES,
        default="1x",
        help="объявленный пробник адаптера: проверка равенства против манифеста, не пересчёт",
    )
    command.add_argument(
        "--window-s",
        type=finite_float,
        default=DEFAULT_WINDOW_S,
        metavar="S",
        help="окно интервалов time-domain, с",
    )
    command.add_argument(
        "--preconnected",
        action="store_true",
        help="операторское объявление: подключение до старта записи, без переподключений в эпохе",
    )
    command.add_argument(
        "--baseline",
        default=None,
        metavar="DIR",
        help="каталог фоновой сессии для сравнения (рядом, без вычитания)",
    )
    command.add_argument(
        "--baseline-shorted-tip",
        action="store_true",
        help="объявление условия фона: наконечник адаптера замкнут на возврат той же сборки",
    )


def cmd_ripple(args: argparse.Namespace) -> int:
    """Обрабатывает ``lnt ripple``: типизированные отказы — наверх, внутренние — exit 1."""
    try:
        sidecar = run_ripple(_request_from_args(args))
    except (InputError, AnalysisError):
        raise
    except Exception as error:  # noqa: BLE001 - граница CLI: внутренний отказ без traceback
        detail = " ".join(str(error).splitlines()) or type(error).__name__
        print(f"Внутренняя ошибка ripple: {detail}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR
    for line in _summary_lines(sidecar.payload):
        print(line)
    return EXIT_OK


def _request_from_args(args: argparse.Namespace) -> RippleRequest:
    """Строит запрос движка из разобранных аргументов; нечисловые отказы — типизированные."""
    session_dir = _resolve_session_dir(cast("str", args.session), cast("Path", args.root))
    session = _load_session_guarded(session_dir)
    baseline_key = cast("str | None", args.baseline)
    baseline_shorted = bool(args.baseline_shorted_tip)
    if baseline_shorted and baseline_key is None:
        raise InputError("ripple: --baseline-shorted-tip требует --baseline")
    return RippleRequest(
        session=session,
        adapter=AdapterSpec(
            cap_nf=cast("float", args.cap_nf),
            series_r_ohm=cast("float", args.series_r_ohm),
            probe_multiplier=_PROBE_MULTIPLIERS[cast("str", args.probe)],
        ),
        band_low_hz=cast("float", args.band_low),
        band_high_hz=cast("float", args.band_high),
        settling=(
            SettlingDeclaration.PRECONNECTED
            if bool(args.preconnected)
            else SettlingDeclaration.UNKNOWN
        ),
        window_s=cast("float", args.window_s),
        baseline_path=Path(baseline_key) if baseline_key is not None else None,
        baseline_attachment=(
            BaselineAttachment.SAME_ADAPTER_TIP_SHORTED if baseline_shorted else None
        ),
    )


def _resolve_session_dir(key: str, root: Path) -> Path:
    """Прямой путь, иначе семантика ``resolve_session_dir``: имя каталога ИЛИ session_id."""
    direct = Path(key)
    if direct.is_dir():
        return direct
    return resolve_session_dir(root, key)


def _load_session_guarded(session_dir: Path) -> LoadedSession:
    """Читает сессию; испорченные байты канала/манифеста — типизированный отказ."""
    try:
        return load_session(session_dir)
    except InputError:
        raise
    except (OSError, ValueError, EOFError) as error:
        detail = " ".join(str(error).splitlines())
        raise InputError(f"ripple: сессия не читается ({session_dir}): {detail}") from error


def _summary_lines(payload: Mapping[str, object]) -> list[str]:
    """Свод: измеренные значения и фактические границы, без вердиктов «норма/годен»."""
    time_domain = cast("Mapping[str, object]", payload["time_domain"])
    options = cast("Mapping[str, object]", payload["options"])
    band = cast("Mapping[str, object]", cast("list[object]", payload["bands"])[0])
    selection = cast("Mapping[str, object]", payload["selection"])
    low_hz = cast("float", options["band_low_hz"])
    high_hz = cast("float", options["band_high_hz"])
    parts = [
        f"time: {_scalars(time_domain)}",
        _band_summary(band),
        f"спан {_value(selection.get('realized_duration_s'))} с",
        f"фон: {_baseline_summary(payload.get('baseline'))}",
        f"полоса запрошена {low_hz:g}-{high_hz:g} Гц",
    ]
    return ["ripple: " + "; ".join(parts), "Сайдкар: ripple.json"]


def _scalars(block: Mapping[str, object]) -> str:
    """Числа блока, либо честное «недоступно» с кодами причин."""
    if block.get("availability") != "available":
        return _unavailable_with_codes(block)
    return ", ".join(f"{name}={_value(block[f'{name}_v'])} В" for name in ("mean", "rms_ac", "vpp"))


def _band_summary(band: Mapping[str, object]) -> str:
    """Полосной RMS с фактическими границами и числом бинов."""
    edges = f"{cast('float', band['low_hz']):g}-{cast('float', band['high_hz']):g} Гц"
    if band.get("availability") != "available":
        return f"полоса {edges}: {_unavailable_with_codes(band)}"
    bin_count = cast("int", band["bin_count"])
    return f"полоса {edges}: rms={_value(band['rms_v'])} В ({bin_count} бинов)"


def _baseline_summary(baseline: object) -> str:
    """Статус сравнения с фоном; измерение фоном не корректируется."""
    if baseline is None:
        return "нет"
    block = cast("Mapping[str, object]", baseline)
    status = cast("str", block["comparison_status"])
    reasons = cast("list[str]", block["reason_codes"])
    return f"{status} ({', '.join(reasons)})" if reasons else status


def _unavailable_with_codes(block: Mapping[str, object]) -> str:
    """«недоступно» плюс машинные коды причин."""
    codes = cast("list[str]", block.get("reason_codes", []))
    joined = ", ".join(codes)
    return f"{_UNAVAILABLE} ({joined})" if joined else _UNAVAILABLE


def _value(value: object) -> str:
    """Число в свод; None (недоступность) никогда не фабрикуется в число."""
    if value is None:
        return _UNAVAILABLE
    return f"{cast('float', value):.5g}"
