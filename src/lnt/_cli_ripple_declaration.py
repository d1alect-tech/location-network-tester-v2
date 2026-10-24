"""Разрешение входов адаптера ``lnt ripple``: декларация контекста против флагов.

Декларация адаптера из контекста сессии приоритетна: незаданный флаг берёт
значение из декларации (при её отсутствии — легаси-дефолт), заданный флаг —
утверждение оператора, несовпадение с декларацией — типизированный отказ
exit 2 одной строкой. Движок и сайдкар не меняются: здесь только выбор
``AdapterSpec`` и ``SettlingDeclaration`` до сборки ``RippleRequest``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from lnt.analysis_v2.ripple_options import SettlingDeclaration
from lnt.context.model import ContextSnapshot
from lnt.context.store import ContextStore
from lnt.errors import InputError
from lnt.ripple.adapter import AdapterSpec
from lnt.ripple.adapter_declaration import AdapterDeclaration, declaration_from_snapshot

if TYPE_CHECKING:
    import argparse

    from lnt.session_store import LoadedSession

__all__ = [
    "DEFAULT_CAP_NF",
    "DEFAULT_SERIES_R_OHM",
    "PROBE_MULTIPLIERS",
    "resolve_adapter",
    "session_declaration",
]

DEFAULT_CAP_NF: Final = 100.0
DEFAULT_SERIES_R_OHM: Final = 0.0
PROBE_MULTIPLIERS: Final[dict[str, int]] = {"1x": 1, "10x": 10}
PROBE_LABELS: Final[dict[int, str]] = {m: p for p, m in PROBE_MULTIPLIERS.items()}
_MISMATCH: Final = "ripple: adapter_declaration_mismatch: "
_PRECONNECTED_CONFLICT: Final = (
    _MISMATCH + "--preconnected противоречит декларации захвата (settling_unknown)"
)


def session_declaration(session: LoadedSession) -> AdapterDeclaration | None:
    """Декларация адаптера из контекста сессии; битые ключи — InputError."""
    snapshot = ContextStore(session.session_dir, session.manifest.session_id).load().snapshot
    if snapshot is None:
        snapshot = ContextSnapshot.empty(session.manifest.session_id)
    return declaration_from_snapshot(snapshot)


def resolve_adapter(
    args: argparse.Namespace, declaration: AdapterDeclaration | None
) -> tuple[AdapterSpec, SettlingDeclaration]:
    """Декларация приоритетна; заданный флаг — утверждение против неё."""
    if declaration is None:
        cap_nf = DEFAULT_CAP_NF if args.cap_nf is None else cast("float", args.cap_nf)
        series_r_ohm = (
            DEFAULT_SERIES_R_OHM if args.series_r_ohm is None else cast("float", args.series_r_ohm)
        )
        probe = PROBE_MULTIPLIERS["1x" if args.probe is None else cast("str", args.probe)]
        settling = (
            SettlingDeclaration.PRECONNECTED if args.preconnected else SettlingDeclaration.UNKNOWN
        )
        return AdapterSpec(
            cap_nf=cap_nf, series_r_ohm=series_r_ohm, probe_multiplier=probe
        ), settling
    spec = declaration.to_spec()
    _assert_flag_value("--cap-nf", args.cap_nf, spec.cap_nf)
    _assert_flag_value("--series-r-ohm", args.series_r_ohm, spec.series_r_ohm)
    _assert_flag_probe(args.probe, spec.probe_multiplier)
    if bool(args.preconnected) and not declaration.preconnected:
        raise InputError(_PRECONNECTED_CONFLICT)
    settling = (
        SettlingDeclaration.PRECONNECTED
        if declaration.preconnected
        else SettlingDeclaration.UNKNOWN
    )
    return spec, settling


def _assert_flag_value(flag: str, value: float | None, declared: float) -> None:
    """Заданный числовой флаг обязан совпасть со значением декларации."""
    if value is None or float(value) == declared:
        return
    raise InputError(
        f"{_MISMATCH}{flag}={float(value):g} противоречит декларации захвата ({declared:g})"
    )


def _assert_flag_probe(probe: str | None, declared_multiplier: int) -> None:
    """Заданный --probe обязан совпасть с множителем декларации."""
    if probe is None or PROBE_MULTIPLIERS[probe] == declared_multiplier:
        return
    declared_label = PROBE_LABELS[declared_multiplier]
    raise InputError(
        f"{_MISMATCH}--probe={probe} противоречит декларации захвата ({declared_label})"
    )
