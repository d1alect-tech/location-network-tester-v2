/** E2E плоскости спектра: тумблер скоп/вход, RBW-подпись, disable-правило, fallback. */

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";
const PANEL = "[data-showcase='spectrum']";

const CATALOG = {
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
  ],
  next_cursor: null,
};

function spectrumPayload(): Record<string, unknown> {
  return {
    frequency_hz: [10, 100, 1000, 10_000],
    psd_v2_per_hz: [1e-6, 1e-4, 1e-2, 1e-5],
    point_count: 4,
    resolution_hz: 100,
    band_low_hz: 3000,
    band_high_hz: 1350000,
  };
}

function referredPayload(): Record<string, unknown> {
  return {
    frequency_hz: [10, 100, 1000, 10_000],
    input_referred_excess_psd_v2_per_hz: [1e-12, 1e-10, 1e-8, 1e-11],
    point_count: 4,
    status: "available",
    reason_code: null,
    qualified_bin_count: 4,
    total_bin_count: 4,
    resolution_hz: 100,
  };
}

function detail(status: string | null): unknown {
  return {
    name: "capture-001",
    manifest: {},
    analysis: {
      needle: {
        line_frequency_hz: 50.0,
        needle_mean_v: 0.0012,
        needle_sigma_ratio: 0.35,
        async_sync_ratio: null,
        cycles_analyzed: 120,
      },
      spectrum: { peaks: [], band_low_hz: 3000, band_high_hz: 1350000, resolution_hz: 100 },
      ch1_input_reference:
        status === null ? null : { status, reason_code: status === "available" ? null : "no_rc" },
    },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

async function mockSpectrum(
  page: Page,
  opts: { reference: string | null; referredStatus?: number },
): Promise<void> {
  const json = (body: unknown): string => JSON.stringify(body);
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(CATALOG) }),
  );
  await page.route("**/api/sessions/capture-001", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: json(detail(opts.reference)),
    }),
  );
  await page.route("**/api/sessions/capture-001/spectrum?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(spectrumPayload()) }),
  );
  await page.route("**/api/sessions/capture-001/spectrum-input-referred?*", (route) => {
    if (opts.referredStatus !== undefined) {
      return route.fulfill({
        status: opts.referredStatus,
        contentType: "application/json",
        body: json({}),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: json(referredPayload()),
    });
  });
}

test("тумблер плоскости и RBW ≈ 1.5×df", async ({ page }) => {
  await mockSpectrum(page, { reference: "available" });
  await page.goto(BASE);
  const panel = page.locator(PANEL);
  await expect(panel.locator(".uplot")).toBeVisible({ timeout: 15_000 });

  const scope = panel.locator('[data-spectrum-plane="scope"]');
  const referred = panel.locator('[data-spectrum-plane="input-referred"]');
  await expect(scope).toHaveAttribute("aria-pressed", "true");
  await expect(referred).toBeEnabled();
  await expect(panel.locator("[data-spectrum-rbw]")).toHaveText("RBW ≈ 150 Гц");

  const requested = page.waitForRequest("**/spectrum-input-referred*");
  await referred.click();
  await requested;
  await expect(referred).toHaveAttribute("aria-pressed", "true");
  await expect(scope).toHaveAttribute("aria-pressed", "false");
  await expect(panel.locator(".uplot")).toBeVisible();
  await expect(panel.locator("[data-spectrum-rbw]")).toHaveText("RBW ≈ 150 Гц");
});

test("unavailable в detail отключает кнопку входа", async ({ page }) => {
  await mockSpectrum(page, { reference: "unavailable" });
  await page.goto(BASE);
  const panel = page.locator(PANEL);
  await expect(panel.locator(".uplot")).toBeVisible({ timeout: 15_000 });

  const referred = panel.locator('[data-spectrum-plane="input-referred"]');
  await expect(referred).toBeDisabled();
  await expect(panel.locator('[data-spectrum-plane="scope"]')).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("404 входа откатывается на скоп без баннера ошибки", async ({ page }) => {
  await mockSpectrum(page, { reference: "available", referredStatus: 404 });
  await page.goto(BASE);
  const panel = page.locator(PANEL);
  await expect(panel.locator(".uplot")).toBeVisible({ timeout: 15_000 });

  await panel.locator('[data-spectrum-plane="input-referred"]').click();
  await expect(panel.locator(".uplot")).toBeVisible();
  const banner = page.locator(".app-v6 .banner-inline");
  if ((await banner.count()) > 0) {
    await expect(banner).not.toBeVisible();
  }
});

test("axe: панель спектра без нарушений", async ({ page }) => {
  await mockSpectrum(page, { reference: "available" });
  await page.goto(BASE);
  const panel = page.locator(PANEL);
  await expect(panel.locator(".uplot")).toBeVisible({ timeout: 15_000 });
  await page.addScriptTag({
    path: resolve(__dirname, "../../../node_modules/axe-core/axe.min.js"),
  });
  const summary = await page.evaluate(() =>
    window.axe
      .run(document.querySelector("[data-showcase='spectrum']") as unknown as Document, {
        runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
      })
      .then((results) =>
        results.violations.map((violation) => ({
          id: violation.id,
          impact: violation.impact ?? null,
          nodes: violation.nodes.length,
        })),
      ),
  );
  expect(summary, `axe violations: ${JSON.stringify(summary)}`).toEqual([]);
});
