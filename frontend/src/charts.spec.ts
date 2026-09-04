import * as os from "node:os";
import * as path from "node:path";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

/** E2E графиков: оверлей A/B uPlot в полном захвате инспекции V6.
 * API подменяется маршрутами с фикстурами бэкенд-контрактов; проверяются
 * ОТРИСОВАННЫЕ данные (легенда/дельта/канва), а не консольные логи. */

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";

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
    {
      id: "capture-002",
      health: "ok",
      created_utc: "2026-08-02T10:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "quiet",
      label: "стенд-Б",
      storage_path: null,
    },
  ],
  next_cursor: null,
};

// Спектр A: известный пик на 1 кГц (значение 1e-2) — проверяем паритет.
const SPECTRUM_A = {
  frequency_hz: [10, 100, 1000, 10_000],
  psd_v2_per_hz: [1e-6, 1e-4, 1e-2, 1e-5],
  point_count: 4,
};

const SPECTRUM_B = {
  frequency_hz: [10, 100, 1000, 10_000],
  psd_v2_per_hz: [2e-6, 3e-4, 8e-3, 2e-5],
  point_count: 4,
};

function detail(name: string): unknown {
  return {
    name,
    manifest: { session_id: name },
    analysis: {
      spectrum: {
        peaks: [{ frequency_hz: 1000, level_db: -20, prominence_db: 18.4, q_factor: 9.5 }],
      },
      ch1_input_reference: { status: "unavailable", reason_code: "manifest_schema_v1" },
    },
    spectrum_available: true,
    waveform_available: true,
    ch2_available: false,
  };
}

async function mockApi(page: Page): Promise<void> {
  const json = (body: unknown): string => JSON.stringify(body);
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(CATALOG) }),
  );
  await page.route("**/api/sessions/capture-001", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(detail("capture-001")) }),
  );
  await page.route("**/api/sessions/capture-002", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(detail("capture-002")) }),
  );
  await page.route("**/api/sessions/capture-001/spectrum?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(SPECTRUM_A) }),
  );
  await page.route("**/api/sessions/capture-002/spectrum?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(SPECTRUM_B) }),
  );
  await page.route("**/api/analysis/sessions/capture-001/.lnt-default-analysis.json", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json({ artifact_key: "art-a" }) }),
  );
  await page.route("**/api/analysis/sessions/capture-002/.lnt-default-analysis.json", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json({ artifact_key: "art-b" }) }),
  );
}

async function paintedRatio(page: Page, selector: string): Promise<number> {
  return page.evaluate((sel) => {
    const canvas = document.querySelector(`${sel} canvas`);
    if (!(canvas instanceof HTMLCanvasElement)) return -1;
    const ctx = canvas.getContext("2d");
    if (ctx === null || canvas.width === 0 || canvas.height === 0) return -1;
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let opaque = 0;
    for (let i = 3; i < data.length; i += 4) if ((data[i] ?? 0) > 0) opaque += 1;
    return opaque / (data.length / 4);
  }, selector);
}

test("оверлей А/Б", async ({ page }) => {
  await mockApi(page);
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  const frame = page.locator(".frame");
  await expect(frame.locator(".uplot")).toHaveCount(1);

  const legend = frame.locator(".u-legend");
  await expect(legend).toContainText("capture-001");
  await expect(legend).toContainText("capture-002");

  await expect.poll(async () => paintedRatio(page, ".frame"), { timeout: 10_000 }).toBeGreaterThan(0.05);

  const canvas = frame.locator("canvas").first();
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  if (box === null) throw new Error("канва не отрисована");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  const liveValue = frame.locator(".u-legend .u-value").first();
  await expect(liveValue).not.toHaveText("—");
  await expect(liveValue).not.toHaveText("--");

  // Пики аннотируются на канве (createPeaksPlugin) и в таблице анализа — DOM .peak-mark нет.
  await expect(page.locator(".analysis-band tbody")).toContainText(/1[\u00a0 ]?000/);
});

test("log-ось и дельта пиков", async ({ page }) => {
  await mockApi(page);
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  const band = page.locator(".analysis-band");
  await expect(band).toContainText(/1[\u00a0 ]?000/);

  const deltaCell = band.locator("[data-delta]").first();
  await expect(deltaCell).toBeVisible();
  // 10*log10(8e-3/1e-2) ≈ -0.969 → минус, глиф ▼.
  const value = Number(await deltaCell.getAttribute("data-delta"));
  expect(Math.abs(value - -0.969)).toBeLessThan(0.05);
  await expect(deltaCell).toContainText("▼");

  await page.locator("[data-pair-swap]").click();
  await expect(page.locator(".pairbar [data-pair='a']")).toContainText("стенд-Б");

  const screenshotPath = path.join(os.tmpdir(), "lnt-v6-overlay-charts.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });
});
