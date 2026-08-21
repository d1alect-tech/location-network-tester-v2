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
  if (session.health === "context_invalid" || session.health === "corrupt_manifest") {
    return {
      session_id: session.id,
      revision: 1,
      health: session.health === "corrupt_manifest" ? "corrupt_manifest" : "context_invalid",
      reason_codes:
        session.health === "corrupt_manifest"
          ? ["manifest_parse_error"]
          : ["context_parse_error", "context_schema_v1"],
      fields: {},
      tags: [],
      notes: null,
    };
  }
  return {
    session_id: session.id,
    revision: 2,
    health: session.health,
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
