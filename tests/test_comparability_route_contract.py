from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from lnt.acquisition_quality import AcquisitionQuality
from lnt.comparability import (
    AdcSetup,
    CalibrationIdentity,
    ComparisonKind,
    ContextValue,
    SessionDescriptor,
    SetupKind,
    WelchGrid,
)
from lnt.types import ChannelMode, SessionType
from lnt.ui.app import create_app
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from pathlib import Path

    from httpx2 import Response


def _descriptor(session_id: str) -> SessionDescriptor:
    return SessionDescriptor(
        session_id=session_id,
        comparison_kind=ComparisonKind.RC_2CH,
        session_type=SessionType.MEASUREMENT,
        channel_mode=ChannelMode.DUAL,
        setup_kind=SetupKind.FLOATING_DIFFERENTIAL_RC_SHUNT_V1,
        probe_multiplier=1.0,
        adc_setup=AdcSetup(range_code=5, range_v=5.0),
        sample_rate_hz=20_000_000.0,
        recipe_identity="welch-v2",
        grid=WelchGrid(window="hann", nperseg=4096, noverlap=2048),
        baseline_identity="baseline-a",
        calibration=CalibrationIdentity(identity="adc-a", applied=False),
        quality=AcquisitionQuality(
            quality_thresholds_version=1,
            channels=(),
            findings=(),
            maximum_callback_gap_s=0.0,
            short_block_count=0,
        ),
        context_fields=(ContextValue(field="site_id", value="lab-a", comparable=True),),
    )


def _write_descriptor(session_dir: Path, descriptor: SessionDescriptor) -> None:
    (session_dir / "comparability.json").write_text(
        json.dumps(asdict(descriptor)), encoding="utf-8"
    )


def _post(root: Path, payload: dict[str, object]) -> Response:
    with TestClient(create_app(root=root, runtime_db=root.parent / "runtime.sqlite3")) as client:
        nonce = client.get("/api/config").json()["mutation_nonce"]
        return client.post(
            "/api/v2/comparability/check",
            headers={"X-LNT-Mutation-Nonce": nonce},
            json=payload,
        )


def test_session_references_use_valid_persisted_descriptors_and_manifest_aliases(
    tmp_path: Path,
) -> None:
    root = tmp_path / "sessions"
    left_dir = root / "left-directory"
    right_dir = root / "right-directory"
    write_manifest(left_dir, session_id="left-manifest-id")
    write_manifest(right_dir, session_id="right-manifest-id")
    _write_descriptor(left_dir, _descriptor("left-manifest-id"))
    _write_descriptor(right_dir, _descriptor("right-manifest-id"))

    response = _post(
        root,
        {
            "left": {"session_id": "left-directory"},
            "right": {"session_id": "right-manifest-id"},
        },
    )

    assert response.status_code == 200
    assert response.json()["comparable"] is True


def test_missing_descriptor_returns_an_explicit_block(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    write_manifest(root / "left")
    write_manifest(root / "right")
    _write_descriptor(root / "right", _descriptor("right"))

    response = _post(root, {"left": {"session_id": "left"}, "right": {"session_id": "right"}})

    assert response.status_code == 200
    assert response.json() == {
        "comparable": False,
        "findings": [
            {
                "dimension": "descriptor",
                "level": "block",
                "code": "comparability_descriptor_unavailable",
                "fields": ["left.comparability_descriptor"],
            }
        ],
    }


def test_invalid_descriptor_reports_only_invalid_fields(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    write_manifest(root / "left")
    write_manifest(root / "right")
    invalid = asdict(_descriptor("left"))
    del invalid["grid"]
    (root / "left" / "comparability.json").write_text(json.dumps(invalid), encoding="utf-8")
    _write_descriptor(root / "right", _descriptor("right"))

    response = _post(root, {"left": {"session_id": "left"}, "right": {"session_id": "right"}})

    assert response.status_code == 200
    finding = response.json()["findings"][0]
    assert finding["code"] == "comparability_descriptor_unavailable"
    assert finding["fields"] == ["left.grid"]


def test_linked_descriptor_is_blocked_without_reading_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "sessions"
    write_manifest(root / "left")
    write_manifest(root / "right")
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(asdict(_descriptor("left"))), encoding="utf-8")
    descriptor_path = root / "left" / "comparability.json"
    descriptor_path.write_text(outside.read_text(encoding="utf-8"), encoding="utf-8")

    def linked(path: Path) -> bool:
        return path == descriptor_path

    monkeypatch.setattr("lnt.ui.routes_quality.is_linked_path", linked)
    _write_descriptor(root / "right", _descriptor("right"))

    response = _post(root, {"left": {"session_id": "left"}, "right": {"session_id": "right"}})

    assert response.status_code == 200
    assert response.json()["findings"][0]["fields"] == ["left.comparability_descriptor"]


def test_descriptor_identity_must_match_manifest_identity(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    write_manifest(root / "left-directory", session_id="left-manifest-id")
    write_manifest(root / "right")
    _write_descriptor(root / "left-directory", _descriptor("invented-id"))
    _write_descriptor(root / "right", _descriptor("right"))

    response = _post(
        root,
        {"left": {"session_id": "left-directory"}, "right": {"session_id": "right"}},
    )

    assert response.status_code == 200
    assert response.json()["findings"][0]["fields"] == ["left.session_id"]


def test_complete_descriptor_clients_remain_supported(tmp_path: Path) -> None:
    left = _descriptor("left")
    right = replace(left, session_id="right")

    response = _post(tmp_path / "sessions", {"left": asdict(left), "right": asdict(right)})

    assert response.status_code == 200
    assert response.json()["comparable"] is True


@pytest.mark.parametrize(
    ("payload", "status_code"),
    [
        ({"left": {"session_id": "missing"}, "right": {"session_id": "missing"}}, 404),
        (
            {
                "left": {"session_id": "shared"},
                "right": {"session_id": "direct-id"},
            },
            409,
        ),
        (
            {
                "left": {"session_id": "direct-id", "unexpected": True},
                "right": {"session_id": "direct-id"},
            },
            422,
        ),
        (
            {
                "left": {"session_id": "../outside"},
                "right": {"session_id": "direct-id"},
            },
            422,
        ),
    ],
)
def test_session_references_preserve_strict_resolver_outcomes(
    tmp_path: Path,
    payload: dict[str, object],
    status_code: int,
) -> None:
    root = tmp_path / "sessions"
    write_manifest(root / "shared", session_id="direct-id")
    write_manifest(root / "other", session_id="shared")

    assert _post(root, payload).status_code == status_code
