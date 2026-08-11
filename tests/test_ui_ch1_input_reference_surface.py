"""API-boundary contract: the session detail surfaces the CH1 input-reference status.

This replaces the earlier source-string test with a behavioral integration test:
a synthetic schema-v1 session is analyzed on disk and served through the real
FastAPI app, and the JSON returned by ``/api/sessions/<name>`` is asserted. The
renderer-side contract (how that payload is drawn) lives in the six Node DOM
tests in ``tests/js/ch1-input-reference.test.mjs``.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import override

from starlette.testclient import TestClient

from lnt.analysis import analyze_measurement_session, write_analysis
from lnt.selftest import SelftestResult
from lnt.simulate import simulate_session
from lnt.ui.app import create_app
from lnt.ui.operations import LntBackend


@dataclass(frozen=True, slots=True)
class _StubBackend(LntBackend):
    """Backend stub; session detail is read from disk and never touches hardware."""

    @override
    def selftest(self) -> SelftestResult:
        return SelftestResult(
            ok=True,
            message="самопроверка успешна",
            frequency_hz=22_400.0,
            cycles_analyzed=1,
        )


def test_session_detail_reports_reason_coded_unavailable_input_reference(
    tmp_path: Path,
) -> None:
    # Given: a synthetic schema-v1 capture (no explicit CH1 model), analyzed on disk.
    root = tmp_path / "sessions"
    root.mkdir()
    session = simulate_session(
        out_dir=root / "legacy-001",
        profile="bad",
        duration_s=2.1,
        sample_rate_hz=250_000.0,
        seed=6022,
    )
    write_analysis(session, analyze_measurement_session(session))

    # When: the detail is fetched through the real API surface.
    with TestClient(create_app(root=root, backend=_StubBackend())) as client:
        response = client.get("/api/sessions/legacy-001")

    # Then: input referral is machine-readably unavailable with the v1 reason code,
    # while the raw scope-plane spectrum stays available for display.
    assert response.status_code == 200
    detail = response.json()
    reference = detail["analysis"]["ch1_input_reference"]
    assert reference["status"] == "unavailable"
    assert reference["reason_code"] == "manifest_schema_v1"
    assert reference["model_kind"] is None
    assert reference["qualified_bin_count"] == 0
    assert detail["spectrum_available"] is True
