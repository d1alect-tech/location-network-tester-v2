from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lnt.analysis import analyze_measurement_session
from lnt.compare import compare_analyses, comparison_to_payload
from lnt.simulate import simulate_session
from tests.ch1_contract_fixtures import (
    Ch1SessionSpec,
    ToneCaptureSpec,
    floating_measurement_setup,
    make_tone_captures,
    self_noise_setup,
    write_v2_session,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_unknown_input_models_keep_existing_raw_b_minus_a_peak_deltas(tmp_path: Path) -> None:
    # Given: two legacy sessions, whose CH1 models are intentionally unknown.
    first = analyze_measurement_session(
        simulate_session(
            out_dir=tmp_path / "first",
            profile="bad",
            duration_s=2.1,
            sample_rate_hz=250_000.0,
            seed=6022,
        ),
    )
    second = analyze_measurement_session(
        simulate_session(
            out_dir=tmp_path / "second",
            profile="bad-damped",
            duration_s=2.1,
            sample_rate_hz=250_000.0,
            seed=6022,
        ),
    )

    # When: the sessions are compared at the raw scope-plane peak frequencies.
    payload = comparison_to_payload(compare_analyses(first, second))

    # Then: B - A remains available, while no fictional input-referred delta is emitted.
    raw_delta = payload["peak_deltas"][0]
    assert raw_delta["delta_db"] == pytest.approx(
        raw_delta["level_b_db"] - raw_delta["level_a_db"],
    )
    assert "input_referred_peak_deltas" not in payload


def test_incompatible_explicit_models_do_not_add_input_referred_comparison(
    tmp_path: Path,
) -> None:
    # Given: two otherwise-compatible captures with different explicit RC component values.
    captures = make_tone_captures(
        ToneCaptureSpec(
            sample_rate_hz=100_000.0,
            duration_s=2.1,
            tone_frequency_hz=10_000.0,
            source_amplitude_v=0.2,
            transfer_gain=0.03,
            baseline_sigma_v=0.0002,
        ),
    )
    setup_a = floating_measurement_setup()
    setup_b = floating_measurement_setup()
    setup_b["c1_f"] = 20e-9
    for name, setup in (("a", setup_a), ("b", setup_b)):
        write_v2_session(
            tmp_path / f"baseline-{name}",
            spec=Ch1SessionSpec(
                session_id=f"baseline-{name}",
                session_type="self_noise",
                source="device",
                sample_rate_hz=100_000.0,
                duration_s=2.1,
                ch1_setup=self_noise_setup(),
                baseline_session=None,
            ),
            ch1=captures.scope_baseline,
            ch2=captures.ch2,
        )
        write_v2_session(
            tmp_path / f"measurement-{name}",
            spec=Ch1SessionSpec(
                session_id=f"measurement-{name}",
                session_type="measurement",
                source="device",
                sample_rate_hz=100_000.0,
                duration_s=2.1,
                ch1_setup=setup,
                baseline_session=f"../baseline-{name}",
            ),
            ch1=captures.scope_measurement,
            ch2=captures.ch2,
        )

    # When: their existing raw peak comparison is requested.
    comparison = compare_analyses(
        analyze_measurement_session(tmp_path / "measurement-a"),
        analyze_measurement_session(tmp_path / "measurement-b"),
    )
    payload = comparison_to_payload(comparison)

    # Then: raw deltas remain mathematically valid and incompatible referral models stay absent.
    raw_delta = payload["peak_deltas"][0]
    assert raw_delta["delta_db"] == pytest.approx(
        raw_delta["level_b_db"] - raw_delta["level_a_db"],
    )
    assert "input_referred_peak_deltas" not in payload
