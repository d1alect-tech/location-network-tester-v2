"""F10 phase_residual_threshold_duration_v2s_surface: потоковый обход записи."""

# Поверхность считается по остатку измеренного канала после удаления 64-бинного
# фазового среднего; масштаб `1.4826 * median(abs(r - median(r)))`. Ячейка
# удерживает прогон `abs(r) >= sigma * scale`, если длительность не меньше
# минимума ячейки. Усечённые прогоны остаются только в occupancy и усечённой
# поддержке, полные — ещё и в счётчиках, суммарном `v2_s` и квантилях.
# Границы спеки `method-notes-families-10-18.md:62-64`: один потоковый проход на
# порог, время `O(4N)`, память `O(chunk_samples)`, хранится не более 4096 эпизодов.

from __future__ import annotations

import math
from functools import partial
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.f10_result import (
    DURATION_BELOW_SAMPLE_RESOLUTION,
    INSUFFICIENT_PHASE_SUPPORT,
    MAD_FACTOR,
    MAD_SCALE,
    MINIMUM_SAMPLES_AT_SHORTEST_DURATION,
    MINIMUM_SAMPLES_PER_BIN,
    OCCUPANCY_ONLY_TRUNCATED,
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_ZERO,
    F10Result,
    F10Run,
    F10Surface,
    _unavailable,
    declared_axes,
)
from lnt.characterization.phase_model import phase_bins_impl
from lnt.characterization.phase_stats import phase_residual_impl
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from numpy.typing import NDArray

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.clipping import ClippingBounds
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]
type Cut = tuple[int, Float64Array, BoolArray, Int64Array, int]
_GRID_BINS: Final = 1 << 20
_MEMBER_LIMIT: Final = 4096
_SAMPLE_BYTES: Final = 64


def compute_f10_threshold_surface(  # noqa: C901, PLR0913 - объявленные гейты рецепта
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    *,
    sample_rate_hz: float,
    phase_bins: int,
    scale: str,
    threshold_sigma: Sequence[float],
    minimum_duration_s: Sequence[float],
    quantiles: Sequence[float],
    edge_episode_handling: str,
    maximum_episodes: int,
    resources: ResourceLimits,
    clipping: ClippingBounds | None = None,
    gap_mask: BoolArray | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> F10Result:
    """Посчитать поверхность порог × минимальная длительность × бин фазы."""
    # ``phase`` — квалифицированный корень циклов CH2, ``means`` — его фазовые
    # средние: корень фазы не пересчитывается (форма входа F05). ``gap_mask`` —
    # явная маска внешних пропусков (``True`` = исключить); фазовые пропуски уже
    # выражены корнем циклов, вторая маска не выдумывается. ``clipping`` даёт
    # позиционированные рельсы АЦП; без них клиппинг не локализуется, и
    # квалификация идёт без исключения клиппинга (пробел F10-15 доказательств).
    rate = float(sample_rate_hz)
    bins = int(phase_bins)
    maximum = int(maximum_episodes)
    if not math.isfinite(rate) or rate <= 0.0:
        raise ValueError("sample rate must be positive and finite")
    if bins <= 0:
        raise ValueError("phase_bins must be positive")
    if maximum <= 0:
        raise ValueError("maximum_episodes must be positive")
    if scale != MAD_SCALE:
        raise ValueError(f"scale must be {MAD_SCALE!r}")
    if edge_episode_handling != OCCUPANCY_ONLY_TRUNCATED:
        raise ValueError(f"edge_episode_handling must be {OCCUPANCY_ONLY_TRUNCATED!r}")
    if int(np.asarray(means.means_v).size) != bins:
        raise ValueError(f"phase mean bin count does not match phase_bins {bins}")
    size = min(int(np.asarray(samples).size), int(phase.sample_count))
    chunk = min(int(resources.chunk_samples), int(resources.max_work_bytes) // _SAMPLE_BYTES)
    if chunk <= 0:
        raise ValueError("resource limits leave no room for one sample chunk")
    surface = F10Surface(
        axes=declared_axes(threshold_sigma, minimum_duration_s, quantiles),
        rate=rate, size=size, maximum=maximum, member_limit=_MEMBER_LIMIT, chunk=chunk,
        mask=_gap_mask(gap_mask, size), rails=_rails(clipping), bins=bins,
    )  # fmt: skip
    if checkpoint is not None:
        checkpoint()
    cuts = partial(_cuts, samples, phase, means, surface, resources)
    if phase.status is Status.UNAVAILABLE:
        return _refused(surface, None, 0, PHASE_REFERENCE_UNAVAILABLE)
    low, high, clipped = _support(cuts, surface, checkpoint)
    observation = int(np.sum(surface.qualified))
    if np.any(surface.qualified < MINIMUM_SAMPLES_PER_BIN):
        return _refused(surface, surface.qualified, observation, INSUFFICIENT_PHASE_SUPPORT)
    estimated = _mad_scale(cuts, low, high, observation, checkpoint)
    if not math.isfinite(estimated) or estimated <= 0.0:
        return _refused(surface, surface.qualified, observation, SCALE_ZERO)
    shortest = min((float(v) for v in surface.axes.durations if v > 0.0), default=None)
    if shortest is not None and math.ceil(shortest * rate) < MINIMUM_SAMPLES_AT_SHORTEST_DURATION:
        return _refused(surface, surface.qualified, observation, DURATION_BELOW_SAMPLE_RESOLUTION)
    _episodes(surface, cuts, estimated, checkpoint)
    surface.clipped = clipped > 0
    return surface.publish(observation)


def _refused(
    surface: F10Surface, qualified: Int64Array | None, observation: int, code: str
) -> F10Result:
    """Отказ с объявленным кодом: пустая поверхность, оси и честная поддержка."""
    return _unavailable(
        (code,), axes=surface.axes, qualified_samples=qualified,
        sample_count=surface.size, observation_count=observation,
    )  # fmt: skip


def _gap_mask(gap_mask: BoolArray | None, size: int) -> BoolArray | None:
    """Объявленная маска внешних пропусков: чужой размер — отказ, а не догадка."""
    if gap_mask is None:
        return None
    mask = np.asarray(gap_mask, dtype=np.bool_)
    if mask.shape != (size,):
        raise ValueError(f"gap_mask shape {mask.shape} does not match the {size}-sample record")
    return mask


def _rails(clipping: ClippingBounds | None) -> tuple[float, float] | None:
    """Позиционированные рельсы АЦП: только они локализуют клиппинг по отсчётам."""
    if clipping is None or clipping.low_v is None or clipping.high_v is None:
        return None
    return float(clipping.low_v), float(clipping.high_v)


def _cuts(
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    surface: F10Surface,
    resources: ResourceLimits,
) -> Iterator[Cut]:
    """Срезы записи: остаток фазового среднего, квалификация, бины и счёт клиппинга."""
    for start in range(0, surface.size, surface.chunk):
        stop = min(surface.size, start + surface.chunk)
        residual, valid = phase_residual_impl(
            samples, phase, means, start, stop, resources=resources
        )
        indices, _ = phase_bins_impl(phase, start, stop, surface.bins)
        clipped = 0
        if surface.rails is not None:
            values = np.asarray(samples[start:stop], dtype=np.float64)
            hit = (values <= surface.rails[0]) | (values >= surface.rails[1])
            clipped = int(np.count_nonzero(hit & valid))
            valid &= ~hit
        if surface.mask is not None:
            valid &= ~surface.mask[start:stop]
        yield start, residual, valid, indices, clipped


def _support(
    cuts: Callable[[], Iterator[Cut]], surface: F10Surface, checkpoint: Callable[[], None] | None
) -> tuple[float, float, int]:
    """Один проход: поддержка по бинам, крайние значения остатка и счёт клиппинга."""
    low, high, clipped = math.inf, -math.inf, 0
    for _, residual, valid, indices, hit in cuts():
        if checkpoint is not None:
            checkpoint()
        surface.qualified += np.bincount(indices[valid], minlength=surface.bins)
        clipped += hit
        if bool(np.any(valid)):
            values = residual[valid]
            low, high = min(low, float(np.min(values))), max(high, float(np.max(values)))
    if not math.isfinite(low) or not math.isfinite(high):
        return 0.0, 0.0, clipped
    return low, high, clipped


def _mad_scale(
    cuts: Callable[[], Iterator[Cut]],
    low: float,
    high: float,
    total: int,
    checkpoint: Callable[[], None] | None,
) -> float:
    """Масштаб `1.4826 * median(abs(r - median(r)))` гистограммными проходами."""
    # Точный `numpy.median` держал бы остаток целиком и нарушил объявленную
    # границу памяти `O(chunk_samples)` (спека:62-64). Оценка берётся по
    # гистограмме фиксированного размера, поэтому её разрешение — ширина бина;
    # замер доли ширины в порогах записан в доказательствах. Медиана — среднее
    # ДВУХ центральных порядковых статистик, как ``numpy``: одна статистика
    # вместо двух уводит медиану на половину уровня при чётном числе отсчётов
    # (измерено на фикстуре с чередующимся знаком).
    if high <= low or total <= 0:
        return 0.0

    def histogram(origin: float, width: float, shift: float, *, absolute: bool) -> Int64Array:
        """Гистограмма квалифицированного остатка на объявленной сетке за один проход."""
        counts = np.zeros(_GRID_BINS, dtype=np.int64)
        top = origin + _GRID_BINS * width
        for _, residual, valid, _, _ in cuts():
            if checkpoint is not None:
                checkpoint()
            values = np.abs(residual - shift) if absolute else residual - shift
            inside = valid & (values >= origin) & (values <= top)
            positions = np.floor((values[inside] - origin) / width).astype(np.int64)
            counts += np.bincount(np.clip(positions, 0, _GRID_BINS - 1), minlength=_GRID_BINS)
        return counts

    def median(counts: Int64Array, origin: float, width: float) -> float:
        """Медиана по накопленной массе гистограммы линейной интерполяцией."""
        cumulative = np.cumsum(counts)
        rank = 0.5 * (total - 1)
        lower = math.floor(rank)
        picked: list[float] = []
        for position in (lower + 1, lower + 2):
            index = min(
                int(np.searchsorted(cumulative, float(position), side="left")), _GRID_BINS - 1
            )
            before = float(cumulative[index - 1]) if index > 0 else 0.0
            share = (position - before) / float(counts[index]) if counts[index] > 0 else 0.0
            picked.append(origin + (index + share) * width)
        return picked[0] if rank == lower else 0.5 * (picked[0] + picked[1])

    width = (high - low) / _GRID_BINS
    centre = median(histogram(low, width, 0.0, absolute=False), low, width)
    reach = max(abs(low - centre), abs(high - centre))
    if reach <= 0.0:
        return 0.0
    mad_width = reach / _GRID_BINS
    return MAD_FACTOR * median(histogram(0.0, mad_width, centre, absolute=True), 0.0, mad_width)


def _episodes(
    surface: F10Surface,
    cuts: Callable[[], Iterator[Cut]],
    scale: float,
    checkpoint: Callable[[], None] | None,
) -> None:
    """Один потоковый проход на каждый объявленный порог (спека:62-64)."""
    for index, sigma in enumerate(surface.axes.sigmas):
        threshold = float(sigma) * scale
        run: F10Run | None = None
        previous_qualified = False
        for start, residual, valid, indices, _ in cuts():
            if checkpoint is not None:
                checkpoint()
            magnitude = np.abs(residual)
            squares = magnitude * magnitude
            # Исключённые отсчёты (клиппинг, пропуск, вне фазы) не образуют
            # прогонов, но делают соседний прогон усечённым.
            above = valid & (magnitude >= threshold)
            size = int(above.size)
            if run is not None and not bool(above[0]):
                surface.settle(index, run, right_qualified=bool(valid[0]))
                run = None
            bounds = np.flatnonzero(np.diff(np.concatenate(([False], above, [False]))))
            for lo, hi in bounds.reshape(-1, 2).tolist():
                if run is not None and lo == 0:
                    run.count += hi - lo
                    run.sum_sq += float(np.sum(squares[lo:hi]))
                    run.per_bin += np.bincount(indices[lo:hi], minlength=run.per_bin.size)
                else:
                    if run is not None:
                        surface.settle(index, run, right_qualified=bool(valid[lo - 1]))
                    run = F10Run(
                        count=hi - lo, sum_sq=float(np.sum(squares[lo:hi])),
                        start_sample=start + lo, phase_bin=int(indices[lo]),
                        left_qualified=bool(valid[lo - 1]) if lo > 0 else previous_qualified,
                        per_bin=np.bincount(indices[lo:hi], minlength=surface.qualified.size),
                    )  # fmt: skip
                if hi < size:
                    surface.settle(index, run, right_qualified=bool(valid[hi]))
                    run = None
            previous_qualified = bool(valid[-1])
        if run is not None:
            surface.settle(index, run, right_qualified=False)
