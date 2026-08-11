"""Парные таблицы произвольных линейных features, bands и harmonics."""

from .models import AnalysisContext, FeatureEffect, FeaturePair, PairedUnit
from .paired import estimate_paired


def analyze_feature_table(
    pairs: tuple[FeaturePair, ...],
    context: AnalysisContext,
    *,
    seed: int = 0,
) -> tuple[FeatureEffect, ...]:
    """Применяет одну парную оценку к каждой общей строке feature-таблицы."""
    if not pairs:
        return ()
    keys = tuple(item.key for item in pairs[0].values_a)
    return tuple(
        FeatureEffect(
            key=key,
            effect=estimate_paired(
                tuple(
                    PairedUnit(
                        unit_id_a=pair.unit_id_a,
                        unit_id_b=pair.unit_id_b,
                        value_a=_feature_value(pair, key, condition="a"),
                        value_b=_feature_value(pair, key, condition="b"),
                    )
                    for pair in pairs
                ),
                context,
                seed=seed + index,
            ),
        )
        for index, key in enumerate(keys)
    )


def _feature_value(pair: FeaturePair, key: str, *, condition: str) -> float:
    values = pair.values_a if condition == "a" else pair.values_b
    matching = tuple(item.value for item in values if item.key == key)
    if len(matching) != 1:
        raise KeyError(key)
    return matching[0]
