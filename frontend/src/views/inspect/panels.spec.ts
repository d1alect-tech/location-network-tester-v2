import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

/** E2E Batch 2–6 progressive disclosure: mount only when the artifact exists.
 * API подменяется page.route как в spectrogram.spec.ts / w1Chrome.spec.ts. */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.resolve(HERE, "../../test-support/analysis-v2-fixtures");
const INSPECT = "http://127.0.0.1:4101/static/v2/#/inspect";
const BANNER =
  "Расширенный анализ (ITIC, гармоники, APD…) для этой сессии не записан. Метрики и спектр v1 на месте.";
const ARTIFACT_KEY = "art-meas";
const HARMONICS_LABEL = "CH1 HF plane, calibration_used=false, compare deltas";
const MEASUREMENT_PANELS = ["harmonics", "notching", "apd", "burst", "trends", "audio"] as const;

function readFixture(rel: string): string {
  return fs.readFileSync(path.join(FIXTURES, rel), "utf8");
}

function catalog(id: string, sessionType: string): unknown {
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

async function mockCatalog(page: Page, id: string, sessionType: string): Promise<void> {
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(catalog(id, sessionType)),
    }),
  );
}

async function mockSessionDetail(page: Page, id: string, metricsRel: string): Promise<void> {
  const body = JSON.stringify(detail(id, readFixture(metricsRel)));
  await page.route(`**/api/sessions/${id}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body }),
  );
}

async function mockPointer(page: Page, id: string): Promise<void> {
  await page.route(`**/api/analysis/sessions/${id}/.lnt-default-analysis.json`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ recipe_id: "default", artifact_key: ARTIFACT_KEY }),
    }),
  );
}

async function mockArtifacts(
  page: Page,
  id: string,
  files: Readonly<Record<string, string>>,
): Promise<void> {
  await page.route(`**/api/analysis/sessions/${id}/artifacts/${ARTIFACT_KEY}/**`, (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "not found" }),
    }),
  );
  for (const [filename, body] of Object.entries(files)) {
    const contentType = filename.endsWith(".csv") ? "text/csv" : "application/json";
    await page.route(
      `**/api/analysis/sessions/${id}/artifacts/${ARTIFACT_KEY}/${filename}`,
      (route) => route.fulfill({ status: 200, contentType, body }),
    );
  }
}

async function openInspect(page: Page, id: string): Promise<void> {
  await page.goto(INSPECT);
  await page.selectOption('select[aria-label="Сессия инспекции"]', id);
}

function panel(page: Page, kind: string) {
  return page.locator(".lnt-w1-chrome").locator(`[data-panel="${kind}"]`);
}

test("measurement fixtures: Batch 2-6 disclosure present, ITIC and CM/DM absent, closed", async ({
  page,
}) => {
  // Given: measurement artifacts, no power_quality.json, no cm_dm_spectrum.csv.
  await mockCatalog(page, "t1-measurement", "measurement");
  await mockSessionDetail(page, "t1-measurement", "measurement/metrics.json");
  await mockPointer(page, "t1-measurement");
  await mockArtifacts(page, "t1-measurement", {
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
});

test("line_quality fixtures: ITIC disclosure present", async ({ page }) => {
  // Given: line_quality session with power_quality.json only.
  await mockCatalog(page, "t1-line-quality", "line_quality");
  await mockSessionDetail(page, "t1-line-quality", "measurement/metrics.json");
  await mockPointer(page, "t1-line-quality");
  await mockArtifacts(page, "t1-line-quality", {
    "power_quality.json": readFixture("line_quality/power_quality.json"),
  });

  // When
  await openInspect(page, "t1-line-quality");

  // Then
  await expect(panel(page, "itic")).toHaveCount(1);
  await expect(panel(page, "itic")).not.toHaveAttribute("open");
  await expect(panel(page, "cm_dm")).toHaveCount(0);
});

test("cm_dm fixtures: CM/DM disclosure present", async ({ page }) => {
  // Given: cm_dm session with cm_dm_spectrum.csv only.
  await mockCatalog(page, "t1-cm-dm", "cm_dm");
  await mockSessionDetail(page, "t1-cm-dm", "measurement/metrics.json");
  await mockPointer(page, "t1-cm-dm");
  await mockArtifacts(page, "t1-cm-dm", {
    "cm_dm_spectrum.csv": readFixture("cm_dm/cm_dm_spectrum.csv"),
  });

  // When
  await openInspect(page, "t1-cm-dm");

  // Then
  await expect(panel(page, "cm_dm")).toHaveCount(1);
  await expect(panel(page, "cm_dm")).not.toHaveAttribute("open");
  await expect(panel(page, "itic")).toHaveCount(0);
});

test("v1-only: T6 banner still, no hollow panels", async ({ page }) => {
  // Given: no pointer, every artifact 404.
  await mockCatalog(page, "t1-v1-only", "measurement");
  await mockSessionDetail(page, "t1-v1-only", "v1-only/metrics.json");
  await page.route("**/api/analysis/sessions/t1-v1-only/.lnt-default-analysis.json", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "not found" }),
    }),
  );
  await page.route("**/api/analysis/sessions/t1-v1-only/artifacts/**", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "not found" }),
    }),
  );

  // When
  await openInspect(page, "t1-v1-only");

  // Then
  const chrome = page.locator(".lnt-w1-chrome");
  await expect(chrome.locator(".lnt-w1-banner")).toHaveText(BANNER);
  await expect(chrome.locator(".lnt-w1-panel")).toHaveCount(0);
  await expect(panel(page, "harmonics")).toHaveCount(0);
  await expect(panel(page, "itic")).toHaveCount(0);
  await expect(panel(page, "cm_dm")).toHaveCount(0);
});
