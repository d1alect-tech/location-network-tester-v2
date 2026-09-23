"""Маппинг F04: сетка tau и лаги АКФ разной длины с масками на массив."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f04_periodicity import DECLARED_CODES
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.models import ArrayReference, FamilyResult
from lnt.characterization.records import (
    Band,
    ScalarSummary,
    Status,
    Support,
    Unit,
    Window,
    validate_unit_name,
)

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f04_periodicity import F04Result

F04_ID: Final = "f04_multicycle_periodicity"
F04_INDEX: Final = 3
_F04_UNITS = (Unit.S, Unit.RATIO, Unit.COUNT)
# Сетка tau и лаги АКФ разной длины, поэтому маска своя у каждого массива.
_F04_WINDOW_KIND: Final = "record"
_ENTRIES: tuple[tuple[str, str, Unit], ...] = (
    ("f04_tau_s", "averaging_time", Unit.S),
    ("f04_adev_mains", "mains_allan_deviation", Unit.RATIO),
    ("f04_adev_carrier", "carrier_allan_deviation", Unit.RATIO),
    ("f04_acf_lag_cycles", "autocorrelation_lag", Unit.COUNT),
    ("f04_cycle_acf", "cycle_duration_autocorrelation", Unit.RATIO),
)


def build_f04_family(
    result: F04Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Собрать конверт F04 поверх результата движка без пересчёта математики."""
    if family.id != F04_ID:
        raise CharacterizationError("family_order", "recipe must declare f04 fourth")
    span = float(record_duration_s)
    if result.status is Status.UNAVAILABLE:
        return _unavailable(result, family, band, measured_channel, span)
    codes = _checked_published(result)
    columns = _columns(result)
    arrays, refs = _packed(columns, partial=result.status is Status.PARTIAL)
    spec = _spec(
        family, band, measured_channel=measured_channel, span=span,
        status=result.status, reasons=codes,
    )  # fmt: skip
    envelope = family_envelope(
        spec, _support(result), array_refs=tuple(refs), comparison_summary=_summaries(result)
    )
    return envelope, arrays


def _unavailable(
    result: F04Result,
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    span: float,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Отказ без выдуманных значений: ни массивов, ни сводок, поддержка нулевая."""
    if not result.reason_codes:
        raise CharacterizationError("status_invariant", "unavailable f04 needs reasons")
    spec = _spec(
        family, band, measured_channel=measured_channel, span=span,
        status=Status.UNAVAILABLE, reasons=_checked_codes(result.reason_codes),
    )  # fmt: skip
    return family_envelope(spec, zero_support()), {}


def _checked_published(result: F04Result) -> tuple[str, ...]:
    """Инварианты публикуемого пути: статус, причины и учёт хранения."""
    if result.status is Status.AVAILABLE and result.reason_codes:
        raise CharacterizationError("status_invariant", "available f04 must have no reasons")
    if result.status is Status.PARTIAL and not result.reason_codes:
        raise CharacterizationError("status_invariant", "partial f04 needs reasons")
    if result.status not in (Status.AVAILABLE, Status.PARTIAL):
        raise CharacterizationError("status_invariant", "unknown f04 status")
    if int(result.stored_count) != int(result.observation_count):
        raise CharacterizationError("status_invariant", "f04 stored must equal observed")
    return _checked_codes(result.reason_codes)


def _packed(
    columns: dict[str, np.ndarray], *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Массивы с маской на каждый массив: сетки разной длины маскируются порознь."""
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for array_id, role, unit in _ENTRIES:
        if array_id not in columns:
            continue
        values = columns[array_id]
        validate_unit_name(array_id, unit)
        mask_id = f"{array_id}_valid" if partial else None
        if mask_id is not None:
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
    return arrays, refs


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Отсортированные коды только из объявленного словаря движка."""
    if any(not code or code not in DECLARED_CODES for code in codes):
        raise CharacterizationError("status_invariant", "f04 reasons must use declared codes")
    if len(set(codes)) != len(codes):
        raise CharacterizationError("status_invariant", "f04 reasons must be unique")
    return tuple(sorted(codes))


def _spec(  # noqa: PLR0913 - конверт несёт весь объявленный инвариант семейства
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F04_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F04_UNITS,
        window=Window(
            kind=_F04_WINDOW_KIND, duration_s=span, sample_count=None, overlap_fraction=0.0
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _columns(result: F04Result) -> dict[str, np.ndarray]:
    """Столбцы tau-группы и лаг-группы; группы разной длины, внутри группы строго вровень."""
    mains_raw = result.adev_mains
    carrier_raw = result.adev_carrier
    if mains_raw is None:
        raise CharacterizationError("status_invariant", "published f04 needs mains adev")
    if result.status is Status.AVAILABLE and carrier_raw is None:
        raise CharacterizationError("status_invariant", "available f04 needs carrier adev")
    tau = np.asarray(result.tau_s, dtype=np.float64)
    mains = np.asarray(mains_raw, dtype=np.float64)
    lags = np.asarray(result.acf_lag_cycles, dtype=np.int64)
    acf = np.asarray(result.cycle_acf, dtype=np.float64)
    if tau.ndim != 1 or mains.ndim != 1 or lags.ndim != 1 or acf.ndim != 1:
        raise CharacterizationError("status_invariant", "f04 arrays must stay one dimensional")
    if tau.size == 0 or mains.size == 0 or lags.size == 0 or acf.size == 0:
        raise CharacterizationError("status_invariant", "published f04 needs nonempty grids")
    if tau.shape != mains.shape:
        raise CharacterizationError("status_invariant", "f04 tau grids must stay aligned")
    if lags.shape != acf.shape:
        raise CharacterizationError("status_invariant", "f04 lag grids must stay aligned")
    columns: dict[str, np.ndarray] = {
        "f04_tau_s": tau,
        "f04_adev_mains": mains,
        "f04_acf_lag_cycles": lags,
        "f04_cycle_acf": acf,
    }
    # Массив несущей опускается целиком, а не публикуется нулями.
    if carrier_raw is not None:
        carrier = np.asarray(carrier_raw, dtype=np.float64)
        if carrier.shape != tau.shape:
            raise CharacterizationError("status_invariant", "f04 tau grids must stay aligned")
        columns["f04_adev_carrier"] = carrier
    return columns


def _summaries(result: F04Result) -> tuple[ScalarSummary, ...]:
    """Сводки только при значениях не None: слип всегда, отношение при живой несущей."""
    summaries: list[ScalarSummary] = []
    slip = result.phase_slip_cycles
    ratio = result.carrier_to_mains_ratio
    if slip is not None:
        summaries.append(
            ScalarSummary(
                name="f04_phase_slip_cycles",
                value=float(slip),
                unit=Unit.COUNT,
            )
        )
    if ratio is not None:
        summaries.append(
            ScalarSummary(
                name="f04_carrier_to_mains_ratio",
                value=float(ratio),
                unit=Unit.RATIO,
            )
        )
    return tuple(summaries)


def _support(result: F04Result) -> Support:
    """Учёт поддержки один в один из результата; интервал точный по определению."""
    start_raw = result.start_s
    end_raw = result.end_s
    if start_raw is None or end_raw is None:
        raise CharacterizationError("status_invariant", "published f04 needs support interval")
    start = float(start_raw)
    end = float(end_raw)
    sample = int(result.sample_count)
    observation = int(result.observation_count)
    missing = int(result.missing_count)
    stored = int(result.stored_count)
    if sample != observation + missing or stored != observation:
        raise CharacterizationError("status_invariant", "invalid f04 support counts")
    return Support(
        start_s=start, end_s=end, duration_s=end - start, sample_count=sample,
        observation_count=observation, missing_count=missing,
        stored_count=stored, selection_rule="all"
    )  # fmt: skip
