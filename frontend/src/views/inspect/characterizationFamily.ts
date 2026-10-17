/** Чтение объявленных полей семейства characterization-v1 из characterization.json.
 *
 * Форма блоков — `family_mapping` в `src/lnt/characterization/metadata_mapping.py`:
 * `qc`, `support`, `band`, `window`, `inference`. Разбор вынесен из
 * `extendedRun.ts`, чтобы тот остался в окне размера модулей; поведение
 * `parseCharacterizationSummary` не меняется.
 *
 * Правило одно: отсутствующее или негодное поле — честный `null`, никогда
 * `NaN`, `0` по умолчанию и не выброшенная ошибка. Бэкенд отдаёт `null` там,
 * где значения нет, и `null` должен дойти до рендера тем же значением.
 */

/** QC-блок семейства: коды причин читаются независимо от reason_codes. */
export type FamilyQc = {
  readonly passed: boolean | null;
  readonly reasonCodes: readonly string[] | null;
};

/** Поддержка семейства: сколько отсчётов сохранено и по какому правилу выбрано. */
export type FamilySupport = {
  readonly storedCount: number | null;
  readonly missingCount: number | null;
  readonly selectionRule: string | null;
};

/** Полоса анализа в Гц; отсутствующая граница — честный null. */
export type FamilyBand = {
  readonly lowHz: number | null;
  readonly highHz: number | null;
};

/** Окно анализа: геометрия одинакова для всех семейств. */
export type FamilyWindow = {
  readonly kind: string | null;
  readonly durationS: number | null;
  readonly sampleCount: number | null;
  readonly overlapFraction: number | null;
};

/** Границы применимости оценки: что вообще можно утверждать по этому семейству. */
export type FamilyInference = {
  readonly estimateScope: string | null;
  readonly populationInference: string | null;
  readonly reasonCode: string | null;
};

/** Всё, что семейство несёт помимо идентичности и статуса. */
export type FamilyDetail = {
  readonly qc: FamilyQc;
  readonly support: FamilySupport;
  readonly band: FamilyBand;
  readonly window: FamilyWindow;
  readonly inference: FamilyInference;
};

/** Одна строка сводки: идентичность, статус, коды причин и пять блоков полей. */
export type FamilySummary = FamilyDetail & {
  readonly id: string;
  readonly status: string;
  /** Коды причин из reason_codes без перевода; null — бандл их не несёт. */
  readonly reasonCodes: readonly string[] | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asFinite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asText(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asFlag(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

/** reason_codes приходит списком строк; один не-строка — весь блок негоден. */
export function asReasonCodes(value: unknown): readonly string[] | null {
  if (!Array.isArray(value)) return null;
  const items: readonly unknown[] = value;
  const codes: string[] = [];
  for (const code of items) {
    if (typeof code !== "string") return null;
    codes.push(code);
  }
  return codes;
}

function readSupport(value: unknown): FamilySupport {
  const support = isRecord(value) ? value : {};
  return {
    storedCount: asFinite(support.stored_count),
    missingCount: asFinite(support.missing_count),
    selectionRule: asText(support.selection_rule),
  };
}

function readBand(value: unknown): FamilyBand {
  const band = isRecord(value) ? value : {};
  return { lowHz: asFinite(band.low_hz), highHz: asFinite(band.high_hz) };
}

function readWindow(value: unknown): FamilyWindow {
  const window = isRecord(value) ? value : {};
  return {
    kind: asText(window.kind),
    durationS: asFinite(window.duration_s),
    sampleCount: asFinite(window.sample_count),
    overlapFraction: asFinite(window.overlap_fraction),
  };
}

function readInference(value: unknown): FamilyInference {
  const inference = isRecord(value) ? value : {};
  return {
    estimateScope: asText(inference.estimate_scope),
    populationInference: asText(inference.population_inference),
    reasonCode: asText(inference.reason_code),
  };
}

function readQc(value: unknown): FamilyQc {
  const qc = isRecord(value) ? value : {};
  return { passed: asFlag(qc.passed), reasonCodes: asReasonCodes(qc.reason_codes) };
}

/** Читает пять объявленных блоков семейства; каждый — независимо от соседей. */
export function readFamilyDetail(item: Record<string, unknown>): FamilyDetail {
  return {
    qc: readQc(item.qc),
    support: readSupport(item.support),
    band: readBand(item.band),
    window: readWindow(item.window),
    inference: readInference(item.inference),
  };
}
