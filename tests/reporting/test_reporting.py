from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from lnt.reporting import (
    DriftConfounds,
    EventSummary,
    HypothesisLink,
    MeasurementPlane,
    PlaneKind,
    Provenance,
    QcDecision,
    QcState,
    RecipeReference,
    ReportInputs,
    SetupContext,
    build_report,
    canonical_json,
    render_csv_tables,
    render_html,
    write_report,
)
from lnt.statistics.models import (
    DescriptiveEffect,
    EffectInterval,
    ExclusionRecord,
    InferentialEffect,
    ResultMetadata,
)

HOSTILE = '<script>alert(1)</script><img src=x onerror="alert(2)">'


def _metadata() -> ResultMetadata:
    return ResultMetadata(
        sampling_unit="repeat",
        hierarchy=("site", "session"),
        n=4,
        missing_count=1,
        exclusions=(ExclusionRecord(member_id="member-x", reason=HOSTILE),),
        estimator_name="paired bootstrap mean",
        interval_method="percentile bootstrap 95%",
    )


def _inputs(*, primary_available: bool = True, missing: tuple[str, ...] = ()) -> ReportInputs:
    metadata = _metadata()
    inferential = InferentialEffect(
        mean_effect=1.25,
        median_effect=1.0,
        robust_effect=1.1,
        interval=EffectInterval(low=0.4, high=2.0),
        stored_differences=(0.5, 1.0, 1.5, 2.0),
        metadata=metadata,
    )
    descriptive = DescriptiveEffect(
        mean_effect=0.25,
        median_effect=0.2,
        robust_effect=0.22,
        stored_differences=(0.1, 0.4),
        metadata=metadata,
    )
    primary = MeasurementPlane(
        kind=PlaneKind.PRIMARY,
        available=primary_available,
        reason_code=None if primary_available else "self_noise_baseline_missing",
        session_id="session-a",
        member_id="member-a",
        unit="V²/Hz",
        estimator="Welch input-referred excess PSD",
        n=4,
        values=(inferential,) if primary_available else (),
    )
    return ReportInputs(
        provenance=Provenance(
            session_ids=("session-a", "session-b"),
            experiment_id="experiment-1",
            recipe_sha256s=("a" * 64,),
            code_identity="git:9d63de7",
            created_at="2026-08-11T12:00:00Z",
        ),
        setup=SetupContext(
            ch1_setup="floating_differential_rc_shunt_v1",
            profile="quiet",
            metadata_snapshot_refs=("session-a/manifest.json",),
            notes=(HOSTILE,),
        ),
        qc=(
            QcDecision(member_id="member-a", state=QcState.INCLUDED, reason="qualified"),
            QcDecision(member_id="member-x", state=QcState.EXCLUDED, reason=HOSTILE),
        ),
        recipes=(
            RecipeReference(
                recipe_sha256="a" * 64,
                session_id="session-a",
                artifact_key="spectrum",
            ),
        ),
        primary_estimands=(inferential,),
        secondary_estimands=(descriptive,),
        planes=(
            MeasurementPlane(
                kind=PlaneKind.SOURCE,
                available=True,
                session_id="session-a",
                member_id="member-a",
                unit="V²/Hz",
                estimator="Welch scope-plane PSD",
                n=4,
                values=(descriptive,),
            ),
            MeasurementPlane(
                kind=PlaneKind.SECONDARY,
                available=True,
                session_id="session-a",
                member_id="member-a",
                unit="V²/Hz",
                estimator="transformer secondary PSD",
                n=4,
                values=(descriptive,),
            ),
            primary,
        ),
        drift_confounds=DriftConfounds(
            aba_label="квалифицированный внутрисерийный контраст",
            drift_value=0.08,
            drift_unit="V²/Hz",
            confound_columns=("temperature_c", "mains_voltage_v"),
        ),
        events=EventSummary(
            candidate_count=3,
            qualified_count=2,
            unqualified_gap_count=1,
            unit="count",
            estimator="T23 threshold inventory",
            n=3,
        ),
        hypotheses=(
            HypothesisLink(
                hypothesis_id="h.noise",
                status="consistent_with_observations",
                status_label="согласуется с наблюдениями",
            ),
        ),
        protocol_qualifications=("Причинный вывод недоступен.",),
        missing_artifacts=missing,
    )


def test_schema_round_trip_is_byte_identical() -> None:
    report = build_report(_inputs())
    first = canonical_json(report)
    restored = type(report).model_validate_json(first)
    assert canonical_json(restored) == first
    assert first.endswith(b"\n")


def test_renderers_are_deterministic_and_fully_labeled() -> None:
    report = build_report(_inputs())
    tables = render_csv_tables(report)
    html = render_html(report)
    assert tuple(tables) == ("estimands.csv", "events.csv", "planes.csv")
    for table in tables.values():
        assert "unit" in table
        assert "estimator" in table
        assert ",n," in table.lower()
    assert "Исходная плоскость" in html
    assert "Вторичная плоскость" in html
    assert "Первичная плоскость" in html
    assert "отчёт для личного анализа" in html


def test_html_escapes_hostile_text_and_has_no_active_or_remote_content() -> None:
    html = render_html(build_report(_inputs()))
    assert "<script" not in html.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=&quot;" in html
    assert re.search(r"https?://", html) is None
    assert "@media print" in html


def test_missing_artifact_becomes_explicit_limitation() -> None:
    report = build_report(_inputs(missing=("events.json",)))
    assert any(item.code == "artifact_missing" for item in report.limitations)
    assert "events.json" in render_html(report)


def test_unavailable_calibration_explains_primary_plane() -> None:
    report = build_report(_inputs(primary_available=False))
    html = render_html(report)
    assert report.planes[2].reason_code == "self_noise_baseline_missing"
    assert "первичная плоскость недоступна: нет базовой сессии самошума" in html


def test_exclusions_section_is_rendered_when_empty() -> None:
    inputs = _inputs()
    report = build_report(inputs.model_copy(update={"qc": ()}))
    html = render_html(report)
    assert "Исключения" in html
    assert "исключений нет" in html


def test_writer_emits_canonical_artifacts(tmp_path: Path) -> None:
    report = build_report(_inputs())
    outputs = write_report(report, tmp_path)
    assert {path.name for path in outputs} == {
        "report.html",
        "report.json",
        "estimands.csv",
        "events.csv",
        "planes.csv",
    }
    assert (tmp_path / "report.json").read_bytes() == canonical_json(report)


def test_golden_hashes_are_stable() -> None:
    report = build_report(_inputs())
    payloads = {
        "json": canonical_json(report),
        "html": render_html(report).encode(),
        **{name: value.encode() for name, value in render_csv_tables(report).items()},
    }
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in payloads.items()}
    assert hashes == {
        "json": "5d09166f8bb5a3180b6422c50ceffe2dabe026a11c9ccbc1700e6ad7d12a70e3",
        "html": "0e14abfb56c890018fe9161ab2d4ab92e40d9550adcc551b1774fb7cafe33642",
        "estimands.csv": "eb8ead20cd54a8218f4c8948aadd4fc3024870684dc96d8c10a45ddf4b1df1bb",
        "events.csv": "2b9f901039fd5c3dc287b71b0eb0d40e3ba4b99e7096f9178c46579ba15db188",
        "planes.csv": "58719a18b24a0605c1cc4b1302bcf792d4df35f6357194bcceb9f0195dc1129e",
    }
