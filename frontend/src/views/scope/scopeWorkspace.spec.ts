/** E2E Todo 7: вкладка «Осциллограф» — live-контур по контрактам routes_live.py.
 * Покрывается: вход #/scope из таббара (после «Захвата»), статус прибора и
 * sim-бейдж без железа; Run POSTает /api/live/start с nonce (мок пишет
 * запрос только при валидном nonce) и показывает busy-причину; кадры идут
 * с темпом мока (SSE-переподключение ~150 мс); Stop освобождает прибор
 * (POST /api/live/stop, состояние «остановлен», кнопки возвращаются);
 * правило группы: смена query внутри #/scope поток не трогает, уход из
 * группы маршрутов {scope, sa} останавливает ровно один раз. */

import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { injectAxe, seriousAxeViolations } from "../../testkit/axe";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(__dirname, "../../../../.omo/evidence/scope-sa-tabs/task-7");
const BASE = "http://127.0.0.1:4101/static/v2/";

let backend: MockLntBackend;

test.beforeEach(async ({ page }) => {
  backend = installMockBackend(page);
});

async function openScope(page: Page): Promise<void> {
  await page.goto(`${BASE}#/scope`);
  await expect(page.locator(".lnt-scope-workspace")).toBeVisible();
}

test("scope tab opens from the tabbar with device status and the sim badge", async ({ page }) => {
  await openScope(page);

  // Таббар: «Осциллограф» сразу после «Захвата», «Спектроанализатор» после
  // него, активна текущая вкладка.
  const links = page.locator(".tabbar a.snav-item");
  await expect(links).toHaveCount(8);
  await expect(links.nth(2)).toHaveAttribute("data-route", "scope");
  await expect(links.nth(3)).toHaveAttribute("data-route", "sa");
  await expect(links.nth(2)).toHaveAttribute("aria-current", "page");
  await expect(page.locator("#nav-scope")).toHaveAttribute("href", "#/scope");

  // Статус прибора (мок ready) и режим симуляции без железа.
  await expect(page.locator(".lnt-scope-device")).toContainText("Устройство: ready");
  await expect(page.locator(".lnt-scope-device")).toContainText("Устройство готово к захвату.");
  await expect(page.locator(".lnt-scope-sim-badge")).toBeVisible();
  await expect(page.locator(".lnt-scope-sim-badge")).toHaveText("Симуляция");
  await expect(page.locator(".lnt-scope-state")).toContainText("не запущен");
  await expect(page.locator("#lnt-scope-stop")).toBeDisabled();
  await expect(page.locator("#lnt-scope-run")).toBeEnabled();
});

test("Run starts the live stream with nonce; frames arrive with cadence; Stop frees", async ({
  page,
}) => {
  await openScope(page);

  // When: оператор жмёт «Запустить».
  await page.locator("#lnt-scope-run").click();

  // Then: захват идёт, причина занятости видна, мок записал запрос с nonce.
  await expect(page.locator(".lnt-scope-state")).toContainText("запущен");
  await expect(page.locator(".lnt-scope-busy")).toContainText("устройство занято вкладкой");
  await expect(page.locator("#lnt-scope-stop")).toBeEnabled();
  await expect(backend.live.startedRequests).toHaveLength(1);
  await expect(backend.live.startedRequests[0]).toMatchObject({
    sample_rate_hz: 8_000_000,
    ch1_range_v: 5,
    ch1_probe_multiplier: 1,
  });

  // Кадры идут с каденцией мока: показания потока оживают и растут.
  const frames = page.locator(".lnt-scope-frame-count");
  await expect(frames).not.toHaveText("—");
  const firstFrame = (await frames.textContent()) ?? "—";
  await expect(frames).not.toHaveText(firstFrame);
  await expect(page.locator(".lnt-scope-rate")).toContainText("8.0 МГц");

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.locator(".lnt-scope-workspace").screenshot({
    path: resolve(EVIDENCE_DIR, "scope-running.png"),
  });

  // When: оператор жмёт «Остановить».
  await page.locator("#lnt-scope-stop").click();

  // Then: прибор освобождён — stop ушёл, статус «остановлен», кнопки вернулись.
  await expect(page.locator(".lnt-scope-state")).toContainText("остановлен");
  await expect(page.locator("#lnt-scope-run")).toBeEnabled();
  await expect(page.locator("#lnt-scope-stop")).toBeDisabled();
  await expect.poll(() => backend.live.stopRequests.length).toBe(1);
});

test("leaving the scope route group stops live exactly once; query change keeps it", async ({
  page,
}) => {
  await openScope(page);
  await page.locator("#lnt-scope-run").click();
  await expect(page.locator(".lnt-scope-state")).toContainText("запущен");

  // When: смена query внутри маршрута (не выход из группы {scope, sa}).
  await page.goto(`${BASE}#/scope?view=readout`);

  // Then: поток жив — кадры продолжают расти, stop не отправлен.
  const frames = page.locator(".lnt-scope-frame-count");
  const before = (await frames.textContent()) ?? "—";
  await expect(frames).not.toHaveText(before);
  expect(backend.live.stopRequests).toHaveLength(0);

  // When: уход из группы инструментальных вкладок.
  await page.goto(`${BASE}#/catalog`);
  await expect(page.locator(".lnt-cat-workspace")).toBeVisible();

  // Then: stop ровно один раз.
  await expect.poll(() => backend.live.stopRequests.length).toBe(1);
});

for (const width of [375, 1280]) {
  test(`responsive snapshot ${width}px: scope skeleton without horizontal overflow`, async ({
    page,
  }) => {
    await openScope(page);
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator(".lnt-scope-workspace")).toBeVisible();
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
    mkdirSync(EVIDENCE_DIR, { recursive: true });
    await page.screenshot({
      path: resolve(EVIDENCE_DIR, `scope-${width}.png`),
      fullPage: false,
    });
  });
}

test("axe reports no serious or critical violations on the scope skeleton", async ({ page }) => {
  await openScope(page);
  await injectAxe(page);
  const summary = await seriousAxeViolations(page);
  expect(summary, `axe serious/critical: ${JSON.stringify(summary)}`).toEqual([]);
});
