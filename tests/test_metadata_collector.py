import json
from dataclasses import dataclass

from lnt.metadata_collector import (
    AcquisitionSettings,
    BuildInfo,
    DeviceDiagnostic,
    MetadataCollector,
    PlatformDiagnostic,
)
from lnt.profiles import FrontEndProfile
from lnt.types import AcquisitionTelemetry, ChannelMode


@dataclass(frozen=True, slots=True)
class FakePlatform:
    def diagnose(self) -> PlatformDiagnostic:
        return PlatformDiagnostic(
            os_version="Windows 11 24H2", architecture="AMD64", timezone="UTC+03:00"
        )


@dataclass(frozen=True, slots=True)
class FakeDevice:
    online: bool = True

    def diagnose(self) -> DeviceDiagnostic:
        if not self.online:
            return DeviceDiagnostic.offline("device_offline")
        return DeviceDiagnostic(
            vid="04B5",
            pid="6022",
            model="Hantek 6022BE",
            firmware="ram-fw-1",
            driver="WinUSB",
            reason_code=None,
        )


def _settings() -> AcquisitionSettings:
    return AcquisitionSettings(
        sample_rate_hz=500_000.0,
        sample_count=1_200_000,
        probe_multiplier=10.0,
        range_v=5.0,
        channel_mode=ChannelMode.DUAL,
        front_end=FrontEndProfile.from_si(resistance_ohm=1_000.0, c1_f=1e-9, c2_f=2e-9),
    )


def _telemetry() -> AcquisitionTelemetry:
    return AcquisitionTelemetry(
        requested_samples=1_200_000,
        captured_samples=1_200_000,
        callback_count=100,
        block_lengths=(12_000,),
        callback_gaps_s=(0.024,),
        expected_block_interval_s=0.024,
        short_block_count=0,
        ch1_clip_low_count=0,
        ch1_clip_high_count=1,
        ch2_clip_low_count=0,
        ch2_clip_high_count=0,
        calibration_used=True,
    )


def test_collector_is_deterministic_with_injected_providers() -> None:
    collector = MetadataCollector(
        clock=lambda: "2026-08-11T10:00:00.000Z",
        platform_probe=FakePlatform(),
        device_probe=FakeDevice(),
        build=BuildInfo(version="2.0.0", build="d879865", frozen=False),
    )

    first = collector.collect(settings=_settings(), telemetry=_telemetry())
    second = collector.collect(settings=_settings(), telemetry=_telemetry())

    assert first == second
    assert first.fields["device.vid"].value == "04B5"
    assert first.fields["acquisition.captured_samples"].value == 1_200_000


def test_snapshot_serialization_never_contains_forbidden_privacy_keys() -> None:
    snapshot = MetadataCollector(
        clock=lambda: "2026-08-11T10:00:00.000Z",
        platform_probe=FakePlatform(),
        device_probe=FakeDevice(),
        build=BuildInfo(version="2.0.0", build="test", frozen=False),
    ).collect(settings=_settings(), telemetry=_telemetry())

    serialized = snapshot.to_json()
    keys = set(json.loads(serialized)["fields"])

    assert keys.isdisjoint(
        {"hostname", "username", "geolocation", "processes", "network_identity", "weather"}
    )
    assert all(
        forbidden not in serialized
        for forbidden in (
            "hostname",
            "username",
            "geolocation",
            "processes",
            "network_identity",
            "weather",
        )
    )


def test_device_offline_collection_succeeds_with_reason_coded_fields() -> None:
    collector = MetadataCollector(
        clock=lambda: "2026-08-11T10:00:00.000Z",
        platform_probe=FakePlatform(),
        device_probe=FakeDevice(online=False),
        build=BuildInfo(version="2.0.0", build="test", frozen=True),
    )

    snapshot = collector.collect(settings=_settings(), telemetry=None)

    for key in ("device.vid", "device.pid", "device.model", "device.firmware", "device.driver"):
        assert snapshot.fields[key].value is None
        assert snapshot.fields[key].reason_code == "device_offline"
    assert snapshot.fields["acquisition.telemetry"].reason_code == "telemetry_unavailable"
