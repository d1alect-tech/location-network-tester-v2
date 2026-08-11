"""Однокональный режим (CH1-only): манифест, хранилище, симуляция, метрики."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from lnt.analysis import analysis_to_payload, analyze_measurement_session, render_analysis
from lnt.compare import compare_analyses, comparison_to_payload, render_comparison
from lnt.errors import InputError, SessionTooShortError
from lnt.manifest import manifest_from_json, manifest_to_json
from lnt.needles import SyncSource, compute_needle_metrics, compute_needle_metrics_single
from lnt.session_store import load_session, write_session
from lnt.signals import generate
from lnt.simulate import simulate_session
from lnt.types import (
    CH1_MANIFEST_SCHEMA_VERSION,
    SCHEMA_VERSION,
    ChannelMeta,
    ChannelMode,
    ChannelRole,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    SessionManifest,
    SessionSource,
    SessionType,
)

SAMPLE_RATE_HZ = 100_000.0
DURATION_S = 2.4
LINE_HZ = 50.0
EXPECTED_CYCLES = int(DURATION_S * LINE_HZ)


def _ch1_meta() -> ChannelMeta:
    return ChannelMeta(
        filename="ch1.npy",
        role=ChannelRole.HF_PROBE,
        unit="V",
        front_end="synthetic",
        range_code=1,
        probe_multiplier=1.0,
    )


def _manifest(*, schema_version: int, sample_count: int) -> SessionManifest:
    setup = None
    if schema_version == CH1_MANIFEST_SCHEMA_VERSION:
        setup = FloatingDifferentialRcShunt(
            resistance_ohm=100.0,
            c1_f=10e-9,
            c2_f=10e-9,
            component_values_basis=ComponentValuesBasis.NOMINAL,
            reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
        )
    now = datetime.now(UTC).isoformat()
    return SessionManifest(
        schema_version=schema_version,
        session_id="syn-single-seed1",
        created_utc=now,
        completed_utc=now,
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=SAMPLE_RATE_HZ,
        duration_s=DURATION_S,
        sample_count=sample_count,
        line_frequency_hz=LINE_HZ,
        profile="bad",
        baseline_session=None,
        parameters={"seed": 1},
        ch1=_ch1_meta(),
        ch2=None,
        acquisition_telemetry=None,
        synthetic_truth=None,
        ch1_setup=setup,
    )


@pytest.mark.parametrize("schema_version", [SCHEMA_VERSION, CH1_MANIFEST_SCHEMA_VERSION])
def test_manifest_roundtrip_ch2_none(schema_version: int) -> None:
    manifest = _manifest(schema_version=schema_version, sample_count=1000)

    restored = manifest_from_json(manifest_to_json(manifest))

    assert restored.ch2 is None
    assert restored.schema_version == schema_version


def test_write_and_load_single_channel_session(tmp_path: Path) -> None:
    sample_count = 1000
    manifest = _manifest(schema_version=SCHEMA_VERSION, sample_count=sample_count)
    ch1 = np.zeros(sample_count, dtype=np.float32)

    session_dir = write_session(
        session_dir=tmp_path / "single",
        manifest=manifest,
        ch1=ch1,
        ch2=None,
    )

    assert not (session_dir / "ch2.npy").exists()
    loaded = load_session(session_dir)
    assert loaded.ch2 is None
    assert loaded.ch1.size == sample_count


def test_write_session_rejects_ch2_array_without_meta(tmp_path: Path) -> None:
    sample_count = 100
    manifest = _manifest(schema_version=SCHEMA_VERSION, sample_count=sample_count)
    ch1 = np.zeros(sample_count, dtype=np.float32)

    with pytest.raises(InputError):
        write_session(
            session_dir=tmp_path / "bad",
            manifest=manifest,
            ch1=ch1,
            ch2=np.zeros(sample_count, dtype=np.float32),
        )


def test_write_session_rejects_missing_ch2_array_with_meta(tmp_path: Path) -> None:
    sample_count = 100
    single = _manifest(schema_version=SCHEMA_VERSION, sample_count=sample_count)
    dual_meta = ChannelMeta(
        filename="ch2.npy",
        role=ChannelRole.LF_TRANSFORMER,
        unit="V",
        front_end="synthetic",
        range_code=1,
        probe_multiplier=1.0,
    )
    manifest = SessionManifest(
        schema_version=single.schema_version,
        session_id=single.session_id,
        created_utc=single.created_utc,
        completed_utc=single.completed_utc,
        source=single.source,
        session_type=single.session_type,
        sample_rate_hz=single.sample_rate_hz,
        duration_s=single.duration_s,
        sample_count=single.sample_count,
        line_frequency_hz=single.line_frequency_hz,
        profile=single.profile,
        baseline_session=single.baseline_session,
        parameters=single.parameters,
        ch1=single.ch1,
        ch2=dual_meta,
        acquisition_telemetry=None,
        synthetic_truth=None,
        ch1_setup=None,
    )

    with pytest.raises(InputError):
        write_session(
            session_dir=tmp_path / "bad",
            manifest=manifest,
            ch1=np.zeros(sample_count, dtype=np.float32),
            ch2=None,
        )


def test_simulate_single_channel_session(tmp_path: Path) -> None:
    session_dir = simulate_session(
        out_dir=tmp_path / "syn-single",
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        seed=1,
        channel_mode=ChannelMode.CH1_ONLY,
    )

    loaded = load_session(session_dir)
    assert loaded.manifest.ch2 is None
    assert loaded.ch2 is None
    assert not (session_dir / "ch2.npy").exists()


def test_single_needle_metrics_on_synthetic() -> None:
    session = generate(
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        rng=np.random.default_rng(1),
        line_frequency_hz=LINE_HZ,
    )

    metrics = compute_needle_metrics_single(session.ch1, sample_rate_hz=SAMPLE_RATE_HZ)

    assert metrics.sync_source is SyncSource.NOMINAL
    assert metrics.cycles_analyzed == EXPECTED_CYCLES
    assert metrics.line_frequency_hz is None
    assert metrics.needle_mean_v > 0.0
    assert metrics.needle_sigma_ratio >= 0.0
    assert metrics.sync_power_v2 is None
    assert metrics.async_power_v2 is None
    assert metrics.async_sync_ratio is None
    assert metrics.lf_envelope_cv is None


def test_single_needle_metrics_close_to_dual_mean() -> None:
    session = generate(
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        rng=np.random.default_rng(7),
        line_frequency_hz=LINE_HZ,
    )

    dual = compute_needle_metrics(session.ch1, session.ch2, sample_rate_hz=SAMPLE_RATE_HZ)
    single = compute_needle_metrics_single(session.ch1, sample_rate_hz=SAMPLE_RATE_HZ)

    assert dual.sync_source is SyncSource.CH2
    assert dual.needle_mean_v == pytest.approx(single.needle_mean_v, rel=0.25)


def test_single_needle_metrics_too_short() -> None:
    short = np.zeros(int(SAMPLE_RATE_HZ * 0.5), dtype=np.float32)

    with pytest.raises(SessionTooShortError):
        compute_needle_metrics_single(short, sample_rate_hz=SAMPLE_RATE_HZ)


def test_analyze_single_channel_session_end_to_end(tmp_path: Path) -> None:
    session_dir = simulate_session(
        out_dir=tmp_path / "syn-single",
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        seed=2,
        channel_mode=ChannelMode.CH1_ONLY,
    )

    result = analyze_measurement_session(session_dir)

    assert result.needle.sync_source is SyncSource.NOMINAL
    assert result.needle.async_sync_ratio is None
    payload = analysis_to_payload(result)
    needle_payload = payload["needle"]
    assert isinstance(needle_payload, dict)
    assert needle_payload["sync_source"] == "nominal"
    assert needle_payload["async_sync_ratio"] is None
    rendered = render_analysis(result)
    assert "н/д" in rendered


def test_compare_dual_vs_single_marks_sync_metrics_unavailable(tmp_path: Path) -> None:
    dual_dir = simulate_session(
        out_dir=tmp_path / "dual",
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        seed=3,
    )
    single_dir = simulate_session(
        out_dir=tmp_path / "single",
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        seed=3,
        channel_mode=ChannelMode.CH1_ONLY,
    )

    comparison = compare_analyses(
        analyze_measurement_session(dual_dir),
        analyze_measurement_session(single_dir),
    )

    by_name = {delta.name: delta for delta in comparison.metric_deltas}
    assert by_name["needle_mean_v"].value_a is not None
    assert by_name["needle_mean_v"].value_b is not None
    assert by_name["async_sync_ratio"].value_a is not None
    assert by_name["async_sync_ratio"].value_b is None
    assert by_name["lf_envelope_cv"].value_b is None
    payload = comparison_to_payload(comparison)
    async_row = next(row for row in payload["metric_deltas"] if row["name"] == "async_sync_ratio")
    assert async_row["value_b"] is None
    rendered = render_comparison(comparison)
    assert "н/д" in rendered
