/** Гварды измерительных блоков ripple.json v1: метрики, интервалы, спектр, полосы.

Лист группы ripple. Инвариант схемы (аудит 2026-10-20): доступная ветка несёт
конечные числа и пустые коды причин; недоступная — null-скаляры, пустые серии и
НЕпустые коды причин. Серии спектра обязаны быть выровнены по длине, сетка —
строго возрастать, плотности — неотрицательны. Значения не фабрикуются.
*/

import {
  isFiniteNumber,
  isFiniteNumberArray,
  isNonnegativeInt,
  isRecord,
  isStringArray,
} from "./guards-ripple-core";
import type {
  RippleBand,
  RippleInterval,
  RippleSpectrum,
  RippleSpectrumSettings,
  RippleTimeDomain,
} from "./types-ripple";

const METRIC_KEYS: readonly string[] = ["mean_v", "rms_ac_v", "vpp_v"];

/** Общий инвариант тайм-домена и метрик интервала: available ⇒ конечные числа
 * (RMS/Vpp неотрицательны, причин нет); unavailable ⇒ null и коды причин. */
export function isMetricBlock(value: unknown): value is RippleTimeDomain {
  if (!isRecord(value)) return false;
  if (value.availability !== "available" && value.availability !== "unavailable") return false;
  if (!isStringArray(value.reason_codes)) return false;
  const available = value.availability === "available";
  for (const key of METRIC_KEYS) {
    const metric = value[key];
    if (available) {
      if (!isFiniteNumber(metric)) return false;
      if (key !== "mean_v" && metric < 0) return false;
    } else if (metric !== null) {
      return false;
    }
  }
  if (available) return value.reason_codes.length === 0;
  return value.reason_codes.length > 0;
}

/** Один интервал: исходные границы, полнота, позиционный ценз и метрики. */
export function isInterval(value: unknown): value is RippleInterval {
  if (!isRecord(value)) return false;
  if (!isNonnegativeInt(value.start_index)) return false;
  if (!isNonnegativeInt(value.end_index_exclusive)) return false;
  if (value.end_index_exclusive <= value.start_index) return false;
  if (
    !isNonnegativeInt(value.sample_count) ||
    value.sample_count !== value.end_index_exclusive - value.start_index
  ) {
    return false;
  }
  if (typeof value.complete !== "boolean") return false;
  if (!(isFiniteNumber(value.realized_duration_s) && value.realized_duration_s > 0)) return false;
  if (value.clip_low_count !== null && !isNonnegativeInt(value.clip_low_count)) return false;
  if (value.clip_high_count !== null && !isNonnegativeInt(value.clip_high_count)) return false;
  return isMetricBlock(value);
}

/** Явные настройки Welch: форма не зависит от доступности спектра, а ветка
 * фона с несостоявшимся сравнением несёт пустой объект настроек. */
export function isSpectrumSettings(value: unknown): value is RippleSpectrumSettings {
  if (!isRecord(value)) return false;
  if (value.nperseg !== undefined && !(isNonnegativeInt(value.nperseg) && value.nperseg >= 2)) {
    return false;
  }
  if (value.max_chunk_samples !== undefined && !isNonnegativeInt(value.max_chunk_samples)) {
    return false;
  }
  if (
    value.overlap_fraction !== undefined &&
    !(isFiniteNumber(value.overlap_fraction) && value.overlap_fraction >= 0)
  ) {
    return false;
  }
  if (value.overlap_fraction !== undefined && value.overlap_fraction > 1) return false;
  if (
    value.resolution_hz !== undefined &&
    !(isFiniteNumber(value.resolution_hz) && value.resolution_hz > 0)
  ) {
    return false;
  }
  if (value.enbw_hz !== undefined && !(isFiniteNumber(value.enbw_hz) && value.enbw_hz > 0)) {
    return false;
  }
  if (
    value.segment_count !== undefined &&
    !(
      value.segment_count === null ||
      (isNonnegativeInt(value.segment_count) && value.segment_count >= 1)
    )
  ) {
    return false;
  }
  if (value.window !== undefined && typeof value.window !== "string") return false;
  if (value.detector !== undefined && typeof value.detector !== "string") return false;
  if (value.detrend !== undefined && typeof value.detrend !== "string") return false;
  if (value.scaling !== undefined && typeof value.scaling !== "string") return false;
  return true;
}

/** Спектр: доступен ⇒ три выровненные конечные серии и счётчики; иначе серии
 * пусты, счётчики null и есть коды причин. Нулевая PSD валидна. */
export function isSpectrum(value: unknown): value is RippleSpectrum {
  if (!isRecord(value)) return false;
  if (value.availability !== "available" && value.availability !== "unavailable") return false;
  if (!isStringArray(value.reason_codes)) return false;
  if (!isSpectrumSettings(value.settings)) return false;
  if (!isFiniteNumberArray(value.frequency_hz)) return false;
  if (!isFiniteNumberArray(value.psd_v2_per_hz)) return false;
  if (!isFiniteNumberArray(value.asd_v_per_sqrt_hz)) return false;
  if (
    value.frequency_hz.length !== value.psd_v2_per_hz.length ||
    value.frequency_hz.length !== value.asd_v_per_sqrt_hz.length
  ) {
    return false;
  }
  if (value.availability === "available") return isAvailableSpectrum(value);
  return isUnavailableSpectrum(value);
}

function isAvailableSpectrum(value: Record<string, unknown>): boolean {
  if (!isFiniteNumberArray(value.frequency_hz)) return false;
  if (!isFiniteNumberArray(value.psd_v2_per_hz)) return false;
  if (!isFiniteNumberArray(value.asd_v_per_sqrt_hz)) return false;
  if (!isStringArray(value.reason_codes)) return false;
  if (value.frequency_hz.length === 0) return false;
  let previous = Number.NEGATIVE_INFINITY;
  for (const frequency of value.frequency_hz) {
    if (frequency <= previous) return false;
    previous = frequency;
  }
  if (value.psd_v2_per_hz.some((level) => level < 0)) return false;
  if (value.asd_v_per_sqrt_hz.some((level) => level < 0)) return false;
  if (!(isNonnegativeInt(value.used_sample_count) && value.used_sample_count >= 1)) return false;
  if (!isNonnegativeInt(value.ignored_tail_samples)) return false;
  return value.reason_codes.length === 0;
}

function isUnavailableSpectrum(value: Record<string, unknown>): boolean {
  if (!isFiniteNumberArray(value.frequency_hz) || value.frequency_hz.length !== 0) return false;
  if (!isFiniteNumberArray(value.psd_v2_per_hz) || value.psd_v2_per_hz.length !== 0) return false;
  if (!isFiniteNumberArray(value.asd_v_per_sqrt_hz) || value.asd_v_per_sqrt_hz.length !== 0) {
    return false;
  }
  if (value.used_sample_count !== null || value.ignored_tail_samples !== null) return false;
  return isStringArray(value.reason_codes) && value.reason_codes.length > 0;
}

/** Хранимая полоса: доступна ⇒ положительные центры внутри запрошенных
 * границ и конечный RMS; недоступна ⇒ null при сохранённых границах. */
export function isBand(value: unknown): value is RippleBand {
  if (!isRecord(value)) return false;
  if (typeof value.id !== "string" || value.id === "") return false;
  if (!(isFiniteNumber(value.low_hz) && value.low_hz >= 0)) return false;
  if (!(isFiniteNumber(value.high_hz) && value.high_hz > value.low_hz)) return false;
  if (value.availability !== "available" && value.availability !== "unavailable") return false;
  if (!isStringArray(value.reason_codes)) return false;
  if (value.availability === "available") return isAvailableBand(value);
  if (
    value.first_center_hz !== null ||
    value.last_center_hz !== null ||
    value.bin_count !== null ||
    value.rms_v !== null
  ) {
    return false;
  }
  return value.reason_codes.length > 0;
}

function isAvailableBand(value: Record<string, unknown>): boolean {
  if (!isFiniteNumber(value.low_hz) || !isFiniteNumber(value.high_hz)) return false;
  if (!isFiniteNumber(value.first_center_hz) || !isFiniteNumber(value.last_center_hz)) {
    return false;
  }
  const low = value.low_hz;
  const high = value.high_hz;
  const first = value.first_center_hz;
  const last = value.last_center_hz;
  if (first <= 0 || last <= 0) return false;
  if (first > last) return false;
  if (first < low || last > high) return false;
  if (!(isNonnegativeInt(value.bin_count) && value.bin_count >= 1)) return false;
  if (!(isFiniteNumber(value.rms_v) && value.rms_v >= 0)) return false;
  return isStringArray(value.reason_codes) && value.reason_codes.length === 0;
}

/** Список хранимых полос: v1 всегда содержит хотя бы одну запрошенную полосу. */
export function isBandList(value: unknown): value is RippleBand[] {
  if (!Array.isArray(value) || value.length === 0) return false;
  return value.every((item) => isBand(item));
}
