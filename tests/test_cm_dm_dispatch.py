"""T8: маршрутизация CM/DM-сессий на точках диспетчеризации панели и CLI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from lnt.analysis import AnalysisResult, LineQualityAnalysis
from lnt.cli import EXIT_INPUT, EXIT_OK, main
from lnt.simulate import simulate_session
from lnt.ui.operations import LntBackend
from tests.cm_dm_fixtures import build_probe_pair_session
from tests.line_quality_fixtures import write_line_quality_session

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

_FS_HZ = 250_000.0


def _rewrite_manifest(session_dir: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    path = session_dir / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestBackendRouting:
    """Диспетчеризация LntBackend.analyze_and_write по типу сессии."""

    def test_backend_analyze_routes_cm_dm(self, tmp_path: Path) -> None:
        # Given: a synthetic probe-pair cm_dm session on disk.
        session = build_probe_pair_session(tmp_path / "cm-dm", duration_s=0.05)

        # When: the panel backend analyzes the session and writes artifacts.
        result = LntBackend().analyze_and_write(session)

        # Then: metrics.json carries the cm_dm section and the spectrum CSV exists.
        payload = json.loads((session / "metrics.json").read_text(encoding="utf-8"))
        assert "cm_dm" in payload
        assert payload["cm_dm"]["status"] == "unavailable"
        assert (session / "cm_dm_spectrum.csv").is_file()
        assert result.analysis.session_type.value == "cm_dm"

    def test_backend_analyze_measurement_unchanged(self, tmp_path: Path) -> None:
        # Given: an ordinary synthetic measurement session.
        session = simulate_session(
            out_dir=tmp_path / "m",
            profile="bad",
            duration_s=2.1,
            sample_rate_hz=_FS_HZ,
            seed=6022,
        )

        # When: the panel backend analyzes it through the same entry point.
        result = LntBackend().analyze_and_write(session)

        # Then: the v1 payload is produced unchanged, without a cm_dm section.
        assert isinstance(result.analysis, AnalysisResult)
        payload = json.loads((session / "metrics.json").read_text(encoding="utf-8"))
        assert "cm_dm" not in payload
        assert payload["needle"] is not None

    def test_backend_analyze_line_quality_unchanged(self, tmp_path: Path) -> None:
        # Given: a transformer line-quality session.
        session = write_line_quality_session(tmp_path / "line")

        # When: the panel backend analyzes it through the same entry point.
        result = LntBackend().analyze_and_write(session)

        # Then: the line-quality path stays untouched, without a cm_dm section.
        assert isinstance(result.analysis, LineQualityAnalysis)
        payload = json.loads((session / "metrics.json").read_text(encoding="utf-8"))
        assert "cm_dm" not in payload
        assert payload["line_quality"] is not None
        assert not (session / "spectrum.csv").exists()


class TestCliRouting:
    """Диспетчеризация CLI-команды analyze по типу сессии."""

    def test_cli_analyze_cm_dm_end_to_end(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Given: a synthetic probe-pair cm_dm session on disk.
        session = build_probe_pair_session(tmp_path / "cm-dm", duration_s=0.05)

        # When: the generic analyze command runs on it.
        code = main(["analyze", str(session)])

        # Then: it exits cleanly with CM/DM artifacts and a readable summary.
        assert code == EXIT_OK
        stdout = capsys.readouterr().out
        assert "CM/DM" in stdout
        payload = json.loads((session / "metrics.json").read_text(encoding="utf-8"))
        assert "cm_dm" in payload
        assert (session / "cm_dm_spectrum.csv").is_file()

    def test_cli_analyze_calibration_session_errors(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Given: a session whose manifest declares the calibration type.
        session = build_probe_pair_session(tmp_path / "calibration", duration_s=0.05)
        _rewrite_manifest(
            session,
            lambda payload: payload.update({"session_type": "cm_dm_calibration"}),
        )

        # When: the generic analyze command runs on it.
        code = main(["analyze", str(session)])

        # Then: the InputError surfaces as the conventional one-line exit-2 report.
        assert code == EXIT_INPUT
        stderr = capsys.readouterr().err
        assert "калибровочн" in stderr
