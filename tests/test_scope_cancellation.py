from __future__ import annotations

import inspect
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

import numpy as np
import pytest
from PyHT6022.LibUsbScope import Oscilloscope

from lnt import scope_io
from lnt.acquire import capture_session
from lnt.errors import DeviceNotFoundError
from lnt.scope_io import NEVER_CANCELLED, CancellationToken, CancelledResult, run_capture
from lnt.simulate import simulate_session
from lnt.ui.job_worker import WorkerCancelled, WorkerContext, execute_job
from lnt.ui.models import CaptureRequest, parse_job_request
from lnt.ui.operations import LntBackend

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from lnt.analysis import AnalysisResult, LineQualityAnalysis
    from lnt.types import SeriesPosition


@dataclass(slots=True)
class _Shutdown:
    calls: list[str]

    def set(self) -> None:
        self.calls.append("shutdown")


@dataclass(slots=True)
class _FakeScope:
    blocks_before_complete: int = 1
    poll_delay_s: float = 0.0
    poll_error: Exception | None = None
    calls: list[str] = field(default_factory=list)
    poll_timeouts: list[int] = field(default_factory=list)
    is_device_firmware_present: bool = True
    _callback: Callable[[object, object], None] | None = None
    _polls: int = 0

    def setup(self) -> None:
        self.calls.append("setup")

    def open_handle(self) -> bool:
        self.calls.append("open")
        return True

    def close_handle(self) -> None:
        self.calls.append("close")

    def flash_firmware(self) -> None:
        self.calls.append("flash")

    def set_interface(self, _index: int) -> None: ...

    def set_num_channels(self, _count: int) -> None: ...

    def set_sample_rate(self, _code: int) -> None: ...

    def set_ch1_voltage_range(self, _code: int) -> None: ...

    def set_ch2_voltage_range(self, _code: int) -> None: ...

    def read_async(
        self,
        callback: Callable[[object, object], None],
        data_size: int,
        outstanding_transfers: int,
        *,
        raw: bool,
    ) -> _Shutdown:
        assert raw
        del data_size, outstanding_transfers
        self.calls.append("read")
        self._callback = callback
        return _Shutdown(self.calls)

    def start_capture(self) -> None:
        self.calls.append("start")

    def stop_capture(self) -> None:
        self.calls.append("stop")

    def poll(self, timeout_ms: int) -> None:
        self.calls.append("poll")
        self.poll_timeouts.append(timeout_ms)
        if self.poll_delay_s:
            time.sleep(self.poll_delay_s)
        if self.poll_error is not None:
            raise self.poll_error
        self._polls += 1
        if self._polls >= self.blocks_before_complete:
            assert self._callback is not None
            raw = bytearray(np.full(64, 128, dtype=np.uint8))
            self._callback(raw, raw)


def _capture(scope: _FakeScope, token: CancellationToken | None = None) -> object:
    if token is None:
        return run_capture(
            scope,
            rate_code=1,
            ch1_range_code=1,
            sample_rate_hz=1_000_000.0,
            requested_samples=32,
        )
    return run_capture(
        scope,
        rate_code=1,
        ch1_range_code=1,
        sample_rate_hz=1_000_000.0,
        requested_samples=32,
        cancellation_token=token,
    )


def test_cancel_before_start_does_not_acquire_scope() -> None:
    scope = _FakeScope()
    token = CancellationToken(lambda: True)

    result = _capture(scope, token)

    assert isinstance(result, CancelledResult)
    assert scope.calls == []


def test_cancel_mid_stream_acknowledges_within_500_ms_and_closes_once() -> None:
    requested = threading.Event()
    scope = _FakeScope(blocks_before_complete=10_000, poll_delay_s=0.25)
    token = CancellationToken(requested.is_set)
    result: list[object] = []
    worker = threading.Thread(target=lambda: result.append(_capture(scope, token)))
    worker.start()
    while not scope.poll_timeouts:
        time.sleep(0)

    started = time.monotonic()
    requested.set()
    worker.join(timeout=0.5)
    latency_ms = (time.monotonic() - started) * 1_000

    assert not worker.is_alive()
    assert latency_ms < 450
    assert isinstance(result[0], CancelledResult)
    assert scope.poll_timeouts == [250]
    assert scope.calls[-3:] == ["stop", "shutdown", "close"]
    assert scope.calls.count("close") == 1


def test_completed_capture_ignores_cancellation_after_requested_samples() -> None:
    requested = threading.Event()
    scope = _FakeScope()

    result = _capture(scope, CancellationToken(requested.is_set))
    requested.set()

    assert not isinstance(result, CancelledResult)
    assert scope.calls[-3:] == ["stop", "shutdown", "close"]


def test_usb_error_wins_when_poll_is_atomic_and_closes_once() -> None:
    requested = threading.Event()

    class UsbError(Exception):
        pass

    UsbError.__module__ = "usb1"
    scope = _FakeScope(poll_error=UsbError("concurrent disconnect"))

    with pytest.raises(DeviceNotFoundError, match="USB"):
        _capture(scope, CancellationToken(requested.is_set))

    requested.set()
    assert scope.calls[-3:] == ["stop", "shutdown", "close"]
    assert scope.calls.count("close") == 1


def test_timeout_path_closes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    scope = _FakeScope(blocks_before_complete=10_000)
    times = iter((0.0, 3.0))
    monkeypatch.setattr("lnt.scope_io.time.monotonic", lambda: next(times))

    with pytest.raises(DeviceNotFoundError, match="поток прервался"):
        _capture(scope)

    assert scope.calls[-3:] == ["stop", "shutdown", "close"]
    assert scope.calls.count("close") == 1


def test_cancelled_capture_leaves_no_session_or_partial_dir(tmp_path: Path) -> None:
    out_dir = tmp_path / "cancelled"

    result = capture_session(
        out_dir=out_dir,
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        scope_factory=_FakeScope,
        cancellation_token=CancellationToken(lambda: True),
    )

    assert isinstance(result, CancelledResult)
    assert list(tmp_path.iterdir()) == []


def test_pinned_hantek_poll_is_replaced_by_bounded_timeout_path() -> None:
    source = inspect.getsource(Oscilloscope.poll)
    bounded_source = inspect.getsource(scope_io)

    assert "handleEvents()" in source
    assert "handleEventsTimeout" in bounded_source


@dataclass(frozen=True, slots=True)
class _SeriesBackend(LntBackend):
    cancelled: threading.Event

    @override
    def capture_one(
        self,
        request: CaptureRequest,
        out_dir: Path,
        series: SeriesPosition | None,
        cancellation_token: CancellationToken = NEVER_CANCELLED,
    ) -> Path | CancelledResult:
        del request, series, cancellation_token
        return simulate_session(
            out_dir=out_dir,
            profile="quiet",
            duration_s=2.4,
            sample_rate_hz=20_000.0,
            seed=1,
        )

    @override
    def analyze_and_write(self, session_dir: Path) -> AnalysisResult | LineQualityAnalysis:
        result = LntBackend.analyze_and_write(self, session_dir)
        self.cancelled.set()
        return result


def test_series_cancel_between_members_keeps_completed_member(tmp_path: Path) -> None:
    cancelled = threading.Event()
    backend = _SeriesBackend(cancelled)
    request = parse_job_request(
        {"kind": "capture", "repeat": 2, "interval_s": 0, "output_name": "series"}
    )

    result = execute_job(
        WorkerContext(
            backend=backend,
            root=tmp_path,
            is_cancelled=cancelled.is_set,
            report=lambda _update: None,
        ),
        request,
    )

    assert isinstance(result, WorkerCancelled)
    assert (tmp_path / "series-001").is_dir()
    assert not (tmp_path / "series-002").exists()
