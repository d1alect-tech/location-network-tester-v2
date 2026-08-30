import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { buildSpectrogramNpz } from "../../test-support/spectrogramNpz";

/** Приёмочные сценарии V6 (ADR-0009): #/inspect — окно сравнения.
 *  Доказываем ОТРИСОВАННЫЙ результат (канвы, глифы, сетка), а не логи. */

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";

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
const WAVEFORM = {
  channel: "ch1",
  time_s: [0, 0.25, 0.5, 0.75],
  voltage_v: [0.05, -0.15, 0.2, -0.1],
  point_count: 4,
};

function detail(name: string, ch2: boolean): unknown {
  return {
    name,
    manifest: { session_id: name },
    analysis: {
      needle: {
        line_frequency_hz: 50.0,
        needle_mean_v: 0.0012,
        needle_sigma_ratio: 0.35,
        async_sync_ratio: ch2 ? 0.08 : null,
        cycles_analyzed: 120,
      },
      spectrum: {
        peaks: [{ frequency_hz: 1000, level_db: -20, prominence_db: 18.4, q_factor: 9.5 }],
        band_low_hz: 3000,
        band_high_hz: 1350000,
        resolution_hz: 100,
      },
      ch1_input_reference: { status: "unavailable", reason_code: "manifest_schema_v1" },
    },
    spectrum_available: true,
    waveform_available: true,
    ch2_available: ch2,
  };
}

function level(timeBins: number, offsetDb: number): {
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

async function mockApi(page: Page, opts?: { bTimeBins?: number; ch2?: boolean }): Promise<void> {
  const ch2 = opts?.ch2 ?? true;
  const bTimeBins = opts?.bTimeBins ?? 16;
  const json = (body: unknown): string => JSON.stringify(body);
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(CATALOG) }),
  );
  await page.route("**/api/sessions/capture-001", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(detail("capture-001", ch2)) }),
  );
  await page.route("**/api/sessions/capture-002", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(detail("capture-002", ch2)) }),
  );
  await page.route("**/api/sessions/capture-001/spectrum?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(SPECTRUM_A) }),
  );
  await page.route("**/api/sessions/capture-002/spectrum?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(SPECTRUM_B) }),
  );
  await page.route("**/api/sessions/capture-001/waveform?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(WAVEFORM) }),
  );
  await page.route("**/api/analysis/sessions/capture-001/.lnt-default-analysis.json", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json({ artifact_key: "art-a" }) }),
  );
  await page.route("**/api/analysis/sessions/capture-002/.lnt-default-analysis.json", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json({ artifact_key: "art-b" }) }),
  );
  await page.route("**/api/analysis/sessions/capture-001/artifacts/art-a/spectrogram.npz", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/octet-stream",
      body: Buffer.from(buildSpectrogramNpz(level(16, 0))),
    }),
  );
  await page.route("**/api/analysis/sessions/capture-002/artifacts/art-b/spectrogram.npz", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/octet-stream",
      body: Buffer.from(buildSpectrogramNpz(level(bTimeBins, 5))),
    }),
  );
}

async function paintedRatio(page: Page, selector: string): Promise<number> {
  return page.evaluate((sel) => {
    const canvas = document.querySelector(`${sel} canvas`);
    if (!(canvas instanceof HTMLCanvasElement)) return -1;
    const ctx = canvas.getContext("2d");
    if (ctx === null || canvas.width === 0 || canvas.height === 0) return -1;
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let opaque = 0;
    for (let i = 3; i < data.length; i += 4) if ((data[i] ?? 0) > 0) opaque += 1;
    return opaque / (data.length / 4);
  }, selector);
}

test("V6-P1: полная сетка сравнения, не стопка воркбенча", async ({ page }) => {
  await mockApi(page);
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();
  // Глобальная шапка скрыта на инспекции.
  await expect(page.locator(".app-header")).toBeHidden();
  // Пара названа.
  await expect(page.locator(".pairbar [data-pair='a']")).toContainText("База");
  await expect(page.locator(".pairbar [data-pair='b']")).toContainText("Сравнение");
  // Тело: каталог слева, главное справа.
  await expect(page.locator(".app-body .col-cat")).toBeVisible();
  await expect(page.locator(".app-body .col-main")).toBeVisible();
  await expect(page.locator(".col-main [data-showcase='spectrum']")).toBeVisible();
  await expect(page.locator(".col-main .analysis-band")).toBeVisible();
  await expect(page.locator(".col-main .v6-extras")).toBeVisible();
  // Старой стопки нет.
  await expect(page.locator(".charts-workbench-host")).toHaveCount(0);
  await expect(page.locator(".lnt-workbench")).toHaveCount(0);
  await expect(page.locator(".lnt-spec-panel")).toHaveCount(0);
});

test("V6-P2: одно окно — оверлей А/Б и спектрограмма по тумблеру", async ({ page }) => {
  await mockApi(page);
  await page.goto(BASE);
  const panel = page.locator("[data-showcase='spectrum']");
  await expect(panel).toBeVisible();
  await expect(panel.locator(".frame")).toBeVisible();
  await expect(panel.locator(".gram")).toBeHidden();
  // Оверлей: обе сессии в легенде одного графика.
  const legend = panel.locator(".frame .u-legend");
  await expect(legend).toContainText("capture-001");
  await expect(legend).toContainText("capture-002");
  // Спектр нарисован.
  await expect
    .poll(async () => paintedRatio(page, "[data-showcase='spectrum'] .frame"), { timeout: 10_000 })
    .toBeGreaterThan(0.05);

  // Переключение в спектрограмму прячет график и показывает грам.
  await panel.locator("[data-spectrum-view='gram']").click();
  await expect(panel).toHaveClass(/is-gram/);
  await expect(panel.locator(".frame")).toBeHidden();
  await expect(panel.locator(".gram")).toBeVisible();
  // Грам закрашен (режим Б по умолчанию).
  await expect
    .poll(async () => paintedRatio(page, "[data-showcase='spectrum'] .gram"), { timeout: 15_000 })
    .toBeGreaterThan(0.5);
  // Возврат к спектру.
  await panel.locator("[data-spectrum-view='spectrum']").click();
  await expect(panel).not.toHaveClass(/is-gram/);
  await expect(panel.locator(".frame")).toBeVisible();
});

test("V6-P3: каталог — группы, сортировка, поиск, клик в пару", async ({ page }) => {
  await mockApi(page);
  await page.goto(BASE);
  const cat = page.locator(".col-cat");
  await expect(cat.locator("[data-session]")).toHaveCount(2);
  // Две разные даты → две группы.
  await expect(cat.locator("[data-cat-group]")).toHaveCount(2);
  // Сортировка по метке распускает группы.
  await cat.locator("[data-cat-sort='label'] button, [data-cat-sort='label']").first().click();
  await expect(cat.locator("[data-cat-group]")).toHaveCount(0);
  // Роли совпадают с парой (авто-подбор первых двух).
  await expect(cat.locator("[data-cat-role='a']")).toHaveCount(1);
  await expect(cat.locator("[data-cat-role='b']")).toHaveCount(1);
  // Поиск сужает.
  await cat.locator("[data-cat-search]").fill("стенд-А");
  await expect(cat.locator("[data-session]")).toHaveCount(1);
  await cat.locator("[data-cat-search]").fill("нет-такого");
  await expect(cat.locator("[data-cat-empty]")).toBeVisible();
});

test("V6-P4: дельта пика из трасс, глиф направления", async ({ page }) => {
  await mockApi(page);
  await page.goto(BASE);
  const deltaCell = page.locator(".analysis-band [data-delta]").first();
  await expect(deltaCell).toBeVisible();
  // 10*log10(8e-3/1e-2) ≈ -0.969 → минус, глиф ▼.
  const value = Number(await deltaCell.getAttribute("data-delta"));
  expect(Math.abs(value - -0.969)).toBeLessThan(0.05);
  await expect(deltaCell).toContainText("▼");
});

test("V6-P5: полный захват и возврат через таббар", async ({ page }) => {
  await mockApi(page);
  await page.goto(BASE);
  await expect(page.locator(".app-header")).toBeHidden();
  await expect(page.locator(".app-v6 .tabbar a[href='#/inspect']")).toHaveAttribute(
    "aria-current",
    "page",
  );
  // Клик по «Каталог» в таббаре возвращает глобальную шапку.
  await page.locator(".app-v6 .tabbar a[href='#/catalog']").click();
  await expect(page).toHaveURL(/#\/catalog/);
  await expect(page.locator(".app-header")).toBeVisible();
  await expect(page.locator(".app-v6")).toHaveCount(0);
});

test("V6-P6: сворачиваемые панели осциллограммы и анализа", async ({ page }) => {
  await mockApi(page);
  await page.goto(BASE);
  const wave = page.locator(".v6-extras details[data-extra='waveform']");
  const w1 = page.locator(".v6-extras details[data-extra='w1']");
  await expect(wave).toBeVisible();
  await expect(w1).toBeVisible();
  // Закрыты по умолчанию.
  expect(await wave.evaluate((el) => (el as HTMLDetailsElement).open)).toBe(false);
  expect(await w1.evaluate((el) => (el as HTMLDetailsElement).open)).toBe(false);
  // Открытие осциллограммы грузит CH1.
  await wave.locator("summary").click();
  await expect(wave.locator(".uplot")).toBeVisible({ timeout: 10_000 });
  // W1-хром содержит CTA пересчёта.
  await w1.locator("summary").click();
  await expect(w1).toContainText("Пересчитать анализ (v2)");
});

test("V6-P7: показания базы, н/д для одноканальной сессии", async ({ page }) => {
  await mockApi(page, { ch2: false });
  await page.goto(BASE);
  const readout = page.locator(".analysis-band .readout-value");
  await expect(readout).toHaveCount(7);
  // P_async/P_sync отсутствует в один канал → «н/д», не 0.
  await expect(page.locator(".analysis-band .readout-cell").filter({ hasText: "P_async" })).toContainText(
    "н/д",
  );
});

test("V6-P8: несовпадение сеток отключает дельту грама", async ({ page }) => {
  await mockApi(page, { bTimeBins: 8 });
  await page.goto(BASE);
  const panel = page.locator("[data-showcase='spectrum']");
  await panel.locator("[data-spectrum-view='gram']").click();
  const deltaBtn = panel.locator("[data-spectrogram-mode='delta']");
  await expect(deltaBtn).toBeDisabled();
  await expect(panel.locator(".gram-scale")).toContainText("не совпадают");
  // Режимы A/B работают.
  await expect(panel.locator("[data-spectrogram-mode='b']")).toBeEnabled();
});

test("V6-P9: пустой каталог — заглушка и прочерки пары", async ({ page }) => {
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], next_cursor: null }),
    }),
  );
  await page.goto(BASE);
  await expect(page.locator(".col-cat [data-cat-empty]")).toBeVisible();
  await expect(page.locator(".pairbar [data-pair='a']")).toContainText("—");
  await expect(page.locator(".pairbar [data-pair='b']")).toContainText("—");
});
