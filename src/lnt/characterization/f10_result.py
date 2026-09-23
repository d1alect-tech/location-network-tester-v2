"""F10 phase_residual_threshold_duration_v2s_surface: результат, коды и форма поверхности."""

# Модуль владеет опубликованной формой семейства: замороженным результатом,
# объявленными осями, накопителями ячеек и правилом закрытия прогона. Математика
# потокового обхода записи живёт в ``f10_threshold_surface``.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Sequence

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]
type Members = dict[tuple[int, int, int], list[tuple[float, float]]]

METHOD: Final = "phase_residual_threshold_duration_v2s_surface"
MAD_SCALE: Final = "mad_times_1.4826"
MAD_FACTOR: Final = 1.4826
OCCUPANCY_ONLY_TRUNCATED: Final = "occupancy_only_truncated"
MINIMUM_SAMPLES_PER_BIN: Final = 20
MINIMUM_SAMPLES_AT_SHORTEST_DURATION: Final = 2

PHASE_REFERENCE_UNAVAILABLE: Final = "phase_reference_unavailable"
INSUFFICIENT_PHASE_SUPPORT: Final = "insufficient_phase_support"
SCALE_ZERO: Final = "scale_zero"
DURATION_BELOW_SAMPLE_RESOLUTION: Final = "duration_below_sample_resolution"
CLIPPED: Final = "clipped"
ARTIFACT_LIMIT: Final = "artifact_limit"

DECLARED_CODES: Final = (
    PHASE_REFERENCE_UNAVAILABLE,
    INSUFFICIENT_PHASE_SUPPORT,
    SCALE_ZERO,
    DURATION_BELOW_SAMPLE_RESOLUTION,
    CLIPPED,
    ARTIFACT_LIMIT,
)

# Граница притязаний спеки `method-notes-families-10-18.md:73-74`, по смыслу
# дословно: поверхность описывает превышение порога в ОДНОЙ измеренной плоскости
# канала. Она не измеряет энергию, повреждение, источник и полезность.
CLAIM_BOUNDARY: Final = (
    "the surface describes threshold exceedance at one measured channel plane; "
    "it does not measure energy, damage, source identity, or utility"
)

# `_unavailable` объявлен публичным через `__all__`, потому что его импортирует
# движок `f10_threshold_surface` (прецедент F03/F07): без этого basedpyright
# считает приватное имя использованным вне модуля, а саму функцию — неиспользованной.
__all__ = ["_unavailable"]


@dataclass(frozen=True, slots=True, kw_only=True)
class F10Axes:
    """Объявленные оси поверхности: пороги, минимальные длительности и квантили."""

    sigmas: Float64Array
    durations: Float64Array
    quantiles: Float64Array


def declared_axes(
    threshold_sigma: Sequence[float],
    minimum_duration_s: Sequence[float],
    quantiles: Sequence[float],
) -> F10Axes:
    """Объявленные оси рецепта: непустые, конечные, внутри своих доменов."""
    return F10Axes(
        sigmas=_checked(threshold_sigma, "threshold_sigma", 0.0),
        durations=_checked(minimum_duration_s, "minimum_duration_s", 0.0, closed=True),
        quantiles=_checked(quantiles, "quantiles", 0.0, high=1.0),
    )


def _checked(
    values: Sequence[float],
    name: str,
    low: float,
    *,
    high: float | None = None,
    closed: bool = False,
) -> Float64Array:
    result = np.asarray(tuple(float(value) for value in values), dtype=np.float64)
    if result.size == 0:
        raise ValueError(f"{name} must be a nonempty list")
    bad = ~np.isfinite(result) | ((result < low) if closed else (result <= low))
    if high is not None:
        bad |= result >= high
    if bool(np.any(bad)):
        raise ValueError(f"{name} holds a value outside its declared domain")
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class F10Episode:
    """Один хранимый полный эпизод: порог, бин начала, время, длительность, V²s."""

    sigma: float
    phase_bin: int
    start_time_s: float
    duration_s: float
    v2_s: float


@dataclass(slots=True)
class F10Run:
    """Закрываемый прогон выше порога: длина, сумма квадратов, старт, бин и соседи."""

    count: int
    sum_sq: float
    start_sample: int
    phase_bin: int
    left_qualified: bool
    per_bin: Int64Array


@dataclass(frozen=True, slots=True, kw_only=True)
class F10Result:
    """Поверхность порог × минимальная длительность × бин фазы по остатку фазы.

    Ячейки адресуются объявленными осями: ``(порог, длительность, бин)`` в порядке
    C, значения осей публикуются массивами. Усечённые прогоны входят только в
    occupancy и ``truncated_samples``, полные — ещё и в счётчики, ``total_v2_s`` и
    квантили, а ``quantile_valid`` объявляет, где квантиль определён, вместо
    выдачи нуля за измерение.
    """

    status: Status
    reason_codes: tuple[str, ...]
    threshold_sigma: Float64Array
    minimum_duration_s: Float64Array
    quantiles: Float64Array
    occupancy: Float64Array
    episode_count: Int64Array
    total_v2_s: Float64Array
    retained_samples: Int64Array
    truncated_samples: Int64Array
    qualified_samples: Int64Array
    qualified_cycles: int
    duration_quantile_s: Float64Array
    episode_quantile_v2_s: Float64Array
    quantile_valid: BoolArray
    episodes: tuple[F10Episode, ...]
    sample_count: int
    observation_count: int
    missing_count: int
    episode_total: int
    truncated_episode_total: int
    stored_count: int
    omitted_count: int


def _unavailable(
    codes: tuple[str, ...], *, axes: F10Axes, qualified_samples: Int64Array | None,
    sample_count: int, observation_count: int,
) -> F10Result:  # fmt: skip
    empty_float = np.empty(0, dtype=np.float64)
    empty_int = np.empty(0, dtype=np.int64)
    return F10Result(
        status=Status.UNAVAILABLE, reason_codes=codes, threshold_sigma=axes.sigmas,
        minimum_duration_s=axes.durations, quantiles=axes.quantiles, occupancy=empty_float,
        episode_count=empty_int, total_v2_s=empty_float, retained_samples=empty_int,
        truncated_samples=empty_int, duration_quantile_s=empty_float,
        quantile_valid=np.empty(0, dtype=np.bool_),
        episode_quantile_v2_s=empty_float, episodes=(), qualified_cycles=0, episode_total=0,
        qualified_samples=empty_int if qualified_samples is None else qualified_samples,
        sample_count=sample_count, observation_count=observation_count,
        missing_count=sample_count - observation_count, truncated_episode_total=0,
        stored_count=0, omitted_count=0,
    )  # fmt: skip


@dataclass(slots=True)
class F10Surface:
    """Контекст и накопители поверхности: объявленная геометрия, ячейки и эпизоды.

    Один объект владеет и нормированным контекстом обхода (частота, длина,
    чанк, квалификаторы), и накопленными ячейками: иначе геометрия дублировалась
    бы в отдельном контекстном датаклассе и могла бы разъехаться.
    """

    axes: F10Axes
    rate: float
    size: int
    maximum: int
    member_limit: int
    chunk: int
    mask: BoolArray | None
    rails: tuple[float, float] | None
    bins: int
    qualified: Int64Array = field(init=False)
    retained: Int64Array = field(init=False)
    truncated: Int64Array = field(init=False)
    counts: Int64Array = field(init=False)
    total_v2: Float64Array = field(init=False)
    members: Members = field(init=False, default_factory=dict)
    episodes: list[F10Episode] = field(init=False, default_factory=list)
    episode_total: int = 0
    truncated_total: int = 0
    member_total: int = 0
    omitted: int = 0
    clipped: bool = False
    artifact: bool = False

    def __post_init__(self) -> None:
        """Завести поддержку и ячейки объявленной формы ``(порог, длительность, бин)``."""
        self.qualified = np.zeros(self.bins, dtype=np.int64)
        shape = (self.axes.sigmas.size, self.axes.durations.size, self.bins)
        self.retained = np.zeros(shape, dtype=np.int64)
        self.truncated = np.zeros(shape, dtype=np.int64)
        self.counts = np.zeros(shape, dtype=np.int64)
        self.total_v2 = np.zeros(shape, dtype=np.float64)

    def settle(self, index: int, run: F10Run, *, right_qualified: bool) -> None:
        """Закрыть прогон: усечение по краю или пропуску, иначе полный эпизод.

        Усечённый прогон остаётся только в occupancy и ``truncated_samples``: он
        исключён из счётчиков, ``v2_s`` и квантилей — это и есть смысл залоченного
        ``edge_episode_handling="occupancy_only_truncated"``.
        """
        reach = run.start_sample + run.count
        edge = run.start_sample == 0 or reach == self.size
        truncated = not run.left_qualified or not right_qualified or edge
        duration = run.count / self.rate
        energy = run.sum_sq / self.rate
        for cell, minimum in enumerate(self.axes.durations):
            if duration < float(minimum):
                continue
            target = self.truncated if truncated else self.retained
            target[index, cell] += run.per_bin
            if truncated:
                continue
            self.counts[index, cell, run.phase_bin] += 1
            self.total_v2[index, cell, run.phase_bin] += energy
            self.remember((index, cell, run.phase_bin), (duration, energy))
        if truncated:
            self.truncated_total += 1
            return
        self.episode_total += 1
        if len(self.episodes) < self.maximum:
            self.episodes.append(F10Episode(
                sigma=float(self.axes.sigmas[index]), phase_bin=run.phase_bin,
                start_time_s=run.start_sample / self.rate, duration_s=duration, v2_s=energy,
            ))  # fmt: skip
            return
        # Отброшенный хранимый эпизод — ровно объявленный предел артефакта: ячейки
        # остаются полными, а факт усечения хранения публикуется кодом.
        self.artifact = True
        self.omitted += 1

    def remember(self, cell: tuple[int, int, int], member: tuple[float, float]) -> None:
        """Запомнить члены квантилей ячейки детерминированно, в пределах бюджета."""
        if self.member_total >= self.member_limit:
            self.artifact = True
            return
        self.members.setdefault(cell, []).append(member)
        self.member_total += 1

    def publish(self, observation: int) -> F10Result:
        """Собрать результат: occupancy, счётчики, суммы и квантили с маской."""
        axes = self.axes
        shape = self.counts.shape
        durations = np.zeros((*shape, axes.quantiles.size), dtype=np.float64)
        energies = np.zeros((*shape, axes.quantiles.size), dtype=np.float64)
        definite = np.zeros(shape, dtype=np.bool_)
        for (index, cell, phase_bin), members in self.members.items():
            definite[index, cell, phase_bin] = True
            pair = np.asarray(members, dtype=np.float64)
            durations[index, cell, phase_bin, :] = np.quantile(pair[:, 0], axes.quantiles)
            energies[index, cell, phase_bin, :] = np.quantile(pair[:, 1], axes.quantiles)
        safe = np.where(self.qualified > 0, self.qualified, 1)
        codes = tuple(
            code for code, hit in ((CLIPPED, self.clipped), (ARTIFACT_LIMIT, self.artifact)) if hit
        )
        return F10Result(
            status=Status.PARTIAL if codes else Status.AVAILABLE, reason_codes=codes,
            threshold_sigma=axes.sigmas, minimum_duration_s=axes.durations,
            quantiles=axes.quantiles, episode_count=self.counts, total_v2_s=self.total_v2,
            occupancy=(self.retained + self.truncated) / safe[None, None, :],
            retained_samples=self.retained, truncated_samples=self.truncated,
            qualified_samples=self.qualified, duration_quantile_s=durations,
            episode_quantile_v2_s=energies, quantile_valid=definite,
            qualified_cycles=int(np.min(self.qualified)) if self.qualified.size else 0,
            episodes=tuple(self.episodes), sample_count=self.size,
            observation_count=observation, missing_count=self.size - observation,
            episode_total=self.episode_total, truncated_episode_total=self.truncated_total,
            stored_count=len(self.episodes), omitted_count=self.omitted,
        )  # fmt: skip
