import { expect, test } from "@playwright/test";

test("AppShell loads offline with zero non-loopback requests", async ({ page }) => {
  const nonLoopbackRequests: string[] = [];

  // Intercept all requests to verify they are only to loopback
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") {
      nonLoopbackRequests.push(url.href);
    }
    await route.continue();
  });

  // Go to the app shell
  await page.goto("http://127.0.0.1:4101/static/v2/");

  // Verify the app shell title is correct
  await expect(page).toHaveTitle("LNT v2 Workbench");
  await expect(page).toHaveURL("http://127.0.0.1:4101/static/v2/#/catalog");
  await expect(page.locator(".lnt-cat-workspace")).toBeVisible();

  // Verify navigation links exist
  const navLinks = page.locator(".nav-link");
  await expect(navLinks).toHaveCount(7);

  // Verify we can navigate to different views
  await page.click("#nav-capture");
  // Todo 40: раздел «Захват» рендерит полный рабочий процесс вместо заглушки.
  await expect(page.locator(".view-title")).toHaveText("Захват");

  await page.click("#nav-inspect");
  await expect(page.locator(".app-v6")).toBeVisible();
  await expect(page.locator(".app-header")).toBeHidden();

  // Verify error boundary works
  // Navigate to experiments with trigger-error query param
  await page.goto("http://127.0.0.1:4101/static/v2/?trigger-error#/experiments");
  const errorPanel = page.locator(".error-panel");
  await expect(errorPanel).toBeVisible();
  await expect(errorPanel.locator(".error-title")).toHaveText("Критическая ошибка интерфейса");
  await expect(errorPanel.locator(".error-message")).toContainText("Тестовая критическая ошибка");

  // Click recovery button and verify we are back on catalog
  // Note: window.location.reload() is called, so we wait for the page to reload and hash to be #/catalog
  await page.click("#btn-recover");
  // Wait for the URL to change back to catalog
  await expect(page).toHaveURL("http://127.0.0.1:4101/static/v2/#/catalog");
  await expect(page.locator(".lnt-cat-workspace")).toBeVisible();

  // Assert zero non-loopback requests
  expect(nonLoopbackRequests).toEqual([]);
});
