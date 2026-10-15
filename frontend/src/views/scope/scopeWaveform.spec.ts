/** E2E Todo 8: живая развёртка — uPlot-рендер кадров обоих каналов,
 * селектор В/дел общей таблицы каналов (в POST /api/live/start уходят
 * выбранные В/дел и пробник), инверсия и пробник × подпись readout,
 * устойчивая сетка и индикация клипа/NaN не проверяется моками плохих
 * кадров (unit-уровень), здесь — живой поток мока и доступность. */

import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { injectAxe, seriousAxeViolations } from "../../testkit/axe";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(__dirname, "../../../../.omo/evidence/scope-sa-tabs/task-8");
const BASE = "http://127.0.0.1:4101/static/v2/";

let backend: MockLntBackend;

test.beforeEach(async ({ page }) => {
  backend = installMockBackend(page);
});

async function openScope(page: Page): Promise<void> {
  await page.goto(`${BASE}#/scope`);
  await expect(page.locator(".lnt-scope-workspace")).toBeVisible();
}

test("Run draws both channels on uPlot with the selected V/div and probe", async ({ page }) => {
  await openScope(page);

  // Выбранные В/дел и пробник уходят в тело запуска (диапазон общий на пару).
  // Задача 14: В/дел и пробник — сегментные группы полосы liveStrip.
  await page.locator("#lnt-scope-vdiv [data-value='1']").click();
  await page.locator("#lnt-scope-probe [data-value='10']").click();
  await page.locator("#lnt-scope-run").click();

  // «Живой режим: запущен» — строгое совпадение: подстрока «запущен»
  // содержится и в «не запущен» (idle), ожидание должно быть настоящим.
  await expect(page.locator(".lnt-scope-state")).toContainText("Живой режим: запущен");
  await expect(page.locator("#lnt-scope-stop")).toBeEnabled();
  await expect(backend.live.startedRequests).toHaveLength(1);
  await expect(backend.live.startedRequests[0]).toMatchObject({
    ch1_range_v: 1,
    ch1_probe_multiplier: 10,
  });

  // Кадры идут: осциллограмма рисуется общим uPlot-стеком, легенда обоих
  // каналов и подпись эффективных В/дел (пробник ×10) на месте.
  const figure = page.locator(".lnt-scope-figure");
  await expect(figure.locator(".lnt-uplot-host canvas").first()).toBeVisible();
  await expect(figure.locator(".u-legend")).toContainText("CH1");
  await expect(figure.locator(".u-legend")).toContainText("CH2");
  await expect(page.locator(".lnt-scope-vdiv-effective")).toHaveText("10 В/дел");

  // Чистый поток: индикатор проблем свёрнут, сетка стабильна.
  await expect(page.locator(".lnt-scope-wave-status")).toBeHidden();

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  // Задача 17b: панель развёртки — прозрачный layout-контейнер (display:
  // contents, ячейки сетки — фигура и статус); снимок — сигнальное окно.
  await page.locator(".lnt-scope-figure").screenshot({
    path: resolve(EVIDENCE_DIR, "scope-wave-running.png"),
  });
});

test("inversion toggle and probe re-render the sweep; label scales", async ({ page }) => {
  await openScope(page);
  await page.locator("#lnt-scope-run").click();
  await expect(page.locator(".lnt-scope-figure .lnt-uplot-host canvas").first()).toBeVisible();

  // Инверсия канала: перерисовка без остановки потока, легенда жива.
  await page.locator("#lnt-scope-invert-ch2").check();
  await expect(page.locator(".lnt-scope-figure .u-legend")).toContainText("CH2");
  await expect(page.locator(".lnt-scope-wave-status")).toBeHidden();

  // Пробник ×10 масштабирует подпись readout эффективных В/дел.
  await page.locator("#lnt-scope-probe [data-value='10']").click();
  await expect(page.locator(".lnt-scope-vdiv-effective")).toHaveText("50 В/дел");

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  // Задача 17b: снимок — фигура (панель .lnt-scope-wave — display: contents).
  await page.locator(".lnt-scope-figure").screenshot({
    path: resolve(EVIDENCE_DIR, "scope-wave-controls.png"),
  });
});

for (const width of [375, 1280]) {
  test(`responsive snapshot ${width}px: waveform panel without horizontal overflow`, async ({
    page,
  }) => {
    await openScope(page);
    await page.locator("#lnt-scope-run").click();
    await expect(page.locator(".lnt-scope-figure .lnt-uplot-host canvas").first()).toBeVisible();
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator(".lnt-scope-workspace")).toBeVisible();
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
    mkdirSync(EVIDENCE_DIR, { recursive: true });
    await page.screenshot({
      path: resolve(EVIDENCE_DIR, `scope-wave-${width}.png`),
      fullPage: false,
    });
  });
}

test("sizing root nests the uPlot host: no empty band above the chart", async ({ page }) => {
  await openScope(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.locator("#lnt-scope-run").click();
  await expect(page.locator(".lnt-scope-figure .lnt-uplot-host canvas").first()).toBeVisible();

  // Геометрия фигуры: host — единственный размерный элемент; его верх
  // совпадает с верхом фигуры, пустой полосы высоты графика над ним нет
  // (дефект: root и host сиблинги, оба по 520 px — над графиком 520 px
  // пустоты, воспроизведено верификатором r3-задачи-7).
  const geometry = await page.evaluate(() => {
    const figure = document.querySelector(".lnt-scope-figure");
    const host = document.querySelector(".lnt-scope-figure .lnt-uplot-host");
    if (figure === null || host === null) return null;
    const f = figure.getBoundingClientRect();
    const h = host.getBoundingClientRect();
    return {
      figureHeight: f.height,
      hostHeight: h.height,
      hostOffsetTop: h.top - f.top,
    };
  });
  if (geometry === null) throw new Error(".lnt-scope-figure/.lnt-uplot-host не найдены");
  expect(
    Math.abs(geometry.figureHeight - geometry.hostHeight),
    `figure ${geometry.figureHeight}px vs host ${geometry.hostHeight}px`,
  ).toBeLessThanOrEqual(2);
  expect(geometry.hostOffsetTop, `host top offset ${geometry.hostOffsetTop}px`).toBeLessThanOrEqual(
    2,
  );

  // DOM: host живёт ВНУТРИ sizing-root (root — единственная точка
  // монтирования в фигуру), а не сиблингом рядом с ним.
  await expect(page.locator(".lnt-scope-figure .lnt-uplot-root .lnt-uplot-host")).toHaveCount(1);
});

test("axe reports no serious or critical violations on the live sweep", async ({ page }) => {
  await openScope(page);
  await page.locator("#lnt-scope-run").click();
  await expect(page.locator(".lnt-scope-figure .lnt-uplot-host canvas").first()).toBeVisible();
  await injectAxe(page);
  const summary = await seriousAxeViolations(page);
  expect(summary, `axe serious/critical: ${JSON.stringify(summary)}`).toEqual([]);
});
