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
const EVIDENCE_11 = resolve(__dirname, "../../../../.omo/evidence/ui-refactor-2/task-11/break-ui");

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

function seedPairWithPeaks(backend: ReturnType<typeof installMockBackend>): void {
  backend.seedCatalog([session("cap-a", "cap-a"), session("cap-b", "cap-b")]);
  for (const id of ["cap-a", "cap-b"]) {
    backend.seedSessionDetail(id, {
      name: id,
      manifest: {},
      analysis: {
        needle: {
          line_frequency_hz: 50.0000007,
          needle_mean_v: 0.0234,
          needle_sigma_ratio: 0.412,
          async_sync_ratio: 0.07,
          cycles_analyzed: 128,
        },
        spectrum: {
          peaks: [{ frequency_hz: 1000, level_db: -40, prominence_db: 12.5, q_factor: 8.2 }],
          band_low_hz: 3000,
          band_high_hz: 1350000,
          resolution_hz: 100,
        },
      },
      spectrum_available: true,
      waveform_available: false,
      ch2_available: false,
    });
  }
  // База выше сравнения на пике → дельта Б−А отрицательная.
  backend.seedSpectrum("cap-a", {
    frequency_hz: [10, 1000, 10_000],
    psd_v2_per_hz: [1e-6, 1e-2, 1e-5],
    point_count: 3,
    resolution_hz: 100,
  });
  backend.seedSpectrum("cap-b", {
    frequency_hz: [10, 1000, 10_000],
    psd_v2_per_hz: [1e-6, 1e-4, 1e-5],
    point_count: 3,
    resolution_hz: 100,
  });
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

test("break-ui 11: нули и пропуски в ленте — факты и н/д, без NaN", async ({ page }) => {
  const backend = installMockBackend(page);
  backend.seedCatalog([session("cap-a", "cap-a"), session("cap-b", "cap-b")]);
  backend.seedSessionDetail("cap-a", {
    name: "cap-a",
    manifest: {},
    analysis: {
      needle: {
        line_frequency_hz: 0,
        needle_mean_v: 0,
        needle_sigma_ratio: 0,
        async_sync_ratio: null,
        cycles_analyzed: 0,
      },
      spectrum: { peaks: [], band_low_hz: 0, band_high_hz: 0, resolution_hz: 0 },
    },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  });
  backend.seedSessionDetail("cap-b", {
    name: "cap-b",
    manifest: {},
    analysis: { needle: {}, spectrum: { peaks: [] } },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  });
  for (const id of ["cap-a", "cap-b"]) {
    backend.seedSpectrum(id, {
      frequency_hz: [10, 100],
      psd_v2_per_hz: [1e-6, 1e-4],
      point_count: 2,
      resolution_hz: 100,
    });
  }
  await page.goto(BASE);
  const band = page.locator(".col-main .analysis-band");
  await expect(band.locator(".band-cell dd")).toHaveCount(7);
  await expect(band).not.toContainText("NaN");
  await expect(band.locator(".band-cell").filter({ hasText: "P_async" })).toContainText("н/д");
  await band.screenshot({ path: resolve(EVIDENCE_11, "zeros-missing.png") });
});

test("break-ui 11: отрицательные дельты пиков — глиф вниз и data-delta", async ({ page }) => {
  seedPairWithPeaks(installMockBackend(page));
  await page.goto(BASE);
  const band = page.locator(".col-main .analysis-band");
  const delta = band.locator("[data-delta]").first();
  await expect(delta).toBeVisible();
  await expect(delta).toHaveClass(/is-down/);
  await band.screenshot({ path: resolve(EVIDENCE_11, "negative-deltas.png") });
});

test("break-ui 11: пара не выбрана — плитки н/д и приглашение Δ", async ({ page }) => {
  installMockBackend(page);
  await page.goto(BASE);
  const band = page.locator(".col-main .analysis-band");
  await expect(band.locator(".band-cell dd").first()).toContainText("н/д");
  await expect(band.locator("[data-delta-empty]")).toBeVisible();
  await band.screenshot({ path: resolve(EVIDENCE_11, "no-pair.png") });
});

test("break-ui 11: мобильная ширина — лента в один столбец без overflow", async ({ page }) => {
  seedPairWithPeaks(installMockBackend(page));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE);
  const band = page.locator(".col-main .analysis-band");
  await expect(band.locator(".band-cell dd")).toHaveCount(7);
  await noHorizontalOverflow(page);
  await band.screenshot({ path: resolve(EVIDENCE_11, "mobile-band.png") });
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
