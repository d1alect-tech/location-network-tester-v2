/** Смоук раунда 3: каждая витрина монтируется и несёт ядро брифа #13 —
 *  channel-bar, пару A/B, дельту, пик-таблицу с Δ-колонкой, вердикты, статус-бар. */
import { expect, test } from "@playwright/test";

const BASE = "http://127.0.0.1:4101/static/v2";

const VARIANTS = [
  { page: "showcase-r3a.html", marker: "r3--a" },
  { page: "showcase-r3b.html", marker: "r3--b" },
  { page: "showcase-r3c.html", marker: "r3--c" },
] as const;

for (const variant of VARIANTS) {
  test(`R3 ${variant.page}: ядро брифа на месте`, async ({ page }) => {
    await page.goto(`${BASE}/${variant.page}`);
    await expect(page.locator("body")).toHaveClass(new RegExp(variant.marker));
    await expect(page.locator('[data-showcase="shell"]')).toBeVisible();

    // Channel-bar с RBW и статус-бар — рамка прибора.
    await expect(page.locator('[data-r3="channelbar"]')).toContainText("RBW");
    await expect(page.locator('[data-r3="statusbar"]')).toContainText("Hantek");

    // Пара A/B и дельта — сигнатура.
    await expect(page.locator('[data-r3="pair"], [data-r3="hero"]').first()).toBeVisible();
    await expect(page.locator('[data-r3="delta"]').first()).toContainText("дБ");
    await expect(page.locator('[data-r3="delta-strip"]')).toBeVisible();

    // Спектр отрисован на канве uPlot.
    await expect(page.locator('[data-r3="spectrum"] canvas').first()).toBeVisible();

    // Пик-таблица с Δ-колонкой: 5 строк данных.
    const table = page.locator('[data-r3="peaks"]');
    await expect(table.locator("thead")).toContainText("Δ, дБ");
    await expect(table.locator("tbody tr")).toHaveCount(5);

    // Вердикты маски: A не проходит (класс fail), B проходит (класс pass).
    await expect(page.locator('[data-r3="verdict-a"]')).toHaveClass(/verdict-fail/);
    await expect(page.locator('[data-r3="verdict-a"]')).toContainText("НЕ ПРОХОДИТ");
    await expect(page.locator('[data-r3="verdict-b"]')).toHaveClass(/verdict-pass/);
    await expect(page.locator('[data-r3="verdict-b"]')).toContainText("все пики ниже лимита");

    // Маркеры SDRangel-стиля.
    await expect(page.locator('[data-r3="markers"]').first()).toContainText("M1");
  });
}

test("R3 индекс: витрины со ссылками", async ({ page }) => {
  await page.goto(`${BASE}/showcase-r3.html`);
  const links = page.locator(".index-list a");
  await expect(links).toHaveCount(4);
  await expect(links.nth(0)).toHaveAttribute("href", "showcase-r3a.html");
});

test("R3 типолаба: переключатель меняет систему", async ({ page }) => {
  await page.goto(`${BASE}/showcase-r3a-type.html`);
  await expect(page.locator("body")).toHaveAttribute("data-type", "t1");
  await expect(page.locator('[data-r3="type-lab"] .type-btn')).toHaveCount(5);
  await page.locator('.type-btn[data-system="t4"]').click();
  await expect(page.locator("body")).toHaveAttribute("data-type", "t4");
  await expect(page.locator('.type-btn[data-system="t4"]')).toHaveAttribute("aria-pressed", "true");
  // Макет стойки под лабой живой.
  await expect(page.locator('[data-r3="spectrum"] canvas').first()).toBeVisible();
});
