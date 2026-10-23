/** E2E секции декларации адаптера (N7): видимость только для
 * ripple+device, утвердительная галка без дефолта, динамика предупреждения
 * пола (правка C / базис / длительность), тело POST /api/jobs с
 * adapter_declaration и стабильность позиций неизменных узлов на двух
 * ширинах — 1280×720 и 1920×1080 (класс дефектов r5 владельца, H12).
 * Существующие пины capture.spec.ts не тронуты; новые — по конвенции
 * классов секции. */

import { type Page, expect, test } from "@playwright/test";
import { installMockBackend } from "./testkit/mockBackend";

const BASE = "http://127.0.0.1:4101/static/v2/";
const STEP2 = '.capture-step[data-capture-step="2"]';
const GROUP = ".capture-adapter-group";

async function openRippleStep2(page: Page, device: boolean): Promise<void> {
  await page.goto(`${BASE}#/capture`);
  await page.locator('label[for="capture-mode-ripple_measurement"]').click();
  if (device) await page.locator('label[for="capture-source-device"]').click();
  await page.getByRole("button", { name: "Далее: параметры" }).click();
  await expect(page.locator(STEP2)).toBeVisible();
}

test.describe("секция декларации адаптера (N7)", () => {
  test("скрыта для прочих режимов и для симулятора", async ({ page }) => {
    installMockBackend(page);

    // Дефолт: rc_measurement + симулятор.
    await page.goto(`${BASE}#/capture`);
    await page.getByRole("button", { name: "Далее: параметры" }).click();
    await expect(page.locator(STEP2)).toBeVisible();
    await expect(page.locator(GROUP)).toBeHidden();

    // ripple + симулятор: декларацию не собираем (D7).
    await page.getByRole("button", { name: "Назад: режим" }).click();
    await page.locator('label[for="capture-mode-ripple_measurement"]').click();
    await page.getByRole("button", { name: "Далее: параметры" }).click();
    await expect(page.locator(STEP2)).toBeVisible();
    await expect(page.locator(GROUP)).toBeHidden();
  });

  test("видима для ripple+device: галка не отмечена, дефолты пресета, подсказка", async ({
    page,
  }) => {
    installMockBackend(page);
    await openRippleStep2(page, true);

    await expect(page.locator(GROUP)).toBeVisible();
    await expect(page.locator(`${GROUP} legend`)).toHaveText("Декларация адаптера");
    await expect(page.locator('input[name="adapter_preconnected"]')).not.toBeChecked();
    await expect(page.locator('input[name="adapter_cap_nf"]')).toHaveValue("100");
    await expect(page.locator('input[name="adapter_series_r_ohm"]')).toHaveValue("0");
    await expect(
      page.locator('input[name="adapter_component_values_basis"][value="nominal"]'),
    ).toBeChecked();
    await expect(page.locator(".capture-adapter-hint")).toBeVisible();
    await expect(page.locator(".capture-adapter-floor")).toBeHidden();

    // a11y-пол: крупные цели 44px у утверждения и опций базиса.
    const confirmBox = await page.locator("label.capture-adapter-confirm").boundingBox();
    expect(confirmBox?.height ?? 0).toBeGreaterThanOrEqual(44);
    for (const option of await page.locator("label.capture-basis-option").all()) {
      const box = await option.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
  });

  test("правка C и переключение базиса обновляют предупреждение пола", async ({ page }) => {
    installMockBackend(page);
    await openRippleStep2(page, true);
    const floor = page.locator(".capture-adapter-floor");
    await expect(floor).toBeHidden();

    // C=1000: пол 11 с длиннее записи 2.4 с — предупреждение появляется.
    await page.locator('input[name="adapter_cap_nf"]').fill("1000");
    await expect(floor).toBeVisible();
    await expect(floor).toContainText("При C=1000 нФ и fs=8000000 Гц");
    await expect(floor).toContainText("нужно ≥11 с записи — увеличьте длительность");

    // Переключение базиса: предупреждение пересчитывается и остаётся верным.
    await page.locator("label.capture-basis-option", { hasText: "измерено оператором" }).click();
    await expect(
      page.locator('input[name="adapter_component_values_basis"][value="operator_measured"]'),
    ).toBeChecked();
    await expect(floor).toContainText("нужно ≥11 с записи");

    // C назад к номиналу — предупреждение уходит (2.4 ≥ 2.0).
    await page.locator('input[name="adapter_cap_nf"]').fill("100");
    await expect(floor).toBeHidden();

    // Длительность короче пола тоже включает предупреждение.
    await page.locator('input[name="duration_s"]').fill("1.5");
    await expect(floor).toBeVisible();
    await expect(floor).toContainText("нужно ≥2 с записи");
  });

  test("предупреждение пола НЕ блокирует «Далее»", async ({ page }) => {
    installMockBackend(page);
    await openRippleStep2(page, true);
    await page.locator('input[name="adapter_cap_nf"]').fill("1000");
    await expect(page.locator(".capture-adapter-floor")).toBeVisible();

    await page.getByRole("button", { name: "Далее: запуск" }).click();
    await expect(page.locator('.capture-step[data-capture-step="3"]')).toBeVisible();
  });

  test("запуск ripple+device отправляет adapter_declaration в POST /api/jobs", async ({ page }) => {
    const backend = installMockBackend(page);
    await openRippleStep2(page, true);

    // Оператор утверждает подключение и базис, меняет C/Rs.
    await page.locator("label.capture-adapter-confirm").click();
    await page.locator("label.capture-basis-option", { hasText: "измерено оператором" }).click();
    await page.locator('input[name="adapter_cap_nf"]').fill("220");
    await page.locator('input[name="adapter_series_r_ohm"]').fill("4.7");

    await page.getByRole("button", { name: "Далее: запуск" }).click();
    await page.getByRole("button", { name: "Запустить запись" }).click();
    await expect(page.locator(".capture-timeline")).toContainText("Задача выполняется");
    backend.pumpAll();
    await expect(page.locator(".capture-timeline")).toContainText("Задача завершена");

    expect(backend.startedRequests).toHaveLength(1);
    await expect(backend.startedRequests[0]).toMatchObject({
      kind: "capture",
      channels: 1,
      adapter_declaration: {
        preconnected: true,
        cap_nf: 220,
        series_r_ohm: 4.7,
        component_values_basis: "operator_measured",
      },
    });
  });

  test("запуск ripple+симулятор уходит kind:simulate без декларации (D7)", async ({ page }) => {
    const backend = installMockBackend(page);
    await openRippleStep2(page, false);

    await page.getByRole("button", { name: "Далее: запуск" }).click();
    await page.getByRole("button", { name: "Запустить запись" }).click();
    backend.pumpAll();
    await expect(page.locator(".capture-timeline")).toContainText("Задача завершена");

    await expect(backend.startedRequests[0]).toMatchObject({ kind: "simulate" });
    await expect(backend.startedRequests[0]).not.toHaveProperty("adapter_declaration");
  });
});

for (const [width, height] of [
  [1280, 720],
  [1920, 1080],
] as const) {
  test(`позиции неизменных узлов равны до/после смены значений @${width}×${height}`, async ({
    page,
  }) => {
    installMockBackend(page);
    await page.setViewportSize({ width, height });
    await openRippleStep2(page, true);

    // Снимок позиций: заголовок шага, поля настроек, статическая строка
    // тракта, раскрытие серии и кнопка «Далее» — узлы и выше, и НИЖЕ
    // динамических слотов секции. Координаты — относительно корня .capture-view:
    // прокрутка контейнера сдвигает и базу, и узлы одинаково, поэтому остаётся
    // только раскладка (Playwright прокручивает цель действия в вид).
    const boxes = (): Promise<number[][]> =>
      page.evaluate(() => {
        const origin = document.querySelector(".capture-view");
        const selectors = [
          '.capture-step[data-capture-step="2"] .capture-step-title',
          'input[name="duration_s"]',
          'input[name="sample_rate_hz"]',
          ".capture-adapter-fixed",
          ".disc-toggle",
          '.capture-step[data-capture-step="2"] .capture-step-actions .lnt-btn-primary',
        ];
        if (origin === null) throw new Error("нет .capture-view");
        const base = origin.getBoundingClientRect();
        const round = (value: number): number => Math.round(value * 10) / 10;
        return selectors.map((selector) => {
          const node = document.querySelector(selector);
          if (node === null) throw new Error(`нет ${selector}`);
          const box = node.getBoundingClientRect();
          return [box.x - base.x, box.y - base.y, box.width, box.height].map(round);
        });
      });

    const before = await boxes();

    // Смена значений: галка прячет подсказку, C включает пол, базис меняется.
    await page.locator("label.capture-adapter-confirm").click();
    await page.locator('input[name="adapter_cap_nf"]').fill("1000");
    await expect(page.locator(".capture-adapter-floor")).toBeVisible();
    await page.locator("label.capture-basis-option", { hasText: "измерено оператором" }).click();

    const after = await boxes();
    expect(after).toEqual(before);
  });
}
