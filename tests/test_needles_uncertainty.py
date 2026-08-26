"""Неопределённость (95% CI) needle-метрик: сеянный бутстрэп по цикловым пикам."""

from pathlib import Path

import numpy as np
import pytest

from lnt import needles as nd
from lnt.analysis import analysis_to_payload, analyze_measurement_session
from lnt.signals import generate
from lnt.simulate import simulate_session

SAMPLE_RATE_HZ = 100_000.0
DURATION_S = 2.4
LINE_HZ = 50.0
METHOD = "seeded_cycle_bootstrap_percentile_95"


def test_dual_channel_uncertainty_brackets_point_estimate() -> None:
    session = generate(
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        rng=np.random.default_rng(1),
        line_frequency_hz=LINE_HZ,
    )

    metrics = nd.compute_needle_metrics(session.ch1, session.ch2, sample_rate_hz=SAMPLE_RATE_HZ)

    uncertainty = metrics.uncertainty
    assert uncertainty is not None
    assert uncertainty.method == METHOD
    assert uncertainty.confidence_level == pytest.approx(0.95)
    assert uncertainty.needle_mean_v.low <= metrics.needle_mean_v <= uncertainty.needle_mean_v.high
    assert (
        uncertainty.needle_sigma_ratio.low
        <= metrics.needle_sigma_ratio
        <= uncertainty.needle_sigma_ratio.high
    )


def test_uncertainty_deterministic_for_fixed_seed() -> None:
    session = generate(
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        rng=np.random.default_rng(1),
        line_frequency_hz=LINE_HZ,
    )

    first = nd.compute_needle_metrics(
        session.ch1,
        session.ch2,
        sample_rate_hz=SAMPLE_RATE_HZ,
        seed=42,
    )
    second = nd.compute_needle_metrics(
        session.ch1,
        session.ch2,
        sample_rate_hz=SAMPLE_RATE_HZ,
        seed=42,
    )

    assert first.uncertainty == second.uncertainty


def test_different_seed_changes_resamples_not_conclusion() -> None:
    session = generate(
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        rng=np.random.default_rng(1),
        line_frequency_hz=LINE_HZ,
    )

    first = nd.compute_needle_metrics(
        session.ch1,
        session.ch2,
        sample_rate_hz=SAMPLE_RATE_HZ,
        seed=1,
    )
    second = nd.compute_needle_metrics(
        session.ch1,
        session.ch2,
        sample_rate_hz=SAMPLE_RATE_HZ,
        seed=2,
    )

    assert first.uncertainty is not None
    assert second.uncertainty is not None
    assert first.uncertainty.method == METHOD
    assert second.uncertainty.method == METHOD
    for side in ("needle_mean_v", "needle_sigma_ratio"):
        one = getattr(first.uncertainty, side)
        two = getattr(second.uncertainty, side)
        assert one.low == pytest.approx(two.low, rel=0.5)
        assert one.high == pytest.approx(two.high, rel=0.5)
    assert first.uncertainty.needle_mean_v.low <= first.needle_mean_v
    assert first.needle_mean_v <= first.uncertainty.needle_mean_v.high
    assert first.uncertainty.needle_sigma_ratio.low <= first.needle_sigma_ratio
    assert first.needle_sigma_ratio <= first.uncertainty.needle_sigma_ratio.high


def test_fewer_than_three_peaks_gives_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nd, "MIN_CYCLES", 2)
    rng = np.random.default_rng(5)
    short = (rng.standard_normal(5000) * 0.01).astype(np.float32)

    metrics = nd.compute_needle_metrics_single(short, sample_rate_hz=SAMPLE_RATE_HZ)

    assert metrics.cycles_analyzed == 2
    assert metrics.uncertainty is None


def test_single_channel_has_uncertainty_too() -> None:
    session = generate(
        profile="bad",
        duration_s=DURATION_S,
        sample_rate_hz=SAMPLE_RATE_HZ,
        rng=np.random.default_rng(1),
        line_frequency_hz=LINE_HZ,
    )

    metrics = nd.compute_needle_metrics_single(session.ch1, sample_rate_hz=SAMPLE_RATE_HZ)

    uncertainty = metrics.uncertainty
    assert uncertainty is not None
    assert uncertainty.method == METHOD
    assert uncertainty.confidence_level == pytest.approx(0.95)


def test_payload_includes_nested_uncertainty(tmp_path: Path) -> None:
    session = simulate_session(
        out_dir=tmp_path / "syn-bad",
        profile="bad",
        duration_s=2.1,
        sample_rate_hz=250_000.0,
        seed=6022,
    )

    result = analyze_measurement_session(session)
    payload = analysis_to_payload(result)

    needle = payload["needle"]
    assert isinstance(needle, dict)
    uncertainty = needle["uncertainty"]
    assert isinstance(uncertainty, dict)
    assert uncertainty["method"] == METHOD
    mean_interval = uncertainty["needle_mean_v"]
    assert isinstance(mean_interval, dict)
    assert isinstance(mean_interval["low"], float)
    assert isinstance(mean_interval["high"], float)
    sigma_interval = uncertainty["needle_sigma_ratio"]
    assert isinstance(sigma_interval, dict)
    assert isinstance(sigma_interval["low"], float)
    assert isinstance(sigma_interval["high"], float)
