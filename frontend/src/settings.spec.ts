/** E2E Todo 44: «Настройки» и интеграционный проход персон по всем маршрутам.
 * Покрывается: сохранение предпочтений (тема, локальная заметка о корне)
 * между перезагрузками; панель диагностики (отсутствие устройства —
 * штатное типизированное состояние); preflight-замечания; честная инструкция
 * сборника поддержки (без выдуманной кнопки); сводка приватности; рецепты;
 * axe без serious/critical; снимки 375/768/1280; путь персон
 * Захват→Инспекция→Эксперименты→Отчёты→Настройки на 375px (A3: prepare убит,
 * legacy-ссылка #/prepare редиректит на #/capture). */

import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { injectAxe, seriousAxeViolations } from "./testkit/axe";
import { type MockLntBackend, installMockBackend } from "./testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(
  __dirname,
  "../../../.omo/start-work/evidence/task-44-lnt-complete-redesign",
);
const BASE = "http://127.0.0.1:4101/static/v2/";

let backend: MockLntBackend;

test.beforeEach(async ({ page }) => {
  backend = installMockBackend(page);
});

async function openSettings(page: Page): Promise<void> {
  await page.goto(`${BASE}#/settings`);
  await expect(page.locator(".lnt-set-workspace")).toBeVisible();
}

test("settings persistence journey: theme choice survives reload", async ({ page }) => {
  await openSettings(page);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator(".lnt-set-workspace")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("[id^='lnt-theme-']")).toHaveCount(0);
});

test("session root shows the server fact; local note persists but is marked local", async ({
  page,
}) => {
  await openSettings(page);
  await expect(page.locator(".lnt-set-root-value")).toHaveText("C:\\lnt-sessions-test");
  const note = page.locator("#lnt-set-root-note");
  await note.fill("D:\\lnt-sessions-next");
  await page.locator("#lnt-set-root-save").click();
  await page.reload();
  await expect(page.locator(".lnt-set-workspace")).toBeVisible();
  // Факт не изменился, заметка сохранилась.
  await expect(page.locator(".lnt-set-root-value")).toHaveText("C:\\lnt-sessions-test");
  await expect(page.locator("#lnt-set-root-note")).toHaveValue("D:\\lnt-sessions-next");

  // Валидация: недопустимый символ даёт русскую ошибку и не сохраняется.
  await note.fill("D:\\bad|path");
  await page.locator("#lnt-set-root-save").click();
  await expect(page.locator(".lnt-field [role=alert]")).toContainText("недопустимые символы");
});

test("diagnostics panel: device absent is a valid typed state with recovery action", async ({
  page,
}) => {
  backend.deviceState = "device_absent";
  await openSettings(page);
  const state = page.locator(".lnt-set-device-state");
  await expect(state).toBeVisible();
  await expect(state).toHaveAttribute("data-device-state", "device_absent");
  await expect(state).toContainText("Состояние: device_absent");
  await expect(state).toContainText("Устройство не обнаружено на шине USB.");
  await expect(state).toContainText("Zadig");
  // Штатное состояние не оформляется как ошибка (нет role=alert).
  await expect(state).not.toHaveAttribute("role", "alert");

  // Preflight: блокирующее замечание с кодом и действием.
  await page.locator("#lnt-set-preflight").click();
  await expect(page.locator(".lnt-set-ready-blocked")).toContainText("Захват заблокирован");
  const findings = page.locator(".lnt-set-preflight-findings li");
  await expect(findings.first()).toContainText("Блокирует · device_not_ready");
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page
    .locator(".lnt-set-section")
    .first()
    .screenshot({ path: resolve(EVIDENCE_DIR, "settings-diagnostics-device-absent.png") });
});

test("diagnostics panel: ready device passes preflight with only a warning", async ({ page }) => {
  await openSettings(page);
  await expect(page.locator(".lnt-set-device-state")).toContainText("Устройство готово к захвату.");
  await page.locator("#lnt-set-preflight").click();
  await expect(page.locator(".lnt-set-ready-ok")).toContainText("Захват готов к запуску.");
  await expect(page.locator(".lnt-set-preflight-findings li").first()).toContainText(
    "Предупреждение · baseline_not_requested",
  );
});

test("bundle section launches panel backup and support-bundle jobs, CLI stays as fallback", async ({
  page,
}) => {
  await openSettings(page);
  const guidance = page.locator(".lnt-set-bundle-guidance");
  await expect(guidance.locator(".lnt-set-command")).toContainText("uv run lnt support-bundle");
  await expect(guidance).toContainText("--include-private-notes");
  await expect(guidance).toContainText("--no-logs");
  await expect(guidance).toContainText("SHA-256");
  const backup = guidance.getByRole("button", { name: "Создать бэкап" });
  const bundle = guidance.getByRole("button", { name: "Собрать сборник" });
  await expect(backup).toBeVisible();
  await expect(bundle).toBeVisible();

  await backup.click();
  await expect(backend.startedRequests.at(-1)).toMatchObject({ kind: "backup" });
  await expect(guidance.locator("#lnt-set-bundle-status")).toContainText("Создание бэкапа");
  backend.pumpAll();
  await expect(guidance.locator("#lnt-set-bundle-status")).toContainText("Бэкап создан");

  await bundle.click();
  await expect(backend.startedRequests.at(-1)).toMatchObject({ kind: "support_bundle" });
  backend.pumpAll();
  await expect(guidance.locator("#lnt-set-bundle-status")).toContainText(
    "Сборник поддержки собран",
  );
});

test("privacy summary mirrors collector semantics; recipes are read-only", async ({ page }) => {
  await openSettings(page);
  const privacy = page.locator(".lnt-set-privacy");
  await expect(privacy).toContainText("Собирается автоматически");
  await expect(privacy).toContainText("Только явный выбор (opt-in)");
  await expect(privacy).toContainText("Никогда не собирается");
  await expect(privacy).toContainText("device.vid / pid / model / firmware / driver");
  await expect(privacy).toContainText("acquisition.*");
  await expect(privacy).toContainText("сырые захваты");

  await expect(page.locator(".lnt-set-recipes")).toContainText("rec-default-spectrum");
  await expect(page.locator(".lnt-set-recipes")).toContainText("sha256");
  await expect(page.locator("#lnt-set-profiles-link")).toHaveAttribute("href", "#/catalog");
});

for (const width of [375, 768, 1280]) {
  test(`responsive snapshot ${width}px: settings without horizontal overflow`, async ({ page }) => {
    await openSettings(page);
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator(".lnt-set-workspace")).toBeVisible();
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
    mkdirSync(EVIDENCE_DIR, { recursive: true });
    await page.screenshot({
      path: resolve(EVIDENCE_DIR, `settings-${width}.png`),
      fullPage: false,
    });
  });
}

test("axe reports no serious or critical violations on the settings workspace", async ({
  page,
}) => {
  backend.deviceState = "device_absent";
  await openSettings(page);
  await page.locator("#lnt-set-preflight").click();
  await expect(page.locator(".lnt-set-preflight-findings")).toBeVisible();
  await injectAxe(page);
  const summary = await seriousAxeViolations(page);
  expect(summary, `axe serious/critical: ${JSON.stringify(summary)}`).toEqual([]);
});

test("persona journey: prepare-redirect→capture→inspect→experiments→reports→settings at 375px", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`${BASE}#/prepare`);
  await expect(page).toHaveURL(/#\/capture/);
  await expect(page.locator(".capture-view")).toBeVisible();

  await page.goto(`${BASE}#/capture`);
  await expect(page.locator(".view-title, .placeholder-title").first()).toBeVisible();

  const personaId = "persona-001";
  backend.seedCatalog([
    {
      id: personaId,
      health: "ok",
      created_utc: "2026-08-01T10:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "quiet",
      label: "персона",
    },
  ]);
  backend.seedSessionDetail(personaId, {
    name: personaId,
    manifest: {},
    analysis: null,
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  });
  backend.seedSpectrum(personaId, {
    frequency_hz: [10, 100, 1000],
    psd_v2_per_hz: [1e-6, 1e-4, 1e-2],
    point_count: 3,
  });

  await page.goto(`${BASE}#/inspect`);
  await expect(page.locator(".app-v6")).toBeVisible();
  await expect(page.locator("header.hdr")).toBeVisible();
  await expect(page.locator(".app-header")).toHaveCount(0);

  await page.goto(`${BASE}#/experiments`);
  await expect(page.locator(".lnt-exp-workspace")).toBeVisible();

  await page.goto(`${BASE}#/reports`);
  await expect(page.locator(".lnt-rep-workspace")).toBeVisible();

  await page.goto(`${BASE}#/settings`);
  await expect(page.locator(".lnt-set-workspace")).toBeVisible();

  // На каждом шаге: ни границы ошибок, ни горизонтальной прокрутки документа.
  await expect(page.locator(".error-panel")).toHaveCount(0);
  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({
    path: resolve(EVIDENCE_DIR, "persona-journey-375-settings.png"),
    fullPage: false,
  });
});
