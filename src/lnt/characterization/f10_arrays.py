"""Опубликованная раскладка F10: оси, ячейки поверхности и хранимые эпизоды.

Раскладка (решение F10-1, потребители F15 и F11): массивы ячеек публикуются
настоящей трёхмерной формой `(порог, длительность, бин)` в порядке C, квантили —
четырёхмерной `(порог, длительность, бин, уровень)`. Кодек поддерживает N-D
сквозь: `array_codec` проверяет числовой dtype, конечность и `prod(shape)`, а
`ArrayReference.shape` это `tuple[int, ...]`. Поэтому ни одна ось не уплощается
и не теряется: координаты всех четырёх осей публикуются отдельными массивами, и
ячейка адресуется значением оси, а не угаданным индексом.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.models import ArrayReference
from lnt.characterization.records import Unit, validate_unit_name

if TYPE_CHECKING:
    from lnt.characterization.f10_result import F10Result

type Entry = tuple[str, str, Unit]

# Домен квантилей публикуется всегда: он объявляет, где квантиль определён, и
# без него нули вне домена читались бы как измеренные нули (решение F10-12).
QUANTILE_MASK: Final = "f10_quantile_valid"
_QUANTILE_IDS: Final = frozenset({"f10_duration_quantile_s", "f10_episode_quantile_v2_s"})
_ENTRIES: Final = (
    ("f10_threshold_sigma", "threshold_axis", Unit.RATIO),
    ("f10_minimum_duration_s", "minimum_duration_axis", Unit.S),
    ("f10_phase_bin", "phase_bin_axis", Unit.COUNT),
    ("f10_quantile_level", "quantile_level_axis", Unit.RATIO),
    ("f10_occupancy", "threshold_occupancy", Unit.RATIO),
    ("f10_episode_count", "episode_count", Unit.COUNT),
    ("f10_total_v2_s", "total_v2_s", Unit.V2_S),
    ("f10_retained_samples", "retained_sample_count", Unit.COUNT),
    ("f10_truncated_samples", "truncated_sample_count", Unit.COUNT),
    ("f10_qualified_samples", "qualified_sample_count", Unit.COUNT),
    ("f10_duration_quantile_s", "duration_quantile", Unit.S),
    ("f10_episode_quantile_v2_s", "episode_v2_s_quantile", Unit.V2_S),
)
_EPISODE_ENTRIES: Final = (
    ("f10_episode_sigma", "episode_threshold", Unit.RATIO),
    ("f10_episode_phase_bin", "episode_phase_bin", Unit.COUNT),
    ("f10_episode_start_time_s", "episode_start_time", Unit.S),
    ("f10_episode_duration_s", "episode_duration", Unit.S),
    ("f10_episode_v2_s", "episode_v2_s", Unit.V2_S),
)


def published(
    result: F10Result, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Оси, ячейки и хранимые эпизоды; частичность объявляется маской на ссылку."""
    cell, quantile = _shapes(result)
    arrays: dict[str, np.ndarray] = {QUANTILE_MASK: _domain(result, quantile)}
    refs: list[ArrayReference] = []
    columns = _columns(result, cell, quantile)
    for array_id, role, unit in _ENTRIES:
        values = columns[array_id]
        # Домен квантилей публикуется всегда, остальные маски — только в частичности.
        if array_id in _QUANTILE_IDS:
            mask_id: str | None = QUANTILE_MASK
        else:
            mask_id = f"{array_id}_valid" if partial else None
        _store(arrays, refs, (array_id, role, unit), values, mask_id)
    _episodes(result, arrays, refs, partial=partial)
    return arrays, refs


def _store(
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
    entry: Entry,
    values: np.ndarray,
    mask_id: str | None,
) -> None:
    """Положить массив, его маску и ссылку в бандл, проверив имя на единицу."""
    array_id, role, unit = entry
    validate_unit_name(array_id, unit)
    # Маска домена квантилей уже лежит в `arrays`: она настоящая, а не единицы.
    if mask_id is not None and mask_id not in arrays:
        arrays[mask_id] = np.ones(values.shape, dtype=np.uint8)
    arrays[array_id] = values
    refs.append(
        ArrayReference(
            array_id=array_id,
            role=role,
            unit=unit,
            dtype=values.dtype.name,
            shape=tuple(int(size) for size in values.shape),
            validity_mask_id=mask_id,
            offsets_id=None,
        )
    )


def _shapes(result: F10Result) -> tuple[tuple[int, int, int], tuple[int, int, int, int]]:
    """Объявленные формы ячеек и квантилей из четырёх векторов осей."""
    thresholds = _axis(result.threshold_sigma).size
    durations = _axis(result.minimum_duration_s).size
    levels = _axis(result.quantiles).size
    bins = _axis(result.qualified_samples, integer=True).size
    return (thresholds, durations, bins), (thresholds, durations, bins, levels)


def _domain(result: F10Result, quantile: tuple[int, int, int, int]) -> np.ndarray:
    """Домен квантилей uint8 формы квантильного массива.

    Кодек требует `mask.shape == array.shape`, поэтому маска ячейки расширяется
    на ось уровня. Расширение не выдумывает значений: уровень квантиля определён
    там же, где определён сам квантиль ячейки.
    """
    valid = np.asarray(result.quantile_valid, dtype=np.bool_)
    if valid.shape != quantile[:3]:
        raise CharacterizationError("status_invariant", "f10 quantile domain must match the cells")
    return np.broadcast_to(valid.astype(np.uint8)[..., None], quantile).copy()


def _columns(
    result: F10Result, cell: tuple[int, int, int], quantile: tuple[int, int, int, int]
) -> dict[str, np.ndarray]:
    """Оси и ячейки объявленной формы; чужая форма — отказ, а не молчаливое уплощение."""
    qualified = _axis(result.qualified_samples, integer=True)
    return {
        "f10_threshold_sigma": _axis(result.threshold_sigma),
        "f10_minimum_duration_s": _axis(result.minimum_duration_s),
        "f10_quantile_level": _axis(result.quantiles),
        # Ось бинов это объявленная координата `0..phase_bins-1` (F10-1), а не
        # измеренная величина: потребитель привязывается к значению оси.
        "f10_phase_bin": np.arange(qualified.size, dtype=np.int64),
        "f10_qualified_samples": qualified,
        "f10_occupancy": _cell(result.occupancy, cell),
        "f10_episode_count": _cell(result.episode_count, cell, integer=True),
        "f10_total_v2_s": _cell(result.total_v2_s, cell),
        "f10_retained_samples": _cell(result.retained_samples, cell, integer=True),
        "f10_truncated_samples": _cell(result.truncated_samples, cell, integer=True),
        "f10_duration_quantile_s": _cell(result.duration_quantile_s, quantile),
        "f10_episode_quantile_v2_s": _cell(result.episode_quantile_v2_s, quantile),
    }


def _axis(raw: np.ndarray, *, integer: bool = False) -> np.ndarray:
    """Один непустой вектор оси в объявленном dtype."""
    values = np.asarray(raw, dtype=np.int64 if integer else np.float64)
    if values.ndim != 1 or values.size == 0:
        raise CharacterizationError("status_invariant", "f10 axes must be nonempty vectors")
    return values


def _cell(raw: np.ndarray, expected: tuple[int, ...], *, integer: bool = False) -> np.ndarray:
    """Один массив ячеек объявленной формы: ось не теряется и не добавляется."""
    values = np.asarray(raw, dtype=np.int64 if integer else np.float64)
    if values.shape != expected:
        raise CharacterizationError("status_invariant", "f10 cells must keep the declared shape")
    return values


def _episodes(
    result: F10Result,
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
    *,
    partial: bool,
) -> None:
    """Хранимые эпизоды выровненными массивами: строк-заглушек для отсутствующих нет.

    Эпизоды публикуются, а не опускаются: пять массивов по 4096 записей это
    163840 байт, что на два порядка ниже `MAX_ARRAYS_BYTES` кодека и предела
    `recipe.resource_limits.max_artifact_bytes` (67108864). Опущенные капом
    эпизоды не додумываются — их число видно в сводках маппера.
    """
    stored = result.episodes
    if len(stored) != int(result.stored_count):
        raise CharacterizationError("status_invariant", "f10 stored episodes must match counter")
    columns = {
        "f10_episode_sigma": np.asarray([item.sigma for item in stored], dtype=np.float64),
        "f10_episode_phase_bin": np.asarray([item.phase_bin for item in stored], dtype=np.int64),
        "f10_episode_start_time_s": np.asarray(
            [item.start_time_s for item in stored], dtype=np.float64
        ),
        "f10_episode_duration_s": np.asarray(
            [item.duration_s for item in stored], dtype=np.float64
        ),
        "f10_episode_v2_s": np.asarray([item.v2_s for item in stored], dtype=np.float64),
    }
    for array_id, role, unit in _EPISODE_ENTRIES:
        mask_id = f"{array_id}_valid" if partial else None
        _store(arrays, refs, (array_id, role, unit), columns[array_id], mask_id)
