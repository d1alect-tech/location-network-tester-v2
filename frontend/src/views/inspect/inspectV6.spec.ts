import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { ApiError } from "../../api/errors";
import type { CatalogSession } from "../../api/types";
import { buildSpectrogramNpz } from "../../test-support/spectrogramNpz";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

/** Приёмочные сценарии V6 (ADR-0009): #/inspect — окно сравнения.
 *  Доказываем ОТРИСОВАННЫЙ результат (канвы, глифы, сетка), а не логи. */

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";

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

function level(
  timeBins: number,
  offsetDb: number,
): {
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

function mockApi(backend: MockLntBackend, opts?: { bTimeBins?: number; ch2?: boolean }): void {
  const ch2 = opts?.ch2 ?? true;
  const bTimeBins = opts?.bTimeBins ?? 16;
  backend.seedCatalog(CATALOG.items);
  backend.seedSessionDetail("capture-001", detail("capture-001", ch2));
  backend.seedSessionDetail("capture-002", detail("capture-002", ch2));
  backend.seedSpectrum("capture-001", SPECTRUM_A);
  backend.seedSpectrum("capture-002", SPECTRUM_B);
  backend.seedWaveform("capture-001", WAVEFORM);
  backend.seedAnalysisPointer("capture-001", { artifact_key: "art-a" });
  backend.seedAnalysisPointer("capture-002", { artifact_key: "art-b" });
  backend.seedArtifact(
    "capture-001",
    "art-a",
    "spectrogram.npz",
    Buffer.from(buildSpectrogramNpz(level(16, 0))),
    "application/octet-stream",
  );
  backend.seedArtifact(
    "capture-002",
    "art-b",
    "spectrogram.npz",
    Buffer.from(buildSpectrogramNpz(level(bTimeBins, 5))),
    "application/octet-stream",
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
  mockApi(installMockBackend(page));
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();
  // Общая оболочка держит шапку; старой .app-header нет.
  await expect(page.locator("header.hdr")).toBeVisible();
  await expect(page.locator(".app-header")).toHaveCount(0);
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
  mockApi(installMockBackend(page));
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
  mockApi(installMockBackend(page));
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

test("V6-P3b: единая шапка спектр+грам — три кластера, органы грама в своём", async ({ page }) => {
  mockApi(installMockBackend(page));
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  const header = panel.locator(".panel-hd.signal-hd");
  await expect(header.locator("[data-signal-cluster]")).toHaveCount(3);
  await expect(
    header.locator('[data-signal-cluster="gram"] [data-gram-bar] [data-spectrogram-mode]'),
  ).toHaveCount(3);
  await expect(
    header.locator('[data-signal-cluster="gram"] [data-gram-bar] [data-spectrogram-mode]').first(),
  ).toBeVisible();
  const gramCluster = header.locator('[data-signal-cluster="gram"]');
  const spectrumCluster = header.locator('[data-signal-cluster="spectrum"]');
  await expect(spectrumCluster).toHaveAttribute("data-active", "");
  await expect(gramCluster).not.toHaveAttribute("data-active", "");
  await panel.locator('[data-spectrum-view="gram"]').click();
  await expect(gramCluster).toHaveAttribute("data-active", "");
  await expect(spectrumCluster).not.toHaveAttribute("data-active", "");
  await panel.locator('[data-spectrum-view="spectrum"]').click();
  await expect(spectrumCluster).toHaveAttribute("data-active", "");
});

test("V6-P3c: быстрые смены пары не оставляют оракулов: один чарт на секцию", async ({ page }) => {
  mockApi(installMockBackend(page));
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();
  const rows = page.locator(".tbl-cat tbody tr[data-session]");
  for (let i = 0; i < 6; i += 1) {
    await rows.nth(i % 2).click();
  }
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await expect(panel.locator(".uplot")).toHaveCount(1);
  const painted = await panel
    .locator(".uplot canvas")
    .first()
    .evaluate((node) => {
      const canvas = node as HTMLCanvasElement;
      const ctx = canvas.getContext("2d");
      if (ctx === null) return false;
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      for (let i = 3; i < data.length; i += 4) if (data[i] !== 0) return true;
      return false;
    });
  expect(painted).toBe(true);
});

test("V6-P4: дельта пика из трасс, глиф направления", async ({ page }) => {
  mockApi(installMockBackend(page));
  await page.goto(BASE);
  const deltaCell = page.locator(".analysis-band [data-delta]").first();
  await expect(deltaCell).toBeVisible();
  // 10*log10(8e-3/1e-2) ≈ -0.969 → минус, глиф ▼.
  const value = Number(await deltaCell.getAttribute("data-delta"));
  expect(Math.abs(value - -0.969)).toBeLessThan(0.05);
  await expect(deltaCell).toContainText("▼");
});

test("V6-P5: полный захват и возврат через таббар", async ({ page }) => {
  mockApi(installMockBackend(page));
  await page.goto(BASE);
  await expect(page.locator("header.hdr .tabbar a[href='#/inspect']")).toHaveAttribute(
    "aria-current",
    "page",
  );
  await page.locator("header.hdr .tabbar a[href='#/catalog']").click();
  await expect(page).toHaveURL(/#\/catalog/);
  await expect(page.locator("header.hdr")).toBeVisible();
  await expect(page.locator(".app-v6")).toHaveCount(0);
  await expect(page.locator(".app-header")).toHaveCount(0);
});

test("V6-P6: сворачиваемые панели осциллограммы и анализа", async ({ page }) => {
  mockApi(installMockBackend(page));
  await page.goto(BASE);
  const section = page.locator(".v6-extras");
  const wave = page.locator(".v6-extras details[data-extra='waveform']");
  const w1 = page.locator(".v6-extras details[data-extra='w1']");
  await expect(wave).toBeVisible();
  await expect(w1).toBeVisible();
  // Закрыты по умолчанию.
  expect(await wave.evaluate((el) => (el as HTMLDetailsElement).open)).toBe(false);
  expect(await w1.evaluate((el) => (el as HTMLDetailsElement).open)).toBe(false);
  // G7: CTA пересчёта живёт в шапке секции и доступен без раскрытия.
  await expect(section.locator(".av2-hd .lnt-btn-primary")).toBeVisible();
  // Открытие осциллограммы грузит CH1.
  await wave.locator("> summary").click();
  await expect(wave.locator(".uplot")).toBeVisible({ timeout: 10_000 });
  // Тело анализа: блок панелей и честные чипы отсутствия (артефакты не засеяны).
  await w1.locator("> summary").click();
  await expect(w1.locator("[data-role=panels-title]")).toBeVisible();
  await expect(w1.locator("[data-absent-panel]")).toHaveCount(6);
});

test("V6-P7: показания базы, н/д для одноканальной сессии", async ({ page }) => {
  mockApi(installMockBackend(page), { ch2: false });
  await page.goto(BASE);
  const readout = page.locator(".analysis-band .band-cell dd");
  await expect(readout).toHaveCount(7);
  // P_async/P_sync отсутствует в один канал → «н/д», не 0.
  await expect(
    page.locator(".analysis-band .band-cell").filter({ hasText: "P_async" }),
  ).toContainText("н/д");
});

test("V6-P8: несовпадение сеток отключает дельту грама", async ({ page }) => {
  mockApi(installMockBackend(page), { bTimeBins: 8 });
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

test("V6-P10: 409 с серверным detail на pair-load — причина видна после canned-префикса", async ({
  page,
}) => {
  // Given: mock-бэкенд засеян, но detail/spectrum базы отвечают 409 с detail.
  const backend = installMockBackend(page);
  mockApi(backend);
  const detailText = "идентификатор сессии неоднозначен: 'syn-quiet-seed6022'";
  await page.route("**/api/sessions/capture-001*", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: detailText }),
    }),
  );

  // When
  await page.goto(BASE);

  // Then: лента ошибки видна; reason = canned-префикс + пробел + серверный detail.
  const band = page.locator("[data-inspect-error]");
  await expect(band).toBeVisible({ timeout: 15_000 });
  await expect(band).toContainText(detailText);
  expect(await band.textContent()).toBe(`${new ApiError("conflict").message} ${detailText}`);
});

test("V6-P11: 500 без detail на pair-load — честный failed из словаря, без «undefined»", async ({
  page,
}) => {
  // Given: сервер базы отвечает 500 с пустым JSON-телом — detail нет.
  const backend = installMockBackend(page);
  mockApi(backend);
  await page.route("**/api/sessions/capture-001*", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
  );

  // When
  await page.goto(BASE);

  // Then: только canned-префикс http-ошибки, без «undefined», вид не упал.
  const band = page.locator("[data-inspect-error]");
  await expect(band).toBeVisible({ timeout: 15_000 });
  const text = (await band.textContent()) ?? "";
  expect(text).toBe(new ApiError("http", { status: 500 }).message);
  expect(text).not.toContain("undefined");
  await expect(page.locator(".app-v6")).toBeVisible();
});

test("V6-P12 (M1): клик ряда пишет в B, «А» ряда в B переносит его в A, слот-клик — фокус, KeyA/KeyB", async ({
  page,
}) => {
  const THREE = [
    ...CATALOG.items,
    {
      id: "capture-003",
      health: "ok",
      created_utc: "2026-07-30T08:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "quiet",
      label: "стенд-В",
      storage_path: null,
    },
  ] as CatalogSession[];
  const backend = installMockBackend(page);
  backend.seedCatalog(THREE);
  backend.seedSessionDetail("capture-001", detail("capture-001", true));
  backend.seedSessionDetail("capture-002", detail("capture-002", true));
  backend.seedSessionDetail("capture-003", detail("capture-003", true));
  backend.seedSpectrum("capture-001", SPECTRUM_A);
  backend.seedSpectrum("capture-002", SPECTRUM_B);
  backend.seedSpectrum("capture-003", SPECTRUM_A);
  backend.seedWaveform("capture-001", WAVEFORM);
  await page.goto(BASE);
  const slotA = page.locator(".pairbar [data-pair='a']");
  const slotB = page.locator(".pairbar [data-pair='b']");
  await expect(slotA).toContainText("стенд-А");
  await expect(slotB).toContainText("стенд-Б");

  // Клик тела незапаренного ряда → B (сравнить с базой), A не тронут.
  const row3 = page.locator('.tbl-cat tbody tr[data-session="capture-003"]');
  await row3.click();
  await expect(slotA).toContainText("стенд-А");
  await expect(slotB).toContainText("стенд-В");

  // Кнопка «А» ряда в B → move: ряд в A, B освобождён.
  await row3.locator('[data-assign="a"]').click();
  await expect(slotA).toContainText("стенд-В");
  await expect(slotB).toContainText("—");

  // Слот-клик: фокус первого ряда рейла, пара не меняется, арм не включается.
  await slotA.click();
  await expect(page.locator(".tbl-cat tbody tr[data-session]").first()).toBeFocused();
  await expect(slotA).toContainText("стенд-В");
  await expect(slotB).toContainText("—");
  await expect(slotA).toHaveAttribute("aria-pressed", "false");

  // KeyA/KeyB на сфокусированном ряду (event.code — физические клавиши).
  await page.locator('.tbl-cat tbody tr[data-session="capture-001"]').focus();
  await page.keyboard.press("KeyA");
  await expect(slotA).toContainText("стенд-А");
  await expect(slotB).toContainText("—");
  await page.locator('.tbl-cat tbody tr[data-session="capture-002"]').focus();
  await page.keyboard.press("KeyB");
  await expect(slotA).toContainText("стенд-А");
  await expect(slotB).toContainText("стенд-Б");
});

test("V6-P13: swap disabled при пустом B — мёртвый контрол закрыт", async ({ page }) => {
  const ONE = [CATALOG.items[0]] as CatalogSession[];
  const backend = installMockBackend(page);
  backend.seedCatalog(ONE);
  backend.seedSessionDetail("capture-001", detail("capture-001", true));
  backend.seedSpectrum("capture-001", SPECTRUM_A);
  backend.seedWaveform("capture-001", WAVEFORM);
  await page.goto(BASE);
  const slotA = page.locator(".pairbar [data-pair='a']");
  const slotB = page.locator(".pairbar [data-pair='b']");
  const swap = page.locator(".pairbar [data-pair-swap]");
  await expect(slotA).toContainText("стенд-А");
  await expect(slotB).toContainText("—");
  await expect(swap).toBeDisabled();
});
