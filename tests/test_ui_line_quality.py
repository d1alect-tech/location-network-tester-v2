"""UI-контракт режима качества сети: модели запросов, backend, payloads."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lnt.analysis import LineQualityAnalysis
from lnt.errors import InputError
from lnt.types import ChannelMode, SessionType
from lnt.ui import operations
from lnt.ui.models import CaptureRequest, parse_job_request
from lnt.ui.operations import LntBackend
from lnt.ui.payloads import session_detail_payload, sessions_payload
from tests.line_quality_fixtures import write_line_quality_session


class TestCaptureRequestInput:
    def test_defaults_to_rc_input(self) -> None:
        request = parse_job_request({"kind": "capture"})

        assert isinstance(request, CaptureRequest)
        assert request.input == "rc"

    def test_accepts_transformer_input_single_channel(self) -> None:
        request = parse_job_request({"kind": "capture", "input": "transformer", "channels": 1})

        assert isinstance(request, CaptureRequest)
        assert request.input == "transformer"

    def test_rejects_transformer_with_dual_channels(self) -> None:
        with pytest.raises(ValidationError):
            parse_job_request({"kind": "capture", "input": "transformer", "channels": 2})

    def test_rejects_transformer_with_self_noise(self) -> None:
        with pytest.raises(ValidationError):
            parse_job_request(
                {"kind": "capture", "input": "transformer", "channels": 1, "self_noise": True},
            )

    def test_rejects_transformer_with_baseline(self) -> None:
        with pytest.raises(ValidationError):
            parse_job_request(
                {
                    "kind": "capture",
                    "input": "transformer",
                    "channels": 1,
                    "baseline_session": "noise",
                },
            )

    def test_rejects_unknown_input(self) -> None:
        with pytest.raises(ValidationError):
            parse_job_request({"kind": "capture", "input": "antenna"})


class TestBackendLineQuality:
    def test_capture_one_maps_transformer_to_line_quality(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        recorded: dict[str, object] = {}

        def record_capture(**kwargs: object) -> Path:
            recorded.update(kwargs)
            out_dir = kwargs["out_dir"]
            assert isinstance(out_dir, Path)
            return out_dir

        monkeypatch.setattr(operations, "capture_session", record_capture)
        request = CaptureRequest(kind="capture", input="transformer", channels=1)

        LntBackend().capture_one(request, tmp_path / "cap", None)

        assert recorded["session_type"] is SessionType.LINE_QUALITY
        assert recorded["channel_mode"] is ChannelMode.CH1_ONLY
        assert recorded["baseline_session"] is None

    def test_analyze_and_write_line_quality_session(self, tmp_path: Path) -> None:
        session = write_line_quality_session(tmp_path / "line")

        result = LntBackend().analyze_and_write(session)

        assert isinstance(result.analysis, LineQualityAnalysis)
        assert (session / "metrics.json").is_file()
        assert not (session / "spectrum.csv").exists()

    def test_compare_rejects_line_quality_session(self, tmp_path: Path) -> None:
        session_a = write_line_quality_session(tmp_path / "a", session_id="line-a")
        session_b = write_line_quality_session(tmp_path / "b", session_id="line-b")

        with pytest.raises(InputError, match="line-quality"):
            LntBackend().compare(session_a, session_b)


class TestLineQualityPayloads:
    def test_sessions_payload_marks_analyzed_without_spectrum_csv(self, tmp_path: Path) -> None:
        session = write_line_quality_session(tmp_path / "line")
        LntBackend().analyze_and_write(session)

        payload = sessions_payload(tmp_path)

        sessions = payload["sessions"]
        assert isinstance(sessions, list)
        entry = next(item for item in sessions if item["name"] == "line")
        assert entry["analyzed"] is True
        assert entry["summary"]["session_type"] == "line_quality"

    def test_session_detail_payload_exposes_line_quality_metrics(self, tmp_path: Path) -> None:
        session = write_line_quality_session(tmp_path / "line")
        LntBackend().analyze_and_write(session)

        payload = session_detail_payload(tmp_path, "line")

        analysis = payload["analysis"]
        assert isinstance(analysis, dict)
        assert analysis["needle"] is None
        assert analysis["spectrum"] is None
        line_quality = analysis["line_quality"]
        assert isinstance(line_quality, dict)
        assert line_quality["thd_ratio"] == pytest.approx(0.05, rel=0.05)
