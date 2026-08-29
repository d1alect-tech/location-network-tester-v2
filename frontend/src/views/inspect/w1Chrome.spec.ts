import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

/** E2E W1 inspect chrome: measurement artifacts vs v1-only banner.
 * API подменяется page.route как в spectrogram.spec.ts. */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.resolve(HERE, "../../test-support/analysis-v2-fixtures");
const INSPECT = "http://127.0.0.1:4101/static/v2/#/inspect";
const BANNER =
  "Расширенный анализ (ITIC, гармоники, APD…) для этой сессии не записан. Метрики и спектр v1 на месте.";
const CTA = "Пересчитать анализ (v2)";
const ARTIFACT_KEY = "art-meas";

function readFixture(rel: string): string {
  return fs.readFileSync(path.join(FIXTURES, rel), "utf8");
}

function catalog(id: string): unknown {
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

async function mockCatalog(page: Page, id: string): Promise<void> {
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(catalog(id)),
    }),
  );
}

async function mockSessionDetail(page: Page, id: string, metricsRel: string): Promise<void> {
  const body = JSON.stringify(detail(id, readFixture(metricsRel)));
  await page.route(`**/api/sessions/${id}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body }),
  );
}

test("measurement fixtures: THD verdict and four scalars, no banner, no eight panels", async ({
  page,
}) => {
  // Given: Batch 2–6 artifacts + v1 metrics for t1-measurement.
  await mockCatalog(page, "t1-measurement");
  await mockSessionDetail(page, "t1-measurement", "measurement/metrics.json");
  await page.route("**/api/analysis/sessions/t1-measurement/.lnt-default-analysis.json", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ recipe_id: "default", artifact_key: ARTIFACT_KEY }),
    }),
  );
  await page.route(
    `**/api/analysis/sessions/t1-measurement/artifacts/${ARTIFACT_KEY}/**`,
    (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "not found" }),
      }),
  );
  const files = {
    "harmonics.json": readFixture("measurement/harmonics.json"),
    "notching.json": readFixture("measurement/notching.json"),
    "burst.json": readFixture("measurement/burst.json"),
    "metrics.json": readFixture("measurement/metrics.json"),
  } as const;
  for (const [filename, body] of Object.entries(files)) {
    await page.route(
      `**/api/analysis/sessions/t1-measurement/artifacts/${ARTIFACT_KEY}/${filename}`,
      (route) => route.fulfill({ status: 200, contentType: "application/json", body }),
    );
  }

  // When
  await page.goto(INSPECT);
  await page.selectOption('select[aria-label="Сессия инспекции"]', "t1-measurement");

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
});

test("v1-only: exact Russian banner and CTA, no fake 0 scalars", async ({ page }) => {
  // Given: v1 metrics/spectrum only — no pointer, no Batch 2–6 artifacts.
  await mockCatalog(page, "t1-v1-only");
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
  await page.goto(INSPECT);
  await page.selectOption('select[aria-label="Сессия инспекции"]', "t1-v1-only");

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
});
