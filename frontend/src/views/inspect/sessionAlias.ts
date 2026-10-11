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

/** Имя каталога → manifest id. Имя, равное id, алиасом не считается. */
export function buildSessionAlias(items: readonly CatalogSession[]): Map<string, string> {
  const alias = new Map<string, string>();
  for (const item of items) {
    const dir = storageDirName(item.storage_path);
    if (dir === null || dir === item.id) continue;
    if (!alias.has(dir)) alias.set(dir, item.id);
  }
  return alias;
}
