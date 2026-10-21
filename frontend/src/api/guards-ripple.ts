/** Корневой runtime-гвард сайдкара ripple.json v1.

Источник формы — `src/lnt/ui/models_ripple.py` (набор ключей v1, канал ch1,
SHA-256 входов) и `src/lnt/analysis_v2/engine_ripple.py` (сборка payload);
гвард зеркалит их один в один и не домысливает полей. Листы группы:
`guards-ripple-core` (идентичности) и `guards-ripple-measurements` (числа).

Сырой JSON не доверяется: числа обязаны быть конечными, счётчики —
неотрицательными целыми, серии — выровненными и возрастающими, а
недоступность — null-скалярами с кодами причин. Битое поле — false, не
исключение; умолчаний и подмен значений нет.
*/

import {
  isAdapter,
  isAlgorithm,
  isOptions,
  isProvenance,
  isQc,
  isRecord,
  isSelection,
  isSessionIdentity,
  isStringArray,
} from "./guards-ripple-core";
import { isBandList, isInterval, isMetricBlock, isSpectrum } from "./guards-ripple-measurements";
import type { RippleArtifactPayload, RippleBaseline } from "./types-ripple";

const TOP_LEVEL_KEYS: readonly string[] = [
  "schema_version",
  "algorithm",
  "options",
  "session",
  "provenance",
  "adapter",
  "selection",
  "qc",
  "time_domain",
  "intervals",
  "spectrum",
  "bands",
  "baseline",
];
const TOP_LEVEL_KEY_SET = new Set<string>(TOP_LEVEL_KEYS);

/** Фон РЯДОМ с измерением: собственная идентичность и собственные числа;
 * сравнение без вычитания, поэтому статус сравнения отделён от доступности
 * его блоков. */
export function isBaseline(value: unknown): value is RippleBaseline {
  if (!isRecord(value)) return false;
  if (!isSessionIdentity(value.session)) return false;
  if (
    value.attachment_basis !== null &&
    value.attachment_basis !== "same_adapter_tip_shorted_to_return"
  ) {
    return false;
  }
  if (value.comparison_status !== "available" && value.comparison_status !== "unavailable") {
    return false;
  }
  if (!isStringArray(value.reason_codes)) return false;
  const available = value.comparison_status === "available";
  if (available ? value.reason_codes.length !== 0 : value.reason_codes.length === 0) return false;
  if (value.selection !== null && !isSelection(value.selection)) return false;
  if (!isMetricBlock(value.time_domain)) return false;
  if (!isSpectrum(value.spectrum)) return false;
  return isBandList(value.bands);
}

/** Полный сайдкар v1: точный набор ключей, схема 1 и каждый блок по форме. */
export function isRippleArtifact(value: unknown): value is RippleArtifactPayload {
  if (!isRecord(value)) return false;
  const keys = Object.keys(value);
  if (keys.length !== TOP_LEVEL_KEYS.length) return false;
  if (!keys.every((key) => TOP_LEVEL_KEY_SET.has(key))) return false;
  if (value.schema_version !== 1) return false;
  if (!isAlgorithm(value.algorithm)) return false;
  if (!isOptions(value.options)) return false;
  if (!isSessionIdentity(value.session)) return false;
  if (!isProvenance(value.provenance)) return false;
  if (!isAdapter(value.adapter)) return false;
  if (!isSelection(value.selection)) return false;
  if (!isQc(value.qc)) return false;
  if (!isMetricBlock(value.time_domain)) return false;
  if (!Array.isArray(value.intervals) || !value.intervals.every((item) => isInterval(item))) {
    return false;
  }
  if (!isSpectrum(value.spectrum)) return false;
  if (!isBandList(value.bands)) return false;
  return value.baseline === null || isBaseline(value.baseline);
}
