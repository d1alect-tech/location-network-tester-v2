import type { CatalogSession } from "../../api/types";

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
    const cmp = dayA.localeCompare(dayB);
    return dir === "asc" ? cmp : -cmp;
  });

  const rows: CatalogRow[] = [];
  for (const day of sortedDays) {
    const daySessions = groups.get(day) ?? [];
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
  sessionId: string,
  pair: { a: string | null; b: string | null }
): "a" | "b" | null {
  if (sessionId === pair.a) return "a";
  if (sessionId === pair.b) return "b";
  return null;
}
