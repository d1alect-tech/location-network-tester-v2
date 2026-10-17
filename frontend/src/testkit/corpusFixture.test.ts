/** Smoke-спека корпус-фикстуры (ui-refactor-3 задача 1, prerequisite C7).
 *
 * Доказывает, что единый мок выражает грязный корпус владельца: include_paths
 * отвечает storage_path на строку, три сиблинга duplicate_id различимы путём,
 * detail-флаги честные (analysis:null + false-пермутации), manifest-less и
 * битый каталог видны в health и отсутствуют в legacy-списке. Вызовы
 * handleRequest синхронны: sleep-ассертов нет. */

import { describe, expect, it } from "vitest";
import type { CatalogPage, LegacySessionsPayload } from "../api/types";
import type { SessionDetailPayload } from "../api/types-plots";
import { buildSessionAlias, storageDirName } from "../views/inspect/sessionAlias";
import {
  CORPUS_DUPLICATE_SESSION_ID,
  CORPUS_MANIFEST_LESS_DIR,
  CORPUS_PARTIAL_DIR,
  CORPUS_TORN_MANIFEST_DIR,
  CORPUS_V2_ARTIFACT_KEY,
  CORPUS_V2_DIR,
  type CorpusRow,
  corpusRows,
  corpusSessions,
} from "./catalogFixture";
import { MockLntBackend } from "./mockBackend";
import type { MockHttpReply } from "./mockHttp";

/** Тела запросов спека не отправляет: любой вызов — ошибка тестовой логики. */
function noBody(): never {
  throw new Error("корпус-спека отправляет только GET");
}

function get(backend: MockLntBackend, path: string, search = ""): MockHttpReply | null {
  return backend.handleRequest({
    method: "GET",
    path,
    searchParams: new URLSearchParams(search),
    nonceOk: false,
    bodyJson: noBody,
  });
}

function bodyOf<T>(reply: MockHttpReply | null): T {
  if (reply === null) throw new Error("мок не ответил: маршрут не найден");
  return reply.body as T;
}

function corpusBackend(rows: readonly CorpusRow[] = corpusRows()): MockLntBackend {
  return new MockLntBackend({ corpus: rows });
}

const CATALOG_QUERY = "page_size=200";

function catalogItems(backend: MockLntBackend, includePaths = true): CatalogPage["items"] {
  const search = includePaths ? `${CATALOG_QUERY}&include_paths=true` : CATALOG_QUERY;
  return bodyOf<CatalogPage>(get(backend, "/api/catalog/sessions", search)).items;
}

function legacyPayload(backend: MockLntBackend): LegacySessionsPayload {
  return bodyOf<LegacySessionsPayload>(get(backend, "/api/sessions"));
}

function detailOf(backend: MockLntBackend, key: string): SessionDetailPayload {
  return bodyOf<SessionDetailPayload>(get(backend, `/api/sessions/${encodeURIComponent(key)}`));
}

/** Пять отказов анализатора реального корпуса: ch2 есть, metrics.json нет. */
const REFUSED_CH2_DIRS = [
  "cap-20260805-163913",
  "cap-20260805-163923",
  "cap-20260805-180623",
  "cap-20260806-093821",
  "first-capture",
];

describe("корпус-фикстура: include_paths → storage_path", () => {
  it("тройка duplicate_id: один session_id, три разных storage_path", () => {
    const backend = corpusBackend();
    const twins = catalogItems(backend).filter((row) => row.id === CORPUS_DUPLICATE_SESSION_ID);

    expect(twins).toHaveLength(3);
    const dirs = twins.map((row) => storageDirName(row.storage_path));
    expect(new Set(dirs).size).toBe(3);
    expect(dirs).toContain(CORPUS_V2_DIR);
    expect(twins.every((row) => row.health === "duplicate_id")).toBe(true);
  });

  it("include_paths=true даёт путь хранения каждой строке", () => {
    const backend = corpusBackend();
    const items = catalogItems(backend);

    expect(items).toHaveLength(corpusRows().length);
    expect(items.every((row) => typeof row.storage_path === "string")).toBe(true);
    expect(items.every((row) => (row.storage_path ?? "") !== "")).toBe(true);
  });

  it("v2-артефакт несёт ровно один каталог, указатель отдаётся по имени каталога", () => {
    const backend = corpusBackend();
    const carriers = corpusRows().filter((row) => row.analysisV2);
    expect(carriers).toHaveLength(1);
    expect(carriers[0]?.dir).toBe(CORPUS_V2_DIR);

    const dir = encodeURIComponent(CORPUS_V2_DIR);
    const reply = get(backend, `/api/analysis/sessions/${dir}/.lnt-default-analysis.json`);
    expect(reply?.status).toBe(200);
    expect(bodyOf<{ artifact_key: string }>(reply).artifact_key).toBe(CORPUS_V2_ARTIFACT_KEY);
  });

  it("dir-имена корпуса читаются product-алиасом, duplicate_id не канонизируется", () => {
    const backend = corpusBackend();
    const items = catalogItems(backend);
    const alias = buildSessionAlias(items);

    // sessionAlias.ts:17 (прецедент F-8): строки duplicate_id пропускаются —
    // их id неоднозначен, ключ остаётся именем каталога.
    expect(alias.get(CORPUS_V2_DIR)).toBeUndefined();
    expect(alias.get("cap-20260806-093843")).toBe("cap-20260806-093846-0014c40f");
    // Каталог без манифеста ключуется именем каталога → алиасом не становится.
    expect(alias.get(CORPUS_MANIFEST_LESS_DIR)).toBeUndefined();
    expect(storageDirName(items[0]?.storage_path)).toBe(CORPUS_V2_DIR);
  });
});

describe("корпус-фикстура: include_paths=false и legacy-потребители", () => {
  it("без include_paths строки НЕ несут storage_path", () => {
    const backend = corpusBackend();
    const items = catalogItems(backend, false);

    expect(items).toHaveLength(corpusRows().length);
    expect(items.some((row) => "storage_path" in row)).toBe(false);
    expect(corpusSessions().some((row) => "storage_path" in row)).toBe(false);
  });

  it("include_paths не трогает legacy /api/sessions", () => {
    const backend = corpusBackend();
    const before = legacyPayload(backend);
    catalogItems(backend, true);
    const after = legacyPayload(backend);

    expect(after).toEqual(before);
    expect(after.sessions.some((row) => "storage_path" in row)).toBe(false);
  });

  it("явно сидированный storage_path строки сохраняется без include_paths", () => {
    const backend = new MockLntBackend();
    backend.seedCatalog([
      {
        id: "written-session",
        health: "ok",
        created_utc: "2026-09-05T10:00:00Z",
        source: "simulator",
        session_type: "rc_measurement",
        profile: "bad",
        label: null,
        storage_path: "/sessions/written-session",
      },
    ]);

    const items = catalogItems(backend, false);
    expect(items[0]?.storage_path).toBe("/sessions/written-session");
    expect(catalogItems(backend, true)[0]?.storage_path).toBe("/sessions/written-session");
  });

  it("старая генератор-фикстура получает путь только по include_paths", () => {
    const backend = new MockLntBackend({ catalogSize: 5 });

    expect(catalogItems(backend, false).some((row) => "storage_path" in row)).toBe(false);
    const withPaths = catalogItems(backend, true);
    expect(withPaths).toHaveLength(5);
    expect(withPaths[0]?.storage_path).toBe(`/sessions/${withPaths[0]?.id}`);
  });
});

describe("корпус-фикстура: грязные строки и честные detail-флаги", () => {
  it("≥5 непроанализированных строк: health «ok», analyzed false, analysis:null", () => {
    const backend = corpusBackend();
    const legacy = legacyPayload(backend).sessions;
    const items = catalogItems(backend);

    expect(legacy.filter((row) => !row.analyzed).length).toBeGreaterThanOrEqual(5);
    for (const dir of REFUSED_CH2_DIRS) {
      const row = items.find((item) => storageDirName(item.storage_path) === dir);
      // C1: health-эндпоинт сказал бы «ok» — analyzed обязан идти из JOIN.
      expect(row?.health).toBe("ok");
      expect(legacy.find((item) => item.name === dir)?.analyzed).toBe(false);

      const detail = detailOf(backend, dir);
      expect(detail.name).toBe(dir);
      expect(detail.analysis).toBeNull();
      expect(detail.spectrum_available).toBe(false);
      expect(detail.waveform_available).toBe(true);
      expect(detail.ch2_available).toBe(true);
    }
  });

  it("manifest-less строка видна в каталоге и отсутствует в legacy-списке", () => {
    const backend = corpusBackend();
    const row = catalogItems(backend).find((item) => item.id === CORPUS_MANIFEST_LESS_DIR);

    expect(row?.health).toBe("corrupt_manifest");
    expect(storageDirName(row?.storage_path)).toBe(CORPUS_MANIFEST_LESS_DIR);
    expect(legacyPayload(backend).sessions.map((item) => item.name)).not.toContain(
      CORPUS_MANIFEST_LESS_DIR,
    );
    // detail-200 невозможен: честный 404 вместо сфабрикованного ответа.
    expect(
      get(backend, `/api/sessions/${encodeURIComponent(CORPUS_MANIFEST_LESS_DIR)}`)?.status,
    ).toBe(404);
  });

  it("битый каталог присутствует в health и пропущен legacy-списком", () => {
    const backend = corpusBackend();
    const row = catalogItems(backend).find((item) => item.id === CORPUS_PARTIAL_DIR);
    const names = legacyPayload(backend).sessions.map((item) => item.name);

    expect(row?.health).toBe("partial");
    expect(names).not.toContain(CORPUS_PARTIAL_DIR);
  });

  it("битый манифест: legacy status invalid + error, summary null", () => {
    const backend = corpusBackend();
    const row = legacyPayload(backend).sessions.find(
      (item) => item.name === CORPUS_TORN_MANIFEST_DIR,
    );

    expect(row?.status).toBe("invalid");
    expect(row?.analyzed).toBe(false);
    expect(row?.summary).toBeNull();
    expect(typeof row?.error).toBe("string");
    expect(catalogItems(backend).find((item) => item.id === CORPUS_TORN_MANIFEST_DIR)?.health).toBe(
      "corrupt_manifest",
    );
  });

  it("пермутации флагов: analyzed без spectrum.csv и line_quality без spectrum", () => {
    const backend = corpusBackend();
    const noSpectrum = detailOf(backend, "cap-20260805-212516");
    expect(noSpectrum.analysis).not.toBeNull();
    expect(noSpectrum.spectrum_available).toBe(false);
    expect(noSpectrum.waveform_available).toBe(true);
    expect(noSpectrum.ch2_available).toBe(false);

    // line_quality: analyzed БЕЗ spectrum.csv (sessions.py:88-90).
    expect(
      legacyPayload(backend).sessions.find((item) => item.name === "qa-line-quality")?.analyzed,
    ).toBe(true);
    const lineQuality = detailOf(backend, "qa-line-quality");
    expect(lineQuality.analysis).not.toBeNull();
    expect(lineQuality.spectrum_available).toBe(false);
  });

  it("проанализированная строка: полный набор флагов без выдуманных метрик", () => {
    const backend = corpusBackend();
    const detail = detailOf(backend, "cap-20260806-093843");

    expect(detail.analysis).not.toBeNull();
    expect(detail.spectrum_available).toBe(true);
    expect(detail.waveform_available).toBe(true);
    expect(detail.ch2_available).toBe(false);
    expect(
      legacyPayload(backend).sessions.find((item) => item.name === "cap-20260806-093843")?.analyzed,
    ).toBe(true);
  });

  it("неоднозначный session_id даёт 409, имя каталога — 200", () => {
    const backend = corpusBackend();
    const ambiguous = encodeURIComponent(CORPUS_DUPLICATE_SESSION_ID);

    expect(get(backend, `/api/sessions/${ambiguous}`)?.status).toBe(409);
    expect(get(backend, `/api/sessions/${ambiguous}/spectrum`)?.status).toBe(409);
    expect(get(backend, `/api/sessions/${ambiguous}/waveform`)?.status).toBe(409);

    const byDir = get(backend, `/api/sessions/${encodeURIComponent(CORPUS_V2_DIR)}`);
    expect(byDir?.status).toBe(200);
    const detail = bodyOf<SessionDetailPayload>(byDir);
    expect(detail.ch2_available).toBe(true);
    expect(detail.spectrum_available).toBe(true);
    // Однозначный session_id резолвится без 409.
    expect(get(backend, `/api/sessions/${encodeURIComponent("qa-line-quality")}`)?.status).toBe(
      200,
    );
  });

  it("порядок строк — keyset бэкенда: created_utc DESC, session_id, storage_path", () => {
    const backend = corpusBackend();
    const items = catalogItems(backend);
    const created = items.map((row) => row.created_utc ?? "");

    for (let index = 1; index < created.length; index += 1) {
      const previous = created[index - 1] ?? "";
      const current = created[index] ?? "";
      expect(previous >= current).toBe(true);
    }
    // Строки без даты идут последними, внутри — по id (имени каталога), ASCII.
    expect(items.slice(-3).map((row) => row.id)).toEqual([
      CORPUS_PARTIAL_DIR,
      CORPUS_MANIFEST_LESS_DIR,
      CORPUS_TORN_MANIFEST_DIR,
    ]);
    expect(
      bodyOf<CatalogPage>(get(backend, "/api/catalog/sessions", CATALOG_QUERY)).next_cursor,
    ).toBeNull();
  });

  it("legacy-ряды ключуются именами каталогов в порядке имен", () => {
    const backend = corpusBackend();
    const names = legacyPayload(backend).sessions.map((row) => row.name);

    expect(names).toEqual([...names].sort());
    expect(names).not.toContain(CORPUS_MANIFEST_LESS_DIR);
    expect(names).not.toContain(CORPUS_PARTIAL_DIR);
    expect(names).toContain(CORPUS_V2_DIR);
    expect(names.every((name) => !name.includes("/") && !name.includes("\\"))).toBe(true);
  });
});
