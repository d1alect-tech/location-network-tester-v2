import { describe, expect, it } from "vitest";
import { privacyGroups, supportBundleGuidance, validateRootNote } from "./settingsModel";

describe("privacyGroups", () => {
  it("mirrors metadata_collector semantics: automatic, opt-in and never groups", () => {
    const groups = privacyGroups();
    expect(groups.map((group) => group.id)).toEqual(["automatic", "opt_in", "never"]);
    const automatic = groups[0];
    if (!automatic) throw new Error("нет группы automatic");
    const keys = automatic.items.map((item) => item.key);
    // Поля из lnt/metadata_collector.py (_base_fields + _telemetry_fields).
    expect(keys.some((key) => key.includes("device.vid"))).toBe(true);
    expect(keys.some((key) => key.includes("os.timezone"))).toBe(true);
    expect(keys.some((key) => key.includes("front_end"))).toBe(true);
    expect(keys.some((key) => key.startsWith("acquisition."))).toBe(true);
  });

  it("private notes are opt-in with the exact CLI flag", () => {
    const groups = privacyGroups();
    const optIn = groups.find((group) => group.id === "opt_in");
    if (!optIn) throw new Error("нет группы opt_in");
    const notes = optIn.items.find((item) => item.key.includes("заметки"));
    expect(notes?.detail).toContain("--include-private-notes");
  });

  it("raw captures and config values are declared never-collected", () => {
    const groups = privacyGroups();
    const never = groups.find((group) => group.id === "never");
    if (!never) throw new Error("нет группы never");
    const keys = never.items.map((item) => item.key).join(" ");
    expect(keys).toContain("сырые захваты");
    expect(keys).toContain("конфигурации");
  });
});

describe("supportBundleGuidance", () => {
  it("reports panel job route available and keeps the exact CLI command", () => {
    const guidance = supportBundleGuidance();
    expect(guidance.httpAvailable).toBe(true);
    expect(guidance.command).toContain("lnt support-bundle");
    expect(guidance.flags.map((flag) => flag.flag)).toEqual([
      "--include-private-notes",
      "--no-logs",
    ]);
    expect(guidance.contents.join("\n")).toContain("dependencies.json");
    expect(guidance.manifestNote).toContain("SHA-256");
  });
});

describe("validateRootNote", () => {
  it("accepts empty and plain single-line paths", () => {
    expect(validateRootNote("")).toEqual({ ok: true, error: null });
    expect(validateRootNote("D:\\lnt-sessions")).toEqual({ ok: true, error: null });
  });

  it("rejects multiline, overlong and invalid-character notes", () => {
    expect(validateRootNote("a\nb").ok).toBe(false);
    expect(validateRootNote(`${"x".repeat(201)}"`).ok).toBe(false);
    expect(validateRootNote("D:\\ses|rm").ok).toBe(false);
  });
});
