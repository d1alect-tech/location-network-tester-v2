/** Сводка и теги инспектора: плитки с фактами, недоступное — словом
 * «недоступно» с причиной в title; пустые теги — «Тегов нет». */

import { describe, expect, it } from "vitest";
import { EMPTY_METRICS, type SessionMetrics } from "./contextMetrics";
import { renderHealthRow, renderReadouts, renderTagsSection } from "./contextSummary";

const META = {
  id: "cap-20260805-180623-a1b2",
  createdUtc: "2026-08-05T18:06:23Z",
  sessionHealth: "ok",
};

function metrics(partial: Partial<SessionMetrics>): SessionMetrics {
  return { ...EMPTY_METRICS, ...partial };
}

describe("renderReadouts", () => {
  it("идентификатор и полная дата читаются в плитках", () => {
    const grid = renderReadouts(META, EMPTY_METRICS);
    expect(grid.className).toContain("lnt-cat-session-summary");
    expect(grid.textContent).toContain(META.id);
    expect(grid.textContent).toContain("5 августа 2026");
  });

  it("сессия без даты показывает прочерк, не NaN и не эпоху", () => {
    const grid = renderReadouts({ ...META, createdUtc: null }, EMPTY_METRICS);
    expect(grid.textContent).not.toContain("NaN");
    expect(grid.textContent).not.toContain("1970");
    expect(grid.textContent).toContain("—");
  });

  it("недоступные длительность и частота подписаны причиной", () => {
    const grid = renderReadouts(META, EMPTY_METRICS);
    const unavailable = grid.querySelectorAll(".is-unavailable");
    expect(unavailable.length).toBe(2);
    expect(unavailable[0]?.getAttribute("title")).toBe(EMPTY_METRICS.durationReason);
  });

  it("значения форматируются по-русски с единицами", () => {
    const grid = renderReadouts(META, metrics({ durationS: 12.4, mainsHz: 50.02 }));
    expect(grid.textContent).toContain("12,4 с");
    expect(grid.textContent).toContain("50,02 Гц");
  });
});

describe("renderHealthRow", () => {
  it("пилюля несёт код здоровья и русскую подпись, строка — ревизию", () => {
    const row = renderHealthRow("context_invalid", 0, META);
    const pill = row.querySelector("[data-cat-context-health='context_invalid']");
    expect(pill?.textContent).toContain("Контекст: Повреждён");
    expect(row.querySelector("[data-cat-revision='0']")?.textContent).toContain("ревизия 0");
    expect(row.textContent).toContain("сессия: Исправна");
  });

  it("неизвестный код здоровья показывается как есть, тон предупреждения", () => {
    const row = renderHealthRow("context_strange", 1, META);
    expect(row.querySelector(".lnt-status-pill")?.textContent).toContain(
      "Контекст: context_strange",
    );
    expect(row.querySelector(".lnt-tone-warn")).not.toBeNull();
  });
});

describe("renderTagsSection", () => {
  it("пустые теги — подпись, а не пустая строка чипов", () => {
    expect(renderTagsSection([]).querySelector(".tag-empty")?.textContent).toBe("Тегов нет");
  });

  it("чипы несут тег текстом и в title", () => {
    const section = renderTagsSection(["контроль", "ночная-серия"]);
    const chips = section.querySelectorAll(".tag-chip");
    expect(chips.length).toBe(2);
    expect(chips[0]?.textContent).toBe("контроль");
    expect(chips[1]?.getAttribute("title")).toBe("ночная-серия");
  });
});
