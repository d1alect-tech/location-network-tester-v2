/** break-ui инспекции (ui-refactor-2): worst-case артифакты по кускам.
 * Todo 9 — секция спектр+грам; todo 11 — лента анализа; todo 13 — analysis-v2.
 * Скриншоты пишутся в .omo/evidence/ui-refactor-2/task-N/break-ui/. */

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { CatalogSession } from "../../api/types";
import { installMockBackend } from "../../testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";

const EVIDENCE_9 = resolve(__dirname, "../../../../.omo/evidence/ui-refactor-2/task-9/break-ui");

function session(id: string, label: string): CatalogSession {
  return {
    id,
    health: "ok",
    created_utc: "2026-08-02T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "bad",
    label,
    storage_path: null,
  };
}

const LONG_ID = "capture-20260802-100000-очень-длинная-метка-стенда-номер-семь-abcdef";

function seedPair(backend: ReturnType<typeof installMockBackend>, ids: [string, string]): void {
  backend.seedCatalog(ids.map((id) => session(id, id)));
  for (const id of ids) {
    backend.seedSessionDetail(id, {
      name: id,
      manifest: {},
      analysis: {
        needle: {},
        spectrum: { peaks: [], band_low_hz: 3000, band_high_hz: 1350000, resolution_hz: 100 },
        ch1_input_reference: { status: "available", reason_code: null },
      },
      spectrum_available: true,
      waveform_available: false,
      ch2_available: false,
    });
    backend.seedSpectrum(id, {
      frequency_hz: [10, 100, 1000, 10_000],
      psd_v2_per_hz: [1e-6, 1e-4, 1e-2, 1e-5],
      point_count: 4,
      resolution_hz: 100,
    });
  }
}

async function noHorizontalOverflow(page: import("@playwright/test").Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "horizontal overflow").toBeLessThanOrEqual(0);
}

test("break-ui 9: штатная пара, вид спектр и вид грам", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, ["cap-a", "cap-b"]);
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  await page.screenshot({ path: resolve(EVIDENCE_9, "ok-spectrum.png"), fullPage: true });
  await panel.locator('[data-spectrum-view="gram"]').click();
  await expect(panel.locator(".gram")).toBeVisible();
  await page.screenshot({ path: resolve(EVIDENCE_9, "ok-gram.png"), fullPage: true });
  await noHorizontalOverflow(page);
});

test("break-ui 9: пустой спектр — честная пустота без NaN", async ({ page }) => {
  const backend = installMockBackend(page);
  backend.seedCatalog([session("cap-a", "cap-a"), session("cap-b", "cap-b")]);
  for (const id of ["cap-a", "cap-b"]) {
    backend.seedSessionDetail(id, {
      name: id,
      manifest: {},
      analysis: { needle: {}, spectrum: { peaks: [] } },
      spectrum_available: true,
      waveform_available: false,
      ch2_available: false,
    });
    backend.seedSpectrum(id, { frequency_hz: [], psd_v2_per_hz: [], point_count: 0 });
  }
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  await expect(panel).not.toContainText("NaN");
  await page.screenshot({ path: resolve(EVIDENCE_9, "empty-spectrum.png"), fullPage: true });
});

test("break-ui 9: ошибка загрузки спектра — статус и повтор", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, ["cap-a", "cap-b"]);
  await page.route("**/api/sessions/*/spectrum*", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: '{"error":"boom"}' }),
  );
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  const status = panel.locator("[data-spectrum-status]");
  await expect(status).toBeVisible();
  await expect(status).toContainText("Не удалось загрузить спектр");
  await expect(panel.getByRole("button", { name: "Пересчитать спектр" })).toBeVisible();
  await page.screenshot({ path: resolve(EVIDENCE_9, "error-spectrum.png"), fullPage: true });
});

test("break-ui 9: длинные id сессий не рвут шапку и пару", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, [LONG_ID, `${LONG_ID}-b`]);
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  await noHorizontalOverflow(page);
  await page.screenshot({ path: resolve(EVIDENCE_9, "long-ids.png"), fullPage: true });
});

test("break-ui 9: мобильная ширина — шапка переносится без overflow", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, ["cap-a", "cap-b"]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  await noHorizontalOverflow(page);
  await page.screenshot({ path: resolve(EVIDENCE_9, "mobile-ok.png"), fullPage: true });
});

test("break-ui 9: prefers-reduced-motion гасит вход секции", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, ["cap-a", "cap-b"]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  const animation = await panel
    .locator(".panel-bd.signal-bd")
    .evaluate((node) => getComputedStyle(node).animationName);
  expect(animation).toBe("none");
});
