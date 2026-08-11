from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

import pytest

from lnt.runtime.lease import (
    HardwareLease,
    HardwareLeaseHeldError,
    LeaseOwner,
    bind_exclusive_loopback,
    current_process_start_time,
)
from lnt.runtime.scheduler import (
    AnalysisQueueFullError,
    OperationClass,
    OperationScheduler,
    run_member_series,
)


def _write_owner(path: Path, owner: LeaseOwner) -> None:
    path.write_text(json.dumps(owner.to_payload()), encoding="utf-8")


def test_second_process_reports_hardware_owner(tmp_path: Path) -> None:
    lease_path = tmp_path / "hardware.lease"
    with HardwareLease.acquire(lease_path, build_id="parent"):
        script = (
            "from pathlib import Path; "
            "from lnt.runtime.lease import HardwareLease, HardwareLeaseHeldError; "
            "import sys; "
            "p=Path(sys.argv[1]); "
            "\ntry: HardwareLease.acquire(p, build_id='child')"
            "\nexcept HardwareLeaseHeldError as e: "
            "print(e.code, e.owner.pid, e.owner.build_id); sys.exit(7)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script, str(lease_path)],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 7
    assert f"hardware_lease_held {os.getpid()} parent" in result.stdout


@pytest.mark.parametrize(
    ("pid", "stored_start", "observed_start"),
    [(999_999_999, 10, None), (os.getpid(), 10, 11)],
)
def test_stale_or_pid_reused_lease_is_recovered(
    tmp_path: Path,
    pid: int,
    stored_start: int,
    observed_start: int | None,
) -> None:
    path = tmp_path / "hardware.lease"
    _write_owner(path, LeaseOwner(pid, stored_start, "old", "2000-01-01T00:00:00Z"))

    lease = HardwareLease.acquire(
        path,
        build_id="new",
        process_probe=lambda requested: (
            observed_start if requested == pid else current_process_start_time(requested)
        ),
    )

    assert lease.owner.build_id == "new"
    lease.release()


def test_live_lease_is_never_recovered_by_age(tmp_path: Path) -> None:
    path = tmp_path / "hardware.lease"
    start = current_process_start_time(os.getpid())
    assert start is not None
    owner = LeaseOwner(os.getpid(), start, "old", "2000-01-01T00:00:00Z")
    _write_owner(path, owner)

    with pytest.raises(HardwareLeaseHeldError) as raised:
        HardwareLease.acquire(path, build_id="new")

    assert raised.value.owner == owner


def test_cpu_bound_and_fifo_are_respected() -> None:
    scheduler = OperationScheduler(cpu_workers=2, cpu_queue_limit=2)
    started = threading.Barrier(3)
    release = threading.Event()
    order: list[int] = []
    lock = threading.Lock()

    def blocking(index: int) -> Callable[[], int]:
        def run() -> int:
            with lock:
                order.append(index)
            if index < 2:
                started.wait()
                release.wait()
            return index

        return run

    first = scheduler.submit(OperationClass.CPU, blocking(0))
    second = scheduler.submit(OperationClass.CPU, blocking(1))
    started.wait()
    third = scheduler.submit(OperationClass.CPU, blocking(2))
    fourth = scheduler.submit(OperationClass.CPU, blocking(3))
    with pytest.raises(AnalysisQueueFullError):
        scheduler.submit(OperationClass.CPU, blocking(4))
    release.set()

    assert [future.result() for future in (first, second, third, fourth)] == [0, 1, 2, 3]
    assert order[2:] == [2, 3]
    scheduler.close()


def test_hardware_jobs_are_fifo_and_serial() -> None:
    scheduler = OperationScheduler(cpu_workers=1, cpu_queue_limit=1)
    release = threading.Event()
    first_started = threading.Event()
    order: list[str] = []

    def first() -> str:
        order.append("first")
        first_started.set()
        release.wait()
        return "first"

    one = scheduler.submit(OperationClass.HARDWARE, first)
    first_started.wait()
    two = scheduler.submit(OperationClass.HARDWARE, lambda: order.append("second") or "second")
    release.set()

    assert one.result() == "first"
    assert two.result() == "second"
    assert order == ["first", "second"]
    scheduler.close()


def test_series_cancellation_is_acknowledged_between_members() -> None:
    cancelled = threading.Event()
    visited: list[int] = []

    def member(index: int, total: int) -> None:
        visited.append(index)
        assert total == 3
        cancelled.set()

    result = run_member_series(total=3, is_cancelled=cancelled.is_set, run_member=member)

    assert result.completed == 1
    assert result.cancelled
    assert visited == [1]


def test_second_exclusive_loopback_bind_fails() -> None:
    with bind_exclusive_loopback(0) as first:
        port = first.getsockname()[1]
        with pytest.raises(OSError, match=r".*"):
            bind_exclusive_loopback(port)
