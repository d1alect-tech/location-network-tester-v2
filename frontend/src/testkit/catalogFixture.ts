/** ТЕСТОВЫЙ ФИКСТУРА-МОДУЛЬ (только e2e/spec, не попадает в продукт):
 * детерминированный генератор каталога на заданное число строк и
 * in-memory бэкенд, повторяющий контракт FastAPI (routes_catalog.py,
 * routes_context.py, routes_profiles.py) — фильтры, keyset-пейджинг,
 * оптимистичная блокировка revision (409), CRUD профилей. */

import type {
  CatalogSession,
  ContextResponse,
  LegacySessionItem,
  ProfileData,
  ProfileKind,
  ProfileRevision,
  SessionHealth,
} from "../api/types";
import type { SessionDetailPayload } from "../api/types-plots";

/** Детерминированный PRNG (mulberry32): одинаковый набор при каждом запуске. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a += 0x6d2b79f5;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const LABELS = ["самошум", "стенд-А", "стенд-Б", "серия-24ч", "после-ремонта"];
const TYPES = ["capture", "simulate", "line_quality"];
const TAGS = ["самошум", "повтор", "контроль", "ночная-серия"];
const PROFILES = ["loft-main", "bench-a", "bench-b"];
const BAD_HEALTH: SessionHealth[] = [
  "corrupt_manifest",
  "missing_files",
  "partial",
  "duplicate_id",
  "context_invalid",
  "analysis_invalid",
];

export function pickHealth(random: () => number): SessionHealth {
  const roll = random();
  if (roll < 0.9) return "ok";
  return BAD_HEALTH[Math.floor(random() * BAD_HEALTH.length)] ?? "ok";
}

export interface CatalogFixtureOptions {
  size: number;
  seed?: number;
}

export function generateSessions(options: CatalogFixtureOptions): CatalogSession[] {
  const random = mulberry32(options.seed ?? 39);
  const items: CatalogSession[] = [];
  for (let index = 0; index < options.size; index += 1) {
    const id = `capture-${String(index + 1).padStart(5, "0")}`;
    const day = 1 + Math.floor(random() * 28);
    const month = 1 + Math.floor(random() * 12);
    const year = random() < 0.5 ? 2025 : 2026;
    items.push({
      id,
      health: pickHealth(random),
      created_utc: `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}T10:00:00Z`,
      source: "disk",
      session_type: TYPES[Math.floor(random() * TYPES.length)] ?? "capture",
      profile: PROFILES[Math.floor(random() * PROFILES.length)] ?? null,
      label: LABELS[Math.floor(random() * LABELS.length)] ?? null,
    });
  }
  // Стабильный keyset-порядок как в query_repository.py.
  items.sort((a, b) => {
    const dateA = a.created_utc ?? "";
    const dateB = b.created_utc ?? "";
    if (dateA !== dateB) return dateB.localeCompare(dateA);
    return a.id.localeCompare(b.id);
  });
  return items;
}

export function contextFor(session: CatalogSession): ContextResponse {
  if (WORST_IDS.has(session.id)) return worstCaseContextFor(session);
  if (session.health === "context_invalid") {
    return {
      session_id: session.id,
      revision: 0,
      health: "context_invalid",
      reason_codes: ["context_cache_malformed"],
      fields: {},
      tags: [],
      notes: null,
    };
  }
  return {
    session_id: session.id,
    revision: 2,
    health: "context_valid",
    reason_codes: [],
    fields: {
      fs_hz: {
        kind: "number",
        value: 1_000_000,
        unit: "Гц",
        source: "profile",
        captured_at: `${session.created_utc}`,
      },
      operator_note_inline: {
        kind: "string",
        value: "оператор не указан",
        source: "user",
        captured_at: `${session.created_utc}`,
      },
      range_v: {
        kind: "number",
        value: 5,
        unit: "В",
        source: "automatic",
        captured_at: `${session.created_utc}`,
      },
      sync_source: {
        kind: "string",
        value: "ch2",
        source: "derived",
        collection_status: "collected",
        captured_at: `${session.created_utc}`,
      },
    },
    tags: [TAGS[session.id.length % TAGS.length] ?? "контроль"],
    notes: `Заметки для ${session.id}`,
  };
}

/** Worst-case набор для «Плотного списка»: длинный идентификатор и метка,
 * повреждённый контекст с кодом причины, сессия без полей и даты,
 * пустые теги/заметки. Ноль строк — пустой массив, одна — slice(0, 1),
 * много — generateSessions полным размером. */
const LONG_ID = "cap-20260804-205912-a1b2c3d4-renamed-after-transformer-230-6-replacement-bench-b";

const WORST_IDS = new Set(worstCaseSessions().map((session) => session.id));

export function worstCaseSessions(): CatalogSession[] {
  return [
    {
      id: LONG_ID,
      health: "duplicate_id",
      created_utc: "2026-08-04T20:59:12Z",
      source: "disk",
      session_type: "line_quality",
      profile: "bench-b",
      label: "стенд-Б (папка переименована после замены трансформатора 230:6)",
    },
    {
      id: "cap-20260805-093014-3d77",
      health: "context_invalid",
      created_utc: "2026-08-05T09:30:14Z",
      source: "disk",
      session_type: "line_quality",
      profile: "bench-b",
      label: "после-ремонта",
    },
    {
      id: "cap-20260804-114502-2f9b",
      health: "missing_files",
      created_utc: null,
      source: null,
      session_type: null,
      profile: null,
      label: null,
    },
    {
      id: "cap-20260805-174311-9f0c",
      health: "ok",
      created_utc: "2026-08-05T17:43:11Z",
      source: "disk",
      session_type: "capture",
      profile: "loft-main",
      label: "самошум",
    },
  ];
}

/** Контекст worst-case сессии: повреждённый не отдаёт полей, у пустой
 * сессии теги/заметки пусты, недостающее остаётся отсутствующим. */
export function worstCaseContextFor(session: CatalogSession): ContextResponse {
  if (session.health === "context_invalid") {
    return {
      session_id: session.id,
      revision: 0,
      health: "context_invalid",
      reason_codes: ["context_cache_malformed"],
      fields: {},
      tags: [],
      notes: null,
    };
  }
  if (session.health === "missing_files") {
    return {
      session_id: session.id,
      revision: 0,
      health: "context_absent",
      reason_codes: [],
      fields: {},
      tags: [],
      notes: null,
    };
  }
  if (session.id === LONG_ID) {
    return {
      session_id: session.id,
      revision: 3,
      health: "context_valid",
      reason_codes: ["context_events_torn_tail"],
      fields: {
        fs_hz: {
          kind: "number",
          value: 1_000_000,
          unit: "Гц",
          source: "profile",
          captured_at: `${session.created_utc}`,
        },
      },
      tags: ["длинный-тег-ночная-серия-после-ремонта-трансформатора-230-6-контроль", "повтор"],
      notes:
        "Папка переименована вручную после замены трансформатора; идентификатор в manifest.json остался прежним — отсюда дубль.",
    };
  }
  return {
    session_id: session.id,
    revision: 2,
    health: "context_valid",
    reason_codes: [],
    fields: {
      sync_source: {
        kind: "string",
        value: "ch2",
        source: "derived",
        collection_status: "collected",
        captured_at: `${session.created_utc}`,
      },
    },
    tags: [],
    notes: "",
  };
}

export function defaultProfiles(): ProfileRevision[] {
  const base: Array<[ProfileKind, string, ProfileData]> = [
    ["location", "loft-main", { alias: "Лофт", outlet: "A1", circuit: "C16" }],
    ["equipment", "scope-hantek", { alias: "Hantek 2D15", model: "2D15" }],
    [
      "front_end",
      "fe-standard",
      {
        resistance: { value: 10, unit: "МОм" },
        c1: { value: 9.5, unit: "пФ" },
        c2: { value: 100, unit: "пФ" },
      },
    ],
    [
      "transformer",
      "tr-230-6",
      {
        nominal_primary: { value: 230, unit: "В" },
        nominal_secondary: { value: 6, unit: "В" },
      },
    ],
    ["conditions", "cond-night", { damper_state: "off", nearby_load_states: ["холодильник"] }],
  ];
  return base.map(([kind, profileId, data], index) => ({
    profile_id: profileId,
    kind,
    revision: 3 + index,
    captured_at: "2026-07-01T09:00:00Z",
    data,
  }));
}

/* ---------------------------------------------------------------------------
 * Корпус-фикстура (ui-refactor-3, задача 1 — prerequisite C7 для задач 6 и 9).
 *
 * Миниатюра реального корпуса владельца (26 каталогов: 20 проанализированных,
 * 5 отказов анализатора на ch2-захватах, 3 каталога с ОДНИМ session_id
 * `syn-quiet-seed6022` — ровно один несёт v2-артефакт анализа, 1 каталог без
 * манифеста). Строка фикстуры — один КАТАЛОГ на диске, а не один session_id:
 * только так выражаются сиблинги duplicate_id с разными storage_path, строка
 * manifest-blind (каталог её видит, legacy-список — нет) и битый каталог.
 *
 * Семантика зеркалит бэкенд, продуктовый код не тронут:
 * - проекция каталога: src/lnt/catalog/reconcile_parse.py:76-95 (нет/битый
 *   манифест → id = ИМЯ КАТАЛОГА, health `corrupt_manifest`; `.partial-` →
 *   `partial`), :55-58 (health «ok» БЕЗ metrics.json — корень дефекта C1,
 *   поэтому analyzed обязан приходить из JOIN, а не из health);
 * - порядок строк: src/lnt/catalog/query_repository.py:76-77
 *   (COALESCE(created_utc,'') DESC, session_id ASC, storage_path ASC);
 * - legacy GET /api/sessions: src/lnt/ui/sessions.py:58-104 (каталог без
 *   manifest.json ПРОПУЩЕН, битый манифест → status `invalid` + error, ключи —
 *   ИМЕНА КАТАЛОГОВ, analyzed = metrics.json && (spectrum.csv || line_quality),
 *   порядок — имя каталога ASC);
 * - detail-флаги: src/lnt/ui/payloads.py:71-87;
 * - неоднозначный session_id: src/lnt/ui/api_support.py:32-36 (409).
 *
 * Ниже ТОЛЬКО новые экспорты: существующие фикстуры модуля не переписаны.
 * ------------------------------------------------------------------------- */

/** Корень мок-корпуса: совпадает с `root` из configPayload единого мока. */
export const CORPUS_ROOT = "C:\\lnt-sessions-test";

/** Три каталога с одним session_id (реальный владелец: syn-quiet-seed6022). */
export const CORPUS_DUPLICATE_SESSION_ID = "syn-quiet-seed6022";

/** Единственный каталог корпуса с v2-артефактом анализа (и с ch2). */
export const CORPUS_V2_DIR = "sim-quiet-20261005-151028";

/** Ключ v2-артефакта; тело артефакта спека сидит сама (реальные фикстуры). */
export const CORPUS_V2_ARTIFACT_KEY = "art-corpus-v2";

/** Каталог без manifest.json: виден в каталоге, невидим для legacy-списка. */
export const CORPUS_MANIFEST_LESS_DIR = "06.08.2026 11-37";

/** Битый каталог (health `partial`): пропущен legacy-списком, виден в health. */
export const CORPUS_PARTIAL_DIR = ".partial-cap-20260807-101500";

/** Каталог с неразбирающимся манифестом: legacy отдаёт status `invalid`. */
export const CORPUS_TORN_MANIFEST_DIR = "cap-20260807-091500-torn";

export type CorpusSessionType =
  | "capture"
  | "simulate"
  | "line_quality"
  | "measurement"
  | "self_noise";

/** Один каталог корпуса: ключ — имя каталога (`dir`), не session_id. */
export interface CorpusRow {
  readonly dir: string;
  /** session_id из манифеста; null — манифеста нет или он не разбирается. */
  readonly sessionId: string | null;
  readonly health: SessionHealth;
  readonly createdUtc: string | null;
  readonly sessionType: CorpusSessionType | null;
  readonly profile: string | null;
  readonly label: string | null;
  /** manifest.json присутствует и разбирается (иначе legacy-список строку не видит). */
  readonly manifest: boolean;
  /** Текст ошибки разбора манифеста: legacy отдаёт status `invalid` + error. */
  readonly manifestError: string | null;
  /** metrics.json — единственный источник правды об analyzed. */
  readonly metrics: boolean;
  readonly spectrum: boolean;
  readonly waveform: boolean;
  readonly ch2: boolean;
  /** .lnt-default-analysis.json — указатель на v2-артефакт анализа. */
  readonly analysisV2: boolean;
}

type CorpusRowSeed = {
  dir: string;
} & Partial<Omit<CorpusRow, "dir">>;

const CORPUS_ROW_DEFAULTS: Omit<CorpusRow, "dir"> = {
  sessionId: null,
  health: "ok",
  createdUtc: null,
  sessionType: "capture",
  profile: null,
  label: null,
  manifest: true,
  manifestError: null,
  metrics: false,
  spectrum: false,
  waveform: true,
  ch2: false,
  analysisV2: false,
};

function corpusRow(seed: CorpusRowSeed): CorpusRow {
  return {
    ...CORPUS_ROW_DEFAULTS,
    ...seed,
    sessionType:
      seed.sessionType === undefined ? CORPUS_ROW_DEFAULTS.sessionType : seed.sessionType,
  };
}

/** Полный путь хранения каталога: Windows-разделитель, как `str(scanned.path)`. */
export function corpusStoragePath(dir: string): string {
  return `${CORPUS_ROOT}\\${dir}`;
}

/** Детерминированный корпус: 14 каталогов, миниатюра реальных 26. */
export function corpusRows(): CorpusRow[] {
  return [
    // Битый каталог: `.partial-` в имени → health `partial`, id = имя каталога
    // (reconcile_parse.py:76-88); legacy-список его пропускает (нет манифеста).
    corpusRow({ dir: CORPUS_PARTIAL_DIR, health: "partial", manifest: false, waveform: false }),
    // Каталог без манифеста: health `corrupt_manifest`, id = имя каталога;
    // manifest-blind для legacy (sessions.py:64-66), виден в каталоге/health.
    corpusRow({
      dir: CORPUS_MANIFEST_LESS_DIR,
      health: "corrupt_manifest",
      manifest: false,
      waveform: false,
    }),
    // Манифест не разбирается: каталог — corrupt_manifest, legacy — invalid.
    corpusRow({
      dir: CORPUS_TORN_MANIFEST_DIR,
      health: "corrupt_manifest",
      manifestError: "манифест не является JSON-объектом",
      waveform: false,
    }),
    // Три каталога с ОДНИМ session_id: разные storage_path, health duplicate_id;
    // ровно один (CORPUS_V2_DIR) несёт ch2 и v2-артефакт анализа.
    corpusRow({
      dir: "sim-quiet-20261005-150929",
      sessionId: CORPUS_DUPLICATE_SESSION_ID,
      health: "duplicate_id",
      createdUtc: "2026-10-05T15:09:29Z",
      sessionType: "simulate",
      profile: "quiet",
      metrics: true,
      spectrum: true,
    }),
    corpusRow({
      dir: "sim-quiet-20261005-151017",
      sessionId: CORPUS_DUPLICATE_SESSION_ID,
      health: "duplicate_id",
      createdUtc: "2026-10-05T15:10:17Z",
      sessionType: "simulate",
      profile: "quiet",
      metrics: true,
      spectrum: true,
    }),
    corpusRow({
      dir: CORPUS_V2_DIR,
      sessionId: CORPUS_DUPLICATE_SESSION_ID,
      health: "duplicate_id",
      createdUtc: "2026-10-05T15:10:28Z",
      sessionType: "simulate",
      profile: "quiet",
      metrics: true,
      spectrum: true,
      ch2: true,
      analysisV2: true,
    }),
    // Пять непроанализированных строк (нет metrics.json) — health ПРИ ЭТОМ «ok»
    // (reconcile_parse.py:55-58): «не проанализировано» не должно выглядеть как «ok».
    corpusRow({
      dir: "cap-20260805-163913",
      sessionId: "cap-20260805-163915-a83892f0",
      createdUtc: "2026-08-05T16:39:15Z",
      ch2: true,
    }),
    corpusRow({
      dir: "cap-20260805-163923",
      sessionId: "cap-20260805-163925-d413c44a",
      createdUtc: "2026-08-05T16:39:25Z",
      ch2: true,
    }),
    corpusRow({
      dir: "cap-20260805-180623",
      sessionId: "cap-20260805-180626-67d66c25",
      createdUtc: "2026-08-05T18:06:26Z",
      ch2: true,
    }),
    corpusRow({
      dir: "cap-20260806-093821",
      sessionId: "cap-20260806-093826-4e2f8915",
      createdUtc: "2026-08-06T09:38:26Z",
      ch2: true,
    }),
    corpusRow({
      dir: "first-capture",
      sessionId: "cap-20260805-163312-1e5bc5a7",
      createdUtc: "2026-08-05T16:33:12Z",
      label: "первый захват",
      ch2: true,
    }),
    // Проанализированная строка с полным набором файлов.
    corpusRow({
      dir: "cap-20260806-093843",
      sessionId: "cap-20260806-093846-0014c40f",
      createdUtc: "2026-08-06T09:38:46Z",
      metrics: true,
      spectrum: true,
    }),
    // metrics.json есть, spectrum.csv нет: analysis !== null при spectrum_available false.
    corpusRow({
      dir: "cap-20260805-212516",
      sessionId: "cap-20260805-212518-4e246d77",
      createdUtc: "2026-08-05T21:25:18Z",
      metrics: true,
    }),
    // line_quality: analyzed БЕЗ spectrum.csv (sessions.py:88-90, needs_spectrum false).
    corpusRow({
      dir: "qa-line-quality",
      sessionId: "qa-line-quality",
      createdUtc: "2026-08-04T12:00:00Z",
      sessionType: "line_quality",
      metrics: true,
    }),
  ];
}

/** Строка каталога (проекция include_paths=false) + её путь хранения. */
export interface CorpusCatalogEntry {
  readonly row: CorpusRow;
  readonly session: CatalogSession;
  readonly storagePath: string;
}

/** Проецирует корпус в строки каталога: без storage_path (его добавляет мок
 * только на include_paths — routes_catalog.py:94) и в keyset-порядке бэкенда. */
export function corpusCatalogEntries(
  rows: readonly CorpusRow[] = corpusRows(),
): CorpusCatalogEntry[] {
  const entries = rows.map((row) => {
    // Нет разбирающегося манифеста → каталог ключуется ИМЕНЕМ КАТАЛОГА,
    // остальные поля проекции пусты (reconcile_parse.py:88-100).
    const projected = row.sessionId !== null;
    const session: CatalogSession = {
      id: row.sessionId ?? row.dir,
      health: row.health,
      created_utc: row.createdUtc,
      source: projected ? "disk" : null,
      session_type: projected ? row.sessionType : null,
      profile: projected ? row.profile : null,
      label: projected ? row.label : null,
    };
    return { row, session, storagePath: corpusStoragePath(row.dir) };
  });
  // Keyset-порядок бэкенда (query_repository.py:76-77): COALESCE(created_utc,'')
  // DESC, session_id ASC, storage_path ASC. Сравнение ASCII (BINARY collation
  // SQLite), не localeCompare: порядок строк обязан совпадать с сервером.
  entries.sort((a, b) => {
    const createdA = a.session.created_utc ?? "";
    const createdB = b.session.created_utc ?? "";
    if (createdA !== createdB) return createdA < createdB ? 1 : -1;
    if (a.session.id !== b.session.id) return a.session.id < b.session.id ? -1 : 1;
    if (a.storagePath === b.storagePath) return 0;
    return a.storagePath < b.storagePath ? -1 : 1;
  });
  return entries;
}

/** Строки каталога корпуса (без storage_path — ответ include_paths=false). */
export function corpusSessions(rows: readonly CorpusRow[] = corpusRows()): CatalogSession[] {
  return corpusCatalogEntries(rows).map((entry) => entry.session);
}

const CORPUS_DURATION_S = 2.4;

function corpusSampleRate(row: CorpusRow): number {
  return row.sessionType === "simulate" ? 500_000 : 8_000_000;
}

/** Legacy-строка GET /api/sessions: ключ — ИМЯ КАТАЛОГА, analyzed — из файлов. */
export function corpusLegacySessions(
  rows: readonly CorpusRow[] = corpusRows(),
): LegacySessionItem[] {
  const visible = rows
    .filter((row) => row.manifest)
    .sort((a, b) => (a.dir < b.dir ? -1 : a.dir > b.dir ? 1 : 0));
  return visible.map((row) => {
    const invalid = row.manifestError !== null;
    const needsSpectrum = row.sessionType !== "line_quality";
    const sampleRate = corpusSampleRate(row);
    return {
      name: row.dir,
      status: invalid ? "invalid" : "valid",
      error: invalid ? `ошибка manifest.json: ${row.manifestError}` : null,
      // sessions.py:88-90: analyzed = metrics.json && (spectrum.csv || line_quality).
      analyzed: !invalid && row.metrics && (row.spectrum || !needsSpectrum),
      summary: invalid
        ? null
        : {
            session_id: row.sessionId,
            created_utc: row.createdUtc,
            source: "disk",
            session_type: row.sessionType,
            profile: row.profile,
            sample_rate_hz: sampleRate,
            duration_s: CORPUS_DURATION_S,
            sample_count: Math.round(CORPUS_DURATION_S * sampleRate),
            label: row.label,
            channels: row.ch2 ? "dual" : "ch1_only",
          },
    };
  });
}

/** Флаги detail-200 (payloads.py:77-87) — то, из чего «н/д» берёт причину. */
export interface CorpusDetailFlags {
  readonly analysis: boolean;
  readonly spectrum: boolean;
  readonly waveform: boolean;
  readonly ch2: boolean;
}

/** Пермутации флагов: analysis:null и наборы с false (задача 9). */
export const CORPUS_DETAIL_FLAGS: Readonly<Record<string, CorpusDetailFlags>> = {
  analyzed_full: { analysis: true, spectrum: true, waveform: true, ch2: false },
  analyzed_dual: { analysis: true, spectrum: true, waveform: true, ch2: true },
  analyzed_no_spectrum: { analysis: true, spectrum: false, waveform: true, ch2: false },
  refused_ch2: { analysis: false, spectrum: false, waveform: true, ch2: true },
  nothing_available: { analysis: false, spectrum: false, waveform: false, ch2: false },
};

export function corpusDetailFlags(row: CorpusRow): CorpusDetailFlags {
  return {
    analysis: row.metrics,
    spectrum: row.spectrum,
    waveform: row.waveform,
    ch2: row.ch2,
  };
}

/** Detail-200 каталога: честные null и false, ноль выдуманных метрик. */
export function corpusDetailPayload(row: CorpusRow, key = row.dir): SessionDetailPayload {
  const sampleRate = corpusSampleRate(row);
  return {
    name: key,
    manifest: {
      session_id: row.sessionId ?? row.dir,
      created_utc: row.createdUtc,
      source: "disk",
      session_type: row.sessionType,
      profile: row.profile,
      sample_rate_hz: sampleRate,
      duration_s: CORPUS_DURATION_S,
      sample_count: Math.round(CORPUS_DURATION_S * sampleRate),
      label: row.label,
    },
    // Нет metrics.json → analysis:null; числа метрик фикстура не выдумывает —
    // спека, которой нужны значения, сидит detail сама (seedSessionDetail).
    analysis: row.metrics ? { session_id: row.sessionId ?? row.dir, schema_version: 1 } : null,
    spectrum_available: row.spectrum,
    waveform_available: row.waveform,
    ch2_available: row.ch2,
  };
}

/** Строка корпуса с валидным манифестом: для неё возможен detail-200. */
function detailVisible(row: CorpusRow): boolean {
  return row.manifest && row.manifestError === null;
}

/** session_id более чем одного каталога: сервер отвечает 409 (api_support.py:32-36). */
export function corpusAmbiguousSessionIds(rows: readonly CorpusRow[] = corpusRows()): string[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    if (row.sessionId === null) continue;
    counts.set(row.sessionId, (counts.get(row.sessionId) ?? 0) + 1);
  }
  return [...counts.entries()]
    .filter(([, count]) => count > 1)
    .map(([id]) => id)
    .sort();
}

/** session_id ровно одного каталога: резолвится без неоднозначности. */
export function corpusUniqueSessionIds(rows: readonly CorpusRow[] = corpusRows()): string[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    if (row.sessionId === null) continue;
    counts.set(row.sessionId, (counts.get(row.sessionId) ?? 0) + 1);
  }
  return [...counts.entries()]
    .filter(([, count]) => count === 1)
    .map(([id]) => id)
    .sort();
}

/** Каталоги без detail-200 (манифеста нет или он битый): мок отвечает 404. */
export function corpusDetailBlindDirs(rows: readonly CorpusRow[] = corpusRows()): string[] {
  return rows.filter((row) => !detailVisible(row)).map((row) => row.dir);
}

/** Detail-200 корпуса: ключ — имя каталога ИЛИ однозначный session_id. */
export function corpusDetails(
  rows: readonly CorpusRow[] = corpusRows(),
): Map<string, SessionDetailPayload> {
  const details = new Map<string, SessionDetailPayload>();
  const ambiguous = new Set(corpusAmbiguousSessionIds(rows));
  for (const row of rows) {
    if (!detailVisible(row)) continue;
    details.set(row.dir, corpusDetailPayload(row));
    if (row.sessionId !== null && !ambiguous.has(row.sessionId)) {
      details.set(row.sessionId, corpusDetailPayload(row, row.sessionId));
    }
  }
  return details;
}

/** Единственный каталог корпуса с v2-артефактом анализа (null — его нет). */
export function corpusV2Dir(rows: readonly CorpusRow[] = corpusRows()): string | null {
  const carriers = rows.filter((row) => row.analysisV2).map((row) => row.dir);
  return carriers.length === 1 ? (carriers[0] ?? null) : null;
}
