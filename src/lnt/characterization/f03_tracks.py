"""Сборка треков F03: медианы, счётчики, капс и статусы (F03-9, F03-13..16)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f03_result import (
    _BELOW_RESOLUTION,
    _LEAKAGE_AMBIGUOUS,
    _PEAK_NOT_OBSERVED,
    _TRACK_TOO_SHORT,
    F03Result,
    _unavailable,
)
from lnt.characterization.records import Status
from lnt.features.tracking import PeakTrack, TrackPointState

type Float64Array = NDArray[np.float64]
type WindowLine = tuple[float, float, float, bool]
type WindowTable = dict[int, list[WindowLine]]

__all__ = ["assemble_tracks"]


def _lookup(table: WindowTable, window_id: str, frequency_hz: float) -> WindowLine:
    """Значения линии по идентификатору окна и частоте точки трека."""
    entries = table.get(int(window_id.rsplit("-", 1)[-1]), [])
    if not entries:
        return (float(frequency_hz), 0.0, 0.0, True)
    return min(entries, key=lambda item: abs(item[0] - float(frequency_hz)))


def _medians(values: Float64Array, window_s: float) -> tuple[float, float, float, float]:
    """Медианы центра, амплитуды, ширины и время жизни трека (F03-9)."""
    return (
        float(np.median(values[:, 0])),
        float(np.median(values[:, 1])),
        float(np.median(values[:, 2])),
        float(values.shape[0]) * float(window_s),
    )


def assemble_tracks(  # noqa: PLR0913 - сборке нужен весь контекст отбора
    tracks: tuple[PeakTrack, ...],
    per_window: list[tuple[int, list[WindowLine]]],
    *,
    total_windows: int,
    window_s: float,
    minimum_lifetime_windows: int,
    maximum_tracks: int,
    below_resolution: bool,
) -> F03Result:
    """Треки в публикации: медианы, счётчики, капс, статусы (F03-9, F03-13..16)."""
    table = dict(per_window)
    kept: list[tuple[Float64Array, int, int, float]] = []
    flags = _Flags()
    for track in tracks:
        outcome = _classify(track, table, int(minimum_lifetime_windows), float(window_s), flags)
        if outcome is not None:
            kept.append(outcome)
    codes = flags.codes(below_resolution=below_resolution)
    if not kept:
        return _empty_outcome(len(tracks), total_windows, codes)
    stored = _select(kept, int(maximum_tracks), float(window_s))
    if not stored:
        return _unavailable(
            tuple(sorted(codes | {_TRACK_TOO_SHORT})), total_windows, len(tracks), len(kept)
        )
    return _publish(
        stored,
        total_windows,
        len(tracks),
        tuple(sorted(codes)),
        status=Status.AVAILABLE if not codes else Status.PARTIAL,
    )


class _Flags:
    """Флаги снятий треков; итоги сворачиваются в коды семейства."""

    gaps: bool
    leakage: bool
    too_short: bool

    def __init__(self) -> None:
        self.gaps = False
        self.leakage = False
        self.too_short = False

    def codes(self, *, below_resolution: bool) -> set[str]:
        """Коды снятий плюс флаг неразрешённой энергии окон."""
        out: set[str] = set()
        if self.gaps:
            out.add(_PEAK_NOT_OBSERVED)
        if self.leakage:
            out.add(_LEAKAGE_AMBIGUOUS)
        if self.too_short:
            out.add(_TRACK_TOO_SHORT)
        if below_resolution:
            out.add(_BELOW_RESOLUTION)
        return out


def _classify(
    track: PeakTrack,
    table: WindowTable,
    minimum_lifetime: int,
    window_s: float,
    flags: _Flags,
) -> tuple[Float64Array, int, int, float] | None:
    """Трек в строку публикации или снятие с флагом причины."""
    values: list[WindowLine] = []
    missing = 0
    for point in track.points:
        if point.state is TrackPointState.OBSERVED and point.frequency_hz is not None:
            values.append(_lookup(table, point.window_id, point.frequency_hz))
        else:
            missing += 1
            flags.gaps = True
    if len(values) < minimum_lifetime:
        flags.too_short = True
        return None
    if any(ambiguous for _, _, _, ambiguous in values):
        flags.leakage = True
        return None
    array = np.asarray(values, dtype=np.float64)
    return (array, len(values), missing, _medians(array, window_s)[0])


def _select(
    kept: list[tuple[Float64Array, int, int, float]], maximum_tracks: int, window_s: float
) -> list[tuple[float, float, float, float, int, int]]:
    """Детерминированный отбор капа: дольше живущие, тай-брейк по центру (F03-14)."""
    rows = [(*_medians(vals, window_s), n, m) for vals, n, m, _ in kept]
    ordered = sorted(rows, key=lambda item: (-item[4], item[0]))
    cap = max(int(maximum_tracks), 0)
    return list(ordered[:cap]) if cap else []


def _publish(
    stored: list[tuple[float, float, float, float, int, int]],
    total_windows: int,
    candidates: int,
    codes: tuple[str, ...],
    *,
    status: Status,
) -> F03Result:
    """Опубликованные треки в порядке центров; учёт по образцу F02 (F03-15)."""
    centers_out = np.asarray([item[0] for item in stored], dtype=np.float64)
    order = np.argsort(centers_out, kind="stable")
    final = [stored[i] for i in order]
    return F03Result(
        status=status,
        reason_codes=codes,
        f_hz=np.asarray([item[0] for item in final], dtype=np.float64),
        a_v=np.asarray([item[1] for item in final], dtype=np.float64),
        df_hz=np.asarray([item[2] for item in final], dtype=np.float64),
        t_life_s=np.asarray([item[3] for item in final], dtype=np.float64),
        windows_observed=np.asarray([item[4] for item in final], dtype=np.int64),
        windows_missing=np.asarray([item[5] for item in final], dtype=np.int64),
        evaluated_window_count=int(total_windows),
        candidate_track_count=int(candidates),
        omitted_track_count=int(candidates - len(stored)),
        sample_count=int(candidates),
        observation_count=len(stored),
        missing_count=int(candidates - len(stored) + sum(item[5] for item in stored)),
        stored_count=len(stored),
    )


def _empty_outcome(candidates: int, total_windows: int, codes: set[str]) -> F03Result:
    """Отказ без опубликованных треков: самый честный код первым (F03-10..13)."""
    if _BELOW_RESOLUTION in codes and codes == {_BELOW_RESOLUTION}:
        return _unavailable((_BELOW_RESOLUTION,), total_windows, candidates, 0)
    if not candidates:
        return _unavailable((_PEAK_NOT_OBSERVED,), total_windows, 0, 0)
    if codes == {_TRACK_TOO_SHORT}:
        return _unavailable((_TRACK_TOO_SHORT,), total_windows, candidates, 0)
    ordered = sorted(codes) or [_PEAK_NOT_OBSERVED]
    return _unavailable(tuple(ordered), total_windows, candidates, 0)
