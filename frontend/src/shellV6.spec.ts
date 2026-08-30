import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

/** Контракт общей V6-оболочки (раскатка дизайна витрины на всё приложение):
 *  единые шапка (.hdr с таббаром .snav-item) и статус-бар (.statusbar) на ВСЕХ
 *  маршрутах; старой .app-header больше нет; инспект не дублирует шелл.
 *  Доказываем отрисованный DOM, а не логи. */

const BASE = "http://127.0.0.1:4101/static/v2/";

const TABS = 6; // Каталог, Захват, Инспекция, Эксперименты, Отчёты, Настройки (prepare скрыт из таббара)

const ROUTES = [
  "catalog",
  "capture",
  "inspect",
  "experiments",
  "reports",
  "settings",
  "prepare",
] as const;

async function mockInspectApi(page: Page): Promise<void> {
  const json = (body: unknown): string => JSON.stringify(body);
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: json({
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
      }),
    }),
  );
  await page.route("**/api/sessions/capture-001", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: json({
        name: "capture-001",
        manifest: {},
        analysis: null,
        spectrum_available: true,
        waveform_available: false,
        ch2_available: false,
      }),
    }),
  );
  await page.route("**/api/sessions/capture-001/spectrum?*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: json({ frequency_hz: [10, 100, 1000], psd_v2_per_hz: [1e-6, 1e-4, 1e-2], point_count: 3 }),
    }),
  );
  await page.route("**/api/analysis/sessions/capture-001/.lnt-default-analysis.json", (route) =>
    route.fulfill({ status: 404, contentType: "application/json", body: json({ detail: "not found" }) }),
  );
}

async function noHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
}

test("S1: общая V6-шапка и статус-бар на всех маршрутах, старой шапки нет", async ({ page }) => {
  await mockInspectApi(page);
  for (const route of ROUTES) {
    await page.goto(`${BASE}#/${route}`);
    // Единая шапка витрины: бренд, таббар из 6 вкладок, статус устройства.
    const header = page.locator("header.hdr");
    await expect(header, `маршрут #/${route}: шапка .hdr`).toBeVisible();
    await expect(header.locator(".hdr-brand")).toHaveText("LNT");
    await expect(header.locator(".tabbar a.snav-item")).toHaveCount(TABS);
    // Статус-бар внизу.
    await expect(page.locator("footer.statusbar"), `маршрут #/${route}: статус-бар`).toBeVisible();
    // Старой шапки больше нет нигде.
    await expect(page.locator(".app-header")).toHaveCount(0);
    // Активная вкладка помечена; на prepare активной вкладки нет.
    const active = header.locator(".tabbar a.snav-item[aria-current='page']");
    if (route === "prepare") {
      await expect(active).toHaveCount(0);
    } else {
      await expect(active).toHaveCount(1);
      await expect(active).toHaveAttribute("href", `#/${route}`);
    }
    await noHorizontalOverflow(page);
  }
});

test("S2: инспект под общей оболочкой — окно сравнения без дублирования шелла", async ({ page }) => {
  await mockInspectApi(page);
  await page.goto(`${BASE}#/inspect`);
  // Окно сравнения на месте: полоса пары, каталог, сигнальное окно, лента анализа.
  await expect(page.locator(".pairbar")).toBeVisible();
  await expect(page.locator(".app-body .col-cat")).toBeVisible();
  await expect(page.locator("[data-showcase='spectrum']")).toBeVisible();
  await expect(page.locator(".analysis-band")).toBeVisible();
  // Шелл не дублируется внутри view-контейнера: ровно одна .hdr на странице.
  await expect(page.locator("header.hdr")).toHaveCount(1);
  await expect(page.locator("#view-container header.hdr")).toHaveCount(0);
  await expect(page.locator("#view-container footer.statusbar")).toHaveCount(0);
  // Таббар общий и рабочий: клик по «Каталог» уводит на #/catalog, шапка остаётся.
  await page.locator("header.hdr .tabbar a[href='#/catalog']").click();
  await expect(page).toHaveURL(/#\/catalog/);
  await expect(page.locator("header.hdr")).toBeVisible();
  await expect(page.locator(".app-header")).toHaveCount(0);
});

test("S2b: персона 375px — общая оболочка без горизонтальной прокрутки", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockInspectApi(page);
  for (const route of ["catalog", "inspect", "settings"] as const) {
    await page.goto(`${BASE}#/${route}`);
    await expect(page.locator("header.hdr")).toBeVisible();
    await expect(page.locator(".error-panel")).toHaveCount(0);
    await noHorizontalOverflow(page);
  }
});
