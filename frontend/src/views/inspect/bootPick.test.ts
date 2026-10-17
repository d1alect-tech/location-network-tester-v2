/** Задача 6 (D1a/C1): boot-выбор по JOIN на корпус-фикстуре.
 * RED→GREEN: первый АНАЛИЗИРОВАННЫЙ ряд в именованном keyset-порядке,
 * пропуск invalid/unanalyzed/manifest-less/dup-без-dir, честная null-пара
 * при нуле кандидатов, стабильный ключ при равных датах. */

import { describe, expect, it } from "vitest";
import type { CatalogSession } from "../../api/types";
import {
  CORPUS_MANIFEST_LESS_DIR,
  CORPUS_PARTIAL_DIR,
  CORPUS_TORN_MANIFEST_DIR,
  CORPUS_V2_DIR,
  corpusCatalogEntries,
  corpusLegacySessions,
  corpusRows,
} from "../../testkit/catalogFixture";
import { compareCatalogKey, loadKey, pickBootPair } from "./bootPick";
import { storageDirName } from "./sessionAlias";

function corpusInput() {
  const sessions: CatalogSession[] = corpusCatalogEntries().map((entry) => ({
    ...entry.session,
    storage_path: entry.storagePath,
  }));
  const legacy = corpusLegacySessions();
  const analyzedByDir = new Map<string, boolean>();
  const invalidByDir = new Map<string, string>();
  for (const row of legacy) {
    if (row.status === "invalid") {
      invalidByDir.set(row.name, row.error ?? "недопустимая сессия");
      continue;
    }
    analyzedByDir.set(row.name, row.analyzed);
  }
  return { sessions, analyzedByDir, invalidByDir };
}

describe("pickBootPair: первый проанализированный в именованном порядке", () => {
  it("A — newest analyzed, B — следующий analyzed, оба dir-ключи дублей", () => {
    const pair = pickBootPair(corpusInput());

    expect(pair.a).toBe("sim-quiet-20261005-151028");
    expect(pair.b).toBe("sim-quiet-20261005-151017");
  });

  it("v2-каталог — первый кандидат (newest + analyzed)", () => {
    const pair = pickBootPair(corpusInput());

    expect(pair.a).toBe(CORPUS_V2_DIR);
  });

  it("manifest-less/partial/torn никогда не выбираются", () => {
    const pair = pickBootPair(corpusInput());

    expect([pair.a, pair.b]).not.toContain(CORPUS_MANIFEST_LESS_DIR);
    expect([pair.a, pair.b]).not.toContain(CORPUS_PARTIAL_DIR);
    expect([pair.a, pair.b]).not.toContain(CORPUS_TORN_MANIFEST_DIR);
  });

  it("нуль analyzed → честная null-пара, unanalyzed в A не фабрикуется", () => {
    const input = corpusInput();
    const denied = new Map<string, boolean>();
    for (const key of input.analyzedByDir.keys()) denied.set(key, false);

    const pair = pickBootPair({ ...input, analyzedByDir: denied });

    expect(pair).toEqual({ a: null, b: null });
  });

  it("один кандидат → B null, а не второй попавшийся unanalyzed", () => {
    const input = corpusInput();
    const single = new Map<string, boolean>([[CORPUS_V2_DIR, true]]);

    const pair = pickBootPair({ ...input, analyzedByDir: single });

    expect(pair).toEqual({ a: CORPUS_V2_DIR, b: null });
  });

  it("duplicate_id без dir кликабелен только по id — в boot не идёт", () => {
    const input = corpusInput();
    const broken: CatalogSession = {
      id: "syn-quiet-seed6022",
      health: "duplicate_id",
      created_utc: "2026-12-31T23:59:59Z",
      source: "disk",
      session_type: "simulate",
      profile: null,
      label: null,
      storage_path: null,
    };
    const analyzedByDir = new Map(input.analyzedByDir);
    analyzedByDir.set("syn-quiet-seed6022", true);

    const pair = pickBootPair({
      sessions: [broken, ...input.sessions],
      analyzedByDir,
      invalidByDir: input.invalidByDir,
    });

    expect(pair.a).toBe(CORPUS_V2_DIR);
    expect(pair.b).toBe("sim-quiet-20261005-151017");
  });
});

describe("compareCatalogKey: зеркало серверного keyset", () => {
  it("created DESC, затем id, затем storage_path", () => {
    const rows = corpusRows();
    const sorted = corpusCatalogEntries().map((entry) => entry.session);
    const resorted = [...sorted].sort(compareCatalogKey);

    expect(resorted.map((row) => row.id)).toEqual(sorted.map((row) => row.id));
    expect(rows.length).toBeGreaterThan(0);
  });

  it("стабилен при равных датах: id, затем путь", () => {
    const mk = (id: string, storage: string): CatalogSession => ({
      id,
      health: "ok",
      created_utc: "2026-08-05T10:00:00Z",
      source: "disk",
      session_type: "capture",
      profile: null,
      label: null,
      storage_path: storage,
    });
    const rows = [mk("b-id", "/r/b"), mk("a-id", "/r/a2"), mk("a-id", "/r/a1")];

    expect([...rows].sort(compareCatalogKey).map((row) => row.storage_path)).toEqual([
      "/r/a1",
      "/r/a2",
      "/r/b",
    ]);
  });
});

describe("loadKey: ключ загрузки пары", () => {
  it("duplicate_id → dir-name, остальные → id", () => {
    const entries = corpusCatalogEntries();
    const dup = entries.find((entry) => entry.session.health === "duplicate_id");
    const plain = entries.find(
      (entry) => entry.session.health === "ok" && entry.session.id !== null,
    );

    expect(dup).not.toBeUndefined();
    expect(plain).not.toBeUndefined();
    if (dup === undefined || plain === undefined) throw new Error("corpus shape changed");
    expect(loadKey({ ...dup.session, storage_path: dup.storagePath })).toBe(
      storageDirName(dup.storagePath),
    );
    expect(loadKey({ ...plain.session, storage_path: plain.storagePath })).toBe(plain.session.id);
  });
});
