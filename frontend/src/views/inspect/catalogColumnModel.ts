import type { CatalogSession } from "../../api/types";
import { compareCatalogKey } from "./bootPick";

export type CatalogSort = "date" | "label";
export type SortDir = "asc" | "desc";

export type CatalogGroupRow = {
  kind: "group";
  day: string;
  header: string;
  count: number;
};

export type CatalogSessionRow = {
  kind: "session";
  session: CatalogSession;
};

export type CatalogEmptyRow = {
  kind: "empty";
};

export type CatalogRow = CatalogGroupRow | CatalogSessionRow | CatalogEmptyRow;

export interface BuildCatalogRowsOptions {
  sessions: readonly CatalogSession[];
  sort: CatalogSort;
  dir: SortDir;
  query: string;
}

function extractDayKey(createdUtc: string | null): string {
  if (!createdUtc) return "unknown";
  const matched = createdUtc.match(/^(\d{4}-\d{2}-\d{2})/);
  const day = matched?.[1];
  return day ?? "unknown";
}

export function buildCatalogRows(options: BuildCatalogRowsOptions): readonly CatalogRow[] {
  const { sessions, sort, dir, query } = options;
  const trimmedQuery = query.trim().toLowerCase();

  const filtered = trimmedQuery
    ? sessions.filter((session) => {
        const text = (session.label ?? session.id).toLowerCase();
        return text.includes(trimmedQuery);
      })
    : sessions;

  if (filtered.length === 0) {
    return [{ kind: "empty" }];
  }

  if (sort === "label") {
    const sorted = [...filtered].sort((a, b) => {
      const textA = a.label ?? a.id;
      const textB = b.label ?? b.id;
      const cmp = textA.localeCompare(textB, "ru");
      return dir === "asc" ? cmp : -cmp;
    });
    return sorted.map((session): CatalogRow => ({ kind: "session", session }));
  }

  const groups = new Map<string, CatalogSession[]>();
  for (const session of filtered) {
    const day = extractDayKey(session.created_utc);
    let group = groups.get(day);
    if (!group) {
      group = [];
      groups.set(day, group);
    }
    group.push(session);
  }

  const sortedDays = Array.from(groups.keys()).sort((dayA, dayB) => {
    // R3: unknown-группа — зеркало API (COALESCE '' DESC): при date/desc она
    // идёт ПОСЛЕДНЕЙ, при date/asc — первой. До этого negated localeCompare
    // ставил unknown ПЕРВОЙ при desc, и первый видимый ряд рейла никогда не
    // совпадал с boot-рядом из API-порядка.
    if (dayA === "unknown" || dayB === "unknown") {
      if (dayA === dayB) return 0;
      const unknownLast = dir === "desc";
      if (dayA === "unknown") return unknownLast ? 1 : -1;
      return unknownLast ? -1 : 1;
    }
    const cmp = dayA.localeCompare(dayB);
    return dir === "asc" ? cmp : -cmp;
  });

  const rows: CatalogRow[] = [];
  for (const day of sortedDays) {
    const daySessions = (groups.get(day) ?? []).sort((a, b) => {
      // Внутри дня — именованный keyset-порядок (зеркало API), а не порядок
      // вставки: первый ряд группы === первый кандидат boot в тот же день.
      const cmp = compareCatalogKey(a, b);
      return dir === "asc" ? -cmp : cmp;
    });
    rows.push({
      kind: "group",
      day,
      header: day,
      count: daySessions.length,
    });
    for (const session of daySessions) {
      rows.push({
        kind: "session",
        session,
      });
    }
  }

  return rows;
}

export function roleOf(
  session: CatalogSession,
  loadKeyOf: (session: CatalogSession) => string,
  pair: { a: string | null; b: string | null },
): "a" | "b" | null {
  // Пара хранит КЛЮЧИ ЗАГРУЗКИ (dir-name для дублей): роль ищется по обоим
  // ключам D1 — id строки и её loadKey.
  const keys = new Set([session.id, loadKeyOf(session)]);
  if (pair.a !== null && keys.has(pair.a)) return "a";
  if (pair.b !== null && keys.has(pair.b)) return "b";
  return null;
}
