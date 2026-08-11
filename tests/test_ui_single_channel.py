"""Однокональный режим в UI-бэкенде: модели, операции, payloads."""

from pathlib import Path

import pytest

from lnt.simulate import simulate_session
from lnt.types import ChannelMode
from lnt.ui import operations
from lnt.ui.models import CaptureRequest, SimulateRequest, parse_job_request
from lnt.ui.operations import LntBackend
from lnt.ui.payloads import session_detail_payload, sessions_payload

SAMPLE_RATE_HZ = 100_000.0
DURATION_S = 2.4


def _simulate(root: Path, name: str, *, channel_mode: ChannelMode) -> Path:
    return simulate_session(
        out_dir=root / name,
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        seed=1,
        channel_mode=channel_mode,
    )


class TestRequestModels:
    def test_capture_request_accepts_channels_one(self) -> None:
        request = parse_job_request(
            {"kind": "capture", "channels": 1},
        )

        assert isinstance(request, CaptureRequest)
        assert request.channels == 1

    def test_capture_request_defaults_to_dual(self) -> None:
        request = parse_job_request({"kind": "capture"})

        assert isinstance(request, CaptureRequest)
        assert request.channels == 2

    def test_simulate_request_accepts_channels_one(self) -> None:
        request = parse_job_request(
            {"kind": "simulate", "profile": "bad", "channels": 1},
        )

        assert isinstance(request, SimulateRequest)
        assert request.channels == 1

    def test_capture_request_rejects_unknown_channels(self) -> None:
        with pytest.raises(ValueError, match="channels"):
            parse_job_request({"kind": "capture", "channels": 3})


class TestBackend:
    def test_capture_one_passes_channel_mode(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        recorded: list[object] = []

        def record_capture(**kwargs: object) -> Path:
            recorded.append(kwargs["channel_mode"])
            out_dir = kwargs["out_dir"]
            assert isinstance(out_dir, Path)
            return out_dir

        monkeypatch.setattr(operations, "capture_session", record_capture)
        request = CaptureRequest(kind="capture", channels=1)

        LntBackend().capture_one(request, tmp_path / "cap", None)

        assert recorded == [ChannelMode.CH1_ONLY]

    def test_simulate_one_single_channel_session(self, tmp_path: Path) -> None:
        request = SimulateRequest(kind="simulate", profile="bad", channels=1)

        session_dir = LntBackend().simulate_one(request, tmp_path / "syn", None)

        assert not (session_dir / "ch2.npy").exists()


class TestPayloads:
    def test_sessions_payload_reports_channels(self, tmp_path: Path) -> None:
        _simulate(tmp_path, "single", channel_mode=ChannelMode.CH1_ONLY)
        _simulate(tmp_path, "dual", channel_mode=ChannelMode.DUAL)

        payload = sessions_payload(tmp_path)

        sessions = payload["sessions"]
        assert isinstance(sessions, list)
        by_name = {entry["name"]: entry for entry in sessions}
        assert by_name["single"]["summary"]["channels"] == "ch1_only"
        assert by_name["dual"]["summary"]["channels"] == "dual"

    def test_session_detail_reports_ch2_availability(self, tmp_path: Path) -> None:
        _simulate(tmp_path, "single", channel_mode=ChannelMode.CH1_ONLY)
        _simulate(tmp_path, "dual", channel_mode=ChannelMode.DUAL)

        single_detail = session_detail_payload(tmp_path, "single")
        dual_detail = session_detail_payload(tmp_path, "dual")

        assert single_detail["ch2_available"] is False
        assert dual_detail["ch2_available"] is True
