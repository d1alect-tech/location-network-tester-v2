/** E2E задача 16: SA-вкладка в общей полосе liveStrip. Покрывается: зоны
 * рендерятся из SA-манифеста (набор ≠ scope; SA-зона НЕ попадает в
 * scope-контейнер при смене вкладки); единый run-кластер отражает
 * live-источник (running → «СТОП» из sharedLiveApi, Stop освобождает);
 * staged-грамматика SA (RBW без запуска → маркер «→ …» + строка + бейдж
 * → Run → SA-конфиг применил, маркировка снята); 409 запуска — баннер с
 * переходом на «Осциллограф», Run не залипает; полоса ≤ 140 px (kill-гейт
 * §6) в idle и running на 1280×720. Мок: installMockBackend (:4101). */

import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { LIVE_ALREADY_RUNNING_RU } from "../../components/liveStrip/liveConflict";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(__dirname, "../../../../.omo/evidence/scope-sa-round4/task-16");
const BASE = "http://127.0.0.1:4101/static/v2/";

const SA_ZONES = ["span", "rbw", "run", "traces", "markers", "peaks"] as const;
const SCOPE_ZONES = new Set(["vert", "horiz", "trig", "measure"]);

let backend: MockLntBackend;

test.beforeEach(async ({ page }) => {
  backend = installMockBackend(page);
});

async function openSa(page: Page): Promise<void> {
  await page.goto(`${BASE}#/sa`);
  await expect(page.locator(".lnt-sa-workspace")).toBeVisible();
  await expect(page.locator(".lnt-live-strip")).toBeVisible();
}

async function zoneNames(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const seen: string[] = [];
    for (const node of document.querySelectorAll<HTMLElement>("[data-zone]")) {
      const zone = node.dataset.zone;
      if (zone !== undefined && !seen.includes(zone)) seen.push(zone);
    }
    return seen;
  });
}

test("SA strip renders zones from the SA manifest; set differs from scope", async ({ page }) => {
  await openSa(page);

  // Зоны из SA-манифеста — в порядке манифеста; набор ≠ scope (задача 16).
  await expect(await zoneNames(page)).toEqual([...SA_ZONES]);
  for (const zone of SA_ZONES) {
    expect(SCOPE_ZONES.has(zone), `зона ${zone} не scope-зона`).toBe(false);
  }

  // Линия 1: ПОЛОСА (два степпера) + RBW (5 сегментов) + ЗАПУСК; линия 2:
  // ТРАССЫ (тумблеры + сброс статистики), МАРКЕРЫ, ПИКИ.
  const line1 = page.locator('[data-band-line="1"]');
  await expect(line1.locator('[data-zone="span"] [data-sa-band-low]')).toBeVisible();
  await expect(line1.locator('[data-zone="span"] [data-sa-band-high]')).toBeVisible();
  await expect(line1.locator('[data-zone="rbw"] [data-sa-rbw] button')).toHaveCount(5);
  await expect(line1.locator('[data-zone="run"] #lnt-sa-run')).toBeVisible();
  const line2 = page.locator('[data-band-line="2"]');
  await expect(line2.locator('[data-zone="traces"] [data-sa-trace="max"]')).toBeVisible();
  await expect(line2.locator('[data-zone="traces"] #lnt-sa-clear')).toBeVisible();
  await expect(line2.locator('[data-zone="markers"] #lnt-sa-markers-clear')).toBeVisible();
  await expect(line2.locator('[data-zone="peaks"] #lnt-sa-peak-search')).toBeVisible();

  // Рендер — общий стек: uPlot-хост живой трассы (второй стек НЕ заводится).
  await page.locator("#lnt-sa-run").click();
  await expect(page.locator(".lnt-sa-figure .lnt-uplot-root .lnt-uplot-host")).toBeVisible();

  // Смена вкладки: SA-зона НЕ попала в scope-контейнер.
  await page.goto(`${BASE}#/scope`);
  await expect(page.locator(".lnt-scope-workspace")).toBeVisible();
  const scopeZones = await zoneNames(page);
  for (const zone of SA_ZONES.filter((zone) => zone !== "run")) {
    expect(scopeZones, `SA-зона ${zone} не в scope-контейнере`).not.toContain(zone);
  }
});

test("run control reflects the shared live source: running → «СТОП»; Stop frees", async ({
  page,
}) => {
  await openSa(page);

  const run = page.locator("#lnt-sa-run");
  const stop = page.locator("#lnt-sa-stop");
  await expect(run).toContainText("ЗАПУСК");
  await expect(stop).toContainText("СТОП");
  await expect(run).toHaveAttribute("aria-checked", "false");

  // Run из SA: старт + SA-контур конфигом (join-семантика воркспейса).
  await run.click();
  await expect(page.locator(".lnt-sa-state")).toHaveAttribute("data-live-state", "running");
  await expect(page.locator(".lnt-live-runctl")).toHaveAttribute("data-run-state", "running");
  await expect(run).toHaveAttribute("aria-checked", "true");
  await expect(run).toBeDisabled();
  await expect(backend.live.startedRequests).toHaveLength(1);

  // Stop освобождает прибор: кластер в idle, кнопки вернулись.
  await stop.click();
  await expect(page.locator(".lnt-sa-state")).toHaveAttribute("data-live-state", "stopped");
  await expect(page.locator(".lnt-live-runctl")).toHaveAttribute("data-run-state", "idle");
  await expect(run).toBeEnabled();
  await expect.poll(() => backend.live.stopRequests.length).toBe(1);
});

test("staged RBW at idle: marker + line + badge; Run applies and clears", async ({ page }) => {
  await openSa(page);

  // When: сегмент «100» без запуска (idle — отложенное изменение).
  await page.locator('[data-zone="rbw"] [data-value="100"]').click();

  // Then: три уровня видимости — маркер, строка, бейдж (AC5).
  const mark = page.locator('[data-live-mark="rbw"]');
  await expect(mark).toBeVisible();
  await expect(mark).toHaveText("→ 100 Гц");
  await expect(page.locator("[data-staged-line]")).toBeVisible();
  await expect(page.locator("[data-staged-line]")).toContainText(
    "применится при следующем запуске: RBW 100 Гц",
  );
  await expect(page.locator(".lnt-live-runbadge")).toBeVisible();

  // When: запуск применяет staged (Run читает селекторы воркспейса).
  await page.locator("#lnt-sa-run").click();
  await expect(page.locator(".lnt-sa-state")).toHaveAttribute("data-live-state", "running");
  await expect
    .poll(() => {
      const last = backend.live.configRequests.at(-1);
      return (last as { sa?: { rbw_hz?: number } } | undefined)?.sa?.rbw_hz;
    })
    .toBe(100);

  // Then: маркировка снята.
  await expect(mark).toBeHidden();
  await expect(page.locator(".lnt-live-runbadge")).toBeHidden();
  await expect(page.locator("[data-staged-line]")).toBeHidden();
});

test("409 start on SA: banner with goto to the scope tab; Run not stuck", async ({ page }) => {
  await openSa(page);

  // Живой захват уже идёт где-то ещё: сервер отвечает 409 на старт.
  await page.route("**/api/live/start", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: LIVE_ALREADY_RUNNING_RU }),
    }),
  );
  await page.locator("#lnt-sa-run").click();

  // Баннер конфликта: вкладка-конкурент + дословная причина + кнопка.
  const banner = page.locator(".lnt-live-conflict");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Запуск уже выполняется на вкладке «Осциллограф»");
  await expect(banner).toContainText(LIVE_ALREADY_RUNNING_RU);
  await expect(page.locator("#lnt-sa-run")).toBeEnabled();
  await expect(page.locator(".lnt-live-runctl")).toHaveAttribute("data-run-state", "idle");

  // «Перейти и остановить»: стоп идемпотентен + переход на конкурента.
  await banner.locator("button").click();
  await expect(page.locator(".lnt-scope-workspace")).toBeVisible();
  expect(page.url().endsWith("#/scope")).toBe(true);
  await expect.poll(() => backend.live.stopRequests.length).toBe(1);
});

test("SA strip height stays within the 140px kill-gate (idle and running)", async ({ page }) => {
  await openSa(page);
  const strip = page.locator(".lnt-live-strip");

  const idle = await strip.boundingBox();
  expect(idle?.height, `полоса idle ${idle?.height}px ≤ 140`).toBeLessThanOrEqual(140);

  await page.locator("#lnt-sa-run").click();
  await expect(page.locator(".lnt-sa-state")).toHaveAttribute("data-live-state", "running");
  // Settle по наблюдаемому сигналу: кадры идут (свипы растут), не пауза.
  const sweeps = page.locator(".lnt-sa-sweep");
  await expect(sweeps).not.toHaveText("—");
  const first = (await sweeps.textContent()) ?? "";
  await expect(sweeps).not.toHaveText(first);

  const running = await strip.boundingBox();
  expect(running?.height, `полоса running ${running?.height}px ≤ 140`).toBeLessThanOrEqual(140);

  // Горизонтального переполнения нет (AC1 по ширине).
  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: resolve(EVIDENCE_DIR, "sa-strip-1280.png"), fullPage: false });
});
