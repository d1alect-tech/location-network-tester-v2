import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/** Витрины редизайна раунд 2 (ТЗ 2026-08-29): направление Adobe, варианты V1–V4. */
const EVIDENCE_DIR = resolve(__dirname, "../../../.omo/start-work/evidence/task-redesign-round2");
const BASE = "http://127.0.0.1:4101/static/v2";

const VARIANTS = [
  { page: "showcase-v1.html", name: "v1-workbench", title: "Классический воркбенч" },
  { page: "showcase-v2.html", name: "v2-compact", title: "Компактная студия" },
  { page: "showcase-v3.html", name: "v3-tabs", title: "Верхние вкладки" },
  { page: "showcase-v4.html", name: "v4-cards", title: "Карточный дашборд" },
] as const;

/** §9.6: внешние запросы запрещены — офлайн-инструмент. Vite HMR (ws://) локален. */
function watchRequests(page: Page): string[] {
  const external: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    const local =
      url.startsWith(BASE) ||
      url.startsWith("http://127.0.0.1:4101") ||
      url.startsWith("ws://127.0.0.1:4101");
    if (!local) {
      external.push(url);
    }
  });
  return external;
}

/** §9.6: ошибки консоли ломают приёмку — фиксируем. */
function watchConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    errors.push(String(error));
  });
  return errors;
}

for (const variant of VARIANTS) {
  test(`витрина ${variant.title}: контент, офлайн, без переполнения`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const external = watchRequests(page);
    const consoleErrors = watchConsoleErrors(page);

    await page.goto(`${BASE}/${variant.page}`);

    // §1: все обязательные секции плотного среза.
    await expect(page.locator('[data-showcase="shell"]')).toBeVisible();
    await expect(page.locator('[data-showcase="catalog"]')).toBeVisible();
    await expect(page.locator('[data-showcase="spectrum"]')).toBeVisible();
    await expect(page.locator('[data-showcase="metrics"]')).toBeVisible();
    await expect(page.locator('[data-showcase="capture-form"]')).toBeVisible();
    await expect(page.locator('[data-showcase="error"]')).toBeVisible();

    // §1.2: каталог не пуст и содержит строки с данными.
    const rows = page.locator('[data-showcase="catalog"] [data-row]');
    expect(await rows.count()).toBeGreaterThanOrEqual(8);

    // §1.2: краевая строка с длинным путём присутствует в каталоге.
    await expect(page.locator('[data-showcase="catalog"] [data-row="edge"]')).toBeVisible();

    // §1.3: спектр нарисован uPlot (canvas) и легенда различает А/Б без цвета.
    await expect(page.locator('[data-showcase="spectrum"] canvas')).toBeVisible();
    await expect(page.locator('[data-showcase="spectrum"] [data-series]')).toHaveCount(2);

    // §9.3/§6: длинный путь и метка не создают горизонтальное переполнение.
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);

    // §9.6: артефакт и чистота сети/консоли.
    await page.screenshot({
      path: resolve(EVIDENCE_DIR, `${variant.name}-1280.png`),
      fullPage: true,
    });
    expect(consoleErrors, `ошибки консоли на ${variant.page}`).toEqual([]);
    expect(external, `внешние запросы на ${variant.page}`).toEqual([]);
  });
}

test("индекс раунда 2 ссылается на все четыре витрины", async ({ page }) => {
  const external = watchRequests(page);
  await page.goto(`${BASE}/showcase-round2.html`);
  for (const variant of VARIANTS) {
    await expect(page.locator(`a[href="${variant.page}"]`)).toBeVisible();
  }
  expect(external).toEqual([]);
});
