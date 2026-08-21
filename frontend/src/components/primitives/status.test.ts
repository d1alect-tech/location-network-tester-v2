import { beforeEach, describe, expect, it } from "vitest";
import { announcePolite, createJobProgress } from "./status";

describe("createJobProgress", () => {
  beforeEach(() => {
    document.body.textContent = "";
  });

  it("renders stage i/N with progressbar semantics", () => {
    const progress = createJobProgress();
    progress.setStage("Запись", 2, 5);
    const bar = progress.root.querySelector('[role="progressbar"]');
    expect(bar).not.toBeNull();
    expect(bar?.getAttribute("aria-valuenow")).toBe("2");
    expect(bar?.getAttribute("aria-valuemax")).toBe("5");
    expect(progress.root.textContent).toContain("Запись: 2 из 5");
  });

  it("indeterminate mode sets aria-busy and announces politely", () => {
    const progress = createJobProgress();
    progress.setIndeterminate("Подготовка устройства…");
    const bar = progress.root.querySelector('[role="progressbar"]');
    expect(bar?.getAttribute("aria-busy")).toBe("true");
    expect(bar?.hasAttribute("aria-valuenow")).toBe(false);
    const live = document.querySelector('[aria-live="polite"]');
    expect(live?.textContent).toContain("Подготовка устройства…");
  });

  it("done() reports completion in Russian", () => {
    const progress = createJobProgress();
    progress.done();
    expect(progress.root.textContent).toContain("Готово");
  });
});

describe("announcePolite", () => {
  beforeEach(() => {
    document.body.textContent = "";
  });

  it("writes into a single polite live region", () => {
    announcePolite("Сессия сохранена");
    announcePolite("Ошибка сети");
    const regions = document.querySelectorAll('[role="status"][aria-live="polite"]');
    expect(regions.length).toBe(1);
    expect(regions[0]?.textContent).toBe("Ошибка сети");
  });
});
