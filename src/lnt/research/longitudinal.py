"""Групповые тренды и описательные lag-корреляции."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from itertools import pairwise

import numpy as np
from scipy.stats import rankdata, t

from lnt.statistics.spectra import benjamini_hochberg

from .longitudinal_models import (
    AnalysisRequest,
    CorrelationFinding,
    CorrelationInterval,
    CorrelationStatus,
    DataQuality,
    Gap,
    LongitudinalResult,
    Observation,
    Trend,
)


def analyze_longitudinal(
    observations: tuple[Observation, ...], request: AnalysisRequest
) -> LongitudinalResult:
    """Нормализует время и строит только описательные результаты."""
    valid: list[tuple[datetime, Observation]] = []
    missing_timestamps = 0
    seen: set[datetime] = set()
    duplicates = 0
    for observation in observations:
        if observation.timestamp is None:
            missing_timestamps += 1
            continue
        parsed = datetime.fromisoformat(observation.timestamp)
        if parsed.tzinfo is None:
            missing_timestamps += 1
            continue
        normalized = parsed.astimezone(UTC)
        if normalized in seen:
            duplicates += 1
            continue
        seen.add(normalized)
        valid.append((normalized, observation))
    valid.sort(key=lambda item: item[0])
    timestamps = tuple(item[0] for item in valid)
    gaps = tuple(
        Gap(
            after_utc=left.isoformat(),
            before_utc=right.isoformat(),
            duration_seconds=(right - left).total_seconds(),
        )
        for left, right in pairwise(timestamps)
    )
    rows = tuple(item[1] for item in valid)
    findings = _correlations(rows, request)
    return LongitudinalResult(
        trends=_trends(rows),
        correlations=_apply_bh(findings),
        data_quality=DataQuality(
            input_count=len(observations),
            usable_count=len(rows),
            missing_timestamp_count=missing_timestamps,
            duplicate_count=duplicates,
            dedupe_policy="keep_first_by_input_order",
            gaps=gaps,
        ),
        normalized_timestamps=timestamps,
    )


def _trends(rows: tuple[Observation, ...]) -> tuple[Trend, ...]:
    grouped: defaultdict[tuple[str, str], list[float | None]] = defaultdict(list)
    for row in rows:
        grouped[("location", row.location)].append(row.outcome)
        grouped[("condition", row.condition)].append(row.outcome)
        if row.timestamp is not None:
            hour = datetime.fromisoformat(row.timestamp).hour
            grouped[("time_of_day", f"{hour // 6 * 6:02d}-{hour // 6 * 6 + 5:02d}")].append(
                row.outcome
            )
        for field in row.metadata:
            grouped[(f"metadata.{field.key}", str(field.value))].append(row.outcome)
    trends: list[Trend] = []
    for (dimension, value), values in sorted(grouped.items()):
        available = [item for item in values if item is not None]
        trends.append(
            Trend(
                group_dimension=dimension,
                group_value=value,
                n=len(available),
                missing_count=len(values) - len(available),
                mean=float(np.mean(available)) if available else None,
            )
        )
    return tuple(trends)


def _correlations(
    rows: tuple[Observation, ...], request: AnalysisRequest
) -> tuple[CorrelationFinding, ...]:
    result: list[CorrelationFinding] = []
    metadata_keys = {field.key for row in rows for field in row.metadata}
    confounds = tuple(
        key for key in ("time_of_day", "load", "location") if key != "load" or key in metadata_keys
    )
    for lag in range(request.max_lag + 1):
        paired_rows = zip(rows[: len(rows) - lag or None], rows[lag:], strict=True)
        pairs = tuple(
            (left.predictor, right.outcome)
            for left, right in paired_rows
            if left.predictor is not None and right.outcome is not None
        )
        missing_count = len(rows) - lag - len(pairs)
        result.append(_correlation(pairs, lag, missing_count, confounds, request))
    return tuple(result)


def _correlation(
    pairs: tuple[tuple[float, float], ...],
    lag: int,
    missing_count: int,
    confounds: tuple[str, ...],
    request: AnalysisRequest,
) -> CorrelationFinding:
    base = CorrelationFinding(
        lag=lag,
        status=CorrelationStatus.UNAVAILABLE,
        coefficient=None,
        interval=None,
        n=len(pairs),
        missing_count=missing_count,
        p_value=None,
        q_value=None,
        multiple_testing="benjamini_hochberg",
        confound_columns=confounds,
        confound_warning="наблюдаемые факторы могут совместно изменяться",
    )
    if len(pairs) < request.minimum_n:
        return base
    x_values = np.asarray([pair[0] for pair in pairs], dtype=np.float64)
    y_values = np.asarray([pair[1] for pair in pairs], dtype=np.float64)
    if np.all(x_values == x_values[0]) or np.all(y_values == y_values[0]):
        return replace(base, status=CorrelationStatus.CORRELATION_UNAVAILABLE)
    coefficient = _spearman(x_values, y_values)
    if abs(coefficient) == 1.0:
        p_value = 0.0
    else:
        statistic = coefficient * np.sqrt((len(pairs) - 2) / (1.0 - coefficient**2))
        p_value = float(2.0 * t.sf(abs(statistic), len(pairs) - 2))
    rng = np.random.default_rng(request.seed + lag)
    sampled = rng.integers(0, len(pairs), size=(request.bootstrap_samples, len(pairs)))
    estimates = np.asarray(
        [
            _spearman(x_values[index], y_values[index])
            for index in sampled
            if np.unique(x_values[index]).size > 1 and np.unique(y_values[index]).size > 1
        ],
        dtype=np.float64,
    )
    finite = estimates[np.isfinite(estimates)]
    low, high = np.quantile(finite, (0.025, 0.975))
    return replace(
        base,
        status=CorrelationStatus.AVAILABLE,
        coefficient=coefficient,
        p_value=p_value,
        interval=CorrelationInterval(low=float(low), high=float(high)),
    )


def _apply_bh(findings: tuple[CorrelationFinding, ...]) -> tuple[CorrelationFinding, ...]:
    available = tuple(item for item in findings if item.p_value is not None)
    q_values = iter(
        benjamini_hochberg(tuple(item.p_value for item in available if item.p_value is not None))
    )
    return tuple(
        replace(item, q_value=next(q_values)) if item.p_value is not None else item
        for item in findings
    )


def _spearman(x_values: np.ndarray, y_values: np.ndarray) -> float:
    x_ranks = np.asarray(rankdata(x_values), dtype=np.float64)
    y_ranks = np.asarray(rankdata(y_values), dtype=np.float64)
    return float(np.corrcoef(x_ranks, y_ranks)[0, 1])
