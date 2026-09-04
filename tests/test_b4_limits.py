"""B4 truth-тесты граничных длительностей ITIC/SEMI-F47 и масок лимитов."""

from __future__ import annotations

import pytest

from lnt.limits.masks import (
    LimitMask,
    LimitPoint,
    evaluate_mask,
    spc_verdict,
    thd_limit_verdict,
)
from lnt.power_quality.detector import evaluate_tolerance


@pytest.mark.parametrize(
    ("duration_s", "ratio", "expected"),
    [
        (0.02, 0.0, "in_tolerance"),
        (0.02, 1.20, "in_tolerance"),
        (0.5, 0.70, "in_tolerance"),
        (0.5, 1.20, "in_tolerance"),
        (10.0, 0.80, "in_tolerance"),
        (10.0, 1.10, "in_tolerance"),
        (0.2, 0.60, "out_of_tolerance"),
        (0.6, 1.15, "out_of_tolerance"),
    ],
)
def test_itic_boundary_truth(duration_s: float, ratio: float, expected: str) -> None:
    assert evaluate_tolerance(duration_s, ratio, curve="itic").value == expected


@pytest.mark.parametrize(
    ("duration_s", "ratio", "expected"),
    [
        (0.2, 0.50, "in_tolerance"),
        (0.2, 1.10, "in_tolerance"),
        (0.5, 0.70, "in_tolerance"),
        (1.0, 0.80, "in_tolerance"),
        (1.0, 1.10, "in_tolerance"),
        (0.2, 0.40, "out_of_tolerance"),
        (0.5, 0.60, "out_of_tolerance"),
        (1.0, 0.70, "out_of_tolerance"),
    ],
)
def test_semi_f47_boundary_truth(duration_s: float, ratio: float, expected: str) -> None:
    assert evaluate_tolerance(duration_s, ratio, curve="semi_f47").value == expected


def test_tolerance_unavailable_on_bad_inputs() -> None:
    assert evaluate_tolerance(float("nan"), 1.0, curve="itic").value == "unavailable"
    assert evaluate_tolerance(-1.0, 1.0, curve="semi_f47").value == "unavailable"
    assert evaluate_tolerance(0.1, float("inf"), curve="itic").value == "unavailable"


def test_mask_pass_fail_and_unavailable() -> None:
    mask = LimitMask(
        name="psd-mask",
        unit="db",
        points=(LimitPoint(x=10.0, y=-40.0), LimitPoint(x=100.0, y=-50.0)),
    )
    assert evaluate_mask(10.0, -50.0, mask) == "pass"
    assert evaluate_mask(10.0, -30.0, mask) == "fail"
    assert evaluate_mask(5.0, -60.0, mask) == "unavailable"
    assert evaluate_mask(10.0, float("nan"), mask) == "unavailable"
    assert evaluate_mask(10.0, -50.0, LimitMask(name="empty", unit="db", points=())) == "unavailable"


def test_spc_and_thd_verdicts_are_honest() -> None:
    assert spc_verdict(0.0, center=0.0, sigma=1.0) == "pass"
    assert spc_verdict(5.0, center=0.0, sigma=1.0) == "fail"
    assert spc_verdict(0.0, center=0.0, sigma=0.0) == "unavailable"
    assert thd_limit_verdict(0.05, limit=0.08, cycles_analyzed=120) == "pass"
    assert thd_limit_verdict(0.10, limit=0.08, cycles_analyzed=120) == "fail"
    assert thd_limit_verdict(0.10, limit=0.08, cycles_analyzed=10) == "unavailable"
    assert thd_limit_verdict(None, limit=0.08, cycles_analyzed=120) == "unavailable"


def test_mask_round_trip_outside_session(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from lnt.limits.masks import load_masks, save_masks

    path = tmp_path / "limits.json"
    masks = (
        LimitMask(
            name="trend-mask",
            unit="v",
            points=(LimitPoint(x=0.0, y=1.0), LimitPoint(x=10.0, y=1.0)),
        ),
    )
    save_masks(path, masks)
    assert load_masks(path) == masks
    manifest = tmp_path / "manifest.json"
    assert not manifest.exists()
