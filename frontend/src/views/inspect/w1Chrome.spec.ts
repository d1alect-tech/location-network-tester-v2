import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import type { CatalogSession } from "../../api/types";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

/** E2E W1 inspect chrome inside V6 extras: measurement artifacts vs v1-only banner.
 * #/inspect mounts .app-v6; W1 lives in collapsed details[data-extra=w1].
 * API подменяется page.route как в spectrogram.spec.ts. */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.resolve(HERE, "../../test-support/analysis-v2-fixtures");
const INSPECT = "http://127.0.0.1:4101/static/v2/#/inspect";
const BANNER =
  "Расширенный анализ (ITIC, гармоники, APD…) для этой сессии не записан. Метрики и спектр v1 на месте.";
const CTA = "Пересчитать анализ (v2)";
const ARTIFACT_KEY = "art-meas";
const SPECTRUM = {
  frequency_hz: [10, 100, 1000],
  psd_v2_per_hz: [1e-6, 1e-4, 1e-2],
  point_count: 3,
};

function readFixture(rel: string): string {
  return fs.readFileSync(path.join(FIXTURES, rel), "utf8");
}

function catalog(id: string): { items: CatalogSession[]; next_cursor: null } {
  return {
    items: [
      {
        id,
        health: "ok",
        created_utc: "2026-08-01T10:00:00Z",
        source: "synthetic",
        session_type: "measurement",
        profile: "quiet",
        label: "стенд-А",
        storage_path: null,
      },
    ],
    next_cursor: null,
  };
}

function detail(name: string, metricsJson: string): unknown {
  return {
    name,
    manifest: { session_id: name },
    analysis: JSON.parse(metricsJson) as unknown,
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

function mockCatalog(backend: MockLntBackend, id: string): void {
  backend.seedCatalog(catalog(id).items);
}

function mockSessionDetail(backend: MockLntBackend, id: string, metricsRel: string): void {
  backend.seedSessionDetail(id, detail(id, readFixture(metricsRel)));
  backend.seedSpectrum(id, SPECTRUM);
}

async function openW1Chrome(page: Page, id: string): Promise<void> {
  await page.goto(INSPECT);
  await expect(page.locator(".app-v6")).toBeVisible();
  await page.locator(".v6-extras details[data-extra='w1'] summary").click();
  await page.selectOption('select[aria-label="Сессия инспекции"]', id);
}

async function expectNoErrorBand(page: Page): Promise<void> {
  const band = page.locator(".app-v6 .banner-inline");
  if ((await band.count()) > 0) await expect(band).not.toBeVisible();
}

test("measurement fixtures: THD verdict and four scalars, no banner, no eight panels", async ({
  page,
}) => {
  // Given: Batch 2–6 artifacts + v1 metrics for t1-measurement.
  const backend = installMockBackend(page);
  mockCatalog(backend, "t1-measurement");
  mockSessionDetail(backend, "t1-measurement", "measurement/metrics.json");
  backend.seedAnalysisPointer("t1-measurement", {
    recipe_id: "default",
    artifact_key: ARTIFACT_KEY,
  });
  const files = {
    "harmonics.json": readFixture("measurement/harmonics.json"),
    "notching.json": readFixture("measurement/notching.json"),
    "burst.json": readFixture("measurement/burst.json"),
    "metrics.json": readFixture("measurement/metrics.json"),
  } as const;
  for (const [filename, body] of Object.entries(files)) {
    backend.seedArtifact("t1-measurement", ARTIFACT_KEY, filename, body);
  }

  // When
  await openW1Chrome(page, "t1-measurement");

  // Then: verdict + four scalars; no missing-artifact banner; no eight hollow panels.
  const chrome = page.locator(".lnt-w1-chrome");
  await expect(chrome).toBeVisible();
  await expect(chrome.locator("[data-thd-verdict]")).toHaveAttribute("data-thd-verdict", "fail");
  await expect(chrome.getByText("THD-V", { exact: true })).toBeVisible();
  await expect(chrome.getByText("Peak Notch Depth", { exact: true })).toBeVisible();
  await expect(chrome.getByText("Burst Count", { exact: true })).toBeVisible();
  await expect(chrome.getByText("σ_pk/μ_pk", { exact: true })).toBeVisible();
  await expect(chrome.locator("[data-scalar]")).toHaveCount(4);
  await expect(page.getByText(BANNER)).toHaveCount(0);
  await expectNoErrorBand(page);
});

test("v1-only: exact Russian banner and CTA, no fake 0 scalars", async ({ page }) => {
  // Given: v1 metrics/spectrum only — no pointer, no Batch 2–6 artifacts.
  const backend = installMockBackend(page);
  mockCatalog(backend, "t1-v1-only");
  mockSessionDetail(backend, "t1-v1-only", "v1-only/metrics.json");

  // When
  await openW1Chrome(page, "t1-v1-only");

  // Then
  const chrome = page.locator(".lnt-w1-chrome");
  await expect(chrome).toBeVisible();
  await expect(chrome.locator(".lnt-w1-banner")).toHaveText(BANNER);
  await expect(page.getByRole("button", { name: CTA })).toBeVisible();
  await expect(chrome.getByText("THD-V", { exact: true })).toHaveCount(0);
  await expect(chrome.getByText("Peak Notch Depth", { exact: true })).toHaveCount(0);
  await expect(chrome.getByText("Burst Count", { exact: true })).toHaveCount(0);
  await expect(chrome.locator('[data-scalar="burst-count"]')).toHaveCount(0);
  await expect(chrome.locator(".lnt-w1-panel")).toHaveCount(0);
  await expectNoErrorBand(page);
});
