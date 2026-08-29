import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/** Витрины редизайна: браузерная поверхность для доказательства сценариев S1–S3. */
const EVIDENCE_DIR = resolve(
  __dirname,
  "../../../.omo/start-work/evidence/task-redesign-showcases",
);
const BASE = "http://127.0.0.1:4101/static/v2";

const VARIANTS = [
  { page: "showcase-a.html", name: "a-instrument", title: "Приборная панель" },
  { page: "showcase-b.html", name: "b-editorial", title: "Научный журнал" },
  { page: "showcase-c.html", name: "c-terminal", title: "Терминал" },
  { page: "showcase-d.html", name: "d-saas", title: "Премиальный SaaS" },
] as const;

/** S2: внешние запросы запрещены — офлайн-инструмент. Vite HMR (ws://) локален. */
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

/** S1: ошибки консоли ломают оценку дизайна — фиксируем. */
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

    // S1: все обязательные секции плотного среза.
    await expect(page.locator('[data-showcase="shell"]')).toBeVisible();
    await expect(page.locator('[data-showcase="catalog"]')).toBeVisible();
    await expect(page.locator('[data-showcase="spectrum"]')).toBeVisible();
    await expect(page.locator('[data-showcase="metrics"]')).toBeVisible();
    await expect(page.locator('[data-showcase="capture-form"]')).toBeVisible();
    await expect(page.locator('[data-showcase="error"]')).toBeVisible();

    // S1: каталог не пуст и содержит строки с данными.
    const rows = page.locator('[data-showcase="catalog"] [data-row]');
    expect(await rows.count()).toBeGreaterThanOrEqual(8);

    // S3: краевая строка с длинным путём присутствует в каталоге.
    await expect(page.locator('[data-showcase="catalog"] [data-row="edge"]')).toBeVisible();

    // S1: спектр нарисован uPlot (canvas) и легенда различает А/Б без цвета.
    await expect(page.locator('[data-showcase="spectrum"] canvas')).toBeVisible();
    await expect(page.locator('[data-showcase="spectrum"] [data-series]')).toHaveCount(2);

    // S3: длинный путь и метка не создают горизонтальное переполнение.
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);

    // S1+S2: артефакт и чистота сети/консоли.
    await page.screenshot({
      path: resolve(EVIDENCE_DIR, `${variant.name}-1280.png`),
      fullPage: true,
    });
    expect(consoleErrors, `ошибки консоли на ${variant.page}`).toEqual([]);
    expect(external, `внешние запросы на ${variant.page}`).toEqual([]);
  });
}

test("индекс редизайна ссылается на все четыре витрины", async ({ page }) => {
  const external = watchRequests(page);
  await page.goto(`${BASE}/showcase-redesign.html`);
  for (const variant of VARIANTS) {
    await expect(page.locator(`a[href="${variant.page}"]`)).toBeVisible();
  }
  expect(external).toEqual([]);
});
