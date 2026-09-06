import { expect, test } from "@playwright/test";
import type { CatalogSession } from "./api/types";
import { type MockLntBackend, installMockBackend } from "./testkit/mockBackend";

// U2/U4: channel-bar дефолтом в inspect и capture; леса снесены.
function catalog(): CatalogSession[] {
  return ["chb-a", "chb-b"].map((id) => ({
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
    analysis: { needle: { cycles_analyzed: 120 }, spectrum: {} },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

const SPECTRUM = {
  frequency_hz: [3000, 45000],
  psd_v2_per_hz: [1e-6, 1e-4],
  point_count: 2,
  resolution_hz: 30,
  band_low_hz: 3000,
  band_high_hz: 45000,
  window: "hann",
  enbw_hz: 45,
};

function seed(backend: MockLntBackend): void {
  backend.seedCatalog(catalog());
  for (const id of ["chb-a", "chb-b"]) {
    backend.seedSessionDetail(id, detail(id));
    backend.seedSpectrum(id, SPECTRUM);
    backend.seedAnalysisPointer(id, null);
  }
}

test("U2: inspect показывает channel-bar с пятью полями", async ({ page }) => {
  seed(installMockBackend(page));
  await page.goto("http://127.0.0.1:4101/static/v2/#/inspect?a=chb-a&b=chb-b");
  const bar = page.locator(".channelbar");
  await expect(bar).toBeVisible();
  await expect(bar.locator('[data-chbar="band"]')).toHaveText("3 кГц – 45 кГц");
  await expect(bar.locator('[data-chbar="rbw"]')).toHaveText("45 Гц");
  await expect(bar.locator('[data-chbar="window"]')).toHaveText("Ханн");
  await expect(bar.locator('[data-chbar="detector"]')).toHaveText("Среднее");
  await expect(bar.locator('[data-chbar="segments"]')).toHaveText("120");
});

test("U2: capture показывает проекцию из формы", async ({ page }) => {
  installMockBackend(page);
  await page.goto("http://127.0.0.1:4101/static/v2/#/capture");
  const bar = page.locator(".channelbar");
  await expect(bar).toBeVisible();
  await expect(bar.locator('[data-chbar="band"]')).toHaveText("3 кГц – 3 МГц");
  await expect(bar.locator('[data-chbar="window"]')).toHaveText("Ханн");
  await expect(bar.locator('[data-chbar="segments"]')).toHaveText("—");
});

test("U2: бар переживает перезагрузку", async ({ page }) => {
  seed(installMockBackend(page));
  await page.goto("http://127.0.0.1:4101/static/v2/#/inspect?a=chb-a&b=chb-b");
  await expect(page.locator(".channelbar")).toBeVisible();
  await page.reload();
  await expect(page.locator(".channelbar")).toBeVisible();
  await expect(page.locator(".channelbar").locator('[data-chbar="band"]')).not.toBeEmpty();
});
