import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import type { CatalogSession } from "../../api/types";
import { type MockLntBackend, installMockBackend } from "../../testkit/mockBackend";

/** E2E W1 inspect chrome inside V6 extras: measurement artifacts vs v1-only banner.
 * #/inspect mounts .app-v6; W1 lives in collapsed details[data-extra=w1].
 * API подменяется page.route как в spectrogram.spec.ts. */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.resolve(HERE, "../../test-support/analysis-v2-fixtures");
const INSPECT = "http://127.0.0.1:4101/static/v2/#/inspect";
const BANNER =
  "Расширенный анализ (ITIC, гармоники, APD…) для этой сессии не записан. Метрики и спектр v1 на месте.";
const CTA = "Пересчитать анализ (v2)";
const ARTIFACT_KEY = "art-meas";
const SPECTRUM = {
  frequency_hz: [10, 100, 1000],
  psd_v2_per_hz: [1e-6, 1e-4, 1e-2],
  point_count: 3,
};

function readFixture(rel: string): string {
  return fs.readFileSync(path.join(FIXTURES, rel), "utf8");
}

function catalog(id: string): { items: CatalogSession[]; next_cursor: null } {
  return {
    items: [
      {
        id,
        health: "ok",
        created_utc: "2026-08-01T10:00:00Z",
        source: "synthetic",
        session_type: "measurement",
        profile: "quiet",
        label: "стенд-А",
        storage_path: null,
      },
    ],
    next_cursor: null,
  };
}

function detail(name: string, metricsJson: string): unknown {
  return {
    name,
    manifest: { session_id: name },
    analysis: JSON.parse(metricsJson) as unknown,
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

function mockCatalog(backend: MockLntBackend, id: string): void {
  backend.seedCatalog(catalog(id).items);
}

function mockSessionDetail(backend: MockLntBackend, id: string, metricsRel: string): void {
  backend.seedSessionDetail(id, detail(id, readFixture(metricsRel)));
  backend.seedSpectrum(id, SPECTRUM);
}

async function openW1Chrome(page: Page, id: string): Promise<void> {
  await page.goto(INSPECT);
  await expect(page.locator(".app-v6")).toBeVisible();
  await page.locator(".v6-extras details[data-extra='w1'] summary").click();
  await page.selectOption('select[aria-label="Сессия инспекции"]', id);
}

async function expectNoErrorBand(page: Page): Promise<void> {
  const band = page.locator(".app-v6 .banner-inline");
  if ((await band.count()) > 0) await expect(band).not.toBeVisible();
}

test("measurement fixtures: THD verdict and four scalars, no banner, no eight panels", async ({
  page,
}) => {
  // Given: Batch 2–6 artifacts + v1 metrics for t1-measurement.
  const backend = installMockBackend(page);
  mockCatalog(backend, "t1-measurement");
  mockSessionDetail(backend, "t1-measurement", "measurement/metrics.json");
  backend.seedAnalysisPointer("t1-measurement", {
    recipe_id: "default",
    artifact_key: ARTIFACT_KEY,
  });
  const files = {
    "harmonics.json": readFixture("measurement/harmonics.json"),
    "notching.json": readFixture("measurement/notching.json"),
    "burst.json": readFixture("measurement/burst.json"),
    "metrics.json": readFixture("measurement/metrics.json"),
  } as const;
  for (const [filename, body] of Object.entries(files)) {
    backend.seedArtifact("t1-measurement", ARTIFACT_KEY, filename, body);
  }

  // When
  await openW1Chrome(page, "t1-measurement");

  // Then: verdict + four scalars; no missing-artifact banner; no eight hollow panels.
  const chrome = page.locator(".lnt-w1-chrome");
  await expect(chrome).toBeVisible();
  await expect(chrome.locator("[data-thd-verdict]")).toHaveAttribute("data-thd-verdict", "fail");
  await expect(chrome.getByText("THD-V", { exact: true })).toBeVisible();
  await expect(chrome.getByText("Peak Notch Depth", { exact: true })).toBeVisible();
  await expect(chrome.getByText("Burst Count", { exact: true })).toBeVisible();
  await expect(chrome.getByText("σ_pk/μ_pk", { exact: true })).toBeVisible();
  await expect(chrome.locator("[data-scalar]")).toHaveCount(4);
  await expect(page.getByText(BANNER)).toHaveCount(0);
  await expectNoErrorBand(page);
});

test("v1-only: exact Russian banner and CTA, no fake 0 scalars", async ({ page }) => {
  // Given: v1 metrics/spectrum only — no pointer, no Batch 2–6 artifacts.
  const backend = installMockBackend(page);
  mockCatalog(backend, "t1-v1-only");
  mockSessionDetail(backend, "t1-v1-only", "v1-only/metrics.json");

  // When
  await openW1Chrome(page, "t1-v1-only");

  // Then
  const chrome = page.locator(".lnt-w1-chrome");
  await expect(chrome).toBeVisible();
  await expect(chrome.locator(".lnt-w1-banner")).toHaveText(BANNER);
  await expect(page.getByRole("button", { name: CTA })).toBeVisible();
  await expect(chrome.getByText("THD-V", { exact: true })).toHaveCount(0);
  await expect(chrome.getByText("Peak Notch Depth", { exact: true })).toHaveCount(0);
  await expect(chrome.getByText("Burst Count", { exact: true })).toHaveCount(0);
  await expect(chrome.locator('[data-scalar="burst-count"]')).toHaveCount(0);
  await expect(chrome.locator(".lnt-w1-panel")).toHaveCount(0);
  await expectNoErrorBand(page);
});

/* ---------- Расширенный прогон: карточки 18 семейств (вариант «Карточки») ---------- */

const CHAR_SESSION = "cap-20260805-180623-very-long-suffix";
const CHAR_ARTIFACT = "art-char-8f21c4d2";
/* Кнопка прогона: строка дублируется локально, как BANNER/CTA выше —
 * импорт extendedRun.ts тянет CSS, который транспилятор спеков не парсит. */
const EXTENDED_RUN_BUTTON = "Запустить расширенный анализ";

function charFamily(
  id: string,
  status: string,
  codes: readonly string[],
  stored: number,
  missing: number,
  lowHz: number,
  highHz: number,
  windowS: number,
  qcPassed: boolean,
): unknown {
  return {
    family_id: id,
    status,
    reason_codes: [...codes],
    comparison_summary: [],
    support: {
      stored_count: stored,
      missing_count: missing,
      selection_rule: "declared_band_full_record",
    },
    band: { low_hz: lowHz, high_hz: highHz },
    window: {
      kind: "hann",
      duration_s: windowS,
      sample_count: stored + missing,
      overlap_fraction: 0.5,
    },
    qc: { passed: qcPassed, reason_codes: [...codes] },
  };
}

/** Реалистичная выдача characterization-v1: 1 доступно, 4 частично, 13 недоступно. */
function charPayload(): unknown {
  const families = [
    charFamily("f01_phase_cycle", "available", [], 4096, 0, 45, 2000, 0.2, true),
    charFamily(
      "f02_amplitude_time_shape",
      "partial",
      ["baseline_unavailable"],
      312,
      88,
      45,
      2000,
      0.04,
      false,
    ),
    charFamily(
      "f03_interharmonic_tracking",
      "partial",
      ["artifact_limit"],
      1840,
      256,
      3000,
      200000,
      0.2,
      false,
    ),
    charFamily(
      "f04_multicycle_periodicity",
      "unavailable",
      ["carrier_unavailable"],
      0,
      20480,
      45,
      2000,
      1,
      false,
    ),
    charFamily(
      "f05_phase_conditioned_statistics",
      "unavailable",
      ["phase_reference_unavailable"],
      0,
      4096,
      45,
      2000,
      0.2,
      false,
    ),
    charFamily(
      "f06_modulation_trajectories",
      "partial",
      ["band_above_nyquist"],
      7420,
      2820,
      30,
      500,
      0.5,
      false,
    ),
    charFamily(
      "f07_comb_sideband_cepstrum",
      "unavailable",
      ["artifact_limit"],
      0,
      2048,
      45,
      8000,
      0.1,
      false,
    ),
    charFamily(
      "f08_transient_morphology",
      "partial",
      ["too_few_samples"],
      96,
      41,
      45,
      2000,
      0.04,
      false,
    ),
    charFamily(
      "f09_event_ordering",
      "unavailable",
      ["insufficient_support"],
      0,
      4096,
      45,
      2000,
      0.2,
      false,
    ),
    charFamily(
      "f10_threshold_episode_surface",
      "unavailable",
      ["phase_reference_unavailable"],
      0,
      4096,
      45,
      2000,
      0.2,
      false,
    ),
    charFamily(
      "f11_conditional_distributions",
      "unavailable",
      ["insufficient_support"],
      0,
      4096,
      45,
      2000,
      0.2,
      false,
    ),
    charFamily(
      "f12_spectral_kurtosis",
      "unavailable",
      ["artifact_limit", "insufficient_frames"],
      0,
      20480,
      500,
      40000,
      0.1,
      false,
    ),
    charFamily(
      "f13_band_envelope_coactivity",
      "unavailable",
      ["channel_missing"],
      0,
      10240,
      30,
      500,
      0.5,
      false,
    ),
    charFamily(
      "f14_cross_channel_event_association",
      "unavailable",
      ["channel_missing"],
      0,
      4096,
      45,
      2000,
      0.2,
      false,
    ),
    charFamily(
      "f15_interpretable_modes",
      "unavailable",
      ["insufficient_support"],
      0,
      4096,
      45,
      8000,
      0.2,
      false,
    ),
    charFamily(
      "f16_multiscale_memory",
      "unavailable",
      ["phase_reference_unavailable"],
      0,
      20480,
      45,
      2000,
      1,
      false,
    ),
    charFamily(
      "f17_cyclic_spectral_coherence",
      "unavailable",
      ["cyclic_frequency_off_grid"],
      0,
      20480,
      500,
      40000,
      0.1,
      false,
    ),
    charFamily(
      "f18_bicoherence_triads",
      "unavailable",
      ["artifact_limit"],
      0,
      4096,
      45,
      8000,
      0.2,
      false,
    ),
  ];
  const first = families[0] as Record<string, unknown>;
  first.comparison_summary = [{ name: "f1_hz", value: 50.01, unit: "Hz" }];
  return { schema_version: 2, families };
}

function charRunSnapshot(status: string, artifactKey: string | null): unknown {
  return {
    job_id: "job-char-1",
    kind: "analysis",
    status,
    stage: "",
    completed: 1,
    total: 1,
    artifact_key: artifactKey,
    error: null,
  };
}

/** Рецепты и задачи прогона: мок-бэкенд их не знает, перехват после installMockBackend. */
async function mockCharacterizationRoutes(page: Page): Promise<void> {
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
      await json(charRunSnapshot("running", null));
      return;
    }
    if (path.startsWith("/api/analysis/runs/") && method === "GET") {
      await json(charRunSnapshot("succeeded", CHAR_ARTIFACT));
      return;
    }
    await route.fallback();
  });
}

test("extended run: card grid groups 18 families by status with RU reasons", async ({ page }) => {
  // Given: characterization-v1 в каталоге рецептов и бандл с длинным id сессии.
  const backend = installMockBackend(page);
  mockCatalog(backend, CHAR_SESSION);
  mockSessionDetail(backend, CHAR_SESSION, "measurement/metrics.json");
  backend.seedArtifact(
    CHAR_SESSION,
    CHAR_ARTIFACT,
    "characterization.json",
    JSON.stringify(charPayload()),
  );
  await mockCharacterizationRoutes(page);

  // When
  await openW1Chrome(page, CHAR_SESSION);
  const extended = page.locator(".lnt-w1-extended");
  await extended.getByRole("button", { name: EXTENDED_RUN_BUTTON }).click();

  // Then: группы по статусу со счётчиками, RU-фраза и сырой код на карточке.
  await expect(extended.locator('[data-family-group="available"] [data-family-id]')).toHaveCount(1);
  await expect(extended.locator('[data-family-group="partial"] [data-family-id]')).toHaveCount(4);
  await expect(extended.locator('[data-family-group="unavailable"] [data-family-id]')).toHaveCount(
    13,
  );
  await expect(extended.locator('[data-group-count="unavailable"]')).toHaveText("13 из 18");
  const f17 = extended.locator('[data-family-id="f17_cyclic_spectral_coherence"]');
  await expect(f17).toContainText("циклическая частота вне сетки");
  await expect(f17).toContainText("cyclic_frequency_off_grid");
  await expect(extended.locator(".lnt-xr-note")).toContainText(CHAR_SESSION);
  await expectNoErrorBand(page);
});

/* F3-F3: последняя интерактивная строка колонки обязана уходить выше
 * фиксированного футера — иначе центр CTA ловит клик под статус-баром. */
test("extended-run CTA clears the fixed statusbar at the end of the scroll", async ({ page }) => {
  // Given: 1440x900, w1-детали раскрыты, сессия выбрана.
  await page.setViewportSize({ width: 1440, height: 900 });
  const backend = installMockBackend(page);
  mockCatalog(backend, "t1-cta-clear");
  mockSessionDetail(backend, "t1-cta-clear", "v1-only/metrics.json");

  // When: прокрутка главной колонки до конца.
  await openW1Chrome(page, "t1-cta-clear");
  const geometry = await page.evaluate((label) => {
    const button = [...document.querySelectorAll("button")].find((n) => n.textContent === label);
    const colMain = document.querySelector(".app-v6 .col-main");
    if (button === undefined || colMain === null) return null;
    colMain.scrollTop = colMain.scrollHeight;
    const col = colMain.getBoundingClientRect();
    const box = button.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return {
      clearance: Math.round(col.bottom - box.bottom),
      hitInside: button.contains(hit),
    };
  }, EXTENDED_RUN_BUTTON);

  // Then: запас не меньше высоты футера .statusbar (32px), клик попадает в кнопку.
  expect(geometry).not.toBeNull();
  expect(geometry?.clearance).toBeGreaterThanOrEqual(32);
  expect(geometry?.hitInside).toBe(true);
});
