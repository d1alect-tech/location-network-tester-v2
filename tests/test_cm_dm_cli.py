from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lnt.cli import EXIT_INPUT, EXIT_OK, main
from lnt.types import ChannelMode, SessionType

if TYPE_CHECKING:
    import pytest

_PROBE_PAIR = ["--probe-pair"]


def _record_capture(**kwargs: object) -> Path:
    out_dir = kwargs["out_dir"]
    assert isinstance(out_dir, Path)
    return out_dir


def test_probe_pair_resolves_cm_dm_session_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a CM/DM probe-pair capture request with default two channels.
    recorded: list[object] = []

    def record_capture(**kwargs: object) -> Path:
        recorded.append((kwargs["session_type"], kwargs["channel_mode"]))
        return _record_capture(**kwargs)

    monkeypatch.setattr("lnt.cli_capture.capture_session", record_capture)

    # When: the public CLI parses and dispatches the capture request.
    code = main(["capture", "--out", str(tmp_path / "cm-dm"), *_PROBE_PAIR])

    # Then: the request resolves to a two-channel cm_dm measurement session.
    assert code == EXIT_OK
    assert recorded == [(SessionType.CM_DM, ChannelMode.DUAL)]


def test_probe_pair_calibrate_resolves_calibration_session_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a CM/DM calibration capture (both pickups on one conductor).
    recorded: list[object] = []

    def record_capture(**kwargs: object) -> Path:
        recorded.append(kwargs["session_type"])
        return _record_capture(**kwargs)

    monkeypatch.setattr("lnt.cli_capture.capture_session", record_capture)

    # When: the calibration flag accompanies --probe-pair.
    code = main(
        ["capture", "--out", str(tmp_path / "calibration"), "--probe-pair-calibrate", *_PROBE_PAIR],
    )

    # Then: the request resolves to the dedicated calibration session type.
    assert code == EXIT_OK
    assert recorded == [SessionType.CM_DM_CALIBRATION]


def test_calibrate_flag_requires_probe_pair(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a calibration flag without its required --probe-pair companion.
    # When: the CLI validates the capture mode flags.
    code = main(["capture", "--out", str(tmp_path / "calibration"), "--probe-pair-calibrate"])
    captured = capsys.readouterr()

    # Then: the request is rejected with an explicit dependency message.
    assert code == EXIT_INPUT
    assert "--probe-pair-calibrate допустим только с --probe-pair" in captured.err


def test_calibration_dir_requires_probe_pair(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a calibration directory reference without --probe-pair.
    # When: the CLI validates the capture mode flags.
    code = main(["capture", "--out", str(tmp_path / "cm-dm"), "--probe-calibration", "../cal"])
    captured = capsys.readouterr()

    # Then: the dangling reference is rejected before hardware access.
    assert code == EXIT_INPUT
    assert "--probe-calibration допустим только с --probe-pair" in captured.err


def test_probe_pair_rejects_self_noise(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a probe-pair capture that also claims self-noise baseline mode.
    # When: the CLI validates mutually exclusive capture modes.
    code = main(["capture", "--out", str(tmp_path / "conflict"), "--self-noise", *_PROBE_PAIR])
    captured = capsys.readouterr()

    # Then: the contradictory combination is rejected.
    assert code == EXIT_INPUT
    assert "--probe-pair взаимоисключающий с --self-noise" in captured.err


def test_probe_pair_rejects_line_quality(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a probe-pair capture that also claims line-quality transformer mode.
    # When: the CLI validates mutually exclusive capture modes.
    code = main(["capture", "--out", str(tmp_path / "conflict"), "--line-quality", *_PROBE_PAIR])
    captured = capsys.readouterr()

    # Then: the contradictory combination is rejected.
    assert code == EXIT_INPUT
    assert "--probe-pair взаимоисключающий с --line-quality" in captured.err


def test_probe_pair_rejects_single_channel(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a probe-pair capture restricted to one channel.
    # When: the CLI validates channel requirements for differential pickup.
    code = main(["capture", "--out", str(tmp_path / "single"), "--channels", "1", *_PROBE_PAIR])
    captured = capsys.readouterr()

    # Then: single-channel saving is rejected outright.
    assert code == EXIT_INPUT
    assert "probe-pair требует два канала" in captured.err


def test_probe_pair_rejects_baseline_and_setup_overrides(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: every baseline or CH1 setup override flag that probe-pair forbids.
    forbidden_flags: list[list[str]] = [
        ["--baseline", "../baseline"],
        ["--termination-ohm", "50"],
        ["--probe-multiplier", "10"],
        ["--component-values-basis", "operator_measured"],
        ["--rc-r-ohm", "100"],
        ["--rc-c1-nf", "10"],
        ["--rc-c2-nf", "10"],
    ]

    for forbidden in forbidden_flags:
        # When: the forbidden flag accompanies --probe-pair.
        code = main(["capture", "--out", str(tmp_path / "override"), *forbidden, *_PROBE_PAIR])
        flag_name = forbidden[0]
        captured = capsys.readouterr()

        # Then: each override is rejected by name.
        assert code == EXIT_INPUT, flag_name
        assert f"--probe-pair не принимает {flag_name}" in captured.err, flag_name


def test_measurement_flow_unaffected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an ordinary capture command without any probe flags.
    recorded: list[object] = []

    def record_capture(**kwargs: object) -> Path:
        recorded.append((kwargs["session_type"], kwargs["channel_mode"]))
        return _record_capture(**kwargs)

    monkeypatch.setattr("lnt.cli_capture.capture_session", record_capture)

    # When: the plain measurement flow runs through the same routing seam.
    code = main(["capture", "--out", str(tmp_path / "measurement")])

    # Then: session type and channel mode stay exactly as before T6.
    assert code == EXIT_OK
    assert recorded == [(SessionType.MEASUREMENT, ChannelMode.DUAL)]
