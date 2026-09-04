/** W2 Playwright: post-capture recording gram inside inspect V6.
 * Pair-driven (catalog auto-pick), no standalone panel, no realtime copy.
 * Absence (pointer/npz 404) is empty state, not an error band. */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { TILE_CELL_CAP } from "./components/charts/spectrogramModel";
import { buildSpectrogramNpz } from "./test-support/spectrogramNpz";

const LABEL = "спектрограмма записи";
const INSPECT = "http://127.0.0.1:4101/static/v2/#/inspect";
const GRAM_CANVAS = "[data-showcase='spectrum'] .gram canvas";
const EMPTY_NOTE = "нет спектрограммы записи";

const SESSION_A = {
  id: "capture-001",
  health: "ok",
  created_utc: "2026-08-01T10:00:00Z",
  source: "capture",
  session_type: "capture",
  profile: "bad",
  label: "стенд-А",
  storage_path: null,
} as const;

const SPECTRUM = {
  frequency_hz: [10, 100, 1000, 10_000],
  psd_v2_per_hz: [1e-6, 1e-4, 1e-2, 1e-5],
  point_count: 4,
};

function detail(name: string): unknown {
  return {
    name,
    manifest: {},
    analysis: null,
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

function smallLevel(): { timeS: number[]; frequencyHz: number[]; powerDb: Float32Array } {
  const timeS = Array.from({ length: 16 }, (_, i) => Number((i * 0.1).toFixed(1)));
  const frequencyHz = Array.from({ length: 4 }, (_, f) => (f + 1) * 1000);
  const powerDb = new Float32Array(16 * 4);
  for (let f = 0; f < 4; f += 1) {
    for (let t = 0; t < 16; t += 1) powerDb[f * 16 + t] = t * 10 + f;
  }
  return { timeS, frequencyHz, powerDb };
}

function overCapLevel(): { timeS: number[]; frequencyHz: number[]; powerDb: Float32Array } {
  const timeS = Array.from({ length: 1024 }, (_, i) => Number((i * 0.01).toFixed(2)));
  const frequencyHz = Array.from({ length: 512 }, (_, j) => j * 10);
  const powerDb = new Float32Array(1024 * 512);
  for (let i = 0; i < powerDb.length; i += 1) powerDb[i] = (i % 97) - 40;
  return { timeS, frequencyHz, powerDb };
}

function json(body: unknown): string {
  return JSON.stringify(body);
}

async function paintedRatio(page: Page, selector: string): Promise<number> {
  return page.evaluate((sel) => {
    const canvas = document.querySelector(sel);
    if (!(canvas instanceof HTMLCanvasElement)) return -1;
    const ctx = canvas.getContext("2d");
    if (ctx === null || canvas.width === 0 || canvas.height === 0) return -1;
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let opaque = 0;
    for (let i = 3; i < data.length; i += 4) if ((data[i] ?? 0) > 0) opaque += 1;
    return opaque / (data.length / 4);
  }, selector);
}

async function mockSession(
  page: Page,
  sessionId: string,
  artifactKey: string,
  npz: ArrayBuffer | "404",
): Promise<void> {
  await page.route(`**/api/sessions/${sessionId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(detail(sessionId)) }),
  );
  await page.route(`**/api/sessions/${sessionId}/spectrum?*`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(SPECTRUM) }),
  );
  await page.route(`**/api/analysis/sessions/${sessionId}/.lnt-default-analysis.json`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: json({ artifact_key: artifactKey }),
    }),
  );
  await page.route(
    `**/api/analysis/sessions/${sessionId}/artifacts/${artifactKey}/spectrogram.npz`,
    (route) => {
      if (npz === "404") {
        return route.fulfill({
          status: 404,
          contentType: "application/json",
          body: json({ detail: "not found" }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/octet-stream",
        body: Buffer.from(npz),
      });
    },
  );
}

async function mockInspect(
  page: Page,
  opts: { artifactKey: string; npz: ArrayBuffer | "404" },
): Promise<void> {
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: json({ items: [SESSION_A], next_cursor: null }),
    }),
  );
  await mockSession(page, SESSION_A.id, opts.artifactKey, opts.npz);
}

async function openGram(page: Page): Promise<void> {
  await page.goto(INSPECT);
  const panel = page.locator("[data-showcase='spectrum']");
  await expect(page.locator(".app-v6")).toBeVisible();
  await panel.locator("[data-spectrum-view='gram']").click();
  await expect(panel).toHaveClass(/is-gram/);
  await expect(panel.locator(".gram")).toBeVisible();
}

test("inspect spectrogram is a recording spectrogram with no realtime copy", async ({ page }) => {
  await mockInspect(page, {
    artifactKey: "art-small",
    npz: buildSpectrogramNpz(smallLevel()),
  });
  await openGram(page);
  const panel = page.locator("[data-showcase='spectrum']");
  await expect(panel.locator(".gram")).toBeVisible();
  await expect(panel.locator(".lnt-spec-chart")).toHaveAttribute("aria-label", LABEL);
  await expect
    .poll(async () => paintedRatio(page, GRAM_CANVAS), { timeout: 15_000 })
    .toBeGreaterThan(0.5);
  const copy = (await panel.innerText()).toLowerCase();
  expect(copy).not.toContain("realtime");
  expect(copy).not.toContain("реалтайм");
});

test("built recording spectrogram stays inside the 524000 cell cap", async ({ page }) => {
  await mockInspect(page, {
    artifactKey: "art-big",
    npz: buildSpectrogramNpz(overCapLevel()),
  });
  await openGram(page);
  // Truncated 1024×511 tile on a small heatmap: opaque ratio is sparse (~0.017),
  // not the dense 16×4 fill (>0.5). Blank canvas is -1; crash would not paint.
  await expect
    .poll(async () => paintedRatio(page, GRAM_CANVAS), { timeout: 15_000 })
    .toBeGreaterThan(0.01);
  const scale = page.locator("[data-showcase='spectrum'] .gram-scale");
  await expect(scale).toHaveText(/… .+ дБ/);
  await expect(scale).not.toContainText("не совпадают");
  await expect(scale).not.toContainText(EMPTY_NOTE);
  expect(TILE_CELL_CAP).toBe(524_000);
});

test("missing npz 404 keeps empty recording spectrogram state", async ({ page }) => {
  await mockInspect(page, { artifactKey: "art-missing", npz: "404" });
  await openGram(page);
  await expect(page.locator("[data-showcase='spectrum'] .gram-scale")).toHaveText(EMPTY_NOTE);
  const modes = page.locator("[data-spectrogram-mode]");
  await expect(modes).toHaveCount(3);
  for (const button of await modes.all()) {
    await expect(button).toBeDisabled();
  }
  const banner = page.locator(".app-v6 .banner-inline");
  const bannerCount = await banner.count();
  if (bannerCount > 0) {
    await expect(banner).not.toBeVisible();
  }
  await expect(page.locator(".app-v6")).toBeVisible();
});
