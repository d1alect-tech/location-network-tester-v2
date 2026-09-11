"""Sparse phase records and crossing accumulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.cycles import rising_zero_crossings

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_settings import PhaseSettings
    from lnt.characterization.local_transform import TransformChunk
    from lnt.characterization.records import Status

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True, kw_only=True)
class PhaseCycles:
    """Sparse successive measured cycle boundaries and their qualification."""

    sample_rate_hz: float
    sample_count: int
    cycle_start_samples: Float64Array
    cycle_end_samples: Float64Array
    cycle_valid: BoolArray
    status: Status
    reason_code: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PhaseMeans:
    """Bounded phase-bin means in saved channel volts."""

    means_v: Float64Array
    counts: Int64Array
    valid_bins: BoolArray
    status: Status
    reason_code: str | None


class PhaseBudgetExceededError(Exception):
    """Raised internally when sparse phase retention reaches its byte budget."""


@dataclass(slots=True)
class CycleBuilder:
    """Accumulate sparse cycles while preserving qualified span boundaries."""

    rate: float
    settings: PhaseSettings
    maximum: int
    starts: list[float] = field(default_factory=list)
    ends: list[float] = field(default_factory=list)
    validity: list[bool] = field(default_factory=list)
    last_value: float | None = None
    last_index: int | None = None
    last_crossing: float | None = None
    crossing_count: int = 0
    support_broken: bool = False

    def break_support(self, *, qualified_gap: bool = True) -> None:
        """Clear adjacency at a supported or expected boundary."""
        self.support_broken |= qualified_gap
        self.last_value = self.last_crossing = None
        self.last_index = None

    def append(self, positions: Float64Array) -> None:
        """Append successive crossing positions under the retention budget."""
        for position in positions:
            current = float(position)
            self.crossing_count += 1
            if self.last_crossing is not None:
                if len(self.starts) >= self.maximum:
                    raise PhaseBudgetExceededError
                frequency = self.rate / (current - self.last_crossing)
                self.starts.append(self.last_crossing)
                self.ends.append(current)
                self.validity.append(
                    self.settings.grid_frequency_low_hz
                    <= frequency
                    <= self.settings.grid_frequency_high_hz
                )
            self.last_crossing = current

    def consume(self, chunk: TransformChunk) -> None:
        """Consume one real qualified transform core or separate a gap."""
        values = chunk.values
        if values is None or np.iscomplexobj(values):
            self.break_support(qualified_gap=chunk.reason_code != "filter_support_too_short")
            return
        real_values = np.asarray(values, dtype=np.float64)
        if real_values.ndim != 1 or real_values.size != chunk.stop_sample - chunk.start_sample:
            raise ValueError("local transform returned inconsistent phase core")
        finite = np.isfinite(real_values)
        boundaries = np.flatnonzero(np.diff(np.r_[False, finite, False]))
        for run_start, run_stop in boundaries.reshape(-1, 2):
            self._consume_run(chunk.start_sample, real_values, int(run_start), int(run_stop))
        if not np.any(finite):
            self.break_support()

    def _consume_run(
        self, chunk_start: int, values: Float64Array, run_start: int, run_stop: int
    ) -> None:
        global_start = chunk_start + run_start
        contiguous = self.last_index is not None and global_start == self.last_index + 1
        if not contiguous:
            self.last_crossing = None
        run = values[run_start:run_stop]
        if contiguous and self.last_value is not None:
            pair = np.array([self.last_value, float(run[0])], dtype=np.float64)
            self.append(rising_zero_crossings(pair) + global_start - 1)
        self.append(rising_zero_crossings(run) + global_start)
        self.last_value = float(run[-1])
        self.last_index = chunk_start + run_stop - 1
        if run_stop < values.size:
            self.break_support()


def phase_bins_impl(
    phase: PhaseCycles, start_sample: int, stop_sample: int, bin_count: int
) -> tuple[Int64Array, BoolArray]:
    """Calculate one requested phase-bin slice from sparse boundaries."""
    if start_sample < 0 or stop_sample < start_sample or stop_sample > phase.sample_count:
        raise ValueError("phase slice is outside the sample record")
    if bin_count <= 0:
        raise ValueError("phase bin count must be positive")
    positions = np.arange(start_sample, stop_sample, dtype=np.int64)
    indices = np.zeros(positions.size, dtype=np.int64)
    valid = np.zeros(positions.size, dtype=np.bool_)
    if positions.size == 0 or phase.cycle_start_samples.size == 0:
        return indices, valid
    cycles = np.searchsorted(phase.cycle_start_samples, positions, side="right") - 1
    safe_cycles = np.maximum(cycles, 0)
    present = cycles >= 0
    present &= phase.cycle_valid[safe_cycles]
    present &= positions < phase.cycle_end_samples[safe_cycles]
    if np.any(present):
        selected = safe_cycles[present]
        fractions = (positions[present] - phase.cycle_start_samples[selected]) / (
            phase.cycle_end_samples[selected] - phase.cycle_start_samples[selected]
        )
        indices[present] = np.floor(fractions * bin_count).astype(np.int64)
        valid[present] = True
    return indices, valid
