import json
from dataclasses import replace

import pytest

from lnt.analysis import AnalysisResult, analyze_measurement_session
from lnt.compare import (
    ComparisonResult,
    compare_analyses,
    comparison_to_payload,
    render_comparison,
)
from lnt.simulate import simulate_session

FS = 250_000.0
DURATION = 2.1


@pytest.fixture(scope="module")
def analyses(tmp_path_factory: pytest.TempPathFactory) -> tuple[AnalysisResult, AnalysisResult]:
    root = tmp_path_factory.mktemp("compare")
    result_a = analyze_measurement_session(
        simulate_session(
            out_dir=root / "a",
            profile="bad",
            duration_s=DURATION,
            sample_rate_hz=FS,
            seed=6022,
        ),
    )
    result_b = analyze_measurement_session(
        simulate_session(
            out_dir=root / "b",
            profile="bad-damped",
            duration_s=DURATION,
            sample_rate_hz=FS,
            seed=6022,
        ),
    )
    return result_a, result_b


@pytest.fixture(scope="module")
def comparison(analyses: tuple[AnalysisResult, AnalysisResult]) -> ComparisonResult:
    return compare_analyses(*analyses)


class TestCompare:
    def test_session_ids_carried(self, comparison: ComparisonResult) -> None:
        assert comparison.session_a_id == "syn-bad-seed6022"
        assert comparison.session_b_id == "syn-bad-damped-seed6022"

    def test_top_peak_delta_about_minus_12db(self, comparison: ComparisonResult) -> None:
        assert comparison.peak_deltas
        top = comparison.peak_deltas[0]
        assert top.delta_db == pytest.approx(top.level_b_db - top.level_a_db)
        assert -14.0 < top.delta_db < -10.0

    def test_matched_peak_q_present_in_both(self, comparison: ComparisonResult) -> None:
        top = comparison.peak_deltas[0]
        assert top.q_a is not None
        assert top.q_b is not None

    def test_needle_mean_improved(self, comparison: ComparisonResult) -> None:
        by_name = {delta.name: delta for delta in comparison.metric_deltas}
        mean_delta = by_name["needle_mean_v"]
        assert mean_delta.value_a is not None
        assert mean_delta.value_b is not None
        assert mean_delta.value_b < mean_delta.value_a


class TestPayload:
    def test_canonical_json_shape(self, comparison: ComparisonResult) -> None:
        payload = comparison_to_payload(comparison)

        assert tuple(payload) == (
            "session_a_id",
            "session_b_id",
            "peak_deltas",
            "metric_deltas",
        )
        assert isinstance(payload["session_a_id"], str)
        assert isinstance(payload["session_b_id"], str)

        peak_deltas = payload["peak_deltas"]
        assert isinstance(peak_deltas, list)
        assert peak_deltas
        for peak_delta in peak_deltas:
            assert isinstance(peak_delta, dict)
            assert tuple(peak_delta) == (
                "frequency_hz",
                "level_a_db",
                "level_b_db",
                "delta_db",
                "q_a",
                "q_b",
            )
            assert isinstance(peak_delta["frequency_hz"], float)
            assert isinstance(peak_delta["level_a_db"], float)
            assert isinstance(peak_delta["level_b_db"], float)
            assert isinstance(peak_delta["delta_db"], float)
            assert isinstance(peak_delta["q_a"], float | None)
            assert isinstance(peak_delta["q_b"], float | None)
            assert peak_delta["delta_db"] == (peak_delta["level_b_db"] - peak_delta["level_a_db"])

        metric_deltas = payload["metric_deltas"]
        assert isinstance(metric_deltas, list)
        assert metric_deltas
        for metric_delta in metric_deltas:
            assert isinstance(metric_delta, dict)
            assert tuple(metric_delta) == ("name", "value_a", "value_b")
            assert isinstance(metric_delta["name"], str)
            assert isinstance(metric_delta["value_a"], float)
            assert isinstance(metric_delta["value_b"], float)

        assert json.loads(json.dumps(payload)) == payload

    def test_unmatched_peak_q_b_remains_none(
        self,
        analyses: tuple[AnalysisResult, AnalysisResult],
    ) -> None:
        result_a, result_b = analyses
        result_b_without_peaks = replace(
            result_b,
            spectrum=replace(result_b.spectrum, peaks=()),
        )

        payload = comparison_to_payload(compare_analyses(result_a, result_b_without_peaks))

        peak_deltas = payload["peak_deltas"]
        assert isinstance(peak_deltas, list)
        assert peak_deltas
        assert peak_deltas[0]["q_b"] is None


class TestRender:
    def test_table_contains_essentials(self, comparison: ComparisonResult) -> None:
        text = render_comparison(comparison)
        assert comparison.session_a_id in text
        assert comparison.session_b_id in text
        assert "дБ" in text
        assert "needle_mean_v" in text

    def test_table_encodes_in_ru_windows_consoles(self, comparison: ComparisonResult) -> None:
        text = render_comparison(comparison)
        text.encode("cp1251")
        text.encode("cp866")
