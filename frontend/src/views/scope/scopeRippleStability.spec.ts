/** Todo 9 e2e: живой чип риппла — честные состояния и стабильная геометрия.
 * Сценарий ripple-событий задаёт мок (rippleScript): settling без чисел,
 * ready с числами, ошибка транспорта гасит числа до следующего события,
 * stopped терминален. Чип — абсолютный оверлей стекла осциллографа: позиции
 * его слотов и соседних оверлеев (screen-note) обязаны быть РАВНЫ между
 * состояниями, включая пустое после ошибки транспорта (класс дефекта
 * владельца — сдвиг контролов при смене текста); чип целиком внутри стекла,
 * без обрезки. Мок переподключает EventSource после каждого ответа, поэтому
 * переходные состояния ловит MutationObserver, а не гонка опроса.
 * Ширины: 1280×720 и шире (1920×720) — требование плана. */

import { type Page, expect, test } from "@playwright/test";
import { SCOPE_LIVE_TAB, openLiveTab } from "../../testkit/liveGeometry";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

let backend: MockLntBackend;

test.beforeEach(({ page }) => {
  backend = installMockBackend(page);
});

/** Снимок чипа в момент изменения: значения, внутренние позиции слотов,
 * якорь чипа в стекле и позиция соседней screen-note. */
interface RippleSnapshot {
  readonly state: string;
  readonly rms: string;
  readonly vpp: string;
  readonly window: string;
  readonly adapter: string;
  readonly positions: number[][];
  readonly box: number[];
  readonly note: number[];
}

declare global {
  interface Window {
    __lntRippleSnapshots?: RippleSnapshot[];
  }
}

/** Пишет снимок при каждом изменении чипа. Внутренние позиции слотов —
 * относительно чипа, якорь и screen-note — относительно стекла: сдвиг
 * самого стекла при старте не выдаётся за сдвиг чипа. Дубли схлопываются. */
async function recordRippleStates(page: Page): Promise<void> {
  await page.evaluate(() => {
    const text = (attr: string): string =>
      document.querySelector<HTMLElement>(`[${attr}]`)?.textContent ?? "";
    const round = (value: number): number => Math.round(value * 10) / 10;
    const viewport = document.querySelector<HTMLElement>(".lnt-scope-viewport");
    const chip = document.querySelector<HTMLElement>("[data-ripple-chip]");
    if (viewport === null || chip === null) throw new Error("чип риппла не смонтирован");
    const record = (): void => {
      const chipBox = chip.getBoundingClientRect();
      const glass = viewport.getBoundingClientRect();
      const positions = [
        ...chip.querySelectorAll<HTMLElement>(":scope > span, .lnt-scope-ripple-metric-key"),
      ]
        .filter((node) => node.getClientRects().length > 0)
        .map((node) => {
          const r = node.getBoundingClientRect();
          return [r.x - chipBox.x, r.y - chipBox.y, r.width, r.height].map(round);
        });
      const noteNode = viewport.querySelector<HTMLElement>(".lnt-scope-screen-note");
      const noteBox = noteNode?.getBoundingClientRect();
      const next: RippleSnapshot = {
        state: text("data-ripple-state"),
        rms: text("data-ripple-rms"),
        vpp: text("data-ripple-vpp"),
        window: text("data-ripple-window"),
        adapter: text("data-ripple-adapter"),
        positions,
        box: [
          chipBox.x - glass.x,
          glass.bottom - chipBox.bottom,
          chipBox.width,
          chipBox.height,
        ].map(round),
        note:
          noteBox === undefined
            ? []
            : [noteBox.x - glass.x, noteBox.y - glass.y, noteBox.width, noteBox.height].map(round),
      };
      const snapshots = window.__lntRippleSnapshots ?? [];
      if (JSON.stringify(snapshots.at(-1)) !== JSON.stringify(next)) snapshots.push(next);
      window.__lntRippleSnapshots = snapshots;
    };
    window.__lntRippleSnapshots = [];
    record();
    new MutationObserver(record).observe(chip, {
      subtree: true,
      childList: true,
      characterData: true,
    });
  });
}

function lastSnapshotOf(snapshots: RippleSnapshot[], state: string): RippleSnapshot {
  const found = [...snapshots].reverse().find((snapshot) => snapshot.state === state);
  if (found === undefined) throw new Error(`нет снимка состояния «${state}»`);
  return found;
}

for (const width of [1280, 1920]) {
  test(`settling → ready → транспорт → stopped: числа приходят/уходят, геометрия стоит @${width}×720`, async ({
    page,
  }) => {
    backend.live.rippleScript = ["settling", "settling", "ready"];
    await openLiveTab(page, SCOPE_LIVE_TAB, { width, height: 720 });
    await recordRippleStates(page);

    await page.locator("#lnt-scope-run").click();
    await page.waitForFunction(() => {
      const snapshots = window.__lntRippleSnapshots ?? [];
      return (
        snapshots.some((item) => item.state === "установление" && item.rms === "—") &&
        snapshots.some((item) => item.state === "готов" && item.rms === "35.4 мВ") &&
        snapshots.some((item) => item.state === "нет данных" && item.rms === "—")
      );
    });
    const live = await page.evaluate(() => window.__lntRippleSnapshots ?? []);
    const settling = lastSnapshotOf(live, "установление");
    const ready = lastSnapshotOf(live, "готов");
    const cleared = lastSnapshotOf(live, "нет данных");
    expect(ready.vpp, "ready показывает Vpp").toBe("100.0 мВ");
    expect(ready.window, "ready показывает окно").toBe("500 мс");
    expect(ready.adapter, "адаптер не зависит от свежести чисел").toBe("100 нФ · 0 Ом · ×1");
    await expect(page.locator("[data-ripple-label]")).toContainText("некалиброванные вольты");
    expect(settling.positions, "settling → ready: слоты внутри чипа").toEqual(ready.positions);
    expect(settling.box, "settling → ready: якорь и размер чипа").toEqual(ready.box);
    expect(settling.note, "settling → ready: screen-note").toEqual(ready.note);
    expect(cleared.positions, "ready → пусто: слоты внутри чипа").toEqual(ready.positions);
    expect(cleared.box, "ready → пусто: якорь и размер чипа").toEqual(ready.box);
    expect(cleared.note, "ready → пусто: screen-note").toEqual(ready.note);

    await page.locator("#lnt-scope-stop").click();
    await page.waitForFunction(() =>
      (window.__lntRippleSnapshots ?? []).some(
        (item) => item.state === "остановлен" && item.rms === "—",
      ),
    );
    const stopped = lastSnapshotOf(
      await page.evaluate(() => window.__lntRippleSnapshots ?? []),
      "остановлен",
    );
    expect(stopped.positions, "ready → stopped: слоты внутри чипа").toEqual(ready.positions);
    expect(stopped.box, "ready → stopped: якорь и размер чипа").toEqual(ready.box);
    expect(stopped.note, "ready → stopped: screen-note").toEqual(ready.note);

    // Чип целиком внутри стекла: без обрезки и без выхода за границы.
    const chip = page.locator("[data-ripple-chip]");
    expect(await chip.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
    const inside = await chip.evaluate((node) => {
      const chipBox = node.getBoundingClientRect();
      const glass = node.closest(".lnt-scope-viewport")?.getBoundingClientRect();
      if (glass === undefined) return false;
      return (
        chipBox.left >= glass.left - 0.5 &&
        chipBox.right <= glass.right + 0.5 &&
        chipBox.top >= glass.top - 0.5 &&
        chipBox.bottom <= glass.bottom + 0.5
      );
    });
    expect(inside).toBe(true);
  });
}
