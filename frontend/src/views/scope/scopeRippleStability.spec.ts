/** Todo 9 e2e: живой чип риппла — честные состояния и стабильная геометрия.
 * Сценарий ripple-событий задаёт мок (rippleScript): settling без чисел,
 * ready с числами и ярлыком, stopped чистит числа. Чип — абсолютный оверлей
 * стекла осциллографа: позиции его слотов и соседних оверлеев (screen-note)
 * обязаны быть РАВНЫ между состояниями (класс дефекта владельца — сдвиг
 * контролов при смене текста); чип целиком внутри стекла, без обрезки.
 * Ширины: 1280×720 и шире (1920×720) — требование плана. */

import { type Page, expect, test } from "@playwright/test";
import { SCOPE_LIVE_TAB, openLiveTab } from "../../testkit/liveGeometry";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

let backend: MockLntBackend;

test.beforeEach(({ page }) => {
  backend = installMockBackend(page);
});

/** Позиции слотов чипа и соседних оверлеев стекла. */
async function chipPositions(page: Page): Promise<number[][]> {
  return page.locator(".lnt-scope-viewport").evaluate((viewport) =>
    [
      ...viewport.querySelectorAll<HTMLElement>(
        "[data-ripple-chip] > span, [data-ripple-chip] .lnt-scope-ripple-metric-key, .lnt-scope-screen-note",
      ),
    ]
      .filter((node) => node.getClientRects().length > 0)
      .map((node) => {
        const r = node.getBoundingClientRect();
        return [r.x, r.y, r.width, r.height].map((value) => Math.round(value * 10) / 10);
      }),
  );
}

for (const width of [1280, 1920]) {
  test(`settling → ready → stopped: числа приходят/уходят, геометрия стоит @${width}×720`, async ({
    page,
  }) => {
    backend.live.rippleScript = ["settling", "ready"];
    await openLiveTab(page, SCOPE_LIVE_TAB, { width, height: 720 });
    const state = page.locator("[data-ripple-state]");
    const rms = page.locator("[data-ripple-rms]");
    const vpp = page.locator("[data-ripple-vpp]");

    await page.locator("#lnt-scope-run").click();
    await expect(state).toHaveText("установление");
    await expect(rms).toHaveText("—");
    const settling = await chipPositions(page);

    await expect(state).toHaveText("готов");
    await expect(rms).toHaveText("35.4 мВ");
    await expect(vpp).toHaveText("100.0 мВ");
    await expect(page.locator("[data-ripple-label]")).toContainText("некалиброванные вольты");
    await expect(page.locator("[data-ripple-adapter]")).toHaveText("100 нФ · 0 Ом · ×1");
    expect(await chipPositions(page), "settling → ready").toEqual(settling);

    await page.locator("#lnt-scope-stop").click();
    await expect(state).toHaveText("остановлен");
    await expect(rms).toHaveText("—");
    await expect(vpp).toHaveText("—");
    expect(await chipPositions(page), "ready → stopped").toEqual(settling);

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
