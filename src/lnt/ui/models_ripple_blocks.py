"""Вложенные измерительные блоки ``ripple.json`` v1: метрики, спектр, полосы.

Лист группы `models_ripple_schema`. Инвариант аудита: доступная ветка несёт
конечные числа и пустые коды причин; недоступная — null-скаляры/пустые ряды и
НЕпустые коды. Ряды спектра выровнены, сетка строго возрастает, плотности
неотрицательны. Значения не фабрикуются.
"""

from __future__ import annotations

from itertools import pairwise

from .models_ripple_primitives import (
    AVAILABILITY,
    CLIP_SCOPES,
    CLIPPING,
    CONTINUITY,
    SETTLING_BASES,
    boolean,
    codes,
    enum,
    fail,
    integer,
    list_of,
    number,
    obj,
    text,
)

_METRIC_NAMES = ("mean_v", "rms_ac_v", "vpp_v")


def validate_metrics(value: object, label: str) -> None:
    """Тайм-домен и метрики интервала: доступность против null-инварианта."""
    block = obj(value, label)
    status = enum(block.get("availability"), f"{label}.availability", AVAILABILITY)
    reason_codes = codes(block.get("reason_codes"), f"{label}.reason_codes")
    if status == "unavailable":
        if any(block.get(name) is not None for name in _METRIC_NAMES):
            fail(f"{label}: недоступная ветка несёт числа")
        if not reason_codes:
            fail(f"{label}: недоступная ветка без кодов причин")
        return
    for name in _METRIC_NAMES:
        metric = number(block.get(name), f"{label}.{name}")
        if name != "mean_v" and metric < 0.0:
            fail(f"{label}.{name} должен быть >= 0")
    if reason_codes:
        fail(f"{label}: доступная ветка с кодами причин")


def validate_interval(value: object, label: str) -> None:
    """Один интервал: исходные границы, полнота, позиционный ценз и метрики."""
    block = obj(value, label)
    start = integer(block.get("start_index"), f"{label}.start_index")
    end = integer(block.get("end_index_exclusive"), f"{label}.end_index_exclusive")
    if end <= start:
        fail(f"{label}: пустой интервал")
    if integer(block.get("sample_count"), f"{label}.sample_count") != end - start:
        fail(f"{label}.sample_count не совпадает с границами")
    boolean(block.get("complete"), f"{label}.complete")
    if number(block.get("realized_duration_s"), f"{label}.realized_duration_s") <= 0.0:
        fail(f"{label}.realized_duration_s должен быть > 0")
    for name in ("clip_low_count", "clip_high_count"):
        if block.get(name) is not None:
            integer(block[name], f"{label}.{name}")
    validate_metrics(block, label)


def validate_selection(value: object, label: str) -> None:
    """Исходные границы спана: счётчик обязан совпасть с полуинтервалом."""
    block = obj(value, label)
    start = integer(block.get("sample_start_index"), f"{label}.sample_start_index")
    end = integer(block.get("sample_end_index_exclusive"), f"{label}.sample_end_index_exclusive")
    if end < start:
        fail(f"{label}: конец раньше начала")
    if integer(block.get("sample_count"), f"{label}.sample_count") != end - start:
        fail(f"{label}.sample_count не совпадает с границами")
    if number(block.get("sample_rate_hz"), f"{label}.sample_rate_hz") <= 0.0:
        fail(f"{label}.sample_rate_hz должен быть > 0")
    if number(block.get("realized_duration_s"), f"{label}.realized_duration_s") < 0.0:
        fail(f"{label}.realized_duration_s должен быть >= 0")
    integer(block.get("excluded_prefix_samples"), f"{label}.excluded_prefix_samples")
    integer(
        block.get("settling_prefix_samples_nominal"),
        f"{label}.settling_prefix_samples_nominal",
    )
    enum(block.get("settling_basis"), f"{label}.settling_basis", SETTLING_BASES)
    enum(block.get("continuity_status"), f"{label}.continuity_status", CONTINUITY)
    codes(block.get("continuity_reason_codes"), f"{label}.continuity_reason_codes")


def validate_qc(value: object) -> None:
    """QC-ценз: unknowable остаётся null, нулём не подменяется."""
    block = obj(value, "qc")
    enum(block.get("clipping_assessment"), "qc.clipping_assessment", CLIPPING)
    if block.get("clip_count_scope") is not None:
        enum(block["clip_count_scope"], "qc.clip_count_scope", CLIP_SCOPES)
    for name in ("clip_low_count", "clip_high_count", "dropped_samples"):
        if block.get(name) is not None:
            integer(block[name], f"qc.{name}")
    integer(block.get("nonfinite_count"), "qc.nonfinite_count")
    if block.get("nonfinite_count_scope") != "selected_span":
        fail("qc.nonfinite_count_scope должен быть selected_span")
    integer(block.get("record_nonfinite_count"), "qc.record_nonfinite_count")
    codes(block.get("reason_codes"), "qc.reason_codes")


def validate_spectrum(value: object, label: str) -> None:
    """Спектр: доступен => выровненные возрастающие ряды; иначе пусто и null."""
    block = obj(value, label)
    status = enum(block.get("availability"), f"{label}.availability", AVAILABILITY)
    reason_codes = codes(block.get("reason_codes"), f"{label}.reason_codes")
    validate_settings(block.get("settings"), f"{label}.settings")
    frequency = number_array(block.get("frequency_hz"), f"{label}.frequency_hz")
    psd = number_array(block.get("psd_v2_per_hz"), f"{label}.psd_v2_per_hz")
    asd = number_array(block.get("asd_v_per_sqrt_hz"), f"{label}.asd_v_per_sqrt_hz")
    if not (len(frequency) == len(psd) == len(asd)):
        fail(f"{label}: ряды спектра не выровнены")
    if status == "unavailable":
        if frequency or psd or asd:
            fail(f"{label}: недоступный спектр несёт ряды")
        counts = (block.get("used_sample_count"), block.get("ignored_tail_samples"))
        if any(value is not None for value in counts):
            fail(f"{label}: недоступный спектр несёт счётчики")
        if not reason_codes:
            fail(f"{label}: недоступный спектр без кодов причин")
        return
    if not frequency:
        fail(f"{label}: доступный спектр без бинов")
    if any(current <= previous for previous, current in pairwise(frequency)):
        fail(f"{label}.frequency_hz должен строго возрастать")
    if any(level < 0.0 for level in psd) or any(level < 0.0 for level in asd):
        fail(f"{label}: отрицательные плотности")
    integer(block.get("used_sample_count"), f"{label}.used_sample_count", minimum=1)
    integer(block.get("ignored_tail_samples"), f"{label}.ignored_tail_samples")
    if reason_codes:
        fail(f"{label}: доступный спектр с кодами причин")


def validate_settings(value: object, label: str) -> None:
    """Явные настройки Welch: поля, которые читает панель, проверяются строго."""
    block = obj(value, label)
    if "nperseg" in block:
        integer(block["nperseg"], f"{label}.nperseg", minimum=2)
    if "max_chunk_samples" in block:
        integer(block["max_chunk_samples"], f"{label}.max_chunk_samples")
    if "overlap_fraction" in block:
        overlap = number(block["overlap_fraction"], f"{label}.overlap_fraction")
        if not 0.0 <= overlap <= 1.0:
            fail(f"{label}.overlap_fraction вне [0, 1]")
    if "resolution_hz" in block and number(block["resolution_hz"], f"{label}.resolution_hz") <= 0.0:
        fail(f"{label}.resolution_hz должен быть > 0")
    if "enbw_hz" in block and number(block["enbw_hz"], f"{label}.enbw_hz") <= 0.0:
        fail(f"{label}.enbw_hz должен быть > 0")
    if "segment_count" in block and block["segment_count"] is not None:
        integer(block["segment_count"], f"{label}.segment_count", minimum=1)
    for name in ("window", "detector", "detrend", "scaling"):
        if name in block:
            text(block[name], f"{label}.{name}")


def number_array(value: object, label: str) -> list[float]:
    """Ряд конечных чисел."""
    return [number(item, f"{label}[{index}]") for index, item in enumerate(list_of(value, label))]


def validate_bands(value: object, label: str) -> None:
    """Список хранимых полос: v1 всегда содержит хотя бы одну запрошенную полосу."""
    items = list_of(value, label)
    if not items:
        fail(f"{label} должен содержать хотя бы одну полосу")
    for index, item in enumerate(items):
        validate_band(item, f"{label}[{index}]")


def validate_band(value: object, label: str) -> None:
    """Хранимая полоса: центры внутри запрошенных границ, RMS неотрицателен."""
    block = obj(value, label)
    text(block.get("id"), f"{label}.id")
    low = number(block.get("low_hz"), f"{label}.low_hz")
    high = number(block.get("high_hz"), f"{label}.high_hz")
    if low < 0.0 or high <= low:
        fail(f"{label}: границы полосы нарушены")
    status = enum(block.get("availability"), f"{label}.availability", AVAILABILITY)
    reason_codes = codes(block.get("reason_codes"), f"{label}.reason_codes")
    if status == "unavailable":
        if any(
            block.get(name) is not None
            for name in ("first_center_hz", "last_center_hz", "bin_count", "rms_v")
        ):
            fail(f"{label}: недоступная полоса несёт числа")
        if not reason_codes:
            fail(f"{label}: недоступная полоса без кодов причин")
        return
    first = number(block.get("first_center_hz"), f"{label}.first_center_hz")
    last = number(block.get("last_center_hz"), f"{label}.last_center_hz")
    if first <= 0.0 or last <= 0.0 or first > last or first < low or last > high:
        fail(f"{label}: центры вне полосы")
    integer(block.get("bin_count"), f"{label}.bin_count", minimum=1)
    if number(block.get("rms_v"), f"{label}.rms_v") < 0.0:
        fail(f"{label}.rms_v должен быть >= 0")
    if reason_codes:
        fail(f"{label}: доступная полоса с кодами причин")
