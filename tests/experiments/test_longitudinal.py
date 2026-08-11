from datetime import UTC, datetime

from lnt.research import (
    AnalysisRequest,
    CorrelationStatus,
    MetadataValue,
    Observation,
    analyze_longitudinal,
)


def _observation(
    index: int,
    *,
    predictor: float,
    outcome: float,
    timestamp: str | None = None,
    location: str = "lab_a",
) -> Observation:
    return Observation(
        observation_id=f"o{index}",
        timestamp=timestamp or f"2026-01-01T{index:02d}:00:00+03:00",
        source_offset="+03:00",
        location=location,
        condition="baseline",
        predictor=predictor,
        outcome=outcome,
        metadata=(MetadataValue(key="load", value=float(index % 3)),),
    )


def test_normalizes_offsets_deduplicates_and_exposes_gaps() -> None:
    # Given
    observations = (
        _observation(3, predictor=1, outcome=1, timestamp="2026-01-01T03:00:00+03:00"),
        _observation(4, predictor=2, outcome=2, timestamp="2026-01-01T01:00:00+00:00"),
        _observation(5, predictor=3, outcome=3, timestamp="2026-01-01T01:00:00+00:00"),
        Observation(
            observation_id="o6",
            timestamp=None,
            source_offset="+03:00",
            location="lab_a",
            condition="baseline",
            predictor=4,
            outcome=4,
        ),
    )

    # When
    result = analyze_longitudinal(observations, AnalysisRequest(minimum_n=2, max_lag=0))

    # Then
    assert result.data_quality.duplicate_count == 1
    assert result.data_quality.dedupe_policy == "keep_first_by_input_order"
    assert result.data_quality.missing_timestamp_count == 1
    assert result.data_quality.gaps[0].duration_seconds == 3600
    assert result.normalized_timestamps[0] == datetime(2026, 1, 1, tzinfo=UTC)


def test_known_lag_is_recovered_with_descriptive_labels() -> None:
    # Given
    predictor = (3.0, 1.0, 4.0, 2.0, 8.0, 5.0, 7.0, 6.0, 9.0, 0.0)
    outcome = (-1.0, -1.0, 3.0, 1.0, 4.0, 2.0, 8.0, 5.0, 7.0, 6.0)
    observations = tuple(
        _observation(index, predictor=x, outcome=y)
        for index, (x, y) in enumerate(zip(predictor, outcome, strict=True))
    )

    # When
    result = analyze_longitudinal(
        observations,
        AnalysisRequest(minimum_n=5, max_lag=3, bootstrap_samples=500, seed=42),
    )

    # Then
    best = max(
        (
            finding
            for finding in result.correlations
            if finding.status is CorrelationStatus.AVAILABLE
        ),
        key=lambda finding: abs(finding.coefficient or 0.0),
    )
    assert (best.lag, best.coefficient, best.result_kind) == (2, 1.0, "descriptive_exploratory")
    assert best.interval is not None
    assert best.multiple_testing == "benjamini_hochberg"
    assert best.q_value is not None


def test_unavailable_correlations_never_claim_nan() -> None:
    # Given
    constant = tuple(_observation(index, predictor=1, outcome=float(index)) for index in range(7))
    too_short = constant[:3]

    # When
    constant_result = analyze_longitudinal(constant, AnalysisRequest(minimum_n=5, max_lag=0))
    short_result = analyze_longitudinal(too_short, AnalysisRequest(minimum_n=5, max_lag=0))

    # Then
    assert constant_result.correlations[0].status is CorrelationStatus.CORRELATION_UNAVAILABLE
    assert constant_result.correlations[0].coefficient is None
    assert short_result.correlations[0].status is CorrelationStatus.UNAVAILABLE
    assert short_result.correlations[0].coefficient is None


def test_grouped_trends_and_confound_warning_are_explicit() -> None:
    # Given
    observations = tuple(
        _observation(
            index,
            predictor=float(index),
            outcome=float(index),
            location="lab_a" if index < 4 else "lab_b",
        )
        for index in range(8)
    )

    # When
    result = analyze_longitudinal(observations, AnalysisRequest(minimum_n=5, max_lag=0))

    # Then
    assert {trend.group_dimension for trend in result.trends} >= {
        "location",
        "condition",
        "time_of_day",
        "metadata.load",
    }
    finding = result.correlations[0]
    assert finding.confound_columns == ("time_of_day", "load", "location")
    assert finding.confound_warning == "наблюдаемые факторы могут совместно изменяться"
    assert finding.exploratory is True
