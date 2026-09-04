"""Команда ``lnt capture``: захват с Hantek 6022BE.

Поверхность CLI, коды выхода 0/1/2/3 и тексты stdout/stderr неизменны;
серийные хелперы переиспользуются из ``lnt.cli_simulate``.
"""
# ruff: noqa: TC003 - CLI-хендлеры держат argparse-контракт видимым

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from lnt._cli_capture import CaptureSetupOptions, build_capture_setup
from lnt.acquire import capture_session
from lnt.cli_simulate import SeriesRun, channel_mode, run_session_series
from lnt.errors import InputError
from lnt.types import ChannelMode, SeriesPosition, SessionType


def capture_session_type(args: argparse.Namespace) -> SessionType:
    """Разрешает тип сессии из режимных флагов capture."""
    self_noise = CaptureSetupOptions.validate_mode_flags(args)
    line_quality = cast("bool", args.line_quality)
    if self_noise and line_quality:
        raise InputError("--self-noise и --line-quality взаимоисключающие")
    if line_quality:
        return SessionType.LINE_QUALITY
    if self_noise:
        return SessionType.SELF_NOISE
    return CaptureSetupOptions.probe_pair_session_type(args)


def cmd_capture(args: argparse.Namespace) -> int:
    """Обработчик ``lnt capture``: захват с устройства серией повторов."""
    session_type = capture_session_type(args)
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
    run = SeriesRun(
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
                else channel_mode(args)
            ),
        )

    return run_session_series(run, write_session)


# Совместимость: прежние приватные имена из ``lnt.cli``.
_capture_session_type = capture_session_type
_cmd_capture = cmd_capture
