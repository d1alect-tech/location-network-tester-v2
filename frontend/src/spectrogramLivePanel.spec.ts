import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { installMockBackend } from "./testkit/mockBackend";

/** E2E live-панели спектрограммы захвата (S3): появление, пустое состояние,
 * post-hoc fallback после завершения, axe, персона 375px. Данных бэкенда
 * панель не меняет — спектр мокается на сетевом слое Playwright. */

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const BASE = "http://127.0.0.1:4101/static/v2/";

async function openCaptureWithSpectrum(page: Page): Promise<void> {
  installMockBackend(page);
  await page.goto(`${BASE}#/capture`);
}

test("live-панель видна сразу с пустым состоянием, canvas не ниже 200px", async ({ page }) => {
  await openCaptureWithSpectrum(page);
  const panel = page.locator("[data-live-spectrogram]");
  await expect(panel).toBeVisible();
  await expect(page.locator("[data-livegram-empty]")).toBeVisible();
  const box = await page.locator("[data-spectrogram-canvas]").boundingBox();
  expect(box, "canvas спектрограммы должен иметь бокс").not.toBeNull();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(200);
});

test("post-hoc fallback: завершённая сессия подписана, пустое скрыто", async ({ page }) => {
  const backend = installMockBackend(page);
  await page.goto(`${BASE}#/capture`);
  await page.getByRole("button", { name: "Запустить запись" }).click();
  backend.pumpAll();
  const session = page.locator("[data-livegram-session]");
  await expect(session).toBeVisible();
  await expect(session).toContainText(/sim-\d{3}/);
  await expect(page.locator("[data-livegram-empty]")).toBeHidden();
});

test("axe: панель спектрограммы без нарушений", async ({ page }) => {
  await openCaptureWithSpectrum(page);
  await expect(page.locator("[data-live-spectrogram]")).toBeVisible();
  await page.addScriptTag({
    path: resolve(__dirname, "../node_modules/axe-core/axe.min.js"),
  });
  const summary = await page.evaluate(() =>
    window.axe
      .run(document.querySelector("[data-live-spectrogram]") as unknown as Document, {
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

test("375px: панель без выхода за вьюпорт", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await openCaptureWithSpectrum(page);
  const panel = page.locator("[data-live-spectrogram]");
  await expect(panel).toBeVisible();
  const overflow = await page.evaluate(() => {
    const node = document.querySelector("[data-live-spectrogram]");
    if (node === null) return -1;
    const box = node.getBoundingClientRect();
    return Math.ceil(box.right) - document.documentElement.clientWidth;
  });
  expect(overflow).toBeLessThanOrEqual(0);
});
