from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

import pytest

from lnt.acquisition_quality import AcquisitionQuality
from lnt.cli import main
from lnt.comparability import (
    AdcSetup,
    CalibrationIdentity,
    ComparisonKind,
    ContextValue,
    SessionDescriptor,
    SetupKind,
    WelchGrid,
)
from lnt.experiments.runner_models import (
    PlannedMember,
    ProtocolRunMode,
    ProtocolRunRecord,
    ProtocolRunStatus,
)
from lnt.experiments.runner_store import ProtocolRunStore
from lnt.types import ChannelMode, SessionType
from tests.experiments.factories import make_experiment

if TYPE_CHECKING:
    from pathlib import Path


def test_experiment_create_list_show_and_stats_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = tmp_path / "experiment.json"
    payload.write_text(make_experiment().model_dump_json(), encoding="utf-8")
    root = tmp_path / "sessions"

    created = main(["experiment", "create", str(payload), "--root", str(root)])
    listed = main(["experiment", "list", "--root", str(root)])
    shown = main(["experiment", "show", "latency-study", "--root", str(root)])
    stats = main(
        [
            "experiment",
            "stats",
            "latency-study",
            "--root",
            str(root),
            "--estimand",
            "latency_s",
            "--units",
            "s",
            "--pair",
            "u1:1:2",
        ]
    )

    output = capsys.readouterr().out
    assert (created, listed, shown, stats) == (0, 0, 0, 0)
    assert "latency-study" in output
    assert '"units": "s"' in output
    assert '"estimator"' in output


def test_experiment_cli_typed_failure_is_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["experiment", "show", "missing", "--root", str(tmp_path / "sessions")])

    error = capsys.readouterr().err
    assert code == 2
    assert "не найден" in error


def test_hypothesis_add_edit_and_status_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "sessions"
    payload = tmp_path / "hypothesis.json"
    hypothesis = {
        "schema_version": 1,
        "hypothesis_id": "lower-latency",
        "revision": 1,
        "statement": "B связано с меньшей задержкой",
        "expected_direction": "decrease",
        "mechanism": "Меньше буферизация",
        "linked_estimands": [],
        "confounds": [],
        "evidence_for": [],
        "evidence_against": [],
        "status": "draft",
        "revision_history": [
            {
                "revision": 1,
                "occurred_at": "2026-08-11T10:00:00.000Z",
                "actor": "user:tester",
                "reason": "Создание",
            }
        ],
    }
    payload.write_text(json.dumps(hypothesis, ensure_ascii=False), encoding="utf-8")

    added = main(["hypothesis", "add", str(payload), "--root", str(root)])
    status = main(["hypothesis", "status", "lower-latency", "--root", str(root)])

    output = capsys.readouterr().out
    assert (added, status) == (0, 0)
    assert "черновик" in output


def test_experiment_trends_cli_is_bounded_and_labeled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "trends.json"
    request.write_text(json.dumps({
        "observations": [{
            "observation_id": f"o-{index}",
            "timestamp": f"2026-08-{index + 1:02d}T10:00:00+00:00",
            "source_offset": str(index),
            "location": "lab",
            "condition": "a",
            "predictor": float(index),
            "outcome": float(index + 1),
            "metadata": [],
        } for index in range(5)],
        "minimum_n": 5,
        "max_lag": 2,
        "bootstrap_samples": 100,
        "seed": 3,
        "units": "s",
    }), encoding="utf-8")

    code = main(["experiment", "trends", str(request), "--root", str(tmp_path / "sessions")])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["metadata"]["units"] == "s"
    assert payload["metadata"]["estimator"] == "descriptive_longitudinal"


def test_experiment_trends_cli_rejects_oversized_query(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "trends.json"
    request.write_text(json.dumps({
        "observations": [], "minimum_n": 5, "max_lag": 101,
        "bootstrap_samples": 100, "seed": 0, "units": "s",
    }), encoding="utf-8")

    code = main(["experiment", "trends", str(request), "--root", str(tmp_path / "sessions")])

    assert code == 2
    assert "max_lag" in capsys.readouterr().err


def _descriptor(session_id: str, *, sample_rate_hz: float = 20_000_000.0) -> SessionDescriptor:
    return SessionDescriptor(
        session_id=session_id,
        comparison_kind=ComparisonKind.RC_2CH,
        session_type=SessionType.MEASUREMENT,
        channel_mode=ChannelMode.DUAL,
        setup_kind=SetupKind.FLOATING_DIFFERENTIAL_RC_SHUNT_V1,
        probe_multiplier=1.0,
        adc_setup=AdcSetup(range_code=5, range_v=5.0),
        sample_rate_hz=sample_rate_hz,
        recipe_identity="welch-v2",
        grid=WelchGrid(window="hann", nperseg=4096, noverlap=2048),
        baseline_identity="baseline-a",
        calibration=CalibrationIdentity(identity="adc-a", applied=False),
        quality=AcquisitionQuality(
            quality_thresholds_version=1, channels=(), findings=(),
            maximum_callback_gap_s=0.0, short_block_count=0,
        ),
        context_fields=(ContextValue(field="site_id", value="lab-a", comparable=True),),
    )


def test_experiment_check_cli_reports_comparability_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "sessions"
    payload = tmp_path / "experiment.json"
    payload.write_text(make_experiment().model_dump_json(), encoding="utf-8")
    assert main(["experiment", "create", str(payload), "--root", str(root)]) == 0
    descriptors = (
        _descriptor("session-a"),
        _descriptor("missing-session", sample_rate_hz=10_000_000.0),
    )
    for descriptor in descriptors:
        directory = root / descriptor.session_id
        directory.mkdir(parents=True)
        (directory / "comparability.json").write_text(
            json.dumps(asdict(descriptor)), encoding="utf-8"
        )
    capsys.readouterr()

    code = main(["experiment", "check", "latency-study", "--root", str(root)])

    output = capsys.readouterr().out
    assert code == 0
    assert "сопоставимость: заблокирована" in output
    assert "sample_rate_mismatch" in output


def test_experiment_confirm_cli_records_actor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "sessions"
    store = ProtocolRunStore(root.parent / "protocol-runs")
    store.create(ProtocolRunRecord(
        run_id="real-1", experiment_id="latency-study", mode=ProtocolRunMode.REAL,
        status=ProtocolRunStatus.AWAITING_CONFIRMATION, revision=1, seed=None,
        generated_order=(1,),
        plan=(PlannedMember(
            protocol_order=1, condition_id="condition-a", instruction="Измерить A",
            block_key="block-1", pairing_key="pair-1",
        ),),
        next_member_index=0, completed_members=(), requested_physical_change="Измерить A",
    ))

    code = main([
        "experiment", "confirm", "real-1", "--actor", "user:operator",
        "--root", str(root),
    ])

    assert code == 0
    assert store.events("real-1")[1].actor == "user:operator"
    assert "user:operator" in capsys.readouterr().out


def test_hypothesis_help_and_invalid_file_explain_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(["hypothesis", "add", "--help"])
    assert "путь к JSON-файлу гипотезы" in capsys.readouterr().out
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"schema_version": 1}', encoding="utf-8")

    code = main(["hypothesis", "add", str(invalid), "--root", str(tmp_path / "sessions")])

    error = capsys.readouterr().err
    assert code == 2
    assert "hypothesis_id" in error
    assert "statement" in error
