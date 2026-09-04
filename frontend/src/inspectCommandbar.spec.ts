import { expect, test } from "@playwright/test";
import { installMockBackend } from "./test-support/mock-lnt-backend";

/** E2E честного командбара inspect (C1): значения формы едут deep-link
 * билетом в capture и предзаполняют форму; device-статус живой
 * (GET /api/device/state с recovery_action), а не муляж. */

const BASE = "http://127.0.0.1:4101/static/v2/";

test.describe("inspect commandbar (C1)", () => {
  test("submit увозит билет в #/capture и предзаполняет форму, а не выбрасывает ввод", async ({
    page,
  }) => {
    installMockBackend(page);
    await page.goto(`${BASE}#/inspect`);
    const bar = page.locator(".cmdbar");
    await expect(bar).toBeVisible();

    // Заполняем командбар inspect своим словарём.
    await bar.locator('select[name="mode"]').selectOption("1ch");
    await bar.locator('select[name="source"]').selectOption("device");
    await bar.locator('input[name="duration"]').fill("1.5");
    await bar.locator('input[name="rate"]').fill("8000000");
    await bar.locator('select[name="range"]').selectOption("2v");
    await bar.locator('input[name="label"]').fill("точка-7");
    await bar.locator('button[type="submit"]').click();

    // Билет в URL: нативные параметры capture (±2 В → ближайший 1 В).
    await expect(page).toHaveURL(/#\/capture\?.*mode=single_channel/);
    await expect(page).toHaveURL(/source=device/);
    await expect(page).toHaveURL(/duration_s=1\.5/);
    await expect(page).toHaveURL(/sample_rate_hz=8000000/);
    await expect(page).toHaveURL(/range_v=1/);
    await expect(page).toHaveURL(/label=%D1%82%D0%BE%D1%87%D0%BA%D0%B0-7/);

    // Форма capture предзаполнена билетом.
    await expect(page.locator(".view-title")).toHaveText("Захват");
    await expect(page.locator('input[name="capture-mode"][value="single_channel"]')).toBeChecked();
    await expect(page.locator('input[name="capture-source"][value="device"]')).toBeChecked();
    await expect(page.locator('input[name="duration_s"]')).toHaveValue("1.5");
    await expect(page.locator('input[name="sample_rate_hz"]')).toHaveValue("8000000");
    await expect(page.locator('select[name="range_v"]')).toHaveValue("1");
    await expect(page.locator('input[name="label"]')).toHaveValue("точка-7");
  });

  test("живой device-статус: ready показывает действие из бэкенда", async ({ page }) => {
    installMockBackend(page);
    await page.goto(`${BASE}#/inspect`);

    const status = page.locator("[data-device-status]");
    await expect(status).toBeVisible();
    await expect(status).toContainText("Устройство готово");
    await expect(status).toContainText("Дополнительные действия не требуются.");
  });

  test("живой device-статус: driver_missing показывает точное действие Zadig", async ({ page }) => {
    installMockBackend(page, { deviceState: "driver_missing" });
    await page.goto(`${BASE}#/inspect`);

    const status = page.locator("[data-device-status]");
    await expect(status).toBeVisible();
    await expect(status).toContainText("Устройство не готово");
    await expect(status).toContainText(
      "Установите WinUSB через Zadig отдельно для обнаруженного VID и повторите проверку.",
    );
  });
});
