/** Нижняя приборная панель: значения и staged-метки не двигают контролы. */
import { type Page, expect, test } from "@playwright/test";
import { SA_LIVE_TAB, SCOPE_LIVE_TAB, openLiveTab } from "../../testkit/liveGeometry";
import { installMockBackend } from "../../testkit/mockBackend";

test.beforeEach(({ page }) => {
  installMockBackend(page);
});

async function positions(page: Page): Promise<number[][]> {
  return page.locator("[data-band]").evaluate((band) =>
    [...band.querySelectorAll<HTMLElement>("button, input, .lnt-live-pzone")]
      .filter((node) => node.getClientRects().length > 0)
      .map((node) => {
        const r = node.getBoundingClientRect();
        return [r.x, r.y, r.width, r.height].map((value) => Math.round(value * 10) / 10);
      }),
  );
}

async function labelCollisions(page: Page): Promise<string[]> {
  return page.locator("[data-band]").evaluate((band) => {
    const leaves = [
      ...band.querySelectorAll<HTMLElement>(
        ".lnt-live-pzone-label, .lnt-live-zone-note, .lnt-live-mark, .lnt-live-runbadge",
      ),
    ].filter((node) => node.getClientRects().length > 0);
    const pairs: string[] = [];
    for (const [i, first] of leaves.entries()) {
      for (const other of leaves.slice(i + 1)) {
        const a = first.getBoundingClientRect();
        const b = other.getBoundingClientRect();
        if (
          Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5 &&
          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5
        ) {
          pairs.push(`${first.textContent} / ${other.textContent}`);
        }
      }
    }
    return pairs;
  });
}

for (const width of [1280, 1920]) {
  test(`scope: staged-цели и длинные показания не сдвигают кнопки @${width}`, async ({ page }) => {
    await openLiveTab(page, SCOPE_LIVE_TAB, { width, height: 720 });
    const before = await positions(page);
    for (const selector of [
      '#lnt-scope-vdiv [data-value="0.5"]',
      '#lnt-scope-probe [data-value="10"]',
      '[data-trigger-mode="single"]',
      '[data-trigger-source="ch2"]',
      '[data-trigger-slope="falling"]',
    ]) {
      if (selector.startsWith("#lnt-scope-vdiv")) {
        await page.locator("#lnt-scope-vdiv .lnt-live-chip-btn").click();
      }
      await page.locator(selector).click();
      expect(await positions(page), selector).toEqual(before);
    }
    expect(await labelCollisions(page), "видимые staged-метки").toEqual([]);
    for (const selector of [
      '#lnt-scope-vdiv [data-value="1"]',
      '#lnt-scope-probe [data-value="1"]',
      '[data-trigger-mode="auto"]',
      '[data-trigger-source="ch1"]',
      '[data-trigger-slope="rising"]',
    ]) {
      if (selector.startsWith("#lnt-scope-vdiv")) {
        await page.locator("#lnt-scope-vdiv .lnt-live-chip-btn").click();
      }
      await page.locator(selector).click();
      expect(await positions(page), selector).toEqual(before);
    }
    // Форматированные показания приходят асинхронно и бывают длиннее пустых.
    await page.locator(".lnt-scope-cursor-inline").evaluate((node) => {
      node.textContent = "Δt 999.999 мкс · ΔV 10.000 В";
    });
    expect(await positions(page), "полные показания курсоров").toEqual(before);
    const readout = page.locator(".lnt-scope-cursor-inline");
    expect(await readout.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
    await expect(page.locator('[data-live-mark="vdiv"]')).toBeHidden();
    await expect(page.locator('[data-live-mark="probe"]')).toBeHidden();
    expect(
      await page.locator("[data-trig-state]").evaluate((node) => {
        const style = getComputedStyle(node);
        return node.clientHeight <= Number.parseFloat(style.lineHeight) + 1;
      }),
      "подпись триггера остаётся в одной строке",
    ).toBe(true);
    await page.locator("#lnt-scope-run").click();
    await expect(page.locator("[data-run-state]")).toHaveAttribute("data-run-state", "running");
    expect(await positions(page), "Запуск").toEqual(before);
    await page.locator("#lnt-scope-stop").click();
    await expect(page.locator("[data-run-state]")).toHaveAttribute("data-run-state", "idle");
    expect(await positions(page), "Стоп").toEqual(before);
    expect(
      await page.locator("[data-band]").evaluate((node) => node.clientHeight),
    ).toBeLessThanOrEqual(140);
  });

  test(`SA: полоса и RBW не сдвигают кнопки; ТРАССЫ без наложений @${width}`, async ({ page }) => {
    await openLiveTab(page, SA_LIVE_TAB, { width, height: 720 });
    const before = await positions(page);
    await page.locator('[data-ctl="rbw"] [data-value="300"]').click();
    expect(await positions(page), "RBW 300").toEqual(before);
    await page.locator("[data-sa-band-low]").fill("1000");
    await page.locator("[data-sa-band-low]").dispatchEvent("change");
    expect(await positions(page), "нижняя граница полосы").toEqual(before);
    await page.locator("[data-sa-band-high]").fill("3999999");
    await page.locator("[data-sa-band-high]").dispatchEvent("change");
    expect(await positions(page), "верхняя граница полосы").toEqual(before);
    expect(await labelCollisions(page), "видимые staged-метки SA").toEqual([]);
    await page.locator('[data-ctl="rbw"] [data-value="50"]').click();
    expect(await positions(page), "возврат RBW").toEqual(before);
    await page.locator("#lnt-sa-run").click();
    await expect(page.locator("[data-run-state]")).toHaveAttribute("data-run-state", "running");
    expect(await positions(page), "Запуск SA").toEqual(before);
    await page.locator("#lnt-sa-stop").click();
    await expect(page.locator("[data-run-state]")).toHaveAttribute("data-run-state", "idle");
    expect(await positions(page), "Стоп SA").toEqual(before);
    expect(await labelCollisions(page)).toEqual([]);
  });
}

for (const height of [625, 720]) {
  test(`scope: список частот открывается вверх без прокрутки экрана @1280×${height}`, async ({
    page,
  }) => {
    await openLiveTab(page, SCOPE_LIVE_TAB, { width: 1280, height });
    const chip = page.locator('[data-ctl="rate"] .lnt-live-chip-btn');
    const menu = page.locator('[data-ctl="rate"] [role="listbox"]');
    const layout = () =>
      page.evaluate(() => {
        const view = document.querySelector("#view-container");
        const band = document.querySelector("[data-band]");
        if (!(view instanceof HTMLElement) || !(band instanceof HTMLElement)) {
          throw new Error("нет окна вида или полосы");
        }
        return [scrollY, view.scrollTop, view.scrollHeight, band.getBoundingClientRect().y];
      });
    const before = await layout();
    await chip.click();
    await expect(menu).toBeVisible();
    expect(await layout(), "открытие мышью").toEqual(before);
    const menuBox = await menu.boundingBox();
    const chipBox = await chip.boundingBox();
    if (menuBox === null || chipBox === null) throw new Error("меню или чип не видны");
    expect(menuBox.y).toBeGreaterThanOrEqual(0);
    expect(menuBox.y + menuBox.height).toBeLessThanOrEqual(chipBox.y);
    await page.keyboard.press("Home");
    expect(await layout(), "первый пункт").toEqual(before);
    await page.keyboard.press("End");
    expect(await layout(), "последний пункт").toEqual(before);
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(chip).toBeFocused();
    expect(await layout(), "Escape").toEqual(before);
    await chip.press("ArrowDown");
    await expect(menu).toBeVisible();
    expect(await layout(), "открытие клавиатурой").toEqual(before);
    await menu.locator('[data-value="100000"]').click();
    await expect(menu).toBeHidden();
    await expect(page.locator('[data-live-mark="rate"]')).toBeVisible();
    expect(await layout(), "выбор частоты").toEqual(before);
  });
}
