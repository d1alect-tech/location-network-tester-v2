/** E2E Todo 9: триггер-панель вкладки «Осциллограф». Честные метки (связь
 * входов DC, никаких обещаний AC/holdoff/предтриггера), режимы
 * auto/normal/single и таблица частот прибора; mode/level на ходу шлют
 * POST /api/live/config с nonce; SINGLE — ровно один сработавший кадр и
 * остановка (мок повторяет контракт InstrumentService: кадр → прибор
 * освобождён; панель подтверждает остановку stop-ом и сразу показывает
 * «остановлен»). A11y-пол: цели 44px, клавиатурный выбор, axe-чистота. */

import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { injectAxe, seriousAxeViolations } from "../../testkit/axe";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(__dirname, "../../../../.omo/evidence/scope-sa-tabs/task-9");
const BASE = "http://127.0.0.1:4101/static/v2/";

let backend: MockLntBackend;

test.beforeEach(async ({ page }) => {
  backend = installMockBackend(page);
});

async function openScope(page: Page): Promise<void> {
  await page.goto(`${BASE}#/scope`);
  await expect(page.locator(".lnt-scope-workspace")).toBeVisible();
}

test("trigger panel: honest labels, rate table, 44px targets, axe clean", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await openScope(page);

  const panel = page.locator(".lnt-scope-trigger");
  await expect(panel.locator(".panel-title")).toHaveText("Триггер");
  // Задача 14: сегменты триггера ре-парентятся в полосу — ищем от корня.
  await expect(page.locator('[data-trigger-mode="single"]')).toHaveText("Одиночный");
  await expect(panel.locator(".lnt-scope-coupling")).toContainText("DC");

  // Таблица прибора (pins: LibUsbScope.py:74-99) — ровно семь записей в
  // списке чипа частоты (задача 14: слот — применённое, выбор отложен).
  const rateField = page.locator(".lnt-scope-rate-field");
  await expect(rateField.locator("[role='option']")).toHaveCount(7);
  await expect(rateField.locator("[data-slot='rate']")).toHaveText("8 МГц");
  await expect(
    rateField.locator("[role='option'][data-value='100000'] .lnt-live-opt-text"),
  ).toHaveText("100 кГц");
  await expect(
    rateField.locator("[role='option'][data-value='8000000'] .lnt-live-opt-text"),
  ).toHaveText("8 МГц");
  await expect(rateField.locator("[role='option'][data-value='8000000']")).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // Честность: панель не обещает AC-связь и holdoff.
  const text = (await panel.textContent()) ?? "";
  expect(text).not.toMatch(/\bAC\b/);
  expect(text).not.toContain("holdoff");

  // A11y-пол: интерактивные цели не ниже 44px (чип частоты вместо семи кнопок).
  for (const selector of [
    '[data-trigger-mode="auto"]',
    ".lnt-scope-rate-field .lnt-live-chip-btn",
    "#lnt-scope-level",
  ]) {
    const box = await page.locator(selector).boundingBox();
    expect(box?.height, `${selector} ниже 44px`).toBeGreaterThanOrEqual(44);
  }

  await injectAxe(page);
  const summary = await seriousAxeViolations(page);
  expect(summary, `axe serious/critical: ${JSON.stringify(summary)}`).toEqual([]);

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: resolve(EVIDENCE_DIR, "scope-trigger-1280.png") });

  // Персона 375px: сегменты переносятся, горизонтального скролла нет.
  await page.setViewportSize({ width: 375, height: 900 });
  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
  await page.screenshot({ path: resolve(EVIDENCE_DIR, "scope-trigger-375.png") });
});

test("mode and level changes POST /api/live/config while running", async ({ page }) => {
  await openScope(page);
  await page.locator("#lnt-scope-run").click();
  // Атрибут, не текст: «запущен» входит и в «не запущен» — совпадение до
  // ответа start гнало шаги вперёд (стейджинг вместо POST).
  await expect(page.locator(".lnt-scope-state")).toHaveAttribute("data-live-state", "running");

  // Клавиатура: фокус на «Норм» + Enter — режим уходит конфигом.
  await page.locator('[data-trigger-mode="normal"]').focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => backend.live.configRequests.length).toBe(1);
  expect(backend.live.configRequests[0]).toMatchObject({ mode: "normal", level_v: 0 });

  // Уровень 2,5 В — вторым конфигом, триггер целиком.
  const level = page.locator("#lnt-scope-level");
  await level.fill("2.5");
  await level.blur();
  await expect.poll(() => backend.live.configRequests.length).toBe(2);
  expect(backend.live.configRequests[1]).toMatchObject({
    level_v: 2.5,
    mode: "normal",
    slope: "rising",
    source: "ch1",
  });

  // Невалидный уровень: ошибка в поле, конфиг не уходит.
  await level.fill("7");
  await level.blur();
  await expect(page.locator(".lnt-scope-trigger [role='alert']")).toContainText("от -5 до 5");
  expect(backend.live.configRequests).toHaveLength(2);
});

test("SINGLE mode: one frame, then the instrument stops", async ({ page }) => {
  await openScope(page);

  await page.locator('[data-trigger-mode="single"]').click();
  await page.locator("#lnt-scope-run").click();
  // Атрибут, не текст: иначе «не запущен» совпадает до ответа start.
  await expect(page.locator(".lnt-scope-state")).toHaveAttribute("data-live-state", "running");
  expect(backend.live.startedRequests[0]).toMatchObject({
    sample_rate_hz: 8_000_000,
    trigger: { mode: "single", level_v: 0, slope: "rising", source: "ch1" },
  });

  // Мок повторяет сервис: один сработавший кадр, прибор освобождён.
  await expect(page.locator(".lnt-scope-frame-count")).toHaveText("1");
  await expect(page.locator(".lnt-scope-state")).toContainText("остановлен");
  await expect.poll(() => backend.live.stopRequests.length).toBe(1);
  await expect(page.locator("#lnt-scope-run")).toBeEnabled();
  await expect(page.locator("#lnt-scope-stop")).toBeDisabled();

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.locator(".lnt-scope-workspace").screenshot({
    path: resolve(EVIDENCE_DIR, "scope-single-stopped.png"),
  });

  // Остановленный прибор кадров не даёт: показание остаётся единственным.
  await expect(page.locator(".lnt-scope-frame-count")).toHaveText("1");
});
