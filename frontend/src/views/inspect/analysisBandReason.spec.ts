import { expect, test } from "@playwright/test";
import type { CatalogSession } from "../../api/types";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";
import { REASON_NO_ARTIFACT, branchNotComputedReason } from "./pairLoadOutcome";

/** Задача 9 (ui-refactor-3): «н/д»-плитки ленты анализа несут ПРИЧИНУ из
 * честных флагов detail (payloads.py:77-87) ВИДИМЫМ соседним узлом —
 * span.band-cell-reason после dd (F-1: причина видна без взаимодействия;
 * title на dd — бонусный дубликат). Значение остаётся «н/д» (пин
 * analysisBand.test.ts), 7 плиток остаются 7. Причины — только словарь
 * pairLoadOutcome (задача 3). Корпус-строки: metrics без spectrum.csv
 * (cap-20260805-212516, qa-line-quality) и analysis:null (163913).
 * Полная сессия — регресс-страж: значения без причин, рендер не изменился. */

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";
const BAND = ".col-main .analysis-band";
const NEEDLE_REASON = branchNotComputedReason("");
const SPECTRUM_REASON = REASON_NO_ARTIFACT;
const NEEDLE_LABELS = ["Частота сети", "μ иглы", "σ/μ", "P_async/P_sync", "Циклов"] as const;

/** rowkey = loadKey (bootPick): session_id для ok-строк, имя каталога — только
 * для duplicate_id. qa-line-quality: id совпадает с именем каталога. */
const ROW_CAP_NO_SPECTRUM = "cap-20260805-212518-4e246d77";
const ROW_CAP_UNANALYZED = "cap-20260805-163915-a83892f0";

async function openCorpusRow(page: import("@playwright/test").Page, rowkey: string): Promise<void> {
  installMockBackend(page, { corpus: true });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();
  // Boot занимает ОБА слота (первые две analyzed): клик тела строки писал бы
  // в B, а ленте нужна база A — кнопка «А» строки назначает её в A напрямую.
  const row = page.locator(`.col-cat tr[data-rowkey="${rowkey}"]`);
  await expect(row).toBeVisible();
  await row.locator('[data-assign="a"]').click();
}

for (const [dir, rowkey] of [
  ["cap-20260805-212516", ROW_CAP_NO_SPECTRUM],
  ["qa-line-quality", "qa-line-quality"],
] as const) {
  test(`«н/д» с видимой причиной из флагов detail: ${dir} (metrics есть, spectrum.csv нет)`, async ({
    page,
  }) => {
    await openCorpusRow(page, rowkey);

    const band = page.locator(BAND);
    const cells = band.locator(".band-cell");
    await expect(cells).toHaveCount(7);
    await expect(band.locator(".band-cell .band-cell-reason")).toHaveCount(7);
    for (const cell of await cells.all()) {
      await expect(cell.locator("dd")).toContainText("н/д");
    }
    for (const label of NEEDLE_LABELS) {
      const reason = cells.filter({ hasText: label }).locator("dd + .band-cell-reason");
      await expect(reason).toBeVisible();
      await expect(reason).toHaveText(NEEDLE_REASON);
    }
    for (const label of ["Полоса", "Разрешение"]) {
      const reason = cells.filter({ hasText: label }).locator("dd + .band-cell-reason");
      await expect(reason).toBeVisible();
      await expect(reason).toHaveText(SPECTRUM_REASON);
    }
  });
}

test("analysis:null → все 7 «н/д» с видимой причиной «нет артефакта»", async ({ page }) => {
  await openCorpusRow(page, ROW_CAP_UNANALYZED);

  const band = page.locator(BAND);
  const cells = band.locator(".band-cell");
  await expect(cells).toHaveCount(7);
  await expect(band.locator(".band-cell .band-cell-reason")).toHaveCount(7);
  for (const cell of await cells.all()) {
    await expect(cell.locator("dd")).toContainText("н/д");
    const reason = cell.locator("dd + .band-cell-reason");
    await expect(reason).toBeVisible();
    await expect(reason).toHaveText(SPECTRUM_REASON);
  }
});

const FULL_SESSION: CatalogSession = {
  id: "capture-001",
  health: "ok",
  created_utc: "2026-08-02T10:00:00Z",
  source: "capture",
  session_type: "capture",
  profile: "bad",
  label: "стенд-А",
  storage_path: null,
};

function fullDetail(): Record<string, unknown> {
  return {
    name: "capture-001",
    manifest: {},
    analysis: {
      needle: {
        line_frequency_hz: 50.0,
        needle_mean_v: 0.0012,
        needle_sigma_ratio: 0.35,
        async_sync_ratio: null,
        cycles_analyzed: 120,
      },
      spectrum: {
        peaks: [{ frequency_hz: 1000, level_db: -40, prominence_db: 12, q_factor: 8 }],
        band_low_hz: 3000,
        band_high_hz: 1350000,
        resolution_hz: 100,
      },
    },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

test("проанализированная полная сессия: значения без причин, рендер не изменился", async ({
  page,
}) => {
  const backend: MockLntBackend = installMockBackend(page);
  backend.seedCatalog([FULL_SESSION]);
  backend.seedSessionDetail("capture-001", fullDetail());
  backend.seedSpectrum("capture-001", {
    frequency_hz: [10, 100, 1000, 10_000],
    psd_v2_per_hz: [1e-6, 1e-4, 1e-2, 1e-5],
    point_count: 4,
    resolution_hz: 100,
    band_low_hz: 3000,
    band_high_hz: 1350000,
  });
  await page.goto(`${BASE}?a=capture-001`);
  await expect(page.locator(".app-v6")).toBeVisible();

  const band = page.locator(BAND);
  const cells = band.locator(".band-cell");
  await expect(cells).toHaveCount(7, { timeout: 15_000 });
  // Полный анализ: ни одной причины — значения факты, узел причины не появился.
  await expect(band.locator(".band-cell .band-cell-reason")).toHaveCount(0);
  await expect(cells.filter({ hasText: "Частота сети" }).locator("dd")).toContainText("50.0000000");
  await expect(cells.filter({ hasText: "Полоса" }).locator("dd")).toContainText(/3[\u00a0 ]?000/);
  // null-поле существующей ветки (async у 1-канальной): «н/д» БЕЗ выдуманной причины.
  await expect(cells.filter({ hasText: "P_async/P_sync" }).locator("dd")).toContainText("н/д");
  await expect(
    cells.filter({ hasText: "P_async/P_sync" }).locator("dd + .band-cell-reason"),
  ).toHaveCount(0);
});
