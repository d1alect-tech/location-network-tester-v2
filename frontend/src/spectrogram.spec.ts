/** E2E спектрограммы записи в инспекции V6: режимы А/Б/Δ и отсутствие
 * артефакта у Б. Пара из каталога; грам внутри сигнального окна.
 * Несовпадение сеток — inspectV6.spec V6-P8, здесь не дублируем. */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import type { CatalogSession } from "./api/types";
import { buildSpectrogramNpz } from "./test-support/spectrogramNpz";
import { type MockLntBackend, installMockBackend } from "./testkit/mockBackend";

const INSPECT = "http://127.0.0.1:4101/static/v2/#/inspect";
const GRAM_CANVAS = "[data-showcase='spectrum'] .gram canvas";
const EMPTY_NOTE = "нет спектрограммы записи";
const MISMATCH_NOTE = "сетки спектрограмм не совпадают";

const CATALOG: { items: CatalogSession[]; next_cursor: null } = {
  items: [
    {
      id: "capture-001",
      health: "ok",
      created_utc: "2026-08-02T10:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "bad",
      label: "стенд-А",
      storage_path: null,
    },
    {
      id: "capture-002",
      health: "ok",
      created_utc: "2026-08-01T09:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "quiet",
      label: "стенд-Б",
      storage_path: null,
    },
  ],
  next_cursor: null,
};

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
    manifest: {},
    analysis: null,
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

function level(
  timeBins: number,
  offsetDb: number,
): {
  timeS: number[];
  frequencyHz: number[];
  powerDb: Float32Array;
} {
  const bands = 4;
  const timeS = Array.from({ length: timeBins }, (_, i) => Number((i * 0.1).toFixed(1)));
  const frequencyHz = Array.from({ length: bands }, (_, f) => (f + 1) * 1000);
  const powerDb = new Float32Array(timeBins * bands);
  for (let f = 0; f < bands; f += 1) {
    for (let t = 0; t < timeBins; t += 1) powerDb[f * timeBins + t] = t * 10 + f + offsetDb;
  }
  return { timeS, frequencyHz, powerDb };
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

function mockPair(backend: MockLntBackend, opts?: { bPointer: "ok" | "404" }): void {
  const bPointer = opts?.bPointer ?? "ok";
  backend.seedCatalog(CATALOG.items);
  backend.seedSessionDetail("capture-001", detail("capture-001"));
  backend.seedSessionDetail("capture-002", detail("capture-002"));
  backend.seedSpectrum("capture-001", SPECTRUM_A);
  backend.seedSpectrum("capture-002", SPECTRUM_B);
  backend.seedAnalysisPointer("capture-001", { artifact_key: "art-a" });
  backend.seedAnalysisPointer("capture-002", bPointer === "404" ? null : { artifact_key: "art-b" });
  backend.seedArtifact(
    "capture-001",
    "art-a",
    "spectrogram.npz",
    Buffer.from(buildSpectrogramNpz(level(16, 0))),
    "application/octet-stream",
  );
  backend.seedArtifact(
    "capture-002",
    "art-b",
    "spectrogram.npz",
    Buffer.from(buildSpectrogramNpz(level(16, 5))),
    "application/octet-stream",
  );
}

async function openGram(page: Page): Promise<void> {
  await page.goto(INSPECT);
  const panel = page.locator("[data-showcase='spectrum']");
  await expect(page.locator(".app-v6")).toBeVisible();
  await panel.locator("[data-spectrum-view='gram']").click();
  await expect(panel).toHaveClass(/is-gram/);
  await expect(panel.locator(".gram")).toBeVisible();
}

test("режимы А/Б/Δ рисуют тайлы", async ({ page }) => {
  mockPair(installMockBackend(page));
  await openGram(page);
  const panel = page.locator("[data-showcase='spectrum']");
  const modeA = panel.locator("[data-spectrogram-mode='a']");
  const modeB = panel.locator("[data-spectrogram-mode='b']");
  const modeDelta = panel.locator("[data-spectrogram-mode='delta']");
  const scale = panel.locator(".gram-scale");

  await expect(modeB).toHaveAttribute("aria-pressed", "true");
  await expect(scale).toHaveText(/дБ/);
  await expect
    .poll(async () => paintedRatio(page, GRAM_CANVAS), { timeout: 15_000 })
    .toBeGreaterThan(0.5);

  await modeA.click();
  await expect(modeA).toHaveAttribute("aria-pressed", "true");
  await expect(modeB).toHaveAttribute("aria-pressed", "false");
  await expect(scale).toHaveText(/дБ/);
  await expect
    .poll(async () => paintedRatio(page, GRAM_CANVAS), { timeout: 15_000 })
    .toBeGreaterThan(0.5);

  await modeDelta.click();
  await expect(modeDelta).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(async () => paintedRatio(page, GRAM_CANVAS), { timeout: 15_000 })
    .toBeGreaterThan(0.5);
  await expect(scale).toHaveText(/[−+].+ … \+.+ дБ/);
});

test("отсутствие артефакта у Б не ломает базу", async ({ page }) => {
  mockPair(installMockBackend(page), { bPointer: "404" });
  await openGram(page);
  const panel = page.locator("[data-showcase='spectrum']");
  const modeA = panel.locator("[data-spectrogram-mode='a']");
  await expect(modeA).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(async () => paintedRatio(page, GRAM_CANVAS), { timeout: 15_000 })
    .toBeGreaterThan(0.5);
  await expect(panel.locator("[data-spectrogram-mode='delta']")).toBeDisabled();
  const scale = panel.locator(".gram-scale");
  await expect(scale).toHaveText(/дБ/);
  await expect(scale).not.toContainText(EMPTY_NOTE);
  await expect(scale).not.toContainText(MISMATCH_NOTE);
  const banner = page.locator(".app-v6 .banner-inline");
  const bannerCount = await banner.count();
  if (bannerCount > 0) {
    await expect(banner).not.toBeVisible();
  }
});
