/** Задача 4 (D1g/C1): JOIN analyzed + health-пилюли рейла на корпус-фикстуре.
 * RED→GREEN: analyzed ТОЛЬКО из legacySessions (никогда из health «ok»),
 * invalid-строка несёт ошибку legacy, corrupt/partial видимы БЕЗ analyzed-пилюли,
 * duplicate-сиблинги различаются по dir-ключу JOIN. Проза сверяется только
 * против экспортов shared-словаря (shipped-copy equality), не литералами. */

import { describe, expect, it, vi } from "vitest";
import type { CatalogSession } from "../../api/types";
import {
  ANALYZED_LABEL,
  HEALTH_LABELS,
  UNANALYZED_LABEL,
} from "../../components/status/sessionHealth";
import {
  CORPUS_MANIFEST_LESS_DIR,
  CORPUS_PARTIAL_DIR,
  CORPUS_TORN_MANIFEST_DIR,
  CORPUS_V2_DIR,
  corpusCatalogEntries,
  corpusLegacySessions,
  corpusRows,
} from "../../testkit/catalogFixture";
import { createCatalogColumn } from "./catalogColumn";
import { joinKey, loadJoinedCatalog } from "./catalogJoinedSource";
import { createPairState } from "./pairState";

function corpusClient() {
  const sessions: CatalogSession[] = corpusCatalogEntries().map((entry) => ({
    ...entry.session,
    storage_path: entry.storagePath,
  }));
  return {
    catalogSessions: async () => ({ items: sessions }),
    legacySessions: async () => ({ sessions: corpusLegacySessions() }),
  };
}

async function mountRail() {
  const column = createCatalogColumn({
    client: corpusClient(),
    pair: createPairState(),
    onPick: vi.fn(),
  });
  await column.reload();
  document.body.replaceChildren(column.root);
  return column;
}

function pillText(row: Element | null, hook: string): string | null {
  return row?.querySelector(`[data-cat-analyzed], [${hook}]`)?.textContent ?? null;
}

describe("JOIN analyzed: пилюля из legacy, не из health", () => {
  it("unanalyzed ch2-отказ: health «ok», пилюля — «Не проанализирована»", async () => {
    const column = await mountRail();
    const row = column.root.querySelector('[data-session="cap-20260805-163915-a83892f0"]');

    expect(row?.querySelector('[data-cat-health="ok"]')?.textContent).toContain(
      HEALTH_LABELS.ok.label,
    );
    const analyzed = row?.querySelector('[data-cat-analyzed="no"]');
    expect(analyzed?.textContent).toBe(UNANALYZED_LABEL);
  });

  it("analyzed: пилюля «Проанализирована» только при metrics.json по JOIN", async () => {
    const column = await mountRail();
    const analyzed = column.root.querySelector(
      '[data-session="cap-20260806-093846-0014c40f"] [data-cat-analyzed="yes"]',
    );
    const refused = column.root.querySelector(
      '[data-session="cap-20260805-163925-d413c44a"] [data-cat-analyzed="no"]',
    );

    expect(analyzed?.textContent).toBe(ANALYZED_LABEL);
    expect(refused?.textContent).toBe(UNANALYZED_LABEL);
    expect(pillText(column.root, "data-cat-health")).not.toBeNull();
  });

  it("duplicate-сиблинги: JOIN по dir-ключу, все три видимы с health-пилюлей", async () => {
    const column = await mountRail();
    const twins = corpusCatalogEntries().filter(
      (entry) => entry.session.id === "syn-quiet-seed6022",
    );

    expect(
      twins.map((entry) => joinKey({ ...entry.session, storage_path: entry.storagePath })),
    ).toContain(CORPUS_V2_DIR);
    const pills = column.root.querySelectorAll('[data-cat-health="duplicate_id"]');
    expect(pills.length).toBe(3);
    expect(pills[0]?.textContent).toContain(HEALTH_LABELS.duplicate_id.label);
  });

  it("manifest-less и partial: видимы с health-пилюлей, БЕЗ analyzed-пилюли", async () => {
    const column = await mountRail();
    const manifestLess = column.root.querySelector(`[data-session="${CORPUS_MANIFEST_LESS_DIR}"]`);
    const partial = column.root.querySelector(`[data-session="${CORPUS_PARTIAL_DIR}"]`);

    expect(manifestLess?.querySelector('[data-cat-health="corrupt_manifest"]')).not.toBeNull();
    expect(partial?.querySelector('[data-cat-health="partial"]')).not.toBeNull();
    expect(manifestLess?.querySelector("[data-cat-analyzed]")).toBeNull();
    expect(partial?.querySelector("[data-cat-analyzed]")).toBeNull();
  });

  it("torn-manifest: legacy invalid → error-пилюля с текстом ошибки", async () => {
    const column = await mountRail();
    const row = column.root.querySelector(`[data-session="${CORPUS_TORN_MANIFEST_DIR}"]`);
    const pill = row?.querySelector('[data-cat-analyzed="invalid"]');

    expect(pill).not.toBeNull();
    expect(pill?.textContent).toContain("манифест");
  });
});

describe("loadJoinedCatalog: контракт JOIN", () => {
  it("analyzedByDir/invalidByDir ключуются именами каталогов", async () => {
    const page = await loadJoinedCatalog(corpusClient());

    expect(page.sessions.length).toBe(corpusRows().length);
    expect(page.analyzedByDir.get(CORPUS_V2_DIR)).toBe(true);
    expect(page.analyzedByDir.get("first-capture")).toBe(false);
    expect(page.analyzedByDir.has(CORPUS_MANIFEST_LESS_DIR)).toBe(false);
    expect(page.invalidByDir.get(CORPUS_TORN_MANIFEST_DIR)).toContain("манифест");
  });

  it("health-эндпоинт врёт «ok» — JOIN всё равно показывает unanalyzed", async () => {
    const sessions: CatalogSession[] = corpusCatalogEntries().map((entry) => ({
      ...entry.session,
      storage_path: entry.storagePath,
    }));
    const page = await loadJoinedCatalog({
      catalogSessions: async () => ({ items: sessions }),
      legacySessions: async () => ({ sessions: corpusLegacySessions() }),
    });

    const refused = sessions.find((row) => row.id === "cap-20260805-163915-a83892f0");
    expect(refused?.health).toBe("ok");
    const key = refused === undefined ? "" : joinKey(refused);
    expect(page.analyzedByDir.get(key)).toBe(false);
  });

  it("legacy-плечо необязательно: отказ или мусор → честная health-проекция", async () => {
    const sessions: CatalogSession[] = corpusCatalogEntries().map((entry) => ({
      ...entry.session,
      storage_path: entry.storagePath,
    }));
    const rejected = await loadJoinedCatalog({
      catalogSessions: async () => ({ items: sessions }),
      legacySessions: async () => {
        throw new Error("обрыв");
      },
    });
    const garbage = await loadJoinedCatalog({
      catalogSessions: async () => ({ items: sessions }),
      legacySessions: async () => ({}) as unknown as { sessions: [] },
    });

    expect(rejected.sessions.length).toBe(sessions.length);
    expect(rejected.analyzedByDir.size).toBe(0);
    expect(garbage.sessions.length).toBe(sessions.length);
    expect(garbage.invalidByDir.size).toBe(0);
  });
});
