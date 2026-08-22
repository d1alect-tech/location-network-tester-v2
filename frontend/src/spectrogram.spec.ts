import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import type { CandidateEventPayload } from "./api/types-analysis";
import { buildSpectrogramNpz } from "./test-support/spectrogramNpz";

/** E2E спектрограммы todo 42: стартовый тайл в капе 524000 ячеек, ТОЧНЫЙ
 * bbox-запрос по числовой форме окна, гонка устаревших ответов уровня,
 * связка маркер ↔ список событий, содержимое CSV и русская ошибка сверхкапа. */

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
  ],
  next_cursor: null,
};

const TIME_BINS = 16;
const BANDS = 4;

/** Малый уровень с известной сеткой: время 0.1·i с, полосы кГц, значение t·10+f. */
function smallLevel(): { timeS: number[]; frequencyHz: number[]; powerDb: Float32Array } {
  const timeS = Array.from({ length: TIME_BINS }, (_, i) => Number((i * 0.1).toFixed(1)));
  const frequencyHz = Array.from({ length: BANDS }, (_, f) => f * 1000);
  const powerDb = new Float32Array(TIME_BINS * BANDS);
  for (let f = 0; f < BANDS; f += 1) {
    for (let t = 0; t < TIME_BINS; t += 1) powerDb[f * TIME_BINS + t] = t * 10 + f;
  }
  return { timeS, frequencyHz, powerDb };
}

function eventAt(peakTimeS: number, snr: number, status: string): CandidateEventPayload {
  return {
    start_sample: 0,
    end_sample: 10,
    peak_sample: Math.round(peakTimeS * 100),
    start_time_s: peakTimeS - 0.01,
    end_time_s: peakTimeS + 0.01,
    peak_time_s: peakTimeS,
    peak_value_v: 0.5,
    polarity: "positive",
    dominant_band: null,
    excess_energy_v2_s: 1,
    snr,
    qualification_status: status,
    boundary: false,
    clipped: false,
  };
}

function eventsPayload(events: CandidateEventPayload[]): unknown {
  return { schema_version: 1, sample_count: 160, events };
}

async function mockCatalog(page: Page): Promise<void> {
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CATALOG) }),
  );
}

async function mockArtifact(
  page: Page,
  key: string,
  npz: ArrayBuffer,
  events: unknown,
): Promise<void> {
  const base = `**/api/analysis/sessions/capture-001/artifacts/${key}`;
  await page.route(`${base}/spectrogram.npz`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/octet-stream",
      body: Buffer.from(npz),
    }),
  );
  await page.route(`${base}/events.json`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(events) }),
  );
}

async function build(page: Page, key: string): Promise<void> {
  await page.selectOption('select[aria-label="Сессия спектрограммы"]', "capture-001");
  await page.fill('input[aria-label="Ключ артефакта анализа"]', key);
  await page.getByRole("button", { name: "Построить спектрограмму" }).click();
}

test("стартовый тайл в капе: рендер канвы, статус и сводка окна", async ({ page }) => {
  await mockCatalog(page);
  await mockArtifact(
    page,
    "art-small",
    buildSpectrogramNpz(smallLevel()),
    eventsPayload([eventAt(0.3, 12, "qualified"), eventAt(0.7, 8, "candidate")]),
  );
  await page.goto("http://127.0.0.1:4101/static/v2/#/inspect");
  await expect(page.locator(".lnt-spec-panel")).toBeVisible();
  await build(page, "art-small");

  // Стартовый тайл = весь уровень (64 ≤ капа), канонический ключ и счётчик.
  const status = page.locator(".lnt-spec-status");
  await expect(status).toHaveAttribute("data-request-key", "t0-16xf0-4");
  await expect(status).toHaveAttribute("data-cells", "64");
  expect(Number.parseInt((await status.getAttribute("data-cells")) ?? "", 10)).toBeLessThanOrEqual(
    524_000,
  );

  // Тепловая карта действительно нарисована пикселями, а не пустой канвой.
  const paintedSamples = await page.evaluate(() => {
    const canvas = document.querySelector(".lnt-spec-chart canvas");
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

  // Сводка видимого окна: диапазоны, статистика дБ и события.
  await expect(page.locator(".lnt-spec-summary-line")).toContainText("ячеек 64");
  await expect(page.locator(".lnt-spec-summary-line")).toContainText("событий 2");
});

test("числовая форма окна даёт ТОЧНЫЙ bbox-запрос и матрицу CSV", async ({ page }) => {
  await mockCatalog(page);
  await mockArtifact(page, "art-small", buildSpectrogramNpz(smallLevel()), eventsPayload([]));
  await page.goto("http://127.0.0.1:4101/static/v2/#/inspect");
  await build(page, "art-small");
  await expect(page.locator(".lnt-spec-status")).toHaveAttribute("data-request-key", "t0-16xf0-4");

  // Окно 0.3–0.7 с × 900–2100 Гц → ячейки t[3..7)×f[1..3), ключ канонический.
  await page.fill('input[aria-label="Начало окна, с"]', "0.3");
  await page.fill('input[aria-label="Конец окна, с"]', "0.7");
  await page.fill('input[aria-label="Нижняя граница окна, Гц"]', "900");
  await page.fill('input[aria-label="Верхняя граница окна, Гц"]', "2100");
  await page.getByRole("button", { name: "Обновить окно" }).click();
  const status = page.locator(".lnt-spec-status");
  await expect(status).toHaveAttribute("data-request-key", "t3-7xf1-3");
  await expect(status).toHaveAttribute("data-cells", "8");

  // CSV матрицы: заголовок + точные значения выбранного bbox (t·10+f).
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать матрицу CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain("spectrogram-t3-7xf1-3.csv");
  const csvPath = path.join(os.tmpdir(), `lnt-t42-${download.suggestedFilename()}`);
  await download.saveAs(csvPath);
  const csv = fs.readFileSync(csvPath, "utf-8");
  expect(csv.startsWith("\uFEFFtime_s,frequency_hz,power_db\n")).toBe(true);
  // ru-RU форматирует тысячи неразрывным пробелом: «1 000».
  expect(csv).toMatch(/,1[\u00a0 ]000,31/);
  expect(csv).toMatch(/,2[\u00a0 ]000,62/);
  // Ровно 8 строк данных bbox — без ячеек вне выбранного окна.
  expect(csv.trimEnd().split("\n")).toHaveLength(9);
});

test("устаревший ответ уровня не перезаписывает свежий (C→A гонка)", async ({ page }) => {
  await mockCatalog(page);
  // «Медленный» артефакт держим до ручного выпуска; события — пустые.
  let releaseSlow!: () => void;
  const slowGate = new Promise<ArrayBuffer>((resolve) => {
    releaseSlow = () => resolve(buildSpectrogramNpz(smallLevel()));
  });
  await page.route("**/artifacts/art-slow/spectrogram.npz", async (route) => {
    const body = await slowGate;
    // Запрос мог быть оборван вторым построением — ответ уже не нужен.
    try {
      await route.fulfill({
        status: 200,
        contentType: "application/octet-stream",
        body: Buffer.from(body),
      });
    } catch {
      /* Запрос закрыт: устаревший полёт отменён продуктом. */
    }
  });
  await page.route("**/artifacts/art-slow/events.json", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(eventsPayload([])),
    }),
  );
  await mockArtifact(
    page,
    "art-fast",
    buildSpectrogramNpz(smallLevel()),
    eventsPayload([eventAt(0.3, 12, "qualified"), eventAt(0.7, 8, "qualified")]),
  );
  await page.goto("http://127.0.0.1:4101/static/v2/#/inspect");

  await build(page, "art-slow"); // полёт А — завис на медленном npz
  await build(page, "art-fast"); // полёт Б — мгновенный ответ
  const status = page.locator(".lnt-spec-status");
  await expect(status).toHaveAttribute("data-request-key", "t0-16xf0-4");
  const list = page.locator(".lnt-event-list [role='option']");
  await expect(list).toHaveCount(2);

  releaseSlow(); // устаревший ответ приходит ПОСЛЕДНИМ
  await page.waitForTimeout(300);
  // Свежее состояние не перезаписано: события и тайл остались от art-fast.
  await expect(list).toHaveCount(2);
  await expect(status).toHaveAttribute("data-request-key", "t0-16xf0-4");
  await expect(page.locator(".lnt-spec-error")).toBeHidden();
});

test("связка маркер ↔ список событий в обе стороны", async ({ page }) => {
  await mockCatalog(page);
  await mockArtifact(
    page,
    "art-small",
    buildSpectrogramNpz(smallLevel()),
    eventsPayload([eventAt(0.3, 12, "qualified"), eventAt(0.7, 8, "candidate")]),
  );
  await page.goto("http://127.0.0.1:4101/static/v2/#/inspect");
  await build(page, "art-small");

  // Два маркера над канвой и две строки списка — по числу событий.
  const markers = page.locator(".lnt-spec-marker");
  await expect(markers).toHaveCount(2);
  const options = page.locator(".lnt-event-list [role='option']");
  await expect(options).toHaveCount(2);

  // Клик по маркеру №2 подсвечивает строку №2 списка.
  await markers.nth(1).click();
  await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
  await expect(markers.nth(1)).toHaveClass(/is-selected/);

  // Обратная связь: клик по строке №1 подсвечивает маркер №1.
  await options.nth(0).click();
  await expect(options.nth(0)).toHaveAttribute("aria-selected", "true");
  await expect(markers.nth(0)).toHaveClass(/is-selected/);
  await expect(markers.nth(1)).not.toHaveClass(/is-selected/);

  // Скриншот панели со спектрограммой и маркерами — во временную директорию.
  await page.screenshot({
    path: path.join(os.tmpdir(), "lnt-t42-spectrogram.png"),
    fullPage: true,
  });
});

test("сверхкапный запрос отклоняется с русской причиной и повтором", async ({ page }) => {
  await mockCatalog(page);
  // Обзор 1024×512 = 524288 ячеек — больше капа на минимальную величину.
  const timeS = Array.from({ length: 1024 }, (_, i) => Number((i * 0.01).toFixed(2)));
  const frequencyHz = Array.from({ length: 512 }, (_, j) => j * 10);
  const powerDb = new Float32Array(1024 * 512);
  for (let i = 0; i < powerDb.length; i += 1) powerDb[i] = (i % 97) - 40;
  await mockArtifact(
    page,
    "art-big",
    buildSpectrogramNpz({ timeS, frequencyHz, powerDb }),
    eventsPayload([]),
  );
  await page.goto("http://127.0.0.1:4101/static/v2/#/inspect");
  await build(page, "art-big");

  // Стартовый тайл усечён по капу: все 1024 времени × 511 полос ≤ 524000.
  const status = page.locator(".lnt-spec-status");
  await expect(status).toHaveAttribute("data-request-key", "t0-1024xf0-511");
  await expect(status).toHaveAttribute("data-cells", "523264");

  // Запрос ВСЕГО хранимого обзора через форму окна → типизированный отказ.
  await page.fill('input[aria-label="Начало окна, с"]', "0");
  await page.fill('input[aria-label="Конец окна, с"]', "10.24");
  await page.fill('input[aria-label="Нижняя граница окна, Гц"]', "0");
  await page.fill('input[aria-label="Верхняя граница окна, Гц"]', "5120");
  await page.getByRole("button", { name: "Обновить окно" }).click();
  const banner = page.locator(".lnt-spec-error");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("больше лимита 524000 ячеек");

  // Повтор возвращает последний допустимый тайл и прячет баннер.
  await page.getByRole("button", { name: "Повторить" }).click();
  await expect(banner).toBeHidden();
  await expect(status).toHaveAttribute("data-request-key", "t0-1024xf0-511");
});
