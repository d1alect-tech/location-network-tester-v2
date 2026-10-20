import { expect, test } from "@playwright/test";
import { installMockBackend } from "../../testkit/mockBackend";

for (const width of [1280, 1920]) {
  test(`шкала до 10 мВ, медленная частота и независимые нули @${width}`, async ({ page }) => {
    const backend = installMockBackend(page);
    await page.setViewportSize({ width, height: 720 });
    await page.goto("http://127.0.0.1:4101/static/v2/#/scope");
    await page.locator("#lnt-scope-vdiv .lnt-live-chip-btn").click();
    const menu = page.locator("#lnt-scope-vdiv [role=listbox]");
    const box = await menu.boundingBox();
    expect(box?.y).toBeGreaterThanOrEqual(0);
    await menu.locator('[data-value="0.01"]').click();
    await page.locator(".lnt-scope-rate-field .lnt-live-chip-btn").click();
    await page.locator('.lnt-scope-rate-field [data-value="100000"]').click();
    await page.locator("#lnt-scope-run").click();
    await expect(page.locator("#lnt-scope-stop")).toBeEnabled();
    expect(backend.live.startedRequests[0]).toMatchObject({
      sample_rate_hz: 100000,
      ch1_range_v: 0.5,
    });
    await expect(page.locator("[data-wave-vdiv]")).toContainText("экранное усиление");
    // Ярлык шкалы и пилюля статуса кадра делят один ряд: пересечение
    // прямоугольников = наложение текста (владелец ловит такое глазами).
    const tagBox = await page.locator("[data-wave-vdiv]").boundingBox();
    if (tagBox === null) throw new Error("нет ярлыка В/дел");
    expect(tagBox.x + tagBox.width).toBeLessThanOrEqual(width);
    const waveStatus = page.locator(".lnt-scope-wave-status");
    if (await waveStatus.isVisible()) {
      const statusBox = await waveStatus.boundingBox();
      if (statusBox === null) throw new Error("нет статуса кадра");
      const overlapW =
        Math.min(tagBox.x + tagBox.width, statusBox.x + statusBox.width) -
        Math.max(tagBox.x, statusBox.x);
      const overlapH =
        Math.min(tagBox.y + tagBox.height, statusBox.y + statusBox.height) -
        Math.max(tagBox.y, statusBox.y);
      expect(Math.max(0, overlapW) * Math.max(0, overlapH)).toBe(0);
    }
    await page.locator("#lnt-scope-stop").click();
    const ground1 = page.locator('[data-ground="ch1"]');
    const ground2 = page.locator('[data-ground="ch2"]');
    const first = await ground1.boundingBox();
    if (first === null) throw new Error("нет ручки нуля");
    await page.mouse.move(first.x + 22, first.y + 22);
    await page.mouse.down();
    await page.mouse.move(first.x + 22, first.y - 40, { steps: 6 });
    await page.mouse.up();
    await expect(ground1).not.toHaveAttribute("aria-valuenow", "0");
    await expect(ground2).toHaveAttribute("aria-valuenow", "0");
    await ground2.press("ArrowDown");
    await expect(ground2).not.toHaveAttribute("aria-valuenow", "0");
    await ground1.dblclick();
    await expect(ground1).toHaveAttribute("aria-valuenow", "0");
    const overflow = await page.evaluate(() => ({
      width: innerWidth,
      height: innerHeight,
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
    }));
    expect(overflow.scrollWidth).toBe(overflow.width);
    expect(overflow.scrollHeight).toBe(overflow.height);
    await page.screenshot({ path: `../.omo/evidence/instrument-bugs-scope-${width}.png` });
  });
}
