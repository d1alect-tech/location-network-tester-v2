"""Characterization bundle assembly: mapped families beside the F01, F02, F05, F06 chain."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f03_bundle import F03_ID, F03_INDEX, build_f03_family
from lnt.characterization.f04_bundle import F04_ID, F04_INDEX, build_f04_family
from lnt.characterization.f06_bundle import build_f01_f02_f05_f06_bundle
from lnt.characterization.f07_bundle import F07_ID, F07_INDEX, build_f07_family
from lnt.characterization.f08_bundle import F08_ID, F08_INDEX, build_f08_family
from lnt.characterization.f09_bundle import F09_ID, F09_INDEX, build_f09_family
from lnt.characterization.f10_bundle import F10_ID, F10_INDEX, build_f10_family
from lnt.characterization.f11_bundle import F11_ID, F11_INDEX, build_f11_family
from lnt.characterization.f13_bundle import F13_ID, F13_INDEX, build_f13_family
from lnt.characterization.f15_bundle import F15_ID, F15_INDEX, build_f15_family
from lnt.characterization.models import CharacterizationBundle
from lnt.characterization.records import Band

if TYPE_CHECKING:
    import numpy as np

    from lnt.analysis_store import CharacterizationRecipe
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f01_phase_cycle import F01Result
    from lnt.characterization.f02_amplitude_shape import F02Result
    from lnt.characterization.f03_result import F03Result
    from lnt.characterization.f04_periodicity import F04Result
    from lnt.characterization.f05_phase_stats import F05Result
    from lnt.characterization.f06_modulation import F06Result
    from lnt.characterization.f07_result import F07Result
    from lnt.characterization.f08_result import F08Result
    from lnt.characterization.f09_result import F09Result
    from lnt.characterization.f10_result import F10Result
    from lnt.characterization.f11_result import F11Result
    from lnt.characterization.f13_result import F13Result
    from lnt.characterization.f15_result import F15Result
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock


def build_characterization_bundle(  # noqa: PLR0913, PLR0917 - рецепт, канал и сетка записи задают сборку
    f01_result: F01Result,
    f02_result: F02Result,
    f03_result: F03Result,
    f04_result: F04Result,
    f05_result: F05Result,
    f06_result: F06Result,
    f07_result: F07Result,
    f08_result: F08Result,
    f09_result: F09Result,
    f10_result: F10Result,
    f11_result: F11Result,
    f13_result: F13Result,
    f15_result: F15Result,
    recipe: CharacterizationRecipe,
    *,
    measured_channel: str = "ch1",
    sample_rate_hz: float,
    record_duration_s: float,
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Assemble the mapped families beside F01, F02, F05, F06 and five placeholders."""
    families = recipe.families
    _require_declared_order(families)
    previous, arrays, tables = build_f01_f02_f05_f06_bundle(
        f01_result,
        f02_result,
        f05_result,
        f06_result,
        recipe,
        measured_channel=measured_channel,
        sample_rate_hz=sample_rate_hz,
        record_duration_s=record_duration_s,
    )
    band = Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)
    f03_family, f03_arrays = build_f03_family(
        f03_result,
        families[F03_INDEX],
        band,
        measured_channel=measured_channel,
        window_s=_window_s(families[F03_INDEX]),
    )
    f04_family, f04_arrays = build_f04_family(
        f04_result,
        families[F04_INDEX],
        band,
        measured_channel=measured_channel,
        record_duration_s=float(record_duration_s),
    )
    f07_family, f07_arrays = build_f07_family(
        f07_result,
        families[F07_INDEX],
        band,
        measured_channel=measured_channel,
        record_duration_s=float(record_duration_s),
        sample_rate_hz=float(sample_rate_hz),
    )
    f08_family, f08_arrays = build_f08_family(
        f08_result,
        families[F08_INDEX],
        band,
        measured_channel=measured_channel,
        record_duration_s=float(record_duration_s),
    )
    f09_family, f09_arrays, f09_tables = build_f09_family(
        f09_result,
        families[F09_INDEX],
        band,
        measured_channel=measured_channel,
        record_duration_s=float(record_duration_s),
    )
    f10_family, f10_arrays = build_f10_family(
        f10_result,
        families[F10_INDEX],
        band,
        measured_channel=measured_channel,
        record_duration_s=float(record_duration_s),
    )
    f11_family, f11_arrays, f11_tables = build_f11_family(
        f11_result,
        families[F11_INDEX],
        band,
        measured_channel=measured_channel,
        record_duration_s=float(record_duration_s),
    )
    f13_family, f13_arrays, f13_tables = build_f13_family(
        f13_result,
        families[F13_INDEX],
        band,
        measured_channel=measured_channel,
        record_duration_s=float(record_duration_s),
    )
    f15_family, f15_arrays, f15_tables = build_f15_family(
        f15_result,
        families[F15_INDEX],
        band,
        measured_channel=measured_channel,
        record_duration_s=float(record_duration_s),
    )
    # Сплайс один на все семейства: позиция -> конверт, остальное остаётся
    # заглушкой ``previous``. Ручные срезы по каждому индексу не масштабируются
    # на оставшиеся 5 семейств, поэтому порядок собирается общим проходом.
    mapped: tuple[tuple[int, FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]], ...] = (
        (F03_INDEX, f03_family, f03_arrays, {}),
        (F04_INDEX, f04_family, f04_arrays, {}),
        (F07_INDEX, f07_family, f07_arrays, {}),
        (F08_INDEX, f08_family, f08_arrays, {}),
        (F09_INDEX, f09_family, f09_arrays, f09_tables),
        (F10_INDEX, f10_family, f10_arrays, {}),
        (F11_INDEX, f11_family, f11_arrays, f11_tables),
        (F13_INDEX, f13_family, f13_arrays, f13_tables),
        (F15_INDEX, f15_family, f15_arrays, f15_tables),
    )
    envelope_by_index = {position: family for position, family, _, _ in mapped}
    bundle = CharacterizationBundle(
        families=tuple(
            envelope_by_index.get(position, previous.families[position])
            for position in range(len(families))
        )
    )
    merged_arrays = {**arrays}
    merged_tables = dict(tables)
    for _, _, family_arrays, family_tables in mapped:
        merged_arrays.update(family_arrays)
        merged_tables.update(family_tables)
    return bundle, merged_arrays, merged_tables


_DECLARED_ORDER: Final = (
    (F03_INDEX, F03_ID),
    (F04_INDEX, F04_ID),
    (F07_INDEX, F07_ID),
    (F08_INDEX, F08_ID),
    (F09_INDEX, F09_ID),
    (F10_INDEX, F10_ID),
    (F11_INDEX, F11_ID),
    (F13_INDEX, F13_ID),
    (F15_INDEX, F15_ID),
)


def _require_declared_order(families: tuple[CharacterizationFamily, ...]) -> None:
    """Отказ, если рецепт объявил семейства не на своих позициях."""
    for position, family_id in _DECLARED_ORDER:
        if len(families) <= position or families[position].id != family_id:
            raise CharacterizationError(
                "family_order", f"recipe must declare {family_id} at position {position}"
            )


def _window_s(family: CharacterizationFamily) -> float:
    """Read the declared F03 window, refusing a non-number."""
    raw = family.value("window_s")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise CharacterizationError("status_invariant", "f03 window_s must be a number")
    return float(raw)
