/** TDD RED (ui-refactor-3, фикс регрессии задачи 6): seedCatalog обязан
 * синтезировать честные legacy-ряды — сидированная спекой сессия несёт
 * артефакты (detail/spectrum сидятся тем же бэкендом), и реальный бэкенд
 * выводит такую сессию в /api/sessions c analyzed=true. До фикса
 * seedCatalog оставлял legacyRows пустым → boot по JOIN честно выбирал
 * null-пару → спектр-панель не монтировалась в e2e (spectrumPlane.spec
 * 5/5 red). Пины: имя ряда = joinKey (имя каталога или id), analyzed=true. */

import { describe, expect, it } from "vitest";
import type { CatalogSession } from "../api/types";
import { CatalogStore } from "./mockCatalogStore";

function session(id: string, storagePath: string | null): CatalogSession {
  return {
    id,
    health: "ok",
    created_utc: "2026-08-02T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "bad",
    label: "стенд-А",
    storage_path: storagePath,
  };
}

describe("mockCatalogStore.seedCatalog: честные legacy-ряды", () => {
  it("сидированная сессия получает legacy-ряд analyzed=true по joinKey=id", () => {
    const store = new CatalogStore(0);
    store.seedCatalog([session("capture-001", null)]);

    const legacy = store.legacySessions();
    expect(legacy).toHaveLength(1);
    expect(legacy[0]).toMatchObject({ name: "capture-001", status: "valid", analyzed: true });
  });

  it("joinKey сидированной сессии = имя каталога из storage_path", () => {
    const store = new CatalogStore(0);
    store.seedCatalog([session("syn-quiet-seed1", "/root/dirname-differs")]);

    expect(store.legacySessions()[0]).toMatchObject({ name: "dirname-differs" });
  });

  it("include_paths-проекция сходится с legacy-ключом: boot резолвит пару", () => {
    const store = new CatalogStore(0);
    store.seedCatalog([session("capture-001", null)]);

    const page = store.catalog(new URLSearchParams("include_paths=true"));
    // Явный storage_path:null не перезаписывается (контракт projectRow),
    // но joinKey от этого не меняется: storageDirName(null) → id.
    expect(page.items[0]?.storage_path).toBeNull();
    // joinKey = id === legacy-имя → analyzedByDir непуст → pickBootPair
    // находит кандидата.
    expect(store.legacySessions().map((row) => row.name)).toContain("capture-001");
  });

  it("конструктор без сида не выдумывает legacy-ряды (честный пустой мир)", () => {
    const store = new CatalogStore(0);
    expect(store.legacySessions()).toHaveLength(0);
  });

  it("seedCorpus не затронут: честные флаги корпуса остаются источником", () => {
    const store = new CatalogStore(0);
    store.seedCorpus();
    const rows = store.legacySessions();
    expect(rows.some((row) => !row.analyzed)).toBe(true);
    expect(rows.some((row) => row.analyzed)).toBe(true);
  });
});
