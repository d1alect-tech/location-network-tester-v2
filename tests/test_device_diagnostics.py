from dataclasses import dataclass

import pytest

from lnt.device_diagnostics import (
    DeviceProbeSnapshot,
    DeviceState,
    diagnose_device_state,
)


@dataclass(frozen=True, slots=True)
class FakeProbe:
    snapshot: DeviceProbeSnapshot

    def probe(self) -> DeviceProbeSnapshot:
        return self.snapshot


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (DeviceProbeSnapshot(backend_available=False), DeviceState.BACKEND_UNAVAILABLE),
        (
            DeviceProbeSnapshot(backend_available=True, driver_available=False),
            DeviceState.DRIVER_MISSING,
        ),
        (
            DeviceProbeSnapshot(backend_available=True, driver_available=True),
            DeviceState.DEVICE_ABSENT,
        ),
        (
            DeviceProbeSnapshot(
                backend_available=True,
                driver_available=True,
                detected_vid="04B4",
            ),
            DeviceState.BOOTLOADER_VID,
        ),
        (
            DeviceProbeSnapshot(
                backend_available=True,
                driver_available=True,
                detected_vid="04B5",
                handle_busy=True,
            ),
            DeviceState.HANDLE_BUSY,
        ),
        (
            DeviceProbeSnapshot(
                backend_available=True,
                driver_available=True,
                detected_vid="04B5",
                handle_opened=True,
                firmware_present=False,
            ),
            DeviceState.FIRMWARE_MISSING,
        ),
        (
            DeviceProbeSnapshot(
                backend_available=True,
                driver_available=True,
                detected_vid="04B5",
                firmware_upload_failed=True,
            ),
            DeviceState.FIRMWARE_UPLOAD_FAILED,
        ),
        (
            DeviceProbeSnapshot(
                backend_available=True,
                driver_available=True,
                detected_vid="04B5",
                handle_opened=True,
                firmware_present=True,
            ),
            DeviceState.READY,
        ),
        (
            DeviceProbeSnapshot(
                backend_available=True,
                driver_available=True,
                detected_vid="04B5",
            ),
            DeviceState.RUNNING_VID,
        ),
    ],
)
def test_state_matrix_when_probe_snapshot_changes(
    snapshot: DeviceProbeSnapshot,
    expected: DeviceState,
) -> None:
    diagnostic = diagnose_device_state(FakeProbe(snapshot))

    assert diagnostic.state is expected
    assert diagnostic.description_ru
    assert diagnostic.recovery_action_ru


def test_absent_device_is_distinct_from_missing_driver() -> None:
    absent = diagnose_device_state(
        FakeProbe(DeviceProbeSnapshot(backend_available=True, driver_available=True))
    )
    missing_driver = diagnose_device_state(
        FakeProbe(DeviceProbeSnapshot(backend_available=True, driver_available=False))
    )

    assert absent.state is DeviceState.DEVICE_ABSENT
    assert missing_driver.state is DeviceState.DRIVER_MISSING
    assert absent.recovery_action_ru != missing_driver.recovery_action_ru
