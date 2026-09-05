/** Бенч спектрограммы todo 42: рендер/интеракция/браузерный RSS на стартовом
 * тайле у капа 524000 ячеек (обзор 1024×512 усекается до 1024×511 = 523264).
 * Паттерн повторяет run-bench.spec.ts: CDP-метрики + RSS через PowerShell;
 * результаты пишутся ТОЛЬКО во %TEMP% (и evidence-каталог при заданном
 * LNT_EVIDENCE_DIR) — frozen results.json/DECISION.md не изменяются. */

import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { buildSpectrogramNpz } from "../src/test-support/spectrogramNpz";

const TIME_BINS = 1024;
const BANDS = 512;

function bigOverview(): ArrayBuffer {
  const timeS = Array.from({ length: TIME_BINS }, (_, i) => Number((i * 0.01).toFixed(2)));
  const frequencyHz = Array.from({ length: BANDS }, (_, j) => j * 10);
  const powerDb = new Float32Array(TIME_BINS * BANDS);
  for (let i = 0; i < powerDb.length; i += 1) powerDb[i] = (i % 97) - 40;
  return buildSpectrogramNpz({ timeS, frequencyHz, powerDb });
}

async function mockBackend(page: Page): Promise<void> {
  await page.route("**/api/catalog/sessions**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "bench-001",
            health: "ok",
            created_utc: "2026-08-01T10:00:00Z",
            source: "capture",
            session_type: "capture",
            profile: "bad",
            label: null,
            storage_path: null,
          },
        ],
        next_cursor: null,
      }),
    }),
  );
  await page.route("**/artifacts/bench-key/spectrogram.npz", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/octet-stream",
      body: Buffer.from(bigOverview()),
    }),
  );
  await page.route("**/artifacts/bench-key/events.json", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ schema_version: 1, sample_count: 10240, events: [] }),
    }),
  );
}

interface BenchWindow extends Window {
  spectrogramBenchReady?: boolean;
}

test("Бенч спектрограммы у капа 524k: рендер, интеракция, RSS", async ({ page }) => {
  await mockBackend(page);
  // Стенд бенча, а не маршрут инспекции: панель-эксплорер монтируется напрямую
  // той же фабрикой (charts/register.ts) — мерим рендер тайла, а не хром вьюхи.
  await page.goto("http://127.0.0.1:4101/static/v2/bench/spectrogram-bench.html");
  await page.waitForFunction(
    () => (window as unknown as BenchWindow).spectrogramBenchReady === true,
  );
  await page.selectOption('select[aria-label="Сессия спектрограммы"]', "bench-001");
  await page.fill('input[aria-label="Ключ артефакта анализа"]', "bench-key");

  // Рендер стартового тайла: клик → статус с счётчиком ячеек в пределах капа.
  const renderStart = Date.now();
  await page.getByRole("button", { name: "Построить спектрограмму" }).click();
  await expect(page.locator(".lnt-spec-status")).toHaveAttribute("data-cells", "523264", {
    timeout: 60_000,
  });
  const renderMs = Date.now() - renderStart;

  // Интеракция: клик «Обновить окно» → применённое окно (нативный dataZoom
  // без пересборки серии). Заполнение полей — подготовка, в бюджет не входит.
  await page.fill('input[aria-label="Начало окна, с"]', "0");
  await page.fill('input[aria-label="Конец окна, с"]', "5.12");
  await page.fill('input[aria-label="Нижняя граница окна, Гц"]', "0");
  await page.fill('input[aria-label="Верхняя граница окна, Гц"]', "5110");
  const interactStart = Date.now();
  await page.getByRole("button", { name: "Обновить окно" }).click();
  await expect(page.locator(".lnt-spec-status")).toHaveAttribute(
    "data-request-key",
    "t0-512xf0-511",
  );
  const interactionMs = Date.now() - interactStart;
  expect(
    Number(await page.locator(".lnt-spec-status").getAttribute("data-cells")),
  ).toBeLessThanOrEqual(524_000);

  // Принудительная сборка мусора перед снимком RSS: измеряем устойчивый
  // след продукта, а не накопленный мусор автоматизации.
  const gcClient = await page.context().newCDPSession(page);
  await gcClient.send("HeapProfiler.collectGarbage");

  // Реальный процессный RSS браузеров Playwright (тот же метод, что в run-bench).
  let browserRssMiB = 0;
  try {
    const psCommand =
      "powershell -NoProfile -Command \"(Get-CimInstance Win32_Process -Filter '(Name = ''chrome.exe'' or Name = ''chrome-headless-shell.exe'') and ExecutablePath like ''%ms-playwright%''').WorkingSetSize | Measure-Object -Sum | Select-Object -ExpandProperty Sum\"";
    browserRssMiB =
      Number.parseInt(execSync(psCommand, { encoding: "utf-8" }).trim(), 10) / (1024 * 1024);
  } catch (error) {
    console.error("Не удалось измерить RSS:", error);
  }

  const result = { cellCount: 523_264, cap: 524_000, renderMs, interactionMs, browserRssMiB };
  console.log("[spectrogram-bench]", result);
  const payload = {
    host: {
      os: `${os.type()} ${os.release()} ${os.arch()}`,
      cpu: os.cpus()[0]?.model ?? "",
      ramGiB: Math.round((os.totalmem() / 2 ** 30) * 10) / 10,
    },
    rss_method:
      "Sum of WorkingSetSize of ms-playwright chrome.exe processes via PowerShell Get-CimInstance Win32_Process",
    results: [result],
  };
  const tempPath = path.join(os.tmpdir(), "lnt-spectrogram-bench.json");
  fs.writeFileSync(tempPath, `${JSON.stringify(payload, null, 2)}\n`);
  console.log(`Results written to ${tempPath}`);
  const evidenceDir = process.env.LNT_EVIDENCE_DIR;
  if (evidenceDir !== undefined && evidenceDir !== "") {
    fs.mkdirSync(evidenceDir, { recursive: true });
    fs.writeFileSync(
      path.join(evidenceDir, "spectrogram-bench.json"),
      `${JSON.stringify(payload, null, 2)}\n`,
    );
  }
});
