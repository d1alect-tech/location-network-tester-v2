"""Characterization bundle assembly: mapped F03 and F04 beside F01, F02, F05, F06."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f03_bundle import F03_ID, F03_INDEX, build_f03_family
from lnt.characterization.f04_bundle import F04_ID, F04_INDEX, build_f04_family
from lnt.characterization.f06_bundle import build_f01_f02_f05_f06_bundle
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
    from lnt.characterization.tables import TableBlock


def build_characterization_bundle(  # noqa: PLR0913, PLR0917 - рецепт, канал и сетка записи задают сборку
    f01_result: F01Result,
    f02_result: F02Result,
    f03_result: F03Result,
    f04_result: F04Result,
    f05_result: F05Result,
    f06_result: F06Result,
    recipe: CharacterizationRecipe,
    *,
    measured_channel: str = "ch1",
    sample_rate_hz: float,
    record_duration_s: float,
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Assemble mapped F03 and F04 beside F01, F02, F05, F06 and ten placeholders."""
    families = recipe.families
    if (
        len(families) <= F04_INDEX
        or families[F03_INDEX].id != F03_ID
        or families[F04_INDEX].id != F04_ID
    ):
        raise CharacterizationError("family_order", "recipe must declare f03 third and f04 fourth")
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
    bundle = CharacterizationBundle(
        families=(
            *previous.families[:F03_INDEX],
            f03_family,
            f04_family,
            *previous.families[F04_INDEX + 1 :],
        )
    )
    return bundle, {**arrays, **f03_arrays, **f04_arrays}, dict(tables)


def _window_s(family: CharacterizationFamily) -> float:
    """Read the declared F03 window, refusing a non-number."""
    raw = family.value("window_s")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise CharacterizationError("status_invariant", "f03 window_s must be a number")
    return float(raw)
