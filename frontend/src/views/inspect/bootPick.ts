/** Авто-выбор пары при старте Инспекции (ui-refactor-3, задача 6 — D1a).
 *
 * ИМЕНОВАННЫЙ ключ сортировки — зеркало серверного keyset
 * (src/lnt/catalog/query_repository.py:76-77): created_utc DESC, session_id
 * ASC, storage_path ASC. Boot берёт первые ДВЕ проанализированные строки
 * (analyzed===true по JOIN) в этом порядке; invalid и строки без analyzed
 * пропускаются, manifest-less никогда не выбирается (у него нет legacy-пары).
 * Ноль кандидатов → честная null-пара, unanalyzed в A НЕ фабрикуется.
 *
 * R4: вход уже обрезан >200 (next_cursor выброшен в catalogJoinedSource) —
 * в этой волне не чинится. */

import type { CatalogSession } from "../../api/types";
import type { PairStateValue } from "./pairState";
import { storageDirName } from "./sessionAlias";

function createdOf(session: CatalogSession): string {
  return session.created_utc ?? "";
}

function storageOf(session: CatalogSession): string {
  return session.storage_path ?? "";
}

/** Серверный keyset-порядок: created DESC, id, storage_path. */
export function compareCatalogKey(a: CatalogSession, b: CatalogSession): number {
  const createdA = createdOf(a);
  const createdB = createdOf(b);
  if (createdA !== createdB) return createdA < createdB ? 1 : -1;
  if (a.id !== b.id) return a.id < b.id ? -1 : 1;
  const storageA = storageOf(a);
  const storageB = storageOf(b);
  if (storageA === storageB) return 0;
  return storageA < storageB ? -1 : 1;
}

/** Ключ загрузки пары: dir-name для duplicate_id, иначе id строки. */
export function loadKey(session: CatalogSession): string {
  if (session.health === "duplicate_id") return storageDirName(session.storage_path) ?? session.id;
  return session.id;
}

export interface BootPickInput {
  readonly sessions: readonly CatalogSession[];
  readonly analyzedByDir: ReadonlyMap<string, boolean>;
  readonly invalidByDir: ReadonlyMap<string, string>;
}

function dirOf(session: CatalogSession): string {
  return storageDirName(session.storage_path) ?? session.id;
}

function isBootable(
  session: CatalogSession,
  analyzedByDir: ReadonlyMap<string, boolean>,
  invalidByDir: ReadonlyMap<string, string>,
): boolean {
  const dir = dirOf(session);
  if (invalidByDir.has(dir)) return false;
  if (analyzedByDir.get(dir) !== true) return false;
  if (session.health === "duplicate_id" && storageDirName(session.storage_path) === null) {
    return false;
  }
  return true;
}

/** Первые две bootable-строки в именованном порядке → ключи загрузки. */
export function pickBootPair(input: BootPickInput): PairStateValue {
  const candidates = input.sessions
    .filter((session) => isBootable(session, input.analyzedByDir, input.invalidByDir))
    .sort(compareCatalogKey);
  const a = candidates[0];
  const b = candidates[1];
  return {
    a: a === undefined ? null : loadKey(a),
    b: b === undefined ? null : loadKey(b),
  };
}
