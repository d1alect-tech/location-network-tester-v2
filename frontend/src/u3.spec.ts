import { expect, test } from "@playwright/test";
import type { CatalogSession } from "./api/types";
import { type MockLntBackend, installMockBackend } from "./testkit/mockBackend";

// U3/U4: сигнатура пары дефолтом — бейджи в паирбаре + Δ-полоса под спектром.
function catalog(): CatalogSession[] {
  return ["u3-a", "u3-b"].map((id) => ({
    id,
    health: "ok",
    created_utc: "2026-08-01T10:00:00Z",
    source: "synthetic",
    session_type: "mains",
    profile: "quiet",
    label: id,
    storage_path: null,
  }));
}

function detail(name: string): unknown {
  return {
    name,
    manifest: { session_id: name },
    analysis: { needle: { cycles_analyzed: 60 }, spectrum: {} },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

function spectrum(psd: number[]): Record<string, unknown> {
  return {
    frequency_hz: [3000, 45000],
    psd_v2_per_hz: psd,
    point_count: 2,
    resolution_hz: 30,
    band_low_hz: 3000,
    band_high_hz: 45000,
    window: "hann",
    enbw_hz: 45,
  };
}

function seed(backend: MockLntBackend): void {
  backend.seedCatalog(catalog());
  backend.seedSessionDetail("u3-a", detail("u3-a"));
  backend.seedSessionDetail("u3-b", detail("u3-b"));
  backend.seedSpectrum("u3-a", spectrum([1e-6, 1e-4]));
  backend.seedSpectrum("u3-b", spectrum([1e-5, 1e-3]));
  backend.seedAnalysisPointer("u3-a", null);
  backend.seedAnalysisPointer("u3-b", null);
}

const INSPECT = "http://127.0.0.1:4101/static/v2/#/inspect?a=u3-a&b=u3-b";

test("U3: бейджи пары показывают Δср +10 дБ", async ({ page }) => {
  seed(installMockBackend(page));
  await page.goto(INSPECT);
  await expect(page.locator(".app-v6")).toBeVisible();
  await expect(page.locator('[data-pair-delta="mean"]')).toHaveText("Δср +10,0 дБ");
  await expect(page.locator('[data-pair-delta="max"]')).toHaveText("Δmax +10,0 дБ");
});

test("U3: Δ-полоса под спектром с тумблером и памятью", async ({ page }) => {
  seed(installMockBackend(page));
  await page.goto(INSPECT);
  const strip = page.locator("[data-delta-strip]");
  await expect(strip).toBeVisible();
  await expect(strip.locator("[data-delta-canvas]")).toBeAttached();
  const toggle = strip.locator("[data-delta-toggle]");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await toggle.click();
  await expect(strip).toHaveClass(/is-closed/);
  await page.reload();
  await expect(page.locator(".app-v6")).toBeVisible();
  await expect(page.locator("[data-delta-strip]")).toHaveClass(/is-closed/);
});

test("U3: бейджи и полоса переживают перезагрузку парой", async ({ page }) => {
  seed(installMockBackend(page));
  await page.goto(INSPECT);
  await expect(page.locator('[data-pair-delta="mean"]')).toHaveText("Δср +10,0 дБ");
  await page.reload();
  await expect(page.locator('[data-pair-delta="mean"]')).toHaveText("Δср +10,0 дБ");
  await expect(page.locator("[data-delta-strip]")).toBeVisible();
});
