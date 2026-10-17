/** Зеркало D1 на клиенте: ключ сессии — имя каталога ИЛИ manifest session_id.
 * Каталог отдаёт manifest id; имя каталога видно только в storage_path
 * (запрос каталога с include_paths). Шов захвата и ручные deep-link несут имя
 * каталога — без алиаса слот пары оставался пустым при живых данных (f3 F-1). */

import type { CatalogSession } from "../../api/types";

/** Последний сегмент storage_path: имя каталога сессии на любой ОС. */
export function storageDirName(storagePath: string | null | undefined): string | null {
  if (typeof storagePath !== "string") return null;
  const trimmed = storagePath.replace(/[\\/]+$/, "");
  const cut = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
  const name = cut === -1 ? trimmed : trimmed.slice(cut + 1);
  if (name === "" || name === "." || name === "..") return null;
  return name;
}

/** Имя каталога → manifest id. Имя, равное id, алиасом не считается.
 * Строки `duplicate_id` пропускаются (F-8): их id неоднозначен, сервер отвечает
 * 409 «идентификатор сессии неоднозначен» на detail/spectrum/pointer, тогда как
 * имя каталога резолвится однозначно (D1). Ключ такой строки остаётся именем
 * каталога. */
export function buildSessionAlias(items: readonly CatalogSession[]): Map<string, string> {
  const alias = new Map<string, string>();
  for (const item of items) {
    if (item.health === "duplicate_id") continue;
    const dir = storageDirName(item.storage_path);
    if (dir === null || dir === item.id) continue;
    if (!alias.has(dir)) alias.set(dir, item.id);
  }
  return alias;
}

/** Мета-индекс строки каталога: ключ — manifest id ИЛИ имя каталога (зеркало D1,
 * как в `buildSessionAlias`). Существующий ключ не вытесняется: id строки важнее
 * чужого имени каталога. */
export function indexSessionMeta(map: Map<string, CatalogSession>, item: CatalogSession): void {
  map.set(item.id, item);
  const dir = storageDirName(item.storage_path);
  if (dir !== null && !map.has(dir)) map.set(dir, item);
}
