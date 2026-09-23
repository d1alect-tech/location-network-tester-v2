"""F08 bounded_single_damped_sinusoid_fit RED analytic tests (todo 17)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pytest
from scipy import signal

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.event_models import RootEvent
from lnt.characterization.f08_result import (
    BELOW_SNR,
    CLIPPED,
    DECLARED_CODES,
    METHOD,
    MULTIMODE,
    OVERLAPPING_EVENTS,
    SINGLE_EXPONENTIAL_POOR,
    TOO_FEW_SAMPLES,
    F08Result,
)
from lnt.characterization.f08_transient import (
    LOCKED_BASELINE,
    compute_f08_transient_morphology,
    guard_span_bounds,
    initial_damped_sinusoid_seed,
)
from lnt.characterization.records import Status, Unit, validate_unit_name
from lnt.events.models import Polarity

FS_HZ = 500_000.0
F_D_HZ = 2000.0
TAU_D_S = 0.002
PHI_RAD = 0.3
AMPLITUDE_V = 1.0
SPAN_SAMPLES = 4000
MAX_EVENTS = 4096

RINGING_LOW_HZ = 100.0
RINGING_HIGH_HZ = 100_000.0
DECAY_MIN_SAMPLES = 1
DECAY_MAX_S = 0.1
AMPLITUDE_PEAK_MULTIPLE = 2.0
PHASE_LOW_RAD = -math.pi
PHASE_HIGH_RAD = math.pi
MAX_FUNCTION_EVALUATIONS = 200
MINIMUM_SNR_DB = 10.0
RESIDUAL_FRACTION_MAX = 0.25
MINIMUM_ZERO_CROSSINGS = 2

EXPECTED_CODES = frozenset(
    {
        "clipped",
        "single_exponential_poor",
        "below_snr",
        "too_few_samples",
        "overlapping_events",
        "multimode",
    }
)

# Аналитическая истина спеки:426-427 для A exp(-t/tau) sin(2 pi f t + phi).
ANALYTIC_DELTA = 0.25
ANALYTIC_ZETA = ANALYTIC_DELTA / math.sqrt(4.0 * math.pi**2 + ANALYTIC_DELTA**2)


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=262_144,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4096,
        max_surrogates=19,
        deterministic_seed=6022,
    )


@dataclass(frozen=True, slots=True)
class _Declared:
    """Объявленные гейты рецепта в одном месте; тест переопределяет по одному."""

    sample_rate_hz: float = FS_HZ
    baseline: str = LOCKED_BASELINE
    ringing_frequency_low_hz: float = RINGING_LOW_HZ
    ringing_frequency_high_hz: float = RINGING_HIGH_HZ
    decay_time_minimum_samples: int = DECAY_MIN_SAMPLES
    decay_time_max_s: float = DECAY_MAX_S
    amplitude_maximum_peak_multiple: float = AMPLITUDE_PEAK_MULTIPLE
    phase_low_rad: float = PHASE_LOW_RAD
    phase_high_rad: float = PHASE_HIGH_RAD
    maximum_function_evaluations: int = MAX_FUNCTION_EVALUATIONS
    minimum_snr_db: float = MINIMUM_SNR_DB
    residual_fraction_max: float = RESIDUAL_FRACTION_MAX
    minimum_zero_crossings: int = MINIMUM_ZERO_CROSSINGS
    maximum_events: int = MAX_EVENTS
    resources: ResourceLimits = field(default_factory=_resources)


def _event(
    start_sample: int,
    end_sample: int,
    *,
    snr_ratio: float = 100.0,
    clipped: bool | None = False,
    peak_value_v: float = AMPLITUDE_V,
    ordinal: int = 0,
) -> RootEvent:
    """Одно объявленное корневое событие; детектор не вызывается."""
    peak_sample = (start_sample + end_sample) // 2
    return RootEvent(
        ordinal=ordinal,
        timeline_segment=0,
        start_sample=start_sample,
        end_sample=end_sample,
        peak_sample=peak_sample,
        start_time_s=start_sample / FS_HZ,
        end_time_s=end_sample / FS_HZ,
        peak_time_s=peak_sample / FS_HZ,
        peak_value_v=peak_value_v,
        polarity=Polarity.POSITIVE,
        snr_ratio=snr_ratio,
        excess_v2_s=0.0,
        v2_s=0.0,
        clipped=clipped,
        dominant_band=None,
        dominant_band_reason_code=None,
        boundary=False,
    )


def _damped(
    length: int = SPAN_SAMPLES,
    *,
    amplitude: float = AMPLITUDE_V,
    tau_s: float = TAU_D_S,
    f_hz: float = F_D_HZ,
    phi_rad: float = PHI_RAD,
) -> np.ndarray:
    """Аналитический A exp(-t/tau) sin(2 pi f t + phi) на сетке записи."""
    t = np.arange(length, dtype=np.float64) / FS_HZ
    return amplitude * np.exp(-t / tau_s) * np.sin(2.0 * np.pi * f_hz * t + phi_rad)


def _record(span: np.ndarray, guard: int | None = None) -> tuple[np.ndarray, int, int]:
    """Запись [guard | span | guard]; возвращает запись и границы спана."""
    length = int(span.size)
    width = length if guard is None else int(guard)
    payload = np.zeros(length + 2 * width, dtype=np.float64)
    payload[width : width + length] = span
    return payload, width, width + length - 1


def _run(
    record: np.ndarray,
    events: tuple[RootEvent, ...],
    *,
    declared: _Declared | None = None,
) -> F08Result:
    d = declared or _Declared()
    return compute_f08_transient_morphology(
        record,
        events,
        sample_rate_hz=d.sample_rate_hz,
        baseline=d.baseline,
        ringing_frequency_low_hz=d.ringing_frequency_low_hz,
        ringing_frequency_high_hz=d.ringing_frequency_high_hz,
        decay_time_minimum_samples=d.decay_time_minimum_samples,
        decay_time_max_s=d.decay_time_max_s,
        amplitude_maximum_peak_multiple=d.amplitude_maximum_peak_multiple,
        phase_low_rad=d.phase_low_rad,
        phase_high_rad=d.phase_high_rad,
        maximum_function_evaluations=d.maximum_function_evaluations,
        minimum_snr_db=d.minimum_snr_db,
        residual_fraction_max=d.residual_fraction_max,
        minimum_zero_crossings=d.minimum_zero_crossings,
        maximum_events=d.maximum_events,
        resources=d.resources,
    )


def _single(
    span: np.ndarray,
    *,
    guard: int | None = None,
    event: RootEvent | None = None,
    declared: _Declared | None = None,
) -> F08Result:
    record, start, end = _record(span, guard)
    return _run(
        record,
        (event if event is not None else _event(start, end),),
        declared=declared,
    )


def _assert_no_fitted_values(result: F08Result, index: int = 0) -> None:
    """Отказ формы не публикует ни частоты, ни постоянной, ни декремента."""
    assert result.f_d_hz[index] is None
    assert result.tau_d_s[index] is None
    assert result.zeta[index] is None
    assert result.residual_fraction[index] is None


def _expected_span(record: np.ndarray, start: int, end: int) -> np.ndarray:
    """Независимая проверка правила спеки:396-397 — guard 1 длительность + детренд."""
    length = end - start + 1
    low = max(0, start - length)
    high = min(int(record.size), end + 1 + length)
    window = np.asarray(record[low:high], dtype=np.float64)
    return signal.detrend(window, type="linear")[start - low : end + 1 - low]


def _zero_crossings(values: np.ndarray) -> int:
    """Число смен знака — независимая реализация правила для n_zc."""
    signs = np.signbit(np.asarray(values, dtype=np.float64))
    return int(np.count_nonzero(signs[1:] != signs[:-1]))


def _rise_samples(values: np.ndarray) -> int:
    """Правило 0.1 -> 0.9 от пика, независимо от движка."""
    level = np.abs(np.asarray(values, dtype=np.float64))
    peak = float(np.max(level))
    assert peak > 0.0
    scaled = level / peak
    low = int(np.flatnonzero(scaled >= 0.1)[0])
    high = int(np.flatnonzero(scaled >= 0.9)[0])
    return high - low


def _multi_spans(count: int) -> tuple[np.ndarray, tuple[RootEvent, ...]]:
    """Непересекающиеся спаны с полными guard-окнами внутри общей записи."""
    span = _damped()
    length = int(span.size)
    record = np.zeros(3 * length * count, dtype=np.float64)
    events: list[RootEvent] = []
    for index in range(count):
        start = index * 3 * length + length
        end = start + length - 1
        record[start : end + 1] = span
        events.append(_event(start, end, ordinal=index + 1))
    return record, tuple(events)


def test_method_and_locked_baseline_match_contract() -> None:
    """Метод заморожен контрактом, baseline залочен рецептом."""
    assert METHOD == "bounded_single_damped_sinusoid_fit"
    assert LOCKED_BASELINE == "linear_detrend"


def test_reason_code_vocabulary_is_closed() -> None:
    """Словарь кодов закрыт и публичен, без посторонних значений."""
    assert DECLARED_CODES == (
        CLIPPED,
        SINGLE_EXPONENTIAL_POOR,
        BELOW_SNR,
        TOO_FEW_SAMPLES,
        OVERLAPPING_EVENTS,
        MULTIMODE,
    )
    assert set(DECLARED_CODES) == EXPECTED_CODES


def test_initialization_recovers_frequency_and_decay_from_the_bare_span() -> None:
    """Спека:426-427: пересечения нуля дают f_d=2000.0, декремент — tau=0.002."""
    span = _damped()
    seed = initial_damped_sinusoid_seed(
        span,
        sample_rate_hz=FS_HZ,
        ringing_frequency_low_hz=RINGING_LOW_HZ,
        ringing_frequency_high_hz=RINGING_HIGH_HZ,
        decay_time_minimum_samples=DECAY_MIN_SAMPLES,
        decay_time_max_s=DECAY_MAX_S,
    )
    assert seed.n_zc == 32
    assert seed.f_d_hz == pytest.approx(F_D_HZ, rel=1e-12)
    assert seed.log_decrement == pytest.approx(ANALYTIC_DELTA, rel=1e-9)
    assert seed.tau_d_s == pytest.approx(TAU_D_S, rel=1e-9)


def test_initialization_needs_a_measurable_decrement() -> None:
    """Один импульс не даёт ни затухания, ни частоты: инициализация отказывает."""
    impulse = np.zeros(SPAN_SAMPLES, dtype=np.float64)
    impulse[1000] = 1.0
    seed = initial_damped_sinusoid_seed(
        impulse,
        sample_rate_hz=FS_HZ,
        ringing_frequency_low_hz=RINGING_LOW_HZ,
        ringing_frequency_high_hz=RINGING_HIGH_HZ,
        decay_time_minimum_samples=DECAY_MIN_SAMPLES,
        decay_time_max_s=DECAY_MAX_S,
    )
    assert seed.tau_d_s is None
    assert seed.log_decrement is None


def test_guard_span_bounds_add_one_event_duration_per_side() -> None:
    """Спека:396-397: guard равен одной длительности события с каждой стороны."""
    assert guard_span_bounds(1000, 1999, 10_000) == (0, 3000)
    assert guard_span_bounds(5000, 5999, 10_000) == (4000, 7000)
    # На границе записи guard клиппится, а не выходит за неё.
    assert guard_span_bounds(0, 999, 10_000) == (0, 2000)
    assert guard_span_bounds(9000, 9999, 10_000) == (8000, 10_000)


def test_declared_linear_detrend_is_the_locked_baseline() -> None:
    """F08-3: нелоченный профиль baseline объявлен неподдерживаемым."""
    with pytest.raises(ValueError, match=r"baseline"):
        _single(_damped(), declared=_Declared(baseline="constant_detrend"))


def test_damped_sinusoid_recovers_decay_and_frequency_within_one_percent() -> None:
    """Положительное спеки:424-427 — f_d и tau_d восстанавливаются с запасом к 1 %."""
    span = _damped()
    record, start, end = _record(span)
    expected = _expected_span(record, start, end)
    result = _run(record, (_event(start, end),))
    assert isinstance(result, F08Result)
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.f_d_hz[0] is not None
    assert result.tau_d_s[0] is not None
    # Аналитическая истина, а не число из движка.
    assert result.f_d_hz[0] == pytest.approx(F_D_HZ, rel=0.01)
    assert result.tau_d_s[0] == pytest.approx(TAU_D_S, rel=0.01)
    # Прямые морфологические величины сверяются с объявленными определениями.
    assert result.n_zc[0] == _zero_crossings(expected)
    assert result.n_zc[0] == 32
    assert result.v_peak_v[0] == pytest.approx(float(np.max(np.abs(expected))), rel=1e-12)
    assert result.v2_s[0] is not None
    assert result.v2_s[0] == pytest.approx(float(np.dot(expected, expected) / FS_HZ), rel=1e-12)
    assert result.v2_s[0] == pytest.approx(0.25 * TAU_D_S, rel=0.05)
    assert result.t_rise_s[0] == pytest.approx(_rise_samples(expected) / FS_HZ, rel=1e-12)
    assert result.residual_fraction[0] is not None
    assert result.residual_fraction[0] < RESIDUAL_FRACTION_MAX


def test_published_zeta_matches_the_analytic_damping_ratio() -> None:
    """zeta выводится из пары фита и сверяется с аналитикой delta=0.25."""
    result = _single(_damped())
    assert result.zeta[0] is not None
    assert result.zeta[0] == pytest.approx(ANALYTIC_ZETA, rel=0.01)


def test_fitted_triple_is_internally_consistent() -> None:
    """Публикуемые f_d, tau_d, zeta согласованы формулой спеки:400."""
    result = _single(_damped())
    f_d = result.f_d_hz[0]
    tau_d = result.tau_d_s[0]
    zeta = result.zeta[0]
    assert f_d is not None
    assert tau_d is not None
    assert zeta is not None
    delta = 1.0 / (f_d * tau_d)
    assert zeta == pytest.approx(delta / math.sqrt(4.0 * math.pi**2 + delta**2), rel=1e-12)


def test_undamped_sinusoid_publishes_no_fitted_resonance() -> None:
    """Контроль спеки:428-429: незатухающий звон не даёт подогнанной частоты."""
    index = np.arange(SPAN_SAMPLES, dtype=np.float64)
    plain = np.sin(2.0 * np.pi * F_D_HZ * index / FS_HZ)
    result = _single(plain)
    assert result.status is Status.UNAVAILABLE
    assert SINGLE_EXPONENTIAL_POOR in result.reason_codes
    assert result.n_zc[0] == 32
    assert result.v_peak_v[0] is not None
    _assert_no_fitted_values(result)


def test_short_impulse_without_ringing_is_not_a_resonance() -> None:
    """Контроль спеки:428-429: одиночный импульс — код, а не частота."""
    impulse = np.zeros(SPAN_SAMPLES, dtype=np.float64)
    impulse[1000] = 1.0
    result = _single(impulse)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (SINGLE_EXPONENTIAL_POOR,)
    assert result.n_zc[0] == 2
    assert result.v2_s[0] == pytest.approx(1.0 / FS_HZ, rel=1e-3)
    _assert_no_fitted_values(result)


def test_raised_zero_crossing_floor_refuses_the_impulse() -> None:
    """Объявленный минимум пересечений реально управляет отказом."""
    impulse = np.zeros(SPAN_SAMPLES, dtype=np.float64)
    impulse[1000] = 1.0
    result = _single(impulse, declared=_Declared(minimum_zero_crossings=4))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (TOO_FEW_SAMPLES,)
    _assert_no_fitted_values(result)


def test_monotone_decay_has_too_few_zero_crossings() -> None:
    """Монотонное затухание не имеет ни одного полного колебания."""
    span = np.exp(-np.arange(SPAN_SAMPLES, dtype=np.float64) / 500.0)
    result = _single(span)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (TOO_FEW_SAMPLES,)
    assert result.n_zc[0] == 1


def test_two_superimposed_modes_flag_single_exponential_poor() -> None:
    """Ограничение спеки:430-432: две равные моды поднимают остаток выше 0.25."""
    two = _damped() + _damped(f_hz=6000.0)
    result = _single(two)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (SINGLE_EXPONENTIAL_POOR,)
    _assert_no_fitted_values(result)


def test_resolved_second_mode_is_flagged_multimode() -> None:
    """Спека:404-405: более одной разрешённой моды — multimode."""
    two = _damped() + 0.2 * _damped(f_hz=10_000.0)
    result = _single(two)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (MULTIMODE,)
    _assert_no_fitted_values(result)


def test_mode_rule_boundary_keeps_a_weak_second_mode_out() -> None:
    """Граница правила мод: -16.5 дБ проходит, -14.9 дБ уже multimode."""
    weak = _damped() + 0.15 * _damped(f_hz=10_000.0)
    strong = _damped() + 0.18 * _damped(f_hz=10_000.0)
    accepted = _single(weak)
    refused = _single(strong)
    assert accepted.status is Status.AVAILABLE
    assert accepted.f_d_hz[0] is not None
    assert refused.status is Status.UNAVAILABLE
    assert refused.reason_codes == (MULTIMODE,)


def test_clipped_and_unknown_clipping_both_refuse() -> None:
    """Спека:416: необрезанное событие обязательно; неизвестный клиппинг — не доказательство."""
    record, start, end = _record(_damped())
    clipped = _run(record, (_event(start, end, clipped=True),))
    unknown = _run(record, (_event(start, end, clipped=None),))
    fine = _run(record, (_event(start, end, clipped=False),))
    assert clipped.reason_codes == (CLIPPED,)
    assert unknown.reason_codes == (CLIPPED,)
    assert clipped.status is Status.UNAVAILABLE
    assert unknown.status is Status.UNAVAILABLE
    assert fine.status is Status.AVAILABLE
    _assert_no_fitted_values(clipped)
    _assert_no_fitted_values(unknown)


def test_snr_gate_uses_the_declared_decibel_floor() -> None:
    """Объявленный гейт SNR 10 дБ: 11 дБ проходит, 9 дБ отказывает."""
    record, start, end = _record(_damped())
    below = _run(record, (_event(start, end, snr_ratio=10.0 ** (9.0 / 20.0)),))
    above = _run(record, (_event(start, end, snr_ratio=10.0 ** (11.0 / 20.0)),))
    assert below.status is Status.UNAVAILABLE
    assert below.reason_codes == (BELOW_SNR,)
    assert above.status is Status.AVAILABLE
    _assert_no_fitted_values(below)


def test_zero_snr_ratio_is_below_snr_not_an_exception() -> None:
    """Неположительное отношение — минус бесконечность дБ, а не исключение."""
    record, start, end = _record(_damped())
    result = _run(record, (_event(start, end, snr_ratio=0.0),))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (BELOW_SNR,)


def test_declared_residual_ceiling_refuses_a_fit_the_default_accepts() -> None:
    """Объявленный rho_max управляет приёмом формы."""
    accepted = _single(_damped())
    refused = _single(_damped(), declared=_Declared(residual_fraction_max=0.0))
    assert accepted.status is Status.AVAILABLE
    assert refused.status is Status.UNAVAILABLE
    assert refused.reason_codes == (SINGLE_EXPONENTIAL_POOR,)
    _assert_no_fitted_values(refused)


def test_declared_evaluation_budget_refuses_an_unconverged_fit() -> None:
    """Спека:412: объявленный бюджет 200 реально ограничивает фит."""
    converged = _single(_damped())
    starved = _single(_damped(), declared=_Declared(maximum_function_evaluations=1))
    assert converged.status is Status.AVAILABLE
    assert starved.status is Status.UNAVAILABLE
    assert starved.reason_codes == (SINGLE_EXPONENTIAL_POOR,)


def test_declared_decay_ceiling_refuses_a_tau_the_default_accepts() -> None:
    """Объявленная верхняя граница tau_d управляет результатом."""
    accepted = _single(_damped())
    refused = _single(_damped(), declared=_Declared(decay_time_max_s=1e-4))
    assert accepted.status is Status.AVAILABLE
    assert refused.status is Status.UNAVAILABLE
    assert refused.reason_codes == (SINGLE_EXPONENTIAL_POOR,)


def test_declared_decay_floor_can_exclude_the_true_constant() -> None:
    """Объявленный минимум tau_d в отсчётах исключает истинную постоянную."""
    refused = _single(_damped(), declared=_Declared(decay_time_minimum_samples=2000))
    assert refused.status is Status.UNAVAILABLE
    assert refused.reason_codes == (SINGLE_EXPONENTIAL_POOR,)


def test_declared_phase_bounds_decide_the_fit() -> None:
    """Объявленные границы фазы принимают верное окно и бракуют неверное."""
    tight = _single(_damped(), declared=_Declared(phase_low_rad=0.25, phase_high_rad=0.35))
    wrong = _single(_damped(), declared=_Declared(phase_low_rad=1.0, phase_high_rad=2.0))
    assert tight.status is Status.AVAILABLE
    assert tight.tau_d_s[0] == pytest.approx(TAU_D_S, rel=0.01)
    assert wrong.status is Status.UNAVAILABLE
    assert wrong.reason_codes == (SINGLE_EXPONENTIAL_POOR,)


def test_declared_amplitude_multiple_bounds_the_amplitude() -> None:
    """Спека:411: амплитуда ограничена 2 * v_peak_v."""
    accepted = _single(_damped())
    refused = _single(_damped(), declared=_Declared(amplitude_maximum_peak_multiple=0.5))
    assert accepted.status is Status.AVAILABLE
    assert refused.status is Status.UNAVAILABLE
    assert refused.reason_codes == (SINGLE_EXPONENTIAL_POOR,)


def test_declared_ringing_band_decides_the_fit() -> None:
    """Объявленная полоса звонка 100..100000 содержит 2000 Гц, узкая — нет."""
    accepted = _single(_damped())
    shifted = _single(_damped(), declared=_Declared(ringing_frequency_low_hz=5000.0))
    assert accepted.status is Status.AVAILABLE
    assert shifted.status is Status.UNAVAILABLE
    assert shifted.reason_codes == (SINGLE_EXPONENTIAL_POOR,)


def test_overlapping_events_refuse_the_whole_inventory() -> None:
    """Пересечение объявленных спанов делает guard-окна неоднозначными."""
    record, start, end = _record(_damped())
    first = _event(start, end, ordinal=1)
    second = _event(start + 500, end + 500, ordinal=2)
    result = _run(record, (first, second))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (OVERLAPPING_EVENTS,)
    assert all(value is None for value in result.f_d_hz)


def test_empty_event_inventory_needs_event_samples() -> None:
    """F08-27: пустой инвентарь — нет спана события, значит нет поддержки отсчётов."""
    result = _run(np.zeros(4 * SPAN_SAMPLES, dtype=np.float64), ())
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (TOO_FEW_SAMPLES,)
    assert result.evaluated_event_count == 0
    assert result.omitted_event_count == 0


def test_event_beyond_the_record_is_too_few_samples() -> None:
    """Спан вне записи не даёт поддержки: отказ без исключения."""
    record, _start, _end = _record(_damped())
    result = _run(record, (_event(int(record.size), int(record.size) + 100),))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (TOO_FEW_SAMPLES,)


def test_nonfinite_span_is_too_few_samples_not_a_fabricated_frequency() -> None:
    """Неконечные отсчёты в guard-окне — отказ, а не исключение и не число."""
    span = _damped()
    span[500] = np.nan
    result = _single(span)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (TOO_FEW_SAMPLES,)


def test_mixed_inventory_reports_partial_with_sorted_codes() -> None:
    """Часть событий принята, часть отклонена: PARTIAL с сортированными кодами."""
    record, events = _multi_spans(2)
    low = _event(events[1].start_sample, events[1].end_sample, snr_ratio=1.0, ordinal=2)
    result = _run(record, (events[0], low))
    assert result.status is Status.PARTIAL
    assert result.reason_codes == (BELOW_SNR,)
    assert result.f_d_hz[0] is not None
    assert result.f_d_hz[1] is None
    assert result.evaluated_event_count == 2
    assert result.omitted_event_count == 0


def test_declared_maximum_events_caps_the_evaluated_inventory() -> None:
    """Спека:414: не более 4096 подогнанных событий, хвост учитывается явно."""
    record, events = _multi_spans(3)
    capped = _run(record, events, declared=_Declared(maximum_events=2))
    assert capped.evaluated_event_count == 2
    assert capped.omitted_event_count == 1
    assert len(capped.f_d_hz) == 3
    assert capped.f_d_hz[0] is not None
    assert capped.f_d_hz[2] is None


def test_every_evaluated_event_refusing_returns_unavailable() -> None:
    """Отказ всех оценённых событий — UNAVAILABLE, усечённый хвост остаётся None."""
    record, events = _multi_spans(2)
    low = _event(events[0].start_sample, events[0].end_sample, snr_ratio=1.0, ordinal=1)
    result = _run(record, (low, events[1]), declared=_Declared(maximum_events=1))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (BELOW_SNR,)
    assert result.evaluated_event_count == 1
    assert result.omitted_event_count == 1
    assert all(value is None for value in result.f_d_hz)


def test_clipped_event_keeps_measured_voltage_and_integral() -> None:
    """Отказ формы не прячет измеренные амплитуду, интеграл и пересечения."""
    span = _damped()
    record, start, end = _record(span)
    expected = _expected_span(record, start, end)
    result = _run(record, (_event(start, end, clipped=True),))
    assert result.v_peak_v[0] == pytest.approx(float(np.max(np.abs(expected))), rel=1e-12)
    assert result.v2_s[0] == pytest.approx(float(np.dot(expected, expected) / FS_HZ), rel=1e-12)
    assert result.n_zc[0] == _zero_crossings(expected)
    assert result.t_rise_s[0] == pytest.approx(_rise_samples(expected) / FS_HZ, rel=1e-12)
    _assert_no_fitted_values(result)


def test_runs_are_bitwise_deterministic() -> None:
    """Два прогона побитово идентичны, включая отказ."""
    span = _damped() + 0.2 * _damped(f_hz=10_000.0)
    first = _single(span)
    second = _single(span)
    assert first == second
    assert first.reason_codes == second.reason_codes
    assert first.v2_s == second.v2_s
    assert first.v_peak_v == second.v_peak_v


def test_resources_are_accepted_but_unspent() -> None:
    """Спека:422: сложность O(K L iters); объявленный бюджет ресурсов не тратится."""
    declared = _Declared()
    result = _single(_damped(), declared=declared)
    assert result.status is Status.AVAILABLE
    assert declared.resources.deterministic_seed == 6022


@pytest.mark.parametrize(
    "declared",
    [
        _Declared(sample_rate_hz=float("nan")),
        _Declared(sample_rate_hz=float("inf")),
        _Declared(sample_rate_hz=0.0),
        _Declared(sample_rate_hz=-FS_HZ),
        _Declared(maximum_events=0),
        _Declared(maximum_events=-1),
        _Declared(decay_time_minimum_samples=0),
        _Declared(decay_time_max_s=0.0),
        _Declared(amplitude_maximum_peak_multiple=0.0),
        _Declared(maximum_function_evaluations=0),
        _Declared(ringing_frequency_high_hz=50.0),
        _Declared(phase_low_rad=1.0, phase_high_rad=1.0),
    ],
)
def test_invalid_declarations_raise_valueerror(declared: _Declared) -> None:
    """Невалидные числовые объявления — ValueError, а не выдуманный код."""
    with pytest.raises(ValueError, match=r".+"):
        _single(_damped(), declared=declared)


@pytest.mark.parametrize(
    ("name", "unit"),
    [
        ("t_rise_s", Unit.S),
        ("v_peak_v", Unit.V),
        # Конвенция репозитория требует суффикс `_v2_s` (как `f02_e_res_v2_s`).
        ("f08_v2_s", Unit.V2_S),
        ("n_zc", Unit.COUNT),
        ("f_d_hz", Unit.HZ),
        ("tau_d_s", Unit.S),
        ("zeta", Unit.RATIO),
    ],
)
def test_persisted_scalar_units_are_accepted(name: str, unit: Unit) -> None:
    """Единицы величин принимаются словарём единиц."""
    validate_unit_name(name, unit)
