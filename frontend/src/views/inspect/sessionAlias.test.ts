import { describe, expect, it } from "vitest";
import type { CatalogSession, SessionHealth } from "../../api/types";
import { buildSessionAlias, indexSessionMeta, storageDirName } from "./sessionAlias";

function session(
  id: string,
  storagePath: string | null,
  health: SessionHealth = "ok",
): CatalogSession {
  return {
    id,
    health,
    created_utc: "2026-09-05T10:00:00Z",
    source: "simulator",
    session_type: "rc_measurement",
    profile: "bad",
    label: null,
    storage_path: storagePath,
  };
}

describe("storageDirName", () => {
  it("posix-путь отдаёт последний сегмент", () => {
    expect(storageDirName("/data/sessions/dirname-differs")).toBe("dirname-differs");
  });

  it("windows-путь отдаёт последний сегмент", () => {
    expect(storageDirName("C:\\lnt-sessions\\f3-bad-a")).toBe("f3-bad-a");
  });

  it("завершающий разделитель не мешает", () => {
    expect(storageDirName("/data/sessions/f3-bad-a/")).toBe("f3-bad-a");
  });

  it("null/пусто/корень — без имени каталога", () => {
    expect(storageDirName(null)).toBeNull();
    expect(storageDirName(undefined)).toBeNull();
    expect(storageDirName("")).toBeNull();
    expect(storageDirName("/")).toBeNull();
  });
});

describe("buildSessionAlias", () => {
  it("имя каталога указывает на manifest id (D1: оба ключа)", () => {
    const alias = buildSessionAlias([session("syn-quiet-seed777", "/root/dirname-differs")]);
    expect(alias.get("dirname-differs")).toBe("syn-quiet-seed777");
  });

  it("не плодит алиас, когда имя каталога равно id", () => {
    const alias = buildSessionAlias([session("sim-001", "/sessions/sim-001")]);
    expect(alias.has("sim-001")).toBe(false);
  });

  it("без storage_path алиасов нет", () => {
    expect(buildSessionAlias([session("x", null)]).size).toBe(0);
  });

  it("F-8: строки duplicate_id не попадают в карту — id неоднозначен (409)", () => {
    const alias = buildSessionAlias([
      session("syn-quiet-seed6022", "/root/sim-quiet-a", "duplicate_id"),
      session("syn-quiet-seed6022", "/root/sim-quiet-b", "duplicate_id"),
    ]);
    expect(alias.size).toBe(0);
  });

  it("F-8: однозначные строки канонизируются и рядом с дублями", () => {
    const alias = buildSessionAlias([
      session("syn-quiet-seed777", "/root/dirname-differs"),
      session("syn-quiet-seed6022", "/root/sim-quiet-a", "duplicate_id"),
    ]);
    expect([...alias.keys()]).toEqual(["dirname-differs"]);
    expect(alias.get("dirname-differs")).toBe("syn-quiet-seed777");
  });
});

describe("indexSessionMeta", () => {
  it("строку видно и по manifest id, и по имени каталога (D1)", () => {
    const map = new Map<string, CatalogSession>();
    const row = session("syn-quiet-seed6022", "/root/sim-quiet-a", "duplicate_id");
    indexSessionMeta(map, row);
    expect(map.get("syn-quiet-seed6022")).toBe(row);
    expect(map.get("sim-quiet-a")).toBe(row);
  });

  it("дубль-id: у каждой строки своё имя каталога, id-ключ не перезаписывает имя", () => {
    const map = new Map<string, CatalogSession>();
    const first = session("syn-quiet-seed6022", "/root/sim-quiet-a", "duplicate_id");
    const second = session("syn-quiet-seed6022", "/root/sim-quiet-b", "duplicate_id");
    indexSessionMeta(map, first);
    indexSessionMeta(map, second);
    expect(map.get("sim-quiet-a")).toBe(first);
    expect(map.get("sim-quiet-b")).toBe(second);
  });

  it("имя каталога не вытесняет существующий ключ", () => {
    const map = new Map<string, CatalogSession>();
    const byId = session("sess-a", "/root/sess-a");
    const byDir = session("syn-x", "/root/sess-a");
    indexSessionMeta(map, byId);
    indexSessionMeta(map, byDir);
    expect(map.get("sess-a")).toBe(byId);
  });
});
