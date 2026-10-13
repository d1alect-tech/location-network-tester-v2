/** E2E плоскостной дивергенции peaks-Δ (ui-refactor-3, задача 10 — D3):
 * Δ пиков в ленте анализа считается из пейлоадов ТОЙ ЖЕ плоскости, что
 * отображает соседний график (panel payloads), в обоих режимах селектора
 * плоскости. Payload выбранной плоскости отсутствует — честное «—» с
 * причиной из словаря задачи 3, БЕЗ тихого scope-отката Δ. Ожидаемые числа
 * — аналитическая фикстурная математика (10·lg(B/A) по сидам), не эхо
 * движка. */

import { expect, test } from "@playwright/test";
import type { CatalogSession } from "../../api/types";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";
const PANEL = "[data-showcase='spectrum']";
const BAND = ".analysis-band";
const DELTA_CELL = "[data-peak-row='0'] td.delta";

const CATALOG: { items: CatalogSession[]; next_cursor: null } = {
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
      created_utc: "2026-08-02T09:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "bad",
      label: "стенд-Б",
      storage_path: null,
    },
  ],
  next_cursor: null,
};

const FREQ = [10, 100, 1000, 10_000] as const;

function scopePayload(psd: readonly number[]): Record<string, unknown> {
  return {
    frequency_hz: [...FREQ],
    psd_v2_per_hz: [...psd],
    point_count: FREQ.length,
    resolution_hz: 100,
  };
}

function referredPayload(psd: readonly number[]): Record<string, unknown> {
  return {
    frequency_hz: [...FREQ],
    input_referred_excess_psd_v2_per_hz: [...psd],
    point_count: FREQ.length,
    status: "available",
    reason_code: null,
    qualified_bin_count: FREQ.length,
    total_bin_count: FREQ.length,
    resolution_hz: 100,
  };
}

// Аналитика фикстуры: пик 1000 Гц → ближайший бин сетки — индекс 2.
// Скоп:  Δ@1000 = 10·lg(2e-2 / 1e-2) = 10·lg(2) ≈ 3.0103 → «3.01».
// Вход:  Δ@1000 = 10·lg(1e-7 / 1e-8) = 10·lg(10) = 10 → «10.00».
const SCOPE_A = scopePayload([1e-6, 1e-4, 1e-2, 1e-5]);
const SCOPE_B = scopePayload([1e-6, 1e-4, 2e-2, 1e-5]);
const REFERRED_A = referredPayload([1e-12, 1e-10, 1e-8, 1e-11]);
const REFERRED_B = referredPayload([1e-12, 1e-10, 1e-7, 1e-11]);
const SCOPE_DELTA_ATTR = (10 * Math.log10(2)).toFixed(2); // "3.01"
const INPUT_DELTA_ATTR = (10 * Math.log10(10)).toFixed(2); // "10.00"

/** Полный конверт detail (payloads.py): пики рендерятся только из честного
 * конверта (задача 9); ch1_input_reference available — кнопка входа активна. */
function detail(name: string): unknown {
  return {
    name,
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
        window: "hann",
        enbw_hz: 150,
      },
      ch1_input_reference: { status: "available", reason_code: null },
    },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

function mockPair(backend: MockLntBackend, referredStatus = 200): void {
  backend.seedCatalog(CATALOG.items);
  backend.seedSessionDetail("capture-001", detail("capture-001"));
  backend.seedSpectrum("capture-001", SCOPE_A);
  backend.seedSpectrum("capture-002", SCOPE_B);
  backend.seedReferredSpectrum("capture-001", REFERRED_A, referredStatus);
  backend.seedReferredSpectrum("capture-002", REFERRED_B, referredStatus);
}

test("Δ пиков и Δср пары следуют селектору плоскости: скоп → вход → скоп", async ({ page }) => {
  mockPair(installMockBackend(page));
  await page.goto(BASE);
  await expect(page.locator(PANEL).locator(".uplot")).toBeVisible({ timeout: 15_000 });

  // Режим скоп (boot-пара A=capture-001, B=capture-002): Δ пиков из
  // скоп-пейлоадов панели — 10·lg(2) → 3.01, Δср по тем же бинам → +0,8 дБ.
  await expect(page.locator(BAND).locator(DELTA_CELL)).toHaveAttribute(
    "data-delta",
    SCOPE_DELTA_ATTR,
  );
  await expect(page.locator("[data-pair-delta='mean']")).toHaveText("Δср +0,8 дБ");

  // Смена плоскости: график перерисовывается из input-referred пейлоадов.
  const requested = page.waitForRequest("**/spectrum-input-referred*");
  await page.locator(PANEL).locator("[data-spectrum-plane='input-referred']").click();
  await requested;
  await expect(
    page.locator(PANEL).locator("[data-spectrum-plane='input-referred']"),
  ).toHaveAttribute("aria-pressed", "true");

  // Δ из ТОЙ ЖЕ плоскости, что график: 10·lg(10) → 10.00 (скоп-число ушло);
  // Δср по входным бинам → +2,5 дБ.
  await expect(page.locator(BAND).locator(DELTA_CELL)).toHaveAttribute(
    "data-delta",
    INPUT_DELTA_ATTR,
  );
  await expect(page.locator("[data-pair-delta='mean']")).toHaveText("Δср +2,5 дБ");

  // Возврат на скоп — симметрия: Δ снова из скоп-плоскости.
  await page.locator(PANEL).locator("[data-spectrum-plane='scope']").click();
  await expect(page.locator(BAND).locator(DELTA_CELL)).toHaveAttribute(
    "data-delta",
    SCOPE_DELTA_ATTR,
  );
  await expect(page.locator("[data-pair-delta='mean']")).toHaveText("Δср +0,8 дБ");
});

test("payload входа отсутствует (500): Δ честно «—» с причиной, без scope-отката Δ", async ({
  page,
}) => {
  // 500 ≠ 404/409: панель НЕ откатывается тихо на скоп — пейлоад выбранной
  // плоскости честно отсутствует, Δ не должен показывать скоп-числа.
  mockPair(installMockBackend(page), 500);
  await page.goto(BASE);
  await expect(page.locator(PANEL).locator(".uplot")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(BAND).locator(DELTA_CELL)).toHaveAttribute(
    "data-delta",
    SCOPE_DELTA_ATTR,
  );

  const requested = page.waitForRequest("**/spectrum-input-referred*");
  await page.locator(PANEL).locator("[data-spectrum-plane='input-referred']").click();
  await requested;

  // Честное отсутствие: числового data-delta нет (скоп-значение 3.01 не
  // протекает), значение ячейки — пиннутый прочерк, причина — видимый узел
  // словаря задачи 3 у таблицы пиков.
  const cell = page.locator(BAND).locator(DELTA_CELL);
  await expect(cell).not.toHaveAttribute("data-delta");
  await expect(cell).toHaveText("—");
  const reason = page.locator(BAND).locator("[data-role='band-reason']");
  await expect(reason).toBeVisible();
  await expect(reason).toHaveText("Сервер вернул ошибку.");
});
