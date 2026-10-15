/** Todo 11 RED: экран осциллографа — послесвечение и прокрутка истории.
 * Покрывается: монтирование панели с канвас-слоями и тумблером (вкл по
 * умолчанию), кадры двигают ползунок истории и подпись кадра, прокрутка
 * назад показывает прошлый кадр и возвращает «Живой», тумблер помнит
 * выключение в localStorage. Канвас в jsdom пуст — жертв проверяется на
 * уровне состояний; живопись — paint-модуль и e2e (todo 19). */

import { afterEach, describe, expect, it } from "vitest";
import type { LiveFramePayload } from "../../api/types-live";
import { SCOPE_PERSISTENCE_STORAGE_KEY, buildScopeScreen } from "./scopeScreen";

function frame(index: number): LiveFramePayload {
  const points = 8;
  const time_s: number[] = [];
  const voltage_v: number[] = [];
  for (let i = 0; i < points; i += 1) {
    time_s.push((i / points) * 0.001);
    voltage_v.push(Math.sin((i / points) * Math.PI * 2));
  }
  return {
    frame_index: index,
    triggered: true,
    emitted_at_s: index / 30,
    dropped_samples: 0,
    skipped_frames: 0,
    sample_rate_hz: 8_000_000,
    frame_samples: 4096,
    decimated: true,
    calibration_used: false,
    ch1: { time_s, voltage_v, point_count: points },
    ch2: { time_s: [...time_s], voltage_v: voltage_v.map((v) => v / 2), point_count: points },
  };
}

afterEach(() => {
  window.localStorage.removeItem(SCOPE_PERSISTENCE_STORAGE_KEY);
});

describe("buildScopeScreen: панель экрана (Todo 11)", () => {
  it("монтирует вьюпорт с двумя канвас-слоями и тумблер послесвечения (вкл)", () => {
    const screen = buildScopeScreen();

    expect(screen.root.querySelector(".lnt-scope-viewport")).toBeInstanceOf(HTMLElement);
    expect(screen.root.querySelector(".lnt-scope-persistence")).toBeInstanceOf(HTMLCanvasElement);
    expect(screen.root.querySelector(".lnt-scope-screen-trace")).toBeInstanceOf(HTMLCanvasElement);
    const persistSeg = screen.root.querySelector("#lnt-scope-persist");
    expect(persistSeg?.querySelector('[data-value="on"]')?.getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(screen.isPersistenceOn()).toBe(true);
    const slider = screen.root.querySelector("#lnt-scope-history") as HTMLInputElement;
    expect(slider.value).toBe("0");
    expect(slider.max).toBe("0");
    expect(screen.historyOffset()).toBe(0);
    const live = screen.root.querySelector("#lnt-scope-live") as HTMLButtonElement;
    expect(live.disabled).toBe(true);
  });

  it("кадры растят ползунок истории и подпись живого кадра", () => {
    const screen = buildScopeScreen();
    const note = screen.root.querySelector(".lnt-scope-screen-note") as HTMLElement;

    screen.applyFrame(frame(1));
    screen.applyFrame(frame(2));
    screen.applyFrame(frame(3));

    const slider = screen.root.querySelector("#lnt-scope-history") as HTMLInputElement;
    expect(slider.max).toBe("2");
    expect(note.textContent).toContain("кадр 3");
    expect(note.textContent).toContain("живой");
    const live = screen.root.querySelector("#lnt-scope-live") as HTMLButtonElement;
    expect(live.disabled).toBe(true);
  });

  it("прокрутка назад показывает прошлый кадр; «Живой» возвращает текущий", () => {
    const screen = buildScopeScreen();
    for (const i of [1, 2, 3, 4, 5]) screen.applyFrame(frame(i));
    const note = screen.root.querySelector(".lnt-scope-screen-note") as HTMLElement;
    const slider = screen.root.querySelector("#lnt-scope-history") as HTMLInputElement;
    const live = screen.root.querySelector("#lnt-scope-live") as HTMLButtonElement;

    // When: ползунок отводится на 2 кадра назад.
    slider.value = "2";
    slider.dispatchEvent(new Event("input", { bubbles: true }));

    // Then: экран показывает кадр 3 (новейший 5, минус 2), живой режим снят.
    expect(screen.historyOffset()).toBe(2);
    expect(note.textContent).toContain("кадр 3");
    expect(note.textContent).toContain("назад");
    expect(live.disabled).toBe(false);

    // When: возврат в живой режим.
    live.click();
    expect(screen.historyOffset()).toBe(0);
    expect(slider.value).toBe("0");
    expect(note.textContent).toContain("кадр 5");
    expect(note.textContent).toContain("живой");
    expect(live.disabled).toBe(true);
  });

  it("тумблер послесвечения (liveSeg Выкл/Вкл) выключает слой и помнит выбор в localStorage", () => {
    const first = buildScopeScreen();
    const offButton = first.root.querySelector<HTMLButtonElement>(
      "#lnt-scope-persist [data-value='off']",
    );

    // When: оператор выключает послесвечение сегментом «Выкл».
    offButton?.click();
    expect(first.isPersistenceOn()).toBe(false);
    expect(window.localStorage.getItem(SCOPE_PERSISTENCE_STORAGE_KEY)).toBe("off");

    // Then: повторное монтирование помнит выключенное состояние.
    const second = buildScopeScreen();
    expect(second.isPersistenceOn()).toBe(false);
    const pressed = second.root.querySelector("#lnt-scope-persist [aria-pressed='true']");
    expect(pressed?.getAttribute("data-value")).toBe("off");
  });

  it("кадры продолжают писаться в историю, пока экран прокручен назад", () => {
    const screen = buildScopeScreen();
    for (const i of [1, 2, 3]) screen.applyFrame(frame(i));
    const slider = screen.root.querySelector("#lnt-scope-history") as HTMLInputElement;
    slider.value = "2";
    slider.dispatchEvent(new Event("input", { bubbles: true }));

    // When: живые кадры продолжают приходить.
    screen.applyFrame(frame(4));
    screen.applyFrame(frame(5));

    // Then: ползунок дорос до 4 кадров, экран остаётся на кадре 1.
    expect(slider.max).toBe("4");
    const note = screen.root.querySelector(".lnt-scope-screen-note") as HTMLElement;
    expect(note.textContent).toContain("кадр 1");
    // Возврат в живой показывает новейший кадр 5.
    (screen.root.querySelector("#lnt-scope-live") as HTMLButtonElement).click();
    expect(note.textContent).toContain("кадр 5");
  });
});
