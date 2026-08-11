"""Injectable scopes for frozen, non-invasive diagnostic mapping checks."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from lnt.errors import DeviceNotFoundError
from lnt.scope_io import RawCallback, ScopeProtocol


class FakeState(StrEnum):
    """Diagnostic states required by the packaging gate."""

    PRESENT = "device-present"
    ABSENT = "absent"
    BOOTLOADER = "bootloader"
    FIRMWARE_MISSING = "firmware-missing"
    DRIVER_MISSING = "driver-missing"


@dataclass(slots=True)
class FakeScope:
    """Minimal mutable implementation of the read-only diagnostic surface."""

    opens: bool
    is_device_firmware_present: bool

    def setup(self) -> bool:
        """Model successful read-only driver setup."""
        return True

    def open_handle(self) -> bool:
        """Model whether the fake device can be opened."""
        return self.opens

    def close_handle(self) -> bool:
        """Model successful handle closure."""
        return True

    def flash_firmware(self) -> bool:
        """Satisfy the production protocol; the diagnostic never calls this."""
        return True

    def set_interface(self, index: int, /) -> bool:
        """Satisfy the production protocol without changing fake state."""
        _ = index
        return True

    def set_num_channels(self, count: int, /) -> bool:
        """Satisfy the production protocol without changing fake state."""
        _ = count
        return True

    def set_sample_rate(self, code: int, /) -> bool:
        """Satisfy the production protocol without changing fake state."""
        _ = code
        return True

    def set_ch1_voltage_range(self, code: int, /) -> bool:
        """Satisfy the production protocol without changing fake state."""
        _ = code
        return True

    def set_ch2_voltage_range(self, code: int, /) -> bool:
        """Satisfy the production protocol without changing fake state."""
        _ = code
        return True

    def read_async(
        self,
        callback: RawCallback,
        data_size: int,
        outstanding_transfers: int,
        *,
        raw: bool,
    ) -> bool:
        """Satisfy the production protocol; capture is never invoked."""
        _ = (callback, data_size, outstanding_transfers, raw)
        return True

    def start_capture(self) -> bool:
        """Satisfy the production protocol; capture is never invoked."""
        return True

    def stop_capture(self) -> bool:
        """Satisfy the production protocol; capture is never invoked."""
        return True

    def poll(self) -> bool:
        """Satisfy the production protocol; capture is never invoked."""
        return True


def fake_factory(state: FakeState) -> Callable[[], ScopeProtocol]:
    """Return a scope factory implementing one deterministic fake state."""
    match state:
        case FakeState.PRESENT:
            return lambda: FakeScope(opens=True, is_device_firmware_present=True)
        case FakeState.ABSENT:
            return lambda: FakeScope(opens=False, is_device_firmware_present=False)
        case FakeState.BOOTLOADER | FakeState.FIRMWARE_MISSING:
            return lambda: FakeScope(opens=True, is_device_firmware_present=False)
        case FakeState.DRIVER_MISSING:

            def missing_driver() -> ScopeProtocol:
                raise DeviceNotFoundError("libusb/WinUSB driver missing")

            return missing_driver
