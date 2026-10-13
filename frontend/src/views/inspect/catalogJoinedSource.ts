/** ЕДИНЫЙ источник каталога Инспекции (ui-refactor-3, задача 4 — вердикт G1/Q1=B).
 *
 * До этого boot (inspectV6) и рейл (catalogColumn) делали ДВА независимых
 * фетча /api/catalog/sessions — два источника одной проекции с дрейфом
 * (бут — с include_paths, рейл — без). Теперь один reload() кормит обоих.
 *
 * JOIN analyzed: legacySessions (/api/sessions, ключи — ИМЕНА КАТАЛОГОВ)
 * соединяется с проекцией каталога по storageDirName(storage_path) с запасным
 * сопоставлением по id. Строка без legacy-пары (corrupt/partial, manifest-blind)
 * остаётся видимой со статусом только из health — analyzed-пилюли у неё нет,
 * что честно: «не проанализировано» никогда не выглядит как «ok».
 *
 * R4: оба фетча обрезают >200 сессий (next_cursor выбрасывается) — известное
 * ограничение, в этой волне не чинится. */

import type { CatalogQuery, CatalogSession } from "../../api/types";
import { storageDirName } from "./sessionAlias";

export interface JoinedCatalogClient {
  catalogSessions(
    query?: CatalogQuery,
    options?: unknown,
  ): Promise<{ readonly items: readonly CatalogSession[] }>;
  legacySessions(options?: unknown): Promise<{ readonly sessions: readonly LegacyRow[] }>;
}

export interface LegacyRow {
  readonly name: string;
  readonly status: string;
  readonly error: string | null;
  readonly analyzed: boolean;
}

export interface JoinedCatalogPage {
  readonly sessions: readonly CatalogSession[];
  /** Имя каталога → analyzed (только для строк с legacy-парой). */
  readonly analyzedByDir: ReadonlyMap<string, boolean>;
  /** Имя каталога → текст ошибки legacy (status invalid). */
  readonly invalidByDir: ReadonlyMap<string, string>;
}

/** Ключ JOIN: имя каталога из storage_path, запасной — id строки. */
export function joinKey(session: CatalogSession): string {
  return storageDirName(session.storage_path) ?? session.id;
}

function invalidText(row: LegacyRow): string | null {
  if (row.status === "invalid") return row.error ?? "недопустимая сессия";
  return null;
}

export async function loadJoinedCatalog(
  client: JoinedCatalogClient,
  options?: unknown,
): Promise<JoinedCatalogPage> {
  const [page, legacy] = await Promise.all([
    client.catalogSessions({ page_size: 200, include_paths: true }, options),
    client
      .legacySessions(options)
      .catch((): { readonly sessions: readonly LegacyRow[] } => ({ sessions: [] })),
  ]);
  const rows = Array.isArray(legacy.sessions) ? legacy.sessions : [];
  const legacyByName = new Map<string, LegacyRow>();
  for (const row of rows) legacyByName.set(row.name, row);
  const analyzedByDir = new Map<string, boolean>();
  const invalidByDir = new Map<string, string>();
  for (const session of page.items) {
    const row = legacyByName.get(joinKey(session));
    if (row === undefined) continue;
    const invalid = invalidText(row);
    if (invalid !== null) {
      invalidByDir.set(joinKey(session), invalid);
      continue;
    }
    analyzedByDir.set(joinKey(session), row.analyzed);
  }
  return { sessions: page.items, analyzedByDir, invalidByDir };
}
