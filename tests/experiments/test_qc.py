from dataclasses import replace
from pathlib import Path

from lnt.acquisition_quality import AcquisitionQuality, QualityCode, QualityFinding
from lnt.capture_preflight import FindingSeverity, PreflightFinding
from lnt.comparability import (
    InclusionState,
    MemberInclusion,
    MemberStateStore,
    recommend_exclusion,
)


def _quality(*codes: QualityCode) -> AcquisitionQuality:
    return AcquisitionQuality(
        quality_thresholds_version=1,
        channels=(),
        findings=tuple(
            QualityFinding(
                code=code,
                channel="ch1" if code in {QualityCode.CLIPPING, QualityCode.UNDER_RANGE} else None,
                message_ru=code.value,
                recovery_action_ru="Решение принимает оператор.",
            )
            for code in codes
        ),
        maximum_callback_gap_s=0.0,
        short_block_count=0,
    )


def test_qc_recommends_exclusion_without_changing_member_state() -> None:
    member = MemberInclusion.proposed(member_id="session-a", actor="author", reason="added")

    recommendations = recommend_exclusion(
        member_id=member.member_id,
        quality=_quality(QualityCode.CLIPPING),
        preflight_findings=(),
    )

    assert member.current.state is InclusionState.PROPOSED
    assert recommendations[0].reason_code == "qc_clipping"
    assert recommendations[0].recommended_state is InclusionState.EXCLUDED


def test_warning_preflight_is_visible_but_does_not_recommend_exclusion() -> None:
    recommendations = recommend_exclusion(
        member_id="session-a",
        quality=_quality(),
        preflight_findings=(
            PreflightFinding(
                severity=FindingSeverity.WARN,
                code="weak_signal",
                message_ru="Слабый сигнал.",
                recovery_action_ru="Проверьте вручную.",
            ),
        ),
    )

    assert recommendations == ()


def test_explicit_exclusion_is_audit_visible_and_undo_restores_previous_state(
    tmp_path: Path,
) -> None:
    store = MemberStateStore(tmp_path, scope_id="experiment-a")
    initial = MemberInclusion.proposed(member_id="session-a", actor="author", reason="member added")
    store.save(initial, expected_revision=0)

    excluded = store.transition(
        member_id="session-a",
        state=InclusionState.EXCLUDED,
        actor="reviewer",
        reason="qc_clipping reviewed",
        expected_revision=1,
    )
    restored = store.undo(
        member_id="session-a",
        actor="reviewer",
        reason="capture accepted after inspection",
        expected_revision=2,
    )

    assert excluded.current.state is InclusionState.EXCLUDED
    assert excluded.current.actor == "reviewer"
    assert excluded.current.reason == "qc_clipping reviewed"
    assert restored.current.state is InclusionState.PROPOSED
    assert [item.revision for item in restored.history] == [1, 2, 3]
    assert store.history("session-a") == restored.history


def test_state_output_keeps_excluded_members_with_reason() -> None:
    first = MemberInclusion.proposed(member_id="a", actor="author", reason="added")
    second = MemberInclusion.proposed(member_id="b", actor="author", reason="added")
    excluded = second.transition(
        state=InclusionState.EXCLUDED,
        actor="reviewer",
        reason="manual exclusion",
    )

    output = (first, excluded)

    assert [item.member_id for item in output] == ["a", "b"]
    assert output[1].current.reason == "manual exclusion"


def test_experiment_and_pair_scopes_use_the_same_append_only_store(tmp_path: Path) -> None:
    experiment_store = MemberStateStore(tmp_path / "experiments", scope_id="exp-1")
    pair_store = MemberStateStore(tmp_path / "comparisons", scope_id="pair-a-b")
    proposed = MemberInclusion.proposed(member_id="session-a", actor="author", reason="added")

    experiment_store.save(proposed, expected_revision=0)
    pair_store.save(replace(proposed, member_id="left"), expected_revision=0)

    assert experiment_store.load("session-a").current.state is InclusionState.PROPOSED
    assert pair_store.load("left").current.state is InclusionState.PROPOSED
