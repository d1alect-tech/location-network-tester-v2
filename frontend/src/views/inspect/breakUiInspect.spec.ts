/** break-ui инспекции (ui-refactor-2): worst-case артифакты по кускам.
 * Todo 9 — секция спектр+грам; todo 11 — лента анализа; todo 13 — analysis-v2.
 * Скриншоты пишутся в .omo/evidence/ui-refactor-2/task-N/break-ui/. */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import type { CatalogSession } from "../../api/types";
import { installMockBackend } from "../../testkit/mockBackend";
import { FAMILY_NAME_RU } from "./familyNames";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";

const EVIDENCE_9 = resolve(__dirname, "../../../../.omo/evidence/ui-refactor-2/task-9/break-ui");
const EVIDENCE_11 = resolve(__dirname, "../../../../.omo/evidence/ui-refactor-2/task-11/break-ui");
const EVIDENCE_13 = resolve(__dirname, "../../../../.omo/evidence/ui-refactor-2/task-13/break-ui");

function session(id: string, label: string): CatalogSession {
  return {
    id,
    health: "ok",
    created_utc: "2026-08-02T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "bad",
    label,
    storage_path: null,
  };
}

const LONG_ID = "capture-20260802-100000-очень-длинная-метка-стенда-номер-семь-abcdef";

function seedPair(backend: ReturnType<typeof installMockBackend>, ids: [string, string]): void {
  backend.seedCatalog(ids.map((id) => session(id, id)));
  for (const id of ids) {
    backend.seedSessionDetail(id, {
      name: id,
      manifest: {},
      analysis: {
        needle: {},
        spectrum: { peaks: [], band_low_hz: 3000, band_high_hz: 1350000, resolution_hz: 100 },
        ch1_input_reference: { status: "available", reason_code: null },
      },
      spectrum_available: true,
      waveform_available: false,
      ch2_available: false,
    });
    backend.seedSpectrum(id, {
      frequency_hz: [10, 100, 1000, 10_000],
      psd_v2_per_hz: [1e-6, 1e-4, 1e-2, 1e-5],
      point_count: 4,
      resolution_hz: 100,
    });
  }
}

async function noHorizontalOverflow(page: import("@playwright/test").Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "horizontal overflow").toBeLessThanOrEqual(0);
}

function seedPairWithPeaks(backend: ReturnType<typeof installMockBackend>): void {
  backend.seedCatalog([session("cap-a", "cap-a"), session("cap-b", "cap-b")]);
  for (const id of ["cap-a", "cap-b"]) {
    backend.seedSessionDetail(id, {
      name: id,
      manifest: {},
      analysis: {
        needle: {
          line_frequency_hz: 50.0000007,
          needle_mean_v: 0.0234,
          needle_sigma_ratio: 0.412,
          async_sync_ratio: 0.07,
          cycles_analyzed: 128,
        },
        spectrum: {
          peaks: [{ frequency_hz: 1000, level_db: -40, prominence_db: 12.5, q_factor: 8.2 }],
          band_low_hz: 3000,
          band_high_hz: 1350000,
          resolution_hz: 100,
        },
      },
      spectrum_available: true,
      waveform_available: false,
      ch2_available: false,
    });
  }
  // База выше сравнения на пике → дельта Б−А отрицательная.
  backend.seedSpectrum("cap-a", {
    frequency_hz: [10, 1000, 10_000],
    psd_v2_per_hz: [1e-6, 1e-2, 1e-5],
    point_count: 3,
    resolution_hz: 100,
  });
  backend.seedSpectrum("cap-b", {
    frequency_hz: [10, 1000, 10_000],
    psd_v2_per_hz: [1e-6, 1e-4, 1e-5],
    point_count: 3,
    resolution_hz: 100,
  });
}

test("break-ui 9: штатная пара, вид спектр и вид грам", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, ["cap-a", "cap-b"]);
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  await page.screenshot({ path: resolve(EVIDENCE_9, "ok-spectrum.png"), fullPage: true });
  await panel.locator('[data-spectrum-view="gram"]').click();
  await expect(panel.locator(".gram")).toBeVisible();
  await page.screenshot({ path: resolve(EVIDENCE_9, "ok-gram.png"), fullPage: true });
  await noHorizontalOverflow(page);
});

test("break-ui 9: пустой спектр — честная пустота без NaN", async ({ page }) => {
  const backend = installMockBackend(page);
  backend.seedCatalog([session("cap-a", "cap-a"), session("cap-b", "cap-b")]);
  for (const id of ["cap-a", "cap-b"]) {
    backend.seedSessionDetail(id, {
      name: id,
      manifest: {},
      analysis: { needle: {}, spectrum: { peaks: [] } },
      spectrum_available: true,
      waveform_available: false,
      ch2_available: false,
    });
    backend.seedSpectrum(id, { frequency_hz: [], psd_v2_per_hz: [], point_count: 0 });
  }
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  await expect(panel).not.toContainText("NaN");
  await page.screenshot({ path: resolve(EVIDENCE_9, "empty-spectrum.png"), fullPage: true });
});

test("break-ui 9: ошибка загрузки спектра — статус и повтор", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, ["cap-a", "cap-b"]);
  await page.route("**/api/sessions/*/spectrum*", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: '{"error":"boom"}' }),
  );
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  const status = panel.locator("[data-spectrum-status]");
  await expect(status).toBeVisible();
  await expect(status).toContainText("Не удалось загрузить спектр");
  await expect(panel.getByRole("button", { name: "Пересчитать спектр" })).toBeVisible();
  await page.screenshot({ path: resolve(EVIDENCE_9, "error-spectrum.png"), fullPage: true });
});

test("break-ui 9: длинные id сессий не рвут шапку и пару", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, [LONG_ID, `${LONG_ID}-b`]);
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  await noHorizontalOverflow(page);
  await page.screenshot({ path: resolve(EVIDENCE_9, "long-ids.png"), fullPage: true });
});

test("break-ui 9: мобильная ширина — шапка переносится без overflow", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, ["cap-a", "cap-b"]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  await noHorizontalOverflow(page);
  await page.screenshot({ path: resolve(EVIDENCE_9, "mobile-ok.png"), fullPage: true });
});

test("break-ui 11: нули и пропуски в ленте — факты и н/д, без NaN", async ({ page }) => {
  const backend = installMockBackend(page);
  backend.seedCatalog([session("cap-a", "cap-a"), session("cap-b", "cap-b")]);
  backend.seedSessionDetail("cap-a", {
    name: "cap-a",
    manifest: {},
    analysis: {
      needle: {
        line_frequency_hz: 0,
        needle_mean_v: 0,
        needle_sigma_ratio: 0,
        async_sync_ratio: null,
        cycles_analyzed: 0,
      },
      spectrum: { peaks: [], band_low_hz: 0, band_high_hz: 0, resolution_hz: 0 },
    },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  });
  backend.seedSessionDetail("cap-b", {
    name: "cap-b",
    manifest: {},
    analysis: { needle: {}, spectrum: { peaks: [] } },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  });
  for (const id of ["cap-a", "cap-b"]) {
    backend.seedSpectrum(id, {
      frequency_hz: [10, 100],
      psd_v2_per_hz: [1e-6, 1e-4],
      point_count: 2,
      resolution_hz: 100,
    });
  }
  await page.goto(BASE);
  const band = page.locator(".col-main .analysis-band");
  await expect(band.locator(".band-cell dd")).toHaveCount(7);
  await expect(band).not.toContainText("NaN");
  await expect(band.locator(".band-cell").filter({ hasText: "P_async" })).toContainText("н/д");
  await band.screenshot({ path: resolve(EVIDENCE_11, "zeros-missing.png") });
});

test("break-ui 11: отрицательные дельты пиков — глиф вниз и data-delta", async ({ page }) => {
  seedPairWithPeaks(installMockBackend(page));
  await page.goto(BASE);
  const band = page.locator(".col-main .analysis-band");
  const delta = band.locator("[data-delta]").first();
  await expect(delta).toBeVisible();
  await expect(delta).toHaveClass(/is-down/);
  await band.screenshot({ path: resolve(EVIDENCE_11, "negative-deltas.png") });
});

test("break-ui 11: пара не выбрана — плитки н/д и приглашение Δ", async ({ page }) => {
  installMockBackend(page);
  await page.goto(BASE);
  const band = page.locator(".col-main .analysis-band");
  await expect(band.locator(".band-cell dd").first()).toContainText("н/д");
  await expect(band.locator("[data-delta-empty]")).toBeVisible();
  await band.screenshot({ path: resolve(EVIDENCE_11, "no-pair.png") });
});

test("break-ui 11: мобильная ширина — лента в один столбец без overflow", async ({ page }) => {
  seedPairWithPeaks(installMockBackend(page));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE);
  const band = page.locator(".col-main .analysis-band");
  await expect(band.locator(".band-cell dd")).toHaveCount(7);
  await noHorizontalOverflow(page);
  await band.screenshot({ path: resolve(EVIDENCE_11, "mobile-band.png") });
});

test("break-ui 9: prefers-reduced-motion гасит вход секции", async ({ page }) => {
  const backend = installMockBackend(page);
  seedPair(backend, ["cap-a", "cap-b"]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(BASE);
  const panel = page.locator('.col-main [data-showcase="spectrum"]');
  await panel.locator(".uplot").waitFor({ timeout: 15_000 });
  const animation = await panel
    .locator(".panel-bd.signal-bd")
    .evaluate((node) => getComputedStyle(node).animationName);
  expect(animation).toBe("none");
});

/* ---------- break-ui 13: секция analysis-v2 (G7 «Disclosure-панели») ---------- */

const W1_ARTIFACT = "art-13";
const CHAR_ARTIFACT = "art-char-13";
const RUN_BUTTON = "Запустить расширенный анализ";
const FIXTURES = resolve(__dirname, "../../test-support/analysis-v2-fixtures");
const PANEL_FILES = [
  "harmonics.json",
  "notching.json",
  "apd.json",
  "burst.json",
  "trends.json",
  "audio_panel.json",
] as const;
const FAMILY_IDS = Object.keys(FAMILY_NAME_RU);

function readFixture(relative: string): string {
  return readFileSync(resolve(FIXTURES, relative), "utf8");
}

/** База пары с метриками v1; указатель и артефакты v2 — по списку файлов. */
function seedAnalysisSession(
  backend: ReturnType<typeof installMockBackend>,
  id: string,
  opts: { readonly pointer?: boolean; readonly files?: readonly string[] } = {},
): void {
  backend.seedCatalog([session(id, id)]);
  backend.seedSessionDetail(id, {
    name: id,
    manifest: {},
    analysis: {
      needle: { needle_sigma_ratio: 0.35, cycles_analyzed: 128 },
      spectrum: { peaks: [], band_low_hz: 3000, band_high_hz: 1350000, resolution_hz: 100 },
    },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  });
  backend.seedSpectrum(id, {
    frequency_hz: [10, 1000, 10_000],
    psd_v2_per_hz: [1e-6, 1e-4, 1e-5],
    point_count: 3,
    resolution_hz: 100,
  });
  if (opts.pointer === false) return;
  backend.seedAnalysisPointer(id, { artifact_key: W1_ARTIFACT });
  for (const name of opts.files ?? []) {
    backend.seedArtifact(id, W1_ARTIFACT, name, readFixture(`measurement/${name}`));
  }
}

async function mockRunRoutes(page: Page): Promise<void> {
  const snapshot = (status: string, key: string | null): unknown => ({
    job_id: "job-13",
    kind: "analysis",
    status,
    stage: "",
    completed: status === "succeeded" ? 1 : 0,
    total: 1,
    artifact_key: key,
    error: null,
  });
  await page.route(/\/api\/analysis\/(recipes|runs)/, async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/static\/v2/, "");
    const method = route.request().method();
    const json = (body: unknown): Promise<void> =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/analysis/recipes" && method === "GET") {
      await json({
        items: [
          {
            recipe_id: "rec-characterization-v1",
            name: "characterization-v1",
            sha256: "c".repeat(64),
            recipe: { kind: "characterization" },
          },
        ],
      });
      return;
    }
    if (path === "/api/analysis/runs" && method === "POST") {
      await json(snapshot("running", null));
      return;
    }
    if (path.startsWith("/api/analysis/runs/") && method === "GET") {
      await json(snapshot("succeeded", CHAR_ARTIFACT));
      return;
    }
    await route.fallback();
  });
}

/** Бандл characterization-v1: минимум полей, отсутствующее — тире на карточке. */
function charBundle(familyCount: number): string {
  const families = FAMILY_IDS.slice(0, familyCount).map((id, index) => ({
    family_id: id,
    status: index % 3 === 0 ? "available" : index % 3 === 1 ? "partial" : "unavailable",
    reason_codes: index % 3 === 1 ? ["artifact_limit"] : index % 3 === 2 ? ["not_computed"] : [],
    comparison_summary: index === 0 ? [{ name: "f1_hz", value: 50.02, unit: "Hz" }] : [],
  }));
  return JSON.stringify({ schema_version: 2, families });
}

async function openSection(page: Page, id: string) {
  await page.goto(BASE);
  const section = page.locator(".analysis-v2");
  await expect(section).toBeVisible();
  await expect(section.locator("[data-session-id]")).toHaveText(id);
  await section.locator("details[data-extra='w1'] > summary").click();
  return section;
}

/** Элементные скриншоты внутри скроллящейся колонки врут: снимаем вьюпорт
 * после прокрутки секции в кадр. */
async function shootSection(page: Page, section: Locator, name: string): Promise<void> {
  await section.scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(EVIDENCE_13, name) });
}

async function runExtended(page: Page, id: string, familyCount: number) {
  const backend = installMockBackend(page);
  seedAnalysisSession(backend, id, { files: [...PANEL_FILES] });
  backend.seedArtifact(id, CHAR_ARTIFACT, "characterization.json", charBundle(familyCount));
  await mockRunRoutes(page);
  const section = await openSection(page, id);
  await section.getByRole("button", { name: RUN_BUTTON }).click();
  // Прогон дошёл до бандла: строка скачивания появляется только после задачи.
  await expect(section.locator(".lnt-w1-extended-downloads button")).not.toHaveCount(0);
  return section;
}

test("break-ui 13: штатная сессия — шапка, вердикт, скаляры, стек панелей", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const backend = installMockBackend(page);
  seedAnalysisSession(backend, "cap-a", { files: [...PANEL_FILES] });
  const section = await openSection(page, "cap-a");

  await expect(section.locator("[data-panel]")).toHaveCount(6);
  await expect(section.locator("[data-absent-panel]")).toHaveCount(0);
  await expect(section.locator("[data-panel-key]")).toHaveCount(6);
  await expect(section.locator("[data-scalar]")).toHaveCount(4);
  await expect(section.locator("[data-thd-verdict]")).toHaveCount(1);
  await noHorizontalOverflow(page);
  await shootSection(page, section, "ok-expanded.png");
  await page.screenshot({ path: resolve(EVIDENCE_13, "ok-fullpage.png"), fullPage: true });
});

test("break-ui 13: свёрнуто и раскрыто — ключевые значения видны в обоих", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const backend = installMockBackend(page);
  seedAnalysisSession(backend, "cap-a", { files: [...PANEL_FILES] });
  await page.goto(BASE);
  const section = page.locator(".analysis-v2");
  await expect(section.locator("[data-panel-key]")).toHaveCount(0);
  await expect(section.locator("[data-role=w1-sum-value]")).not.toHaveText("сессия не выбрана");
  await shootSection(page, section, "collapsed.png");

  await section.locator("details[data-extra='waveform'] > summary").click();
  await section.locator("details[data-extra='w1'] > summary").click();
  await expect(section.locator("[data-panel]")).toHaveCount(6);
  await shootSection(page, section, "expanded.png");

  // Пол тач-цели: и раскрытия, и CTA не ниже 44px.
  const heights = await section.evaluate((node) => {
    const rows = [...node.querySelectorAll<HTMLElement>("summary, .av2-cta")];
    return rows.map((row) => Math.round(row.getBoundingClientRect().height));
  });
  expect(heights.every((height) => height >= 44)).toBe(true);
});

test("break-ui 13: нет артефактов — шесть честных чипов вместо пустого стека", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const backend = installMockBackend(page);
  seedAnalysisSession(backend, "cap-a", { files: [] });
  const section = await openSection(page, "cap-a");

  await expect(section.locator("[data-absent-panel]")).toHaveCount(6);
  await expect(section.locator("[data-panel]")).toHaveCount(0);
  await expect(section.locator('[data-absent-tone="absent"]')).toHaveCount(6);
  await expect(section.locator("[data-role=w1-sum-value]")).toContainText("панелей 0");
  await noHorizontalOverflow(page);
  await shootSection(page, section, "missing-artifacts.png");
});

test("break-ui 13: нет анализа v2 — баннер, legacy-вердикт, стека панелей нет", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const backend = installMockBackend(page);
  seedAnalysisSession(backend, "cap-a", { pointer: false });
  const section = await openSection(page, "cap-a");

  await expect(section.locator(".lnt-w1-banner")).toBeVisible();
  await expect(section.locator('[data-thd-verdict="legacy"]')).toBeVisible();
  await expect(section.locator("[data-absent-panel]")).toHaveCount(0);
  await expect(section.locator("[data-panel]")).toHaveCount(0);
  await expect(section.locator("[data-role=panels-title]")).toBeHidden();
  await shootSection(page, section, "v1-only-banner.png");
});

test("break-ui 13: 18 семейств — решённый блок карточек в ритме секции", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const section = await runExtended(page, "cap-a", 18);

  await expect(section.locator("[data-family-id]")).toHaveCount(18);
  await noHorizontalOverflow(page);
  await section.locator(".lnt-w1-extended").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(EVIDENCE_13, "families-18.png") });
  await page.screenshot({ path: resolve(EVIDENCE_13, "families-18-fullpage.png"), fullPage: true });
});

test("break-ui 13: одно семейство в бандле — сетки нет, секция не рвётся", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const section = await runExtended(page, "cap-a", 1);

  await expect(section.locator("[data-family-id]")).toHaveCount(0);
  await noHorizontalOverflow(page);
  await shootSection(page, section, "families-1.png");
});

test("break-ui 13: ноль семейств в бандле — сетки нет, секция не рвётся", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const section = await runExtended(page, "cap-a", 0);

  await expect(section.locator("[data-family-id]")).toHaveCount(0);
  await expect(section.locator("[data-panel]")).toHaveCount(6);
  await noHorizontalOverflow(page);
  await shootSection(page, section, "families-0.png");
});

test("break-ui 13: длинный id сессии — шапка переносится без overflow", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const backend = installMockBackend(page);
  seedAnalysisSession(backend, LONG_ID, { files: [...PANEL_FILES] });
  const section = await openSection(page, LONG_ID);

  await expect(section.locator("[data-panel]")).toHaveCount(6);
  await noHorizontalOverflow(page);
  await shootSection(page, section, "long-id-1440.png");

  await page.setViewportSize({ width: 375, height: 812 });
  await noHorizontalOverflow(page);
  await shootSection(page, section, "long-id-375.png");
});

test("break-ui 13: 375px — шапка, чипы и стек переносятся без overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const backend = installMockBackend(page);
  seedAnalysisSession(backend, "cap-a", { files: ["harmonics.json"] });
  const section = await openSection(page, "cap-a");

  await expect(section.locator("[data-panel]")).toHaveCount(1);
  await expect(section.locator("[data-absent-panel]")).toHaveCount(5);
  await noHorizontalOverflow(page);
  await shootSection(page, section, "mobile-375.png");
  await page.screenshot({ path: resolve(EVIDENCE_13, "mobile-375-fullpage.png"), fullPage: true });
});

test("break-ui 13: движение — вход гасится reduced-motion, раскрытие без анимации", async ({
  page,
}) => {
  const backend = installMockBackend(page);
  seedAnalysisSession(backend, "cap-a", { files: [...PANEL_FILES] });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const section = await openSection(page, "cap-a");
  await expect(section.locator("[data-panel]")).toHaveCount(6);

  // Вход тела на смене пары гасится.
  const bodyAnimation = await section
    .locator(".av2-body")
    .first()
    .evaluate((node) => getComputedStyle(node).animationName);
  expect(bodyAnimation).toBe("none");

  // Частое действие (раскрытие/сворачивание) — без анимации и без перехода.
  const disclosure = section.locator("details[data-extra='w1']");
  const motion = await disclosure.evaluate((node) => {
    const style = getComputedStyle(node);
    const body = node.querySelector(".av2-body");
    return {
      transition: style.transitionDuration,
      animation: style.animationName,
      bodyTransition: body === null ? null : getComputedStyle(body).transitionDuration,
    };
  });
  expect(motion.transition).toBe("0s");
  expect(motion.animation).toBe("none");
  expect(motion.bodyTransition).toBe("0s");
  await shootSection(page, section, "reduced-motion.png");
});
