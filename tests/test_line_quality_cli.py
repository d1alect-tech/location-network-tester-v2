"""CLI-контракт режима качества сети: capture-флаги, analyze, compare."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from lnt.cli import EXIT_DEVICE, EXIT_INPUT, EXIT_OK, main
from tests.line_quality_fixtures import write_line_quality_session

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.usefixtures("no_hantek_driver")
def test_capture_line_quality_flag_reaches_device_boundary(tmp_path: Path) -> None:
    # Given/When: a line-quality capture request (single probe on the transformer).
    code = main(["capture", "--out", str(tmp_path / "line"), "--line-quality"])

    # Then: the contract parses and stops only at the missing device.
    assert code == EXIT_DEVICE


@pytest.mark.usefixtures("no_hantek_driver")
def test_capture_line_quality_accepts_probe_multiplier_override(tmp_path: Path) -> None:
    # Given/When: an explicit 1x probe (direct BNC cable) declaration.
    code = main(
        [
            "capture",
            "--out",
            str(tmp_path / "line"),
            "--line-quality",
            "--probe-multiplier",
            "1",
        ],
    )

    # Then: the override is a valid part of the capture contract.
    assert code == EXIT_DEVICE


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--self-noise"],
        ["--baseline", "../noise"],
        ["--rc-r-ohm", "100", "--rc-c1-nf", "10", "--rc-c2-nf", "10"],
        ["--termination-ohm", "50"],
    ],
)
@pytest.mark.usefixtures("no_hantek_driver")
def test_capture_line_quality_rejects_foreign_mode_flags(
    tmp_path: Path,
    extra_args: list[str],
) -> None:
    # When/Then: line-quality does not mix with measurement/self-noise contracts.
    code = main(["capture", "--out", str(tmp_path / "line"), "--line-quality", *extra_args])
    assert code == EXIT_INPUT


@pytest.mark.usefixtures("no_hantek_driver")
def test_probe_multiplier_requires_line_quality(tmp_path: Path) -> None:
    # When/Then: the probe multiplier belongs to the transformer contract only.
    code = main(["capture", "--out", str(tmp_path / "m"), "--probe-multiplier", "10"])
    assert code == EXIT_INPUT


def test_analyze_line_quality_session_prints_thd(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a synthetic line-quality session on disk.
    session = write_line_quality_session(tmp_path / "line")

    # When: the generic analyze command runs.
    code = main(["analyze", str(session)])

    # Then: the operator sees mains-quality metrics and metrics.json exists.
    assert code == EXIT_OK
    stdout = capsys.readouterr().out
    assert "THD" in stdout
    assert "H3" in stdout
    payload = json.loads((session / "metrics.json").read_text(encoding="utf-8"))
    assert payload["line_quality"]["thd_ratio"] == pytest.approx(0.05, rel=0.05)
    assert not (session / "spectrum.csv").exists()


def test_compare_rejects_line_quality_sessions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: two line-quality sessions.
    session_a = write_line_quality_session(tmp_path / "a", session_id="line-a")
    session_b = write_line_quality_session(tmp_path / "b", session_id="line-b", h3_ratio=0.08)

    # When: the operator tries to A/B them.
    code = main(["compare", str(session_a), str(session_b)])

    # Then: the CLI refuses with a clear one-line error.
    assert code == EXIT_INPUT
    stderr = capsys.readouterr().err
    assert "line-quality" in stderr
