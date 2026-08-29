import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";

/** V5 «Аналитическая станция» — эволюция V3. Контракт улучшений, каждое из которых
 *  адресует конкретный дефект V3: расслоение шапки, статус-бар, отсутствие дублей
 *  чисел, весь срез без прокрутки на 1280x800 и маркеры пиков, связанные с таблицей. */
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(__dirname, "../../../.omo/start-work/evidence/task-redesign-round2");
const BASE = "http://127.0.0.1:4101/static/v2";
const PAGE = `${BASE}/showcase-v5.html`;

function watchConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));
  return errors;
}

test("V5-S1: шапка расслоена, контекст документа и статус-бар на месте", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const consoleErrors = watchConsoleErrors(page);
  await page.goto(PAGE);

  for (const section of ["shell", "catalog", "spectrum", "metrics", "capture-form", "error"]) {
    await expect(page.locator(`[data-showcase="${section}"]`)).toBeVisible();
  }

  // Навигация в шапке; статус активной задачи из неё убран (дефект V3: 6 сущностей в 32px).
  const header = page.locator(".app-v5 .hdr");
  await expect(header.locator(".tabbar")).toBeVisible();
  expect(await header.textContent()).not.toContain("Серия 2 из 5");

  // Полоса контекста документа: какая сессия открыта, включая путь моноширинно (§1.2).
  const docbar = page.locator(".app-v5 .docbar");
  await expect(docbar).toBeVisible();
  const docText = (await docbar.textContent()) ?? "";
  expect(docText).toContain("стенд-А");
  expect(docText).toContain("Захват");
  expect(docText).toContain("Исправна");
  await expect(docbar.locator("[data-doc-path]")).toBeVisible();

  // Статус-бар (§5.5): глобальная задача и корень сессий — в V3 не было ни того, ни другого.
  const statusbar = page.locator(".app-v5 .statusbar");
  await expect(statusbar).toBeVisible();
  const statusText = (await statusbar.textContent()) ?? "";
  expect(statusText).toContain("Корень:");
  expect(statusText).toContain("Серия 2 из 5");

  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
  expect(consoleErrors).toEqual([]);
});

test("V5-S2: весь срез читается на 1280x800 без вертикальной прокрутки", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);
  const fit = await page.evaluate(() => {
    const main = document.querySelector(".app-v5 .col-main");
    const peaks = document.querySelector('[data-showcase="metrics"]');
    const form = document.querySelector('[data-showcase="capture-form"]');
    const plot = document.querySelector('[data-showcase="spectrum"] .spectrum-plot');
    return {
      docScroll: document.documentElement.scrollHeight,
      docClient: document.documentElement.clientHeight,
      mainScroll: main?.scrollHeight ?? 0,
      mainClient: main?.clientHeight ?? 0,
      peaksBottom: peaks?.getBoundingClientRect().bottom ?? 0,
      formBottom: form?.getBoundingClientRect().bottom ?? 0,
      plotHeight: plot?.getBoundingClientRect().height ?? 0,
      spectrumHeight:
        document.querySelector('[data-showcase="spectrum"]')?.getBoundingClientRect().height ?? 0,
      bottomRowHeight:
        document.querySelector(".app-v5 .bottom-row")?.getBoundingClientRect().height ?? 0,
      viewport: window.innerHeight,
      blocks: Array.from(main?.children ?? []).map(
        (el) =>
          `${el.getAttribute("data-showcase") ?? el.className}=${Math.round(el.getBoundingClientRect().height)}`,
      ),
    };
  });
  expect(fit.docScroll).toBeLessThanOrEqual(fit.docClient + 1);
  expect(fit.mainScroll).toBeLessThanOrEqual(fit.mainClient + 1);
  expect(fit.peaksBottom).toBeLessThanOrEqual(fit.viewport + 1);
  expect(fit.formBottom).toBeLessThanOrEqual(fit.viewport + 1);
  // График забирает свободную высоту, а не сидит на фиксированных 280px как в V3.
  expect(fit.plotHeight, `ярусы: ${fit.blocks.join(" ")}`).toBeGreaterThanOrEqual(300);
  // График — самый высокий ярус рабочей области, а не остаток после форм и таблиц.
  expect(fit.spectrumHeight).toBeGreaterThan(fit.bottomRowHeight);
});

test("V5-S3: показания не задвоены — каждое число на экране один раз", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);
  const counts = await page.evaluate(() => {
    const labels = ["Частота сети", "P_async/P_sync", "Разрешение"];
    const nodes = Array.from(document.querySelectorAll("body *")).filter((el) =>
      Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE),
    );
    return labels.map((label) => ({
      label,
      hits: nodes.filter((el) => (el.textContent ?? "").trim() === label).length,
    }));
  });
  for (const entry of counts) {
    expect(entry.hits, `«${entry.label}» встречается ${entry.hits} раз`).toBe(1);
  }
});

test("V5-S4: маркеры пиков нанесены на график и связаны с таблицей", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);
  const marks = page.locator('[data-showcase="spectrum"] .peak-mark');
  await expect(marks).toHaveCount(5);

  // Маркеры стоят внутри области графика и подписаны частотой.
  const geometry = await page.evaluate(() => {
    const plot = document.querySelector('[data-showcase="spectrum"] .spectrum-plot');
    const box = plot?.getBoundingClientRect();
    return Array.from(document.querySelectorAll(".peak-mark")).map((el) => {
      const r = el.getBoundingClientRect();
      return {
        inside: !!box && r.left >= box.left - 1 && r.right <= box.right + 1,
        label: (el.textContent ?? "").trim(),
      };
    });
  });
  expect(geometry).toHaveLength(5);
  for (const mark of geometry) {
    expect(mark.inside).toBe(true);
    expect(mark.label).toMatch(/кГц/);
  }

  // Наведение на строку таблицы пиков подсвечивает соответствующую частоту в спектре.
  const row = page.locator('[data-showcase="metrics"] [data-peak-row="1"]');
  await expect(row).toBeVisible();
  await row.hover();
  await expect(page.locator('.peak-mark[data-peak="1"]')).toHaveClass(/is-hot/);
  await expect(page.locator('.peak-mark[data-peak="0"]')).not.toHaveClass(/is-hot/);
  await page.screenshot({ path: resolve(EVIDENCE_DIR, "v5-peak-hover-1280.png"), fullPage: true });
});

test("V5-S6: фокусируемы только те строки пиков, где фокус что-то делает", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });

  // V5: строка ведёт к маркеру на графике — точка остановки клавиатуры оправдана (§6).
  await page.goto(PAGE);
  const v5Rows = await page
    .locator('[data-showcase="metrics"] [data-peak-row]')
    .evaluateAll((els) => els.map((el) => el.getAttribute("tabindex")));
  expect(v5Rows).toHaveLength(5);
  expect(new Set(v5Rows)).toEqual(new Set(["0"]));
  await page.locator('[data-showcase="metrics"] [data-peak-row="2"]').focus();
  await expect(page.locator('.peak-mark[data-peak="2"]')).toHaveClass(/is-hot/);

  // V1: та же таблица никуда не ведёт — пустых точек остановки быть не должно.
  await page.goto(`${BASE}/showcase-v1.html`);
  const v1Rows = await page
    .locator('[data-showcase="metrics"] [data-peak-row]')
    .evaluateAll((els) => els.map((el) => el.getAttribute("tabindex")));
  expect(v1Rows).toHaveLength(5);
  expect(v1Rows.filter((value) => value !== null)).toEqual([]);
});

test("V5-S5: индекс раунда 2 ведёт на V5 и витрина снимается артефактом", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${BASE}/showcase-round2.html`);
  await expect(page.locator('a[href="showcase-v5.html"]')).toBeVisible();
  await page.goto(PAGE);
  await page.screenshot({ path: resolve(EVIDENCE_DIR, "v5-station-1280.png"), fullPage: true });
});
