import { expect, test } from "@playwright/test";
import { installMockBackend } from "./testkit/mockBackend";

// U1/U4: R3-A «Стойка» — дефолт, леса снесены. ?ui=new оставлен в URL для
// совместимости закладок, ни на что не влияет.
test("U4: дефолт включает токены R3-A и Плекс", async ({ page }) => {
  installMockBackend(page);
  await page.goto("http://127.0.0.1:4101/static/v2/#/inspect");
  await expect(page.locator(".app-v6")).toBeVisible();

  const tokens = await page.evaluate(() => {
    const styles = getComputedStyle(document.documentElement);
    return {
      chrome: styles.getPropertyValue("--lnt-chrome").trim(),
      canvas: styles.getPropertyValue("--lnt-canvas").trim(),
      ui: styles.getPropertyValue("--lnt-ui").trim(),
      mono: styles.getPropertyValue("--lnt-mono").trim(),
      a: styles.getPropertyValue("--lnt-a").trim(),
      accent: styles.getPropertyValue("--lnt-accent").trim(),
    };
  });
  expect(tokens.chrome).toBe("#1e2125");
  expect(tokens.canvas).toBe("#17191c");
  expect(tokens.a).toBe("#3ec9e6");
  expect(tokens.accent).toBe("#5681ff");
  expect(tokens.ui).toContain("IBM Plex Sans");
  expect(tokens.mono).toContain("IBM Plex Mono");

  const brandFont = await page
    .locator(".hdr-brand")
    .evaluate((node) => getComputedStyle(node).fontFamily);
  expect(brandFont).toContain("IBM Plex Sans");
});

test("U4: плотность R3-A в скоупе inspect", async ({ page }) => {
  installMockBackend(page);
  await page.goto("http://127.0.0.1:4101/static/v2/#/inspect");
  await expect(page.locator(".app-v6")).toBeVisible();
  const vars = await page.locator(".app-v6").evaluate((node) => {
    const styles = getComputedStyle(node);
    return {
      radiusPanel: styles.getPropertyValue("--lnt-radius-panel").trim(),
      rowMin: styles.getPropertyValue("--lnt-table-row-min").trim(),
    };
  });
  expect(vars.radiusPanel).toBe("2px");
  expect(vars.rowMin).toBe("26px");
});

test("U4: ?ui=new ни на что не влияет", async ({ page }) => {
  installMockBackend(page);
  await page.goto("http://127.0.0.1:4101/static/v2/?ui=new#/inspect");
  await expect(page.locator(".app-v6")).toBeVisible();
  const chrome = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--lnt-chrome").trim(),
  );
  expect(chrome).toBe("#1e2125");
});
