/** Задача 14 RED: чип + stateless listbox (частота, 7 опций > 5). Меню
 * принадлежит только своему чипу: Esc/клик мимо закрывают БЕЗ изменений
 * чужих контролов; опция-цель помечена «→»; aria-selected = применённое;
 * слот [data-slot] показывает ПРИМЕНЁННОЕ значение — staged-цель НИКОГДА
 * не рендерится как текущая (AC5/негативный сценарий). */

import { afterEach, describe, expect, it } from "vitest";
import { createLiveChip, paintLiveChip } from "./liveChip";

function button(root: ParentNode, selector: string): HTMLButtonElement {
  const node = root.querySelector(selector);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`нет кнопки ${selector}`);
  return node;
}

const OPTIONS = [
  { value: "100000", text: "100 кГц" },
  { value: "2000000", text: "2 МГц" },
  { value: "8000000", text: "8 МГц" },
];

function mountChip(): { chip: ReturnType<typeof createLiveChip>; picks: string[] } {
  const picks: string[] = [];
  const chip = createLiveChip(
    {
      key: "rate",
      aria: "Частота дискретизации",
      options: OPTIONS,
      current: "8000000",
      menuTitle: "Частота · применяется при запуске",
    },
    (value) => picks.push(value),
  );
  document.body.append(chip.root);
  return { chip, picks };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("createLiveChip", () => {
  it("слот показывает применённое значение; меню закрыто, haspopup объявлен", () => {
    const { chip } = mountChip();
    const slot = chip.root.querySelector("[data-slot='rate']");
    expect(slot?.textContent).toBe("8 МГц");
    const menu = chip.root.querySelector("[role='listbox']");
    expect(menu).toBeInstanceOf(HTMLElement);
    expect((menu as HTMLElement).hidden).toBe(true);
    expect(chip.root.querySelector(".lnt-live-chip-btn")?.getAttribute("aria-haspopup")).toBe(
      "listbox",
    );
  });

  it("клик по чипу открывает меню, клик мимо закрывает без изменений", () => {
    const { chip, picks } = mountChip();
    const menu = chip.root.querySelector<HTMLElement>("[role='listbox']");
    button(chip.root, ".lnt-live-chip-btn").click();
    expect(menu?.hidden).toBe(false);
    // Клик мимо (document) — закрыть, ничего не выбрать.
    document.body.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
    expect(menu?.hidden).toBe(true);
    expect(picks).toEqual([]);
  });

  it("выбор опции зовёт onPick, закрывает меню, слот НЕ меняется (staged ≠ текущее)", () => {
    const { chip, picks } = mountChip();
    button(chip.root, ".lnt-live-chip-btn").click();
    button(chip.root, "[role='option'][data-value='2000000']").click();
    expect(picks).toEqual(["2000000"]);
    const menu = chip.root.querySelector<HTMLElement>("[role='listbox']");
    expect(menu?.hidden).toBe(true);
    // Негативный (AC4/AC5): staged-число НЕ в элементе текущего значения.
    expect(chip.root.querySelector("[data-slot='rate']")?.textContent).toBe("8 МГц");
  });

  it("Esc закрывает меню stateless: без выбора и без изменений", () => {
    const { chip, picks } = mountChip();
    const menu = chip.root.querySelector<HTMLElement>("[role='listbox']");
    button(chip.root, ".lnt-live-chip-btn").click();
    menu?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(menu?.hidden).toBe(true);
    expect(picks).toEqual([]);
  });

  it("опция-цель помечена «→»; paintApplied переводит слот и aria-selected", () => {
    const { chip } = mountChip();
    chip.markTarget("2000000");
    const target = chip.root.querySelector<HTMLElement>("[role='option'][data-value='2000000']");
    expect(target?.querySelector<HTMLElement>(".lnt-live-opt-mark")?.hidden).toBe(false);
    expect(
      chip.root
        .querySelector("[role='option'][data-value='8000000']")
        ?.getAttribute("aria-selected"),
    ).toBe("true");
    // Применение: слот обновляется, метка гаснет.
    chip.paintApplied("2000000");
    expect(chip.root.querySelector("[data-slot='rate']")?.textContent).toBe("2 МГц");
    expect(target?.querySelector<HTMLElement>(".lnt-live-opt-mark")?.hidden).toBe(true);
    expect(target?.getAttribute("aria-selected")).toBe("true");
  });
});

describe("paintLiveChip (модульная покраска по хосту)", () => {
  it("сохраняет внешнее применённое значение и цель при повторном открытии", () => {
    const { chip } = mountChip();
    paintLiveChip(chip.root, "2000000", "100000");
    button(chip.root, ".lnt-live-chip-btn").click();
    expect(chip.root.querySelector('[aria-selected="true"]')?.getAttribute("data-value")).toBe(
      "2000000",
    );
    expect(document.activeElement?.getAttribute("data-value")).toBe("100000");
  });

  it("красит слот/aria-selected/метку цели по хосту зоны", () => {
    const { chip } = mountChip();
    paintLiveChip(chip.root, "2000000", "100000");
    expect(chip.root.querySelector("[data-slot='rate']")?.textContent).toBe("2 МГц");
    expect(
      chip.root
        .querySelector(".lnt-live-opt-mark:not([hidden])")
        ?.closest("[role='option']")
        ?.getAttribute("data-value"),
    ).toBe("100000");
  });
});
