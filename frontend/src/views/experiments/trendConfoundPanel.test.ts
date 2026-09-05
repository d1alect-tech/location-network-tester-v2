/** C1: trendConfoundPanel — панель смешивающих факторов байт-в-байт
 * как в trendView.ts (RED: модулей пока нет). */
import { describe, expect, it } from "vitest";
import {
  buildTrendConfoundPanel,
  readTrendConfoundFromRoot,
  renderTrendConfoundChecklist,
} from "./trendConfoundPanel";

describe("readTrendConfoundFromRoot", () => {
  it("returns an empty checklist by default", () => {
    expect(readTrendConfoundFromRoot()).toEqual([]);
  });
});

describe("buildTrendConfoundPanel", () => {
  it("shows an explicit empty-checklist note", () => {
    const panel = buildTrendConfoundPanel([]);
    expect(panel.className).toContain("lnt-exp-confound-host");
    expect(panel.textContent).toContain("Смешивающие факторы");
    expect(panel.textContent).toContain("Чек-лист смешивающих факторов пуст.");
  });

  it("marks unchecked items as non-interpretable, verbatim", () => {
    const panel = buildTrendConfoundPanel([
      { key: "освещение", checked: false, note: "окна без штор" },
      { key: "прогрев", checked: true },
      { key: "питание", checked: false },
    ]);
    const text = panel.textContent ?? "";
    expect(text).toContain("освещение: НЕ проверен — окна без штор");
    expect(text).toContain("прогрев: проверен");
    expect(text).toContain(
      "питание: НЕ проверен · неконтролируемый смешивающий фактор делает связь неинтерпретируемой",
    );
  });
});

describe("renderTrendConfoundChecklist", () => {
  it("removes the host and appends nothing for an empty checklist", () => {
    const root = document.createElement("div");
    root.append(buildTrendConfoundPanel([{ key: "освещение", checked: true }]));

    renderTrendConfoundChecklist(root, []);

    expect(root.querySelector(".lnt-exp-confound-host")).toBeNull();
  });

  it("replaces the previous host with the new checklist", () => {
    const root = document.createElement("div");
    root.append(buildTrendConfoundPanel([{ key: "старый", checked: true }]));

    renderTrendConfoundChecklist(root, [{ key: "новый", checked: false }]);

    expect(root.querySelectorAll(".lnt-exp-confound-host").length).toBe(1);
    expect(root.textContent).toContain("новый: НЕ проверен");
    expect(root.textContent).not.toContain("старый");
  });
});
