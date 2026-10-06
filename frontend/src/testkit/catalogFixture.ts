/** ТЕСТОВЫЙ ФИКСТУРА-МОДУЛЬ (только e2e/spec, не попадает в продукт):
 * детерминированный генератор каталога на заданное число строк и
 * in-memory бэкенд, повторяющий контракт FastAPI (routes_catalog.py,
 * routes_context.py, routes_profiles.py) — фильтры, keyset-пейджинг,
 * оптимистичная блокировка revision (409), CRUD профилей. */

import type {
  CatalogSession,
  ContextResponse,
  ProfileData,
  ProfileKind,
  ProfileRevision,
  SessionHealth,
} from "../api/types";

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
