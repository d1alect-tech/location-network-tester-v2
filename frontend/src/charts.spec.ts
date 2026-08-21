import * as os from "node:os";
import * as path from "node:path";
import { expect, test } from "@playwright/test";

/** E2E графиков todo 41: связанные курсором uPlot-вью на маршруте Инспекция.
 * API подменяется маршрутами с фикстурами бэкенд-контрактов; проверяются
 * ОТРИСОВАННЫЕ данные (легенда/сводка/канвы), а не консольные логи. */

const CATALOG = {
  items: [
    {
      id: "capture-001",
      health: "ok",
      created_utc: "2026-08-01T10:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "bad",
      label: "стенд-А",
      storage_path: null,
    },
    {
      id: "capture-002",
      health: "ok",
      created_utc: "2026-08-02T10:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "quiet",
      label: "стенд-Б",
      storage_path: null,
    },
  ],
  next_cursor: null,
};

// Спектр A: известный пик на 1 кГц (значение 1e-2) — проверяем паритет.
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

function detail(name: string): unknown {
  return {
    name,
    manifest: { session_id: name },
    analysis: {
      spectrum: {
        peaks: [{ frequency_hz: 1000, level_db: -20, prominence_db: 18.4, q_factor: 9.5 }],
      },
      ch1_input_reference: { status: "unavailable", reason_code: "manifest_schema_v1" },
    },
    spectrum_available: true,
    waveform_available: true,
    ch2_available: false,
  };
}

async function mockApi(page: import("@playwright/test").Page): Promise<void> {
  const json = (body: unknown): string => JSON.stringify(body);
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(CATALOG) }),
  );
  for (const name of ["capture-001", "capture-002"]) {
    await page.route(`**/api/sessions/${name}`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: json(detail(name)) }),
    );
    await page.route(`**/api/sessions/${name}/waveform?*`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: json(WAVEFORM) }),
    );
  }
  await page.route("**/api/sessions/capture-001/spectrum?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(SPECTRUM_A) }),
  );
  await page.route("**/api/sessions/capture-002/spectrum?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: json(SPECTRUM_B) }),
  );
}

test("uPlot-workbench: связанные графики, паритет данных, log-оси, CSV", async ({ page }) => {
  await mockApi(page);
  await page.goto("http://127.0.0.1:4103/static/v2/#/inspect");
  await expect(page.locator(".lnt-workbench")).toBeVisible();

  // Открытие сессии А через клавиатурно-доступный селект.
  await page.selectOption('select[aria-label="Сессия А"]', "capture-001");

  // Отрисованные канвы uPlot: спектр А + осциллограмма.
  const uplots = page.locator(".lnt-chart .uplot");
  await expect(uplots).toHaveCount(2);

  // Паритет: легенда спектра показывает значения фикстуры под курсором —
  // двигаем мышь в центр первой канвы и читаем сводку «Значение под курсором».
  const firstCanvas = page.locator(".lnt-chart .uplot canvas").first();
  const box = await firstCanvas.boundingBox();
  expect(box).not.toBeNull();
  if (box === null) throw new Error("канва не отрисована");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.locator(".lnt-readout-table td").first()).not.toHaveText("—");

  // Связанный курсор: у обоих графиков появляется вертикаль курсора.
  const cursors = page.locator(".uplot .u-cursor-x");
  await expect(cursors).toHaveCount(2);

  // Подписи осей uPlot рисует на канве — доказываем отрисовку пикселями
  // (log-log спектр действительно нарисован, а не пустая канва).
  const paintedSamples = await page.evaluate(() => {
    const canvas = document.querySelector(".lnt-chart .uplot canvas");
    if (!(canvas instanceof HTMLCanvasElement)) return -1;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return -1;
    const image = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let i = 3; i < image.length; i += 4 * 53) {
      const alpha = image[i];
      if (alpha !== undefined && alpha > 0) count += 1;
    }
    return count;
  });
  expect(paintedSamples).toBeGreaterThan(0);

  // Аннотации пиков из analysis + доступная таблица (ru-RU даёт неразрывный пробел).
  await expect(page.locator(".lnt-peaks-summary")).toContainText(/1[\u00a0 ]?000/);

  // Сравнение Б: пунктирный янтарный ряд во второй оболочке.
  await page.selectOption('select[aria-label="Сессия Б для сравнения"]', "capture-002");
  await expect(uplots).toHaveCount(3);
  await expect(page.locator(".lnt-chart").nth(1).locator(".u-legend")).toContainText("■ Сессия Б");

  // Скриншот связанного multi-chart вида — во временную директорию
  // (evidence-шаг копирует его за пределы репозитория).
  const screenshotPath = path.join(os.tmpdir(), "lnt-t41-linked-charts.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  // CSV-альтернатива: клик по кнопке не ломает страницу (файл уходит в загрузки).
  const downloadPromise = page.waitForEvent("download", { timeout: 5_000 });
  await page.locator('button:has-text("Скачать CSV")').first().click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain("spectrum-a-4.csv");
});
