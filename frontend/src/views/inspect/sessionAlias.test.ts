import { describe, expect, it } from "vitest";
import type { CatalogSession } from "../../api/types";
import { buildSessionAlias, storageDirName } from "./sessionAlias";

function session(id: string, storagePath: string | null): CatalogSession {
  return {
    id,
    health: "ok",
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
});
