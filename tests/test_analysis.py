import json
from pathlib import Path

import pytest

from lnt.analysis import (
    AnalysisResult,
    analysis_to_payload,
    analyze_measurement_session,
    render_analysis,
    write_analysis,
)
from lnt.needles import MIN_CYCLES
from lnt.simulate import simulate_session

FS = 250_000.0
DURATION = 2.1
RING_F0 = 22_400.0


@pytest.fixture(scope="module")
def bad_session(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return simulate_session(
        out_dir=tmp_path_factory.mktemp("analysis") / "syn-bad",
        profile="bad",
        duration_s=DURATION,
        sample_rate_hz=FS,
        seed=6022,
    )


@pytest.fixture(scope="module")
def bad_result(bad_session: Path) -> AnalysisResult:
    return analyze_measurement_session(bad_session)


class TestAnalyzeSession:
    def test_metadata_carried_from_manifest(self, bad_result: AnalysisResult) -> None:
        assert bad_result.session_id == "syn-bad-seed6022"
        assert bad_result.profile == "bad"
        assert bad_result.sample_rate_hz == FS

    def test_needle_metrics_recovered(self, bad_result: AnalysisResult) -> None:
        assert bad_result.needle.cycles_analyzed >= MIN_CYCLES
        assert 0.14 < bad_result.needle.needle_mean_v < 0.26

    def test_spectrum_peak_at_ring(self, bad_result: AnalysisResult) -> None:
        assert bad_result.spectrum.peaks
        top = bad_result.spectrum.peaks[0]
        assert abs(top.frequency_hz - RING_F0) <= 2.0 * bad_result.spectrum.resolution_hz


class TestAnalysisPayload:
    def test_canonical_shape(self, bad_result: AnalysisResult) -> None:
        payload = analysis_to_payload(bad_result)

        assert set(payload) == {
            "schema_version",
            "session_id",
            "profile",
            "source",
            "session_type",
            "sample_rate_hz",
            "duration_s",
            "needle",
            "line_quality",
            "spectrum",
            "ch1_input_reference",
        }
        assert payload["line_quality"] is None
        needle = payload["needle"]
        assert isinstance(needle, dict)
        assert needle.keys() == {
            "sync_source",
            "cycles_analyzed",
            "line_frequency_hz",
            "needle_mean_v",
            "needle_sigma_ratio",
            "sync_power_v2",
            "async_power_v2",
            "async_sync_ratio",
            "lf_envelope_cv",
        }
        assert needle["sync_source"] == "ch2"
        spectrum = payload["spectrum"]
        assert isinstance(spectrum, dict)
        assert spectrum.keys() == {
            "resolution_hz",
            "band_low_hz",
            "band_high_hz",
            "peaks",
        }
        assert payload["schema_version"] == 2
        assert payload["ch1_input_reference"] == {
            "status": "unavailable",
            "reason_code": "manifest_schema_v1",
            "model_kind": None,
            "baseline_session_id": None,
            "model": None,
            "qualification_rule_id": None,
            "qualified_bin_count": 0,
            "total_bin_count": 0,
            "corrected_peaks": [],
        }


class TestArtifacts:
    def test_metrics_json_and_spectrum_csv(
        self,
        bad_session: Path,
        bad_result: AnalysisResult,
    ) -> None:
        metrics_path, spectrum_path = write_analysis(bad_session, bad_result)
        assert metrics_path.name == "metrics.json"
        assert spectrum_path.name == "spectrum.csv"

        metrics_text = metrics_path.read_text(encoding="utf-8")
        assert (
            metrics_text
            == json.dumps(
                analysis_to_payload(bad_result),
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        payload = json.loads(metrics_text)
        assert payload["session_id"] == bad_result.session_id
        assert payload["needle"]["needle_mean_v"] == pytest.approx(
            bad_result.needle.needle_mean_v,
        )
        top = payload["spectrum"]["peaks"][0]
        assert top["frequency_hz"] == pytest.approx(bad_result.spectrum.peaks[0].frequency_hz)

        lines = spectrum_path.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "frequency_hz,psd_v2_per_hz"
        assert len(lines) - 1 == bad_result.spectrum.frequencies_hz.size
        first_freq = float(lines[1].split(",")[0])
        assert first_freq == pytest.approx(float(bad_result.spectrum.frequencies_hz[0]))


class TestRender:
    def test_summary_contains_essentials(self, bad_result: AnalysisResult) -> None:
        text = render_analysis(bad_result)
        assert bad_result.session_id in text
        assert str(bad_result.needle.cycles_analyzed) in text
        assert "Гц" in text
        assert "дБ" in text

    def test_summary_encodes_in_ru_windows_consoles(self, bad_result: AnalysisResult) -> None:
        text = render_analysis(bad_result)
        text.encode("cp1251")
        text.encode("cp866")
