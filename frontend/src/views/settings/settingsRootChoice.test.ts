import { describe, expect, it } from "vitest";
import { folderRestartCommand } from "./settingsRootChoice";

describe("folderRestartCommand", () => {
  it("wraps a plain path in double quotes", () => {
    expect(folderRestartCommand("D:\\lnt-sessions")).toBe(
      'uv run lnt ui --root "D:\\lnt-sessions"',
    );
  });

  it("quotes paths with spaces and Cyrillic", () => {
    expect(folderRestartCommand("D:\\мои сессии\\розетка А")).toBe(
      'uv run lnt ui --root "D:\\мои сессии\\розетка А"',
    );
  });

  it("trims surrounding whitespace before quoting", () => {
    expect(folderRestartCommand("  D:\\lnt-sessions  ")).toBe(
      'uv run lnt ui --root "D:\\lnt-sessions"',
    );
  });

  it("quotes UNC paths", () => {
    expect(folderRestartCommand("\\\\server\\share")).toBe(
      'uv run lnt ui --root "\\\\server\\share"',
    );
  });
});
