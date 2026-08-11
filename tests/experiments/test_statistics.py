from dataclasses import replace

import numpy as np
import pytest

from lnt.comparability import InclusionState, MemberInclusion
from lnt.experiments import MultiplicityPolicy, Protocol, ProtocolDeclaration
from lnt.statistics import (
    PROTOCOL_TO_ESTIMATOR,
    AbaUnit,
    AnalysisContext,
    ContrastRefusal,
    DescriptiveEffect,
    Estimator,
    EstimatorRejectedError,
    FeaturePair,
    FeatureValue,
    InferentialEffect,
    PairedUnit,
    PairingError,
    ProtocolInferenceDeclaration,
    RawRepeatedSamplesError,
    SpectrumPair,
    analyze_aba,
    analyze_feature_table,
    analyze_spectra,
    authorize_estimator,
    estimate_paired,
    linear_ratio_to_db,
    paired_unit_from_aggregates,
)


def declaration(kind: Protocol = Protocol.AB) -> ProtocolDeclaration:
    return ProtocolDeclaration(
        kind=kind,
        sampling_unit="subject",
        site_key="site_id",
        subject_key="subject_id",
        block_key="block_id",
        pairing_key="pair_id",
        assignment_scheme="balanced_explicit",
        order_scheme="declared_step_order",
        within_unit_aggregation="median",
        independence_assumptions=("Независимы только разные subject_id.",),
        minimum_n=2,
        multiplicity_policy=MultiplicityPolicy.FDR_BH,
    )


def context(kind: Protocol = Protocol.AB) -> AnalysisContext:
    excluded = MemberInclusion.proposed(member_id="bad", actor="tester", reason="review")
    excluded = excluded.transition(
        state=InclusionState.EXCLUDED,
        actor="tester",
        reason="qc_clipping",
    )
    return AnalysisContext(
        protocol=declaration(kind),
        hierarchy=("site_id", "subject_id", "block_id"),
        missing_count=1,
        member_states=(excluded,),
    )


def pairs(differences: tuple[float, ...]) -> tuple[PairedUnit, ...]:
    return tuple(
        PairedUnit(unit_id_a=f"u{index}", unit_id_b=f"u{index}", value_a=10.0, value_b=10 + delta)
        for index, delta in enumerate(differences)
    )


def test_protocol_table_rejects_unlocked_estimator() -> None:
    assert PROTOCOL_TO_ESTIMATOR[Protocol.ABA] == (Estimator.QUALIFIED_WITHIN_RUN_CONTRAST,)

    with pytest.raises(EstimatorRejectedError) as caught:
        authorize_estimator(declaration(), Estimator.BLOCK_PAIRED)

    assert caught.value.reason_code == "estimator_not_allowed_for_protocol"


def test_paired_fixture_recovers_linear_effect_with_labeled_metadata() -> None:
    result = estimate_paired(pairs((1.8, 2.0, 2.2, 1.9, 2.1)), context(), seed=17)

    assert isinstance(result, InferentialEffect)
    assert result.mean_effect == pytest.approx(2.0)
    assert result.interval.low <= 2.0 <= result.interval.high
    assert result.metadata.sampling_unit == "subject"
    assert result.metadata.hierarchy == ("site_id", "subject_id", "block_id")
    assert result.metadata.n == 5
    assert result.metadata.missing_count == 1
    assert result.metadata.exclusions[0].member_id == "bad"
    assert result.metadata.estimator_name == "paired_difference"
    assert result.metadata.interval_method == "seeded_block_bootstrap_percentile_95"


def test_no_effect_interval_covers_zero_and_seed_is_deterministic() -> None:
    values = pairs((-0.2, 0.1, 0.0, 0.2, -0.1, 0.05))

    first = estimate_paired(values, context(), seed=4)
    second = estimate_paired(values, context(), seed=4)

    assert isinstance(first, InferentialEffect)
    assert isinstance(second, InferentialEffect)
    assert first.interval == second.interval
    assert first.interval.low <= 0 <= first.interval.high


def test_robust_effect_resists_one_outlier() -> None:
    result = estimate_paired(pairs((1.0, 1.0, 1.0, 1.0, 100.0)), context(), seed=3)

    assert isinstance(result, InferentialEffect)
    assert result.robust_effect == pytest.approx(1.0)
    assert result.mean_effect > 10


def test_db_conversion_occurs_only_after_linear_ratio_estimation() -> None:
    assert linear_ratio_to_db(estimate=2.0) == pytest.approx(3.0102999566)


def test_pseudoreplication_and_shuffled_pairing_are_typed_errors() -> None:
    with pytest.raises(RawRepeatedSamplesError):
        paired_unit_from_aggregates(
            unit_id_a="u1",
            unit_id_b="u1",
            value_a=(1.0, 2.0),
            value_b=3.0,
        )
    with pytest.raises(PairingError):
        estimate_paired(
            (PairedUnit(unit_id_a="u1", unit_id_b="u2", value_a=1.0, value_b=2.0),),
            context(),
        )


def test_n_below_three_is_descriptive_without_interval() -> None:
    result = estimate_paired(pairs((1.0, 2.0)), context())

    assert isinstance(result, DescriptiveEffect)
    assert result.interval is None
    assert result.metadata.interval_method == "none_insufficient_n"


def test_aba_science_effect_is_qualified_noncausal_contrast() -> None:
    units = tuple(
        AbaUnit(unit_id=f"u{index}", value_a1=base, value_b=base + 0.2, value_a2=base)
        for index, base in enumerate((0.0, 0.01, -0.01, 0.02))
    )

    result = analyze_aba(units, context(Protocol.ABA), seed=11)

    assert not isinstance(result, ContrastRefusal)
    assert result.result_kind == "qualified within-run contrast"
    assert result.effect.mean_effect == pytest.approx(0.2)
    assert result.drift.mean_effect == pytest.approx(0.0)
    assert (
        result.description_ru
        == "Квалифицированный внутрисерийный контраст; причинный вывод недоступен."
    )


def test_aba_high_drift_blocks_pooled_contrast() -> None:
    units = tuple(
        AbaUnit(unit_id=f"u{index}", value_a1=0.0, value_b=0.2, value_a2=0.4) for index in range(4)
    )

    result = analyze_aba(units, context(Protocol.ABA))

    assert isinstance(result, ContrastRefusal)
    assert result.result_kind == "qualified within-run contrast"
    assert result.reason_code == "a_drift_exceeds_half_effect_or_two_sd"
    assert result.drift_effect == pytest.approx(0.4)


def test_cohort_inference_requires_independence_and_predefined_estimator() -> None:
    cohort = declaration(Protocol.COHORT)
    with pytest.raises(EstimatorRejectedError) as caught:
        authorize_estimator(cohort, "cohort_mean_difference")
    assert caught.value.reason_code == "descriptive_only_protocol"

    allowed = authorize_estimator(
        cohort,
        "cohort_mean_difference",
        inference=ProtocolInferenceDeclaration(
            independent_units_declared=True,
            predefined_estimator="cohort_mean_difference",
        ),
    )
    assert allowed == "cohort_mean_difference"


def test_feature_table_uses_paired_machinery() -> None:
    feature_pairs = tuple(
        FeaturePair(
            unit_id_a=f"u{index}",
            unit_id_b=f"u{index}",
            values_a=(FeatureValue(key="band.low.power_v2", value=1.0),),
            values_b=(FeatureValue(key="band.low.power_v2", value=1.0 + delta),),
        )
        for index, delta in enumerate((0.1, 0.2, 0.3))
    )

    table = analyze_feature_table(feature_pairs, context(), seed=7)

    assert table[0].key == "band.low.power_v2"
    assert isinstance(table[0].effect, InferentialEffect)
    assert table[0].effect.mean_effect == pytest.approx(0.2)


def test_spectral_fdr_and_clusters_are_stored_and_deterministic() -> None:
    frequencies = (100.0, 200.0, 300.0, 400.0)
    spectra = tuple(
        SpectrumPair(
            unit_id_a=f"u{index}",
            unit_id_b=f"u{index}",
            values_a=(1.0, 1.0, 1.0, 1.0),
            values_b=(1.0, 2.0 + index * 0.01, 2.0 + index * 0.02, 1.0),
        )
        for index in range(5)
    )

    first = analyze_spectra(frequencies, spectra, context(), seed=19)
    second = analyze_spectra(frequencies, spectra, context(), seed=19)

    assert first.q_values == second.q_values
    assert all(np.isfinite(first.q_values))
    assert first.clusters == second.clusters
    assert first.clusters[0].low_hz == 200.0
    assert first.clusters[0].high_hz == 300.0


def test_repeated_blocks_selects_block_estimator() -> None:
    repeated = context(Protocol.REPEATED_BLOCKS)
    result = estimate_paired(pairs((1.0, 1.1, 0.9)), repeated, seed=1)

    assert result.metadata.estimator_name == "block_paired"
    assert authorize_estimator(repeated.protocol, Estimator.BLOCK_PAIRED) is Estimator.BLOCK_PAIRED


def test_declared_minimum_n_above_observed_keeps_result_descriptive() -> None:
    strict = replace(context(), protocol=declaration().model_copy(update={"minimum_n": 5}))

    result = estimate_paired(pairs((1.0, 1.0, 1.0)), strict)

    assert isinstance(result, DescriptiveEffect)
