/** E2E Todo 14: вкладка «Спектроанализатор» — живые трассы SA по контракту
 * routes_live.py + models_live.py. Покрывается: вход #/sa из таббара (после
 * «Осциллографа»), статус прибора и sim-бейдж; Run POSTает start с nonce и
 * SA-конфиг (sa в /api/live/config), трасса спектра рисуется общим uPlot-
 * стеком (легенда трассы, показания свипа/RBW/топ-пика растут); сценарий
 * IS-3: смена #/scope→#/sa — НОЛЬ stop/start запросов, та же live-сессия
 * (вкладка присоединяется конфигом SA, поток и каденс не перезапускаются);
 * тумблеры max-hold добавляют серию; правило группы: уход из {scope, sa}
 * останавливает ровно один раз; a11y-пол (axe, 44px, персона 375px). */

import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { injectAxe, seriousAxeViolations } from "../../testkit/axe";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(__dirname, "../../../../.omo/evidence/scope-sa-tabs/task-14");
const BASE = "http://127.0.0.1:4101/static/v2/";

let backend: MockLntBackend;

test.beforeEach(async ({ page }) => {
  backend = installMockBackend(page);
});

async function openSa(page: Page): Promise<void> {
  await page.goto(`${BASE}#/sa`);
  await expect(page.locator(".lnt-sa-workspace")).toBeVisible();
}

test("sa tab opens from the tabbar after the scope tab with device status and sim badge", async ({
  page,
}) => {
  await openSa(page);

  // Таббар: «Спектроанализатор» сразу после «Осциллографа», активна вкладка.
  const links = page.locator(".tabbar a.snav-item");
  await expect(links).toHaveCount(8);
  await expect(links.nth(3)).toHaveAttribute("data-route", "sa");
  await expect(links.nth(3)).toHaveAttribute("aria-current", "page");
  await expect(page.locator("#nav-sa")).toHaveAttribute("href", "#/sa");

  // Статус прибора (мок ready) и режим симуляции без железа.
  await expect(page.locator(".lnt-sa-device")).toContainText("Устройство: ready");
  await expect(page.locator(".lnt-sa-sim-badge")).toBeVisible();
  await expect(page.locator(".lnt-sa-state")).toContainText("не запущен");
  await expect(page.locator("#lnt-sa-stop")).toBeDisabled();
  await expect(page.locator("#lnt-sa-run")).toBeEnabled();

  // Селекторы контракта: пять окон, четыре детектора, полоса по умолчанию.
  const windowOptions = page.locator("[data-sa-window] option");
  await expect(windowOptions).toHaveCount(5);
  await expect(page.locator("[data-sa-detector] option")).toHaveCount(4);
  await expect(page.locator("[data-sa-band-high]")).toHaveValue("4000000");
});

test("Run starts live and shows the live spectrum trace with meta readout", async ({ page }) => {
  await openSa(page);
  await page.locator("#lnt-sa-run").click();

  // Захват идёт; мок записал старт с nonce и SA-конфиг с дефолтами вкладки.
  await expect(page.locator(".lnt-sa-state")).toHaveAttribute("data-live-state", "running");
  await expect(backend.live.startedRequests).toHaveLength(1);
  await expect(backend.live.configRequests.length).toBeGreaterThanOrEqual(1);
  expect(backend.live.configRequests[0]).toMatchObject({
    sa: {
      rbw_hz: 50,
      window: "hann",
      band_low_hz: 0,
      band_high_hz: 4_000_000,
      detector: "mean",
    },
  });

  // Трасса рисуется общим uPlot-стеком: легенда живой трассы, показания
  // свипа растут (каденция мока — SSE-переподключение ~150 мс).
  const figure = page.locator(".lnt-sa-figure");
  await expect(figure.locator(".lnt-uplot-host canvas").first()).toBeVisible();
  await expect(figure.locator(".u-legend")).toContainText("Трасса");
  const sweeps = page.locator(".lnt-sa-sweep");
  await expect(sweeps).not.toHaveText("—");
  const firstSweep = (await sweeps.textContent()) ?? "—";
  await expect(sweeps).not.toHaveText(firstSweep);
  await expect(page.locator(".lnt-sa-rbw")).toContainText("50 Гц");
  // Тон мока стоит НА сетке полосы: пик графика и показание совпадают
  // (0…4 МГц, индекс 8 из 63 → 507.9 кГц).
  await expect(page.locator(".lnt-sa-peak")).toContainText("507.9 кГц");

  // Пиксельная правда: канва графика реально закрашена (оси/трасса),
  // не пустой тёмный прямоугольник.
  const painted = await page.evaluate(() => {
    const canvas = document.querySelector(".lnt-sa-figure .lnt-uplot-host canvas");
    if (!(canvas instanceof HTMLCanvasElement)) return 0;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return 0;
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
      const alpha = data[i + 3] ?? 0;
      if (alpha === 0) continue;
      const red = data[i] ?? 0;
      const green = data[i + 1] ?? 0;
      const blue = data[i + 2] ?? 0;
      if (red > 60 || green > 60 || blue > 60) count += 1;
    }
    return count;
  });
  expect(painted, "трасса/оси не закрашены").toBeGreaterThan(500);

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.setViewportSize({ width: 1280, height: 1600 });
  await page.locator(".lnt-sa-workspace").screenshot({
    path: resolve(EVIDENCE_DIR, "sa-live-1280.png"),
  });

  // Max-hold тумблер добавляет вторую серию на том же стеке.
  await page.locator('[data-sa-trace="max"]').check();
  await expect(figure.locator(".u-legend")).toContainText("Max-hold");
});

test("switch #/scope→#/sa: zero stop/start requests, same live session (IS-3)", async ({
  page,
}) => {
  // Given: живой поток запущен на вкладке «Осциллограф».
  await page.goto(`${BASE}#/scope`);
  await page.locator("#lnt-scope-run").click();
  await expect(page.locator(".lnt-scope-state")).toHaveAttribute("data-live-state", "running");
  await expect(backend.live.startedRequests).toHaveLength(1);

  // When: оператор переходит на «Спектроанализатор» (смена внутри группы).
  await page.locator("#nav-sa").click();
  await expect(page.locator(".lnt-sa-workspace")).toBeVisible();

  // Then: НИ одного нового start/stop — та же live-сессия; вкладка
  // присоединилась, настроив SA-контур конфигом (это не перезапуск).
  await expect(backend.live.stopRequests).toHaveLength(0);
  await expect(backend.live.startedRequests).toHaveLength(1);
  await expect.poll(() => backend.live.configRequests.length).toBeGreaterThanOrEqual(1);
  expect(backend.live.configRequests[backend.live.configRequests.length - 1]).toMatchObject({
    sa: { rbw_hz: 50, detector: "mean" },
  });

  // И поток жив: трассы SA приходят той же сессией — свипы растут и
  // график рисуется без единого клика на этой вкладке.
  const sweeps = page.locator(".lnt-sa-sweep");
  await expect(sweeps).not.toHaveText("—");
  const joinedSweep = (await sweeps.textContent()) ?? "—";
  await expect(sweeps).not.toHaveText(joinedSweep);
  await expect(page.locator(".lnt-sa-figure .lnt-uplot-host canvas").first()).toBeVisible();
  await expect(page.locator("#lnt-sa-run")).toBeDisabled();
  await expect(page.locator("#lnt-sa-stop")).toBeEnabled();

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.setViewportSize({ width: 1280, height: 1600 });
  await page.locator(".lnt-sa-workspace").screenshot({
    path: resolve(EVIDENCE_DIR, "sa-joined-1280.png"),
  });
});

test("leaving the sa route group stops live exactly once", async ({ page }) => {
  await openSa(page);
  await page.locator("#lnt-sa-run").click();
  await expect(page.locator(".lnt-sa-state")).toHaveAttribute("data-live-state", "running");
  await expect(page.locator(".lnt-sa-figure .lnt-uplot-host canvas").first()).toBeVisible();

  // When: уход из группы инструментальных вкладок.
  await page.goto(`${BASE}#/catalog`);
  await expect(page.locator(".lnt-cat-workspace")).toBeVisible();

  // Then: stop ровно один раз.
  await expect.poll(() => backend.live.stopRequests.length).toBe(1);
});

for (const width of [375, 1280]) {
  test(`responsive snapshot ${width}px: sa skeleton without horizontal overflow`, async ({
    page,
  }) => {
    await openSa(page);
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator(".lnt-sa-workspace")).toBeVisible();
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
    mkdirSync(EVIDENCE_DIR, { recursive: true });
    await page.screenshot({
      path: resolve(EVIDENCE_DIR, `sa-${width}.png`),
      fullPage: false,
    });
  });
}

test("axe reports no serious or critical violations on the sa skeleton", async ({ page }) => {
  await openSa(page);
  await injectAxe(page);
  const summary = await seriousAxeViolations(page);
  expect(summary, `axe serious/critical: ${JSON.stringify(summary)}`).toEqual([]);
});
