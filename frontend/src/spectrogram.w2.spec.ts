/** W2 Playwright: post-capture spectrogram A copy, no realtime UI, 404 empty, cap 524000. */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { TILE_CELL_CAP } from "./components/charts/spectrogramModel";
import { buildSpectrogramNpz } from "./test-support/spectrogramNpz";

const LABEL = "спектрограмма записи";
const INSPECT = "http://127.0.0.1:4101/static/v2/#/inspect";

const CATALOG = {
  items: [
    {
      id: "capture-001",
      health: "ok",
      created_utc: "2026-08-01T10:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "bad",
      label: "стенд-А",
      storage_path: null,
    },
  ],
  next_cursor: null,
};

const EVENTS = { schema_version: 1, sample_count: 16, events: [] };

function smallLevel(): { timeS: number[]; frequencyHz: number[]; powerDb: Float32Array } {
  const timeS = Array.from({ length: 16 }, (_, i) => Number((i * 0.1).toFixed(1)));
  const frequencyHz = Array.from({ length: 4 }, (_, f) => f * 1000);
  const powerDb = new Float32Array(16 * 4);
  for (let f = 0; f < 4; f += 1) {
    for (let t = 0; t < 16; t += 1) powerDb[f * 16 + t] = t * 10 + f;
  }
  return { timeS, frequencyHz, powerDb };
}

async function mockCatalog(page: Page): Promise<void> {
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CATALOG) }),
  );
}

test("inspect spectrogram is a recording spectrogram with no realtime copy", async ({ page }) => {
  await mockCatalog(page);
  await page.goto(INSPECT);
  const panel = page.locator(".lnt-spec-panel");
  await expect(panel).toBeVisible();
  await expect(panel.locator(".lnt-chart-title")).toHaveText(LABEL);
  await expect(page.locator(".lnt-spec-chart")).toHaveAttribute("aria-label", LABEL);
  await expect(page.locator(".lnt-spec-status")).toHaveText(LABEL);
  const copy = (await panel.innerText()).toLowerCase();
  expect(copy).not.toContain("realtime");
  expect(copy).not.toContain("реалтайм");
});

test("built recording spectrogram stays inside the 524000 cell cap", async ({ page }) => {
  await mockCatalog(page);
  await page.route("**/artifacts/art-small/spectrogram.npz", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/octet-stream",
      body: Buffer.from(buildSpectrogramNpz(smallLevel())),
    }),
  );
  await page.route("**/artifacts/art-small/events.json", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(EVENTS) }),
  );
  await page.goto(INSPECT);
  await page.selectOption('select[aria-label="Сессия спектрограммы"]', "capture-001");
  await page.fill('input[aria-label="Ключ артефакта анализа"]', "art-small");
  await page.getByRole("button", { name: "Построить спектрограмму" }).click();
  const status = page.locator(".lnt-spec-status");
  await expect(status).toHaveAttribute("data-cells", "64");
  expect(TILE_CELL_CAP).toBe(524_000);
  expect(Number.parseInt((await status.getAttribute("data-cells")) ?? "", 10)).toBeLessThanOrEqual(
    TILE_CELL_CAP,
  );
});

test("missing npz 404 keeps empty recording spectrogram state", async ({ page }) => {
  await mockCatalog(page);
  await page.route("**/artifacts/art-missing/spectrogram.npz", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "not found" }),
    }),
  );
  await page.route("**/artifacts/art-missing/events.json", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "not found" }),
    }),
  );
  await page.goto(INSPECT);
  await page.selectOption('select[aria-label="Сессия спектрограммы"]', "capture-001");
  await page.fill('input[aria-label="Ключ артефакта анализа"]', "art-missing");
  await page.getByRole("button", { name: "Построить спектрограмму" }).click();
  await expect(page.locator(".lnt-spec-status")).toHaveText(LABEL);
  await expect(page.locator(".lnt-spec-error")).toBeHidden();
  await expect(page.locator(".lnt-spec-panel")).toBeVisible();
});
