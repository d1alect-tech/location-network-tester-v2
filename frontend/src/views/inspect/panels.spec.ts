import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import type { CatalogSession } from "../../api/types";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

/** E2E Batch 2–6 progressive disclosure inside V6 extras: mount only when the artifact exists.
 * #/inspect mounts .app-v6; W1 lives in collapsed details[data-extra=w1].
 * API подменяется page.route как в spectrogram.spec.ts / w1Chrome.spec.ts. */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.resolve(HERE, "../../test-support/analysis-v2-fixtures");
const INSPECT = "http://127.0.0.1:4101/static/v2/#/inspect";
const BANNER =
  "Расширенный анализ (ITIC, гармоники, APD…) для этой сессии не записан. Метрики и спектр v1 на месте.";
const ARTIFACT_KEY = "art-meas";
const SPECTRUM = {
  frequency_hz: [10, 100, 1000],
  psd_v2_per_hz: [1e-6, 1e-4, 1e-2],
  point_count: 3,
};
const HARMONICS_LABEL = "CH1 HF plane, calibration_used=false, compare deltas";
const MEASUREMENT_PANELS = ["harmonics", "notching", "apd", "burst", "trends", "audio"] as const;

function readFixture(rel: string): string {
  return fs.readFileSync(path.join(FIXTURES, rel), "utf8");
}

function catalog(id: string, sessionType: string): { items: CatalogSession[]; next_cursor: null } {
  return {
    items: [
      {
        id,
        health: "ok",
        created_utc: "2026-08-01T10:00:00Z",
        source: "synthetic",
        session_type: sessionType,
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

function mockCatalog(backend: MockLntBackend, id: string, sessionType: string): void {
  backend.seedCatalog(catalog(id, sessionType).items);
}

function mockSessionDetail(backend: MockLntBackend, id: string, metricsRel: string): void {
  backend.seedSessionDetail(id, detail(id, readFixture(metricsRel)));
  backend.seedSpectrum(id, SPECTRUM);
}

function mockPointer(backend: MockLntBackend, id: string): void {
  backend.seedAnalysisPointer(id, { recipe_id: "default", artifact_key: ARTIFACT_KEY });
}

function mockArtifacts(
  backend: MockLntBackend,
  id: string,
  files: Readonly<Record<string, string>>,
): void {
  // Единый мок по умолчанию отдаёт 404 на незасиженные артефакты.
  for (const [filename, body] of Object.entries(files)) {
    backend.seedArtifact(id, ARTIFACT_KEY, filename, body);
  }
}

async function openInspect(page: Page, id: string): Promise<void> {
  await page.goto(INSPECT);
  await expect(page.locator(".app-v6")).toBeVisible();
  await page.locator(".v6-extras details[data-extra='w1'] summary").click();
  await page.selectOption('select[aria-label="Сессия инспекции"]', id);
}

async function expectNoErrorBand(page: Page): Promise<void> {
  const band = page.locator(".app-v6 .banner-inline");
  if ((await band.count()) > 0) await expect(band).not.toBeVisible();
}

function panel(page: Page, kind: string) {
  return page.locator(".lnt-w1-chrome").locator(`[data-panel="${kind}"]`);
}

test("measurement fixtures: Batch 2-6 disclosure present, ITIC and CM/DM absent, closed", async ({
  page,
}) => {
  // Given: measurement artifacts, no power_quality.json, no cm_dm_spectrum.csv.
  const backend = installMockBackend(page);
  mockCatalog(backend, "t1-measurement", "measurement");
  mockSessionDetail(backend, "t1-measurement", "measurement/metrics.json");
  mockPointer(backend, "t1-measurement");
  mockArtifacts(backend, "t1-measurement", {
    "harmonics.json": readFixture("measurement/harmonics.json"),
    "notching.json": readFixture("measurement/notching.json"),
    "apd.json": readFixture("measurement/apd.json"),
    "burst.json": readFixture("measurement/burst.json"),
    "trends.json": readFixture("measurement/trends.json"),
    "audio_panel.json": readFixture("measurement/audio_panel.json"),
  });

  // When
  await openInspect(page, "t1-measurement");

  // Then: six disclosures exist and start closed; ITIC/CM-DM never mount.
  const chrome = page.locator(".lnt-w1-chrome");
  await expect(chrome).toBeVisible();
  for (const kind of MEASUREMENT_PANELS) {
    const node = panel(page, kind);
    await expect(node).toHaveCount(1);
    await expect(node).not.toHaveAttribute("open");
  }
  await expect(chrome.getByText(HARMONICS_LABEL)).toBeVisible();
  await expect(panel(page, "itic")).toHaveCount(0);
  await expect(panel(page, "cm_dm")).toHaveCount(0);
  await expect(page.getByText(BANNER)).toHaveCount(0);
  await expect(panel(page, "notching").locator("table")).toHaveCount(0);
  await panel(page, "notching").locator("summary").click();
  await expect(panel(page, "notching").locator("table")).toHaveCount(1);
  await expectNoErrorBand(page);
});

test("line_quality fixtures: ITIC disclosure present", async ({ page }) => {
  // Given: line_quality session with power_quality.json only.
  const backend = installMockBackend(page);
  mockCatalog(backend, "t1-line-quality", "line_quality");
  mockSessionDetail(backend, "t1-line-quality", "measurement/metrics.json");
  mockPointer(backend, "t1-line-quality");
  mockArtifacts(backend, "t1-line-quality", {
    "power_quality.json": readFixture("line_quality/power_quality.json"),
  });

  // When
  await openInspect(page, "t1-line-quality");

  // Then
  await expect(panel(page, "itic")).toHaveCount(1);
  await expect(panel(page, "itic")).not.toHaveAttribute("open");
  await expect(panel(page, "cm_dm")).toHaveCount(0);
  await expectNoErrorBand(page);
});

test("cm_dm fixtures: CM/DM disclosure present", async ({ page }) => {
  // Given: cm_dm session with cm_dm_spectrum.csv only.
  const backend = installMockBackend(page);
  mockCatalog(backend, "t1-cm-dm", "cm_dm");
  mockSessionDetail(backend, "t1-cm-dm", "measurement/metrics.json");
  mockPointer(backend, "t1-cm-dm");
  mockArtifacts(backend, "t1-cm-dm", {
    "cm_dm_spectrum.csv": readFixture("cm_dm/cm_dm_spectrum.csv"),
  });

  // When
  await openInspect(page, "t1-cm-dm");

  // Then
  await expect(panel(page, "cm_dm")).toHaveCount(1);
  await expect(panel(page, "cm_dm")).not.toHaveAttribute("open");
  await expect(panel(page, "itic")).toHaveCount(0);
  await expectNoErrorBand(page);
});

test("v1-only: T6 banner still, no hollow panels", async ({ page }) => {
  // Given: no pointer, every artifact 404.
  const backend = installMockBackend(page);
  mockCatalog(backend, "t1-v1-only", "measurement");
  mockSessionDetail(backend, "t1-v1-only", "v1-only/metrics.json");

  // When
  await openInspect(page, "t1-v1-only");

  // Then
  const chrome = page.locator(".lnt-w1-chrome");
  await expect(chrome.locator(".lnt-w1-banner")).toHaveText(BANNER);
  await expect(chrome.locator(".lnt-w1-panel")).toHaveCount(0);
  await expect(panel(page, "harmonics")).toHaveCount(0);
  await expect(panel(page, "itic")).toHaveCount(0);
  await expect(panel(page, "cm_dm")).toHaveCount(0);
  await expectNoErrorBand(page);
});
