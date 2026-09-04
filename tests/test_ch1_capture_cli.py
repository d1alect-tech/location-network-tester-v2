from __future__ import annotations

from pathlib import Path

import pytest

from lnt.cli import EXIT_DEVICE, EXIT_INPUT, EXIT_OK, main
from lnt.types import ChannelMode, ComponentValuesBasis, FloatingDifferentialRcShunt


@pytest.mark.usefixtures("no_hantek_driver")
def test_capture_accepts_explicit_baseline_and_floating_rc_component_options(
    tmp_path: Path,
) -> None:
    # Given: a measurement capture with an explicit baseline and component provenance.
    # When: the capture command is parsed before hardware access.
    code = main(
        [
            "capture",
            "--out",
            str(tmp_path / "measurement"),
            "--baseline",
            "../baseline",
            "--rc-r-ohm",
            "100",
            "--rc-c1-nf",
            "10",
            "--rc-c2-nf",
            "10",
            "--component-values-basis",
            "operator_measured",
        ],
    )

    # Then: parsing reaches the ordinary no-device boundary instead of rejecting the contract.
    assert code == EXIT_DEVICE


@pytest.mark.usefixtures("no_hantek_driver")
def test_self_noise_capture_accepts_explicit_termination_option(tmp_path: Path) -> None:
    # Given: a self-noise baseline capture with its scope termination declared.
    # When: the CLI accepts the capture request.
    code = main(
        [
            "capture",
            "--out",
            str(tmp_path / "baseline"),
            "--self-noise",
            "--termination-ohm",
            "50",
        ],
    )

    # Then: it reaches device acquisition with a typed self-noise setup.
    assert code == EXIT_DEVICE


@pytest.mark.parametrize(
    "override_args",
    [
        ["--rc-r-ohm", "100"],
        ["--rc-c1-nf", "10"],
        ["--rc-c2-nf", "10"],
        ["--rc-r-ohm", "100", "--rc-c1-nf", "10"],
        ["--component-values-basis", "operator_measured"],
        [
            "--rc-r-ohm",
            "100",
            "--rc-c1-nf",
            "10",
            "--rc-c2-nf",
            "10",
            "--component-values-basis",
            "nominal",
        ],
    ],
)
@pytest.mark.usefixtures("no_hantek_driver")
def test_measurement_capture_rejects_partial_or_contradictory_rc_overrides(
    tmp_path: Path,
    override_args: list[str],
) -> None:
    # Given: a capture command with incomplete or semantically contradictory RC provenance.
    # When: parser and capture setup validate the measurement request.
    code = main(["capture", "--out", str(tmp_path / "measurement"), *override_args])

    # Then: invalid provenance stops before the ordinary no-device boundary.
    assert code == EXIT_INPUT


@pytest.mark.parametrize(
    "measurement_args",
    [
        ["--baseline", "../measurement"],
        ["--rc-r-ohm", "100", "--rc-c1-nf", "10", "--rc-c2-nf", "10"],
        ["--component-values-basis", "operator_measured"],
    ],
)
@pytest.mark.usefixtures("no_hantek_driver")
def test_self_noise_capture_rejects_measurement_only_flags(
    tmp_path: Path,
    measurement_args: list[str],
) -> None:
    # Given: a self-noise capture with a measurement-only baseline or RC flag.
    # When: its setup is validated before hardware access.
    code = main(["capture", "--out", str(tmp_path / "baseline"), "--self-noise", *measurement_args])

    # Then: no measurement setup is silently ignored.
    assert code == EXIT_INPUT


def test_capture_rc_triplet_without_basis_records_operator_measured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: all three explicitly supplied RC values without a basis override.
    captured_setups: list[FloatingDifferentialRcShunt] = []

    def record_capture(**kwargs: object) -> Path:
        setup = kwargs["ch1_setup"]
        out_dir = kwargs["out_dir"]
        assert isinstance(setup, FloatingDifferentialRcShunt)
        assert isinstance(out_dir, Path)
        captured_setups.append(setup)
        return out_dir

    monkeypatch.setattr("lnt.cli_capture.capture_session", record_capture)

    # When: the public CLI builds a measurement capture request.
    code = main(
        [
            "capture",
            "--out",
            str(tmp_path / "measurement"),
            "--rc-r-ohm",
            "100",
            "--rc-c1-nf",
            "10",
            "--rc-c2-nf",
            "10",
        ],
    )

    # Then: explicit components are never recorded as nominal defaults.
    assert code == EXIT_OK
    assert captured_setups[0].component_values_basis is ComponentValuesBasis.OPERATOR_MEASURED


def test_capture_without_rc_overrides_records_nominal_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a measurement capture without explicit component flags.
    captured_setups: list[FloatingDifferentialRcShunt] = []

    def record_capture(**kwargs: object) -> Path:
        setup = kwargs["ch1_setup"]
        out_dir = kwargs["out_dir"]
        assert isinstance(setup, FloatingDifferentialRcShunt)
        assert isinstance(out_dir, Path)
        captured_setups.append(setup)
        return out_dir

    monkeypatch.setattr("lnt.cli_capture.capture_session", record_capture)

    # When: the public CLI builds the default measurement capture request.
    code = main(["capture", "--out", str(tmp_path / "measurement")])

    # Then: only the documented nominal RC setup is recorded.
    assert code == EXIT_OK
    assert captured_setups[0].component_values_basis is ComponentValuesBasis.NOMINAL


@pytest.mark.parametrize(
    ("channel_args", "expected_mode"),
    [
        ([], ChannelMode.DUAL),
        (["--channels", "2"], ChannelMode.DUAL),
        (["--channels", "1"], ChannelMode.CH1_ONLY),
    ],
)
def test_capture_channels_flag_maps_to_channel_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    channel_args: list[str],
    expected_mode: ChannelMode,
) -> None:
    # Given: a capture request with an optional --channels flag.
    captured_modes: list[object] = []

    def record_capture(**kwargs: object) -> Path:
        out_dir = kwargs["out_dir"]
        assert isinstance(out_dir, Path)
        captured_modes.append(kwargs["channel_mode"])
        return out_dir

    monkeypatch.setattr("lnt.cli_capture.capture_session", record_capture)

    # When: the public CLI builds the capture request.
    code = main(["capture", "--out", str(tmp_path / "measurement"), *channel_args])

    # Then: the channel mode reaches capture_session explicitly.
    assert code == EXIT_OK
    assert captured_modes == [expected_mode]


def test_simulate_channels_flag_writes_single_channel_session(tmp_path: Path) -> None:
    # Given/When: a synthetic single-channel session via the public CLI.
    out_dir = tmp_path / "syn-single"
    code = main(
        [
            "simulate",
            "--profile",
            "bad",
            "--out",
            str(out_dir),
            "--duration",
            "2.4",
            "--rate",
            "100000",
            "--channels",
            "1",
        ],
    )

    # Then: the session is written without a CH2 track.
    assert code == EXIT_OK
    assert (out_dir / "ch1.npy").exists()
    assert not (out_dir / "ch2.npy").exists()
