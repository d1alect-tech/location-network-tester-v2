/** Задача 8 (UX-контракт): панель «Риппл / шум» показывает СОХРАНЁННЫЕ числа
 * и не двигает ни один слот/контрол при смене данных (есть ↔ н/д ↔ длинные
 * числа) на 1280×720 и 1920×720. Плюс: страница не получает вертикальный
 * скролл, значения не обрезаются и не перекрываются.
 *
 * Числа в data-value сверяются с байтами фикстуры 1:1 — формат текста не
 * подменяет измеренное значение. При LNT_QA_DIR спек пишет скриншоты и
 * geometry JSON для ручного QA. */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { isRippleArtifact } from "../../../api/guards-ripple";
import type { CatalogSession } from "../../../api/types";
import type {
  RippleArtifactPayload,
  RippleAvailability,
  RippleBaseline,
} from "../../../api/types-ripple";
import { installMockBackend } from "../../../testkit/mockBackend";

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";
const QA_DIR = process.env.LNT_QA_DIR;
const FIXTURES = fileURLToPath(new URL("./fixtures/", import.meta.url));

/** РЕАЛЬНЫЕ артефакты кампании (task-3 verify-qa-sessions), скопированные в
 * fixtures/: constant 63a0ef56… (доступный спектр, все уровни 0) и
 * clip-mismatch 31bea3ca… (недоступный спектр, длинный QC). Вне репозитория
 * спек не читает ничего. */
function realArtifact(name: string): RippleArtifactPayload {
  const parsed: unknown = JSON.parse(readFileSync(`${FIXTURES}${name}.json`, "utf8"));
  if (!isRippleArtifact(parsed)) throw new Error(`фикстура ${name} не прошла гвард ripple`);
  return parsed;
}

const hex64 = (char: string): string => char.repeat(64);

/** Четырнадцать различных кодов причин: строка QC не влезает в слот, и
 * панель обязана сказать об этом фактическим числом, а не обрезать молча. */
const MANY_CODES = [
  "clipping_unknown",
  "clip_census_inconsistent",
  "nonfinite_samples",
  "known_gap",
  "settling_unknown",
  "settling",
  "empty_span",
  "insufficient_samples",
  "insufficient_segments",
  "baseline_incompatible",
  "baseline_missing",
  "baseline_calibration_identity_unknown",
  "stale_input",
  "some_unknown_machine_code",
];

const SESSIONS: CatalogSession[] = [
  {
    id: "ripple-a",
    health: "ok",
    created_utc: "2026-08-03T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "lab",
    label: "Риппл A",
  },
  {
    id: "ripple-b",
    health: "ok",
    created_utc: "2026-08-02T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "lab",
    label: "Риппл B",
  },
  {
    id: "ripple-c",
    health: "ok",
    created_utc: "2026-08-01T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "lab",
    label: "Риппл C",
  },
  {
    id: "ripple-real-constant",
    health: "ok",
    created_utc: "2026-07-31T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "lab",
    label: "Риппл: константа",
  },
  {
    id: "ripple-real-clip",
    health: "ok",
    created_utc: "2026-07-30T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "lab",
    label: "Риппл: ценз не сошёлся",
  },
  {
    id: "ripple-many-codes",
    health: "ok",
    created_utc: "2026-07-29T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "lab",
    label: "Риппл: много кодов QC",
  },
];

type Variant = {
  readonly mean: number | null;
  readonly rms: number | null;
  readonly vpp: number | null;
  readonly bandRms: number | null;
  readonly bandAvailable: boolean;
  readonly spectrumAvailable: boolean;
};

const NORMAL: Variant = {
  mean: 0.000005173322720890401,
  rms: 0.002117531120011638,
  vpp: 0.021350678987801075,
  bandRms: 0.0006369719075516393,
  bandAvailable: true,
  spectrumAvailable: true,
};
const ABSENT: Variant = {
  mean: null,
  rms: null,
  vpp: null,
  bandRms: null,
  bandAvailable: false,
  spectrumAvailable: false,
};
const LONG: Variant = {
  mean: -0.123456789,
  rms: 0.123456789,
  vpp: 0.987654321,
  bandRms: 0.0009996,
  bandAvailable: true,
  spectrumAvailable: true,
};

function baseline(): RippleBaseline {
  return {
    session: {
      session_id: "ripple-bg",
      manifest_sha256: hex64("a"),
      ch1_sha256: hex64("b"),
      channel: "ch1",
      source: "device",
    },
    attachment_basis: "same_adapter_tip_shorted_to_return",
    comparison_status: "unavailable",
    reason_codes: ["baseline_incompatible"],
    selection: null,
    time_domain: {
      availability: "available",
      reason_codes: [],
      mean_v: 0,
      rms_ac_v: 0.001,
      vpp_v: 0.003,
    },
    spectrum: {
      availability: "unavailable",
      reason_codes: ["baseline_incompatible"],
      settings: {},
      used_sample_count: null,
      ignored_tail_samples: null,
      frequency_hz: [],
      psd_v2_per_hz: [],
      asd_v_per_sqrt_hz: [],
    },
    bands: [
      {
        id: "ripple",
        low_hz: 1,
        high_hz: 500,
        first_center_hz: null,
        last_center_hz: null,
        bin_count: null,
        availability: "unavailable",
        reason_codes: ["baseline_incompatible"],
        rms_v: null,
      },
    ],
  };
}

function artifact(id: string, variant: Variant): RippleArtifactPayload {
  const availability: RippleAvailability = variant.mean === null ? "unavailable" : "available";
  const spectrumAvailable = variant.spectrumAvailable;
  return {
    schema_version: 1,
    algorithm: { id: "ripple_observed_v1", version: 1, rms: "population_centered_float64" },
    options: { band_low_hz: 1, band_high_hz: 500, interval_window_s: 1 },
    session: {
      session_id: id,
      manifest_sha256: hex64("f"),
      ch1_sha256: hex64("e"),
      channel: "ch1",
      source: "device",
    },
    provenance: {
      capture_metadata_basis: "legacy_capture_metadata_not_adapter_provenance",
      operator_attachment: "preconnected_no_reconnection",
      voltage_plane: "recorded_ch1_volts_observed_uncalibrated",
      range_code: 10,
      probe_multiplier: 1,
      calibration_used: false,
      calibration_identity: "legacy_bit_identical_conversion",
      hardware_qualification: "unverified",
    },
    adapter: {
      topology_id: "series_c_at_dut_tip_x1_v1",
      cap_nf: 100,
      series_r_ohm: 0,
      rin_ohm: 1_000_000,
      probe_multiplier: 1,
      component_values_basis: "nominal",
      rail_nominal_v: 12,
      fc_hz: 1.5915494309189535,
      tau_s: 0.1,
      plateau_gain: 1,
      transfer_status: "nominal_transfer_declared",
      assumption_codes: ["one_pole_nominal_transfer", "component_values_nominal"],
    },
    selection: {
      sample_start_index: 10_000,
      sample_end_index_exclusive: 40_000,
      sample_count: 30_000,
      sample_rate_hz: 10_000,
      realized_duration_s: 3,
      excluded_prefix_samples: 10_000,
      settling_prefix_samples_nominal: 10_000,
      settling_basis: "capture_start_assuming_preconnected",
      continuity_status: "host_contiguous_unverified",
      continuity_reason_codes: ["host_contiguous_unverified"],
    },
    qc: {
      clipping_assessment: "no_rail_hits",
      clip_count_scope: "float32_endpoints_from_manifest_conversion",
      clip_low_count: 0,
      clip_high_count: 0,
      nonfinite_count: 0,
      nonfinite_count_scope: "selected_span",
      record_nonfinite_count: 0,
      dropped_samples: 0,
      reason_codes: [],
    },
    time_domain: {
      availability,
      reason_codes: availability === "unavailable" ? ["clipping_unknown"] : [],
      mean_v: variant.mean,
      rms_ac_v: variant.rms,
      vpp_v: variant.vpp,
    },
    intervals: [
      {
        start_index: 10_000,
        end_index_exclusive: 20_000,
        sample_count: 10_000,
        complete: true,
        realized_duration_s: 1,
        availability: variant.mean === null ? "unavailable" : "available",
        reason_codes: variant.mean === null ? ["clipping_unknown"] : [],
        clip_low_count: variant.mean === null ? null : 0,
        clip_high_count: variant.mean === null ? null : 0,
        mean_v: variant.mean,
        rms_ac_v: variant.rms,
        vpp_v: variant.vpp,
      },
      {
        start_index: 20_000,
        end_index_exclusive: 30_000,
        sample_count: 10_000,
        complete: true,
        realized_duration_s: 1,
        availability: "available",
        reason_codes: [],
        clip_low_count: 0,
        clip_high_count: 0,
        mean_v: 0.00001,
        rms_ac_v: 0.0022,
        vpp_v: 0.021,
      },
    ],
    spectrum: spectrumAvailable
      ? {
          availability: "available",
          reason_codes: [],
          settings: {
            nperseg: 10_000,
            max_chunk_samples: 1_000_000,
            overlap_fraction: 0.5,
            window: "hann",
            detector: "mean",
            detrend: "constant",
            scaling: "density",
            resolution_hz: 1,
            enbw_hz: 1.5,
            segment_count: 5,
          },
          used_sample_count: 30_000,
          ignored_tail_samples: 0,
          frequency_hz: [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 500],
          psd_v2_per_hz: [
            1e-10, 1e-6, 5e-7, 2.5e-7, 1.25e-7, 6.25e-8, 3.1e-8, 1.5e-8, 7.5e-9, 3.7e-9, 1.9e-9,
          ],
          asd_v_per_sqrt_hz: [
            1e-5, 1e-3, 7.071e-4, 5e-4, 3.536e-4, 2.5e-4, 1.761e-4, 1.225e-4, 8.66e-5, 6.083e-5,
            4.359e-5,
          ],
        }
      : {
          availability: "unavailable",
          reason_codes: ["insufficient_segments"],
          settings: {},
          used_sample_count: null,
          ignored_tail_samples: null,
          frequency_hz: [],
          psd_v2_per_hz: [],
          asd_v_per_sqrt_hz: [],
        },
    bands: [
      {
        id: "ripple",
        low_hz: 1,
        high_hz: 500,
        first_center_hz: variant.bandAvailable ? 1 : null,
        last_center_hz: variant.bandAvailable ? 500 : null,
        bin_count: variant.bandAvailable ? 500 : null,
        availability: variant.bandAvailable ? "available" : "unavailable",
        reason_codes: variant.bandAvailable ? [] : ["clipping_unknown"],
        rms_v: variant.bandRms,
      },
    ],
    baseline: baseline(),
  };
}

/** Артефакт с 14 различными кодами причин и девятизначными счётчиками
 * клиппинга — худший случай для фиксированного слота QC. */
function manyCodesArtifact(id: string): RippleArtifactPayload {
  const base = artifact(id, NORMAL);
  return {
    ...base,
    qc: {
      ...base.qc,
      clipping_assessment: "clip_census_inconsistent",
      clip_low_count: 123_456_789,
      clip_high_count: 987_654_321,
      reason_codes: [...MANY_CODES],
    },
  };
}

function install(page: Page): void {
  const backend = installMockBackend(page);
  backend.seedCatalog(SESSIONS);
  for (const item of SESSIONS) {
    backend.seedSessionDetail(item.id, {
      name: item.id,
      manifest: { session_id: item.id },
      analysis: {},
      spectrum_available: true,
      waveform_available: false,
      ch2_available: false,
    });
  }
  backend.seedRipple("ripple-a", artifact("ripple-a", NORMAL));
  backend.seedRipple("ripple-b", artifact("ripple-b", ABSENT));
  backend.seedRipple("ripple-c", artifact("ripple-c", LONG));
  backend.seedRipple("ripple-real-constant", realArtifact("ripple-constant-zero-spectrum"));
  backend.seedRipple("ripple-real-clip", realArtifact("ripple-clip-mismatch-qc"));
  backend.seedRipple("ripple-many-codes", manyCodesArtifact("ripple-many-codes"));
}

type Geometry = {
  readonly state: string;
  readonly availability: string;
  readonly positions: number[][];
  readonly overlaps: string[];
  readonly clipped: string[];
  readonly qc: {
    readonly scrollWidth: number;
    readonly clientWidth: number;
    readonly scrollHeight: number;
    readonly clientHeight: number;
    readonly textLength: number;
    readonly codes: string;
    readonly omitted: string;
    readonly hidden: string;
    readonly hiddenCodes: string;
    readonly text: string;
  };
  readonly page: {
    readonly scrollY: number;
    readonly docOverflow: number;
    readonly viewOverflow: number;
    readonly colMainOverflow: number;
    readonly headerOverflow: number;
  };
  readonly panel: { readonly width: number; readonly height: number };
  readonly horizontal: { readonly left: number; readonly right: number } | null;
};

async function measure(page: Page): Promise<Geometry> {
  return page.locator("[data-ripple-panel]").evaluate((root) => {
    const round = (value: number): number => Math.round(value * 10) / 10;
    const panel = root.getBoundingClientRect();
    const nodes = [
      ...root.querySelectorAll<HTMLElement>(
        "[data-ripple-slot], [data-ripple-mode], [data-ripple-band]",
      ),
    ].filter((node) => node.getClientRects().length > 0);
    const positions = nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return [
        round(rect.x - panel.x),
        round(rect.y - panel.y),
        round(rect.width),
        round(rect.height),
      ];
    });
    const overlaps: string[] = [];
    for (let first = 0; first < nodes.length; first += 1) {
      for (let second = first + 1; second < nodes.length; second += 1) {
        const a = nodes[first]?.getBoundingClientRect();
        const b = nodes[second]?.getBoundingClientRect();
        if (a === undefined || b === undefined) continue;
        const dx = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const dy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (dx > 0.5 && dy > 0.5) {
          overlaps.push(`${nodes[first]?.className} / ${nodes[second]?.className}`);
        }
      }
    }
    const clipped = [
      ...root.querySelectorAll<HTMLElement>(
        ".ripple-card-value, .ripple-interval, .ripple-chip, .ripple-qc, .ripple-chart-meta",
      ),
    ]
      .filter((node) => node.getClientRects().length > 0 && node.scrollWidth > node.clientWidth + 1)
      .map((node) => `${node.className}:${node.textContent ?? ""}`);
    const view = document.querySelector(".view-container");
    const colMain = document.querySelector(".col-main");
    const colRect = colMain?.getBoundingClientRect() ?? null;
    const chips = root.querySelector<HTMLElement>(".ripple-chips");
    const qc = root.querySelector<HTMLElement>("[data-ripple-qc]");
    return {
      state: root.getAttribute("data-state") ?? "",
      availability: root.getAttribute("data-availability") ?? "",
      positions,
      overlaps,
      clipped,
      qc: {
        scrollWidth: qc?.scrollWidth ?? -1,
        clientWidth: qc?.clientWidth ?? -1,
        scrollHeight: qc?.scrollHeight ?? -1,
        clientHeight: qc?.clientHeight ?? -1,
        textLength: (qc?.textContent ?? "").length,
        codes: qc?.getAttribute("data-qc-codes") ?? "",
        omitted: qc?.getAttribute("data-qc-omitted") ?? "",
        hidden: qc?.getAttribute("data-qc-hidden") ?? "",
        hiddenCodes: qc?.getAttribute("data-qc-hidden-codes") ?? "",
        text: qc?.textContent ?? "",
      },
      page: {
        scrollY: window.scrollY,
        docOverflow: document.documentElement.scrollHeight - window.innerHeight,
        viewOverflow: view === null ? -1 : view.scrollHeight - view.clientHeight,
        colMainOverflow: colMain === null ? -1 : colMain.scrollHeight - colMain.clientHeight,
        headerOverflow: chips === null ? -1 : chips.scrollWidth - chips.clientWidth,
      },
      panel: { width: round(panel.width), height: round(panel.height) },
      horizontal:
        colRect === null
          ? null
          : { left: round(panel.left - colRect.left), right: round(panel.right - colRect.right) },
    };
  });
}

function expectClean(geometry: Geometry, label: string): void {
  expect(geometry.overlaps, `${label}: перекрытия слотов`).toEqual([]);
  expect(geometry.clipped, `${label}: обрезанные значения`).toEqual([]);
  expect(geometry.qc.scrollWidth, `${label}: QC обрезана по ширине`).toBeLessThanOrEqual(
    geometry.qc.clientWidth + 1,
  );
  expect(geometry.qc.scrollHeight, `${label}: QC обрезана по высоте`).toBeLessThanOrEqual(
    geometry.qc.clientHeight + 1,
  );
  expect(geometry.page.scrollY, `${label}: window.scrollY`).toBe(0);
  expect(geometry.page.docOverflow, `${label}: вертикальный скролл документа`).toBeLessThanOrEqual(
    1,
  );
  expect(geometry.page.viewOverflow, `${label}: вертикальный скролл вида`).toBeLessThanOrEqual(1);
  expect(geometry.page.headerOverflow, `${label}: чипы шапки`).toBeLessThanOrEqual(1);
  expect(geometry.horizontal?.left ?? 0, `${label}: панель левее колонки`).toBeGreaterThanOrEqual(
    -1,
  );
  expect(geometry.horizontal?.right ?? 0, `${label}: панель правее колонки`).toBeLessThanOrEqual(1);
}

function saveEvidence(width: number, label: string, geometry: Geometry): void {
  if (QA_DIR === undefined) return;
  mkdirSync(QA_DIR, { recursive: true });
  writeFileSync(
    join(QA_DIR, `ripple-geometry-${width}-${label}.json`),
    JSON.stringify(geometry, null, 2),
    "utf8",
  );
}

for (const width of [1280, 1920]) {
  test(`V8-1 @${width}×720: сохранённые числа и неподвижные слоты`, async ({ page }) => {
    install(page);
    await page.setViewportSize({ width, height: 720 });
    await page.goto(`${BASE}?a=ripple-a&b=ripple-c`);
    const panel = page.locator("[data-ripple-panel]");
    await expect(panel).toHaveAttribute("data-state", "ready");
    await expect(panel).toHaveAttribute("data-session-id", "ripple-a");
    await panel.scrollIntoViewIfNeeded();

    // 1) data-value — байты артефакта, не форматированная подмена.
    const rendered = await panel.evaluate((root) =>
      Object.fromEntries(
        [...root.querySelectorAll<HTMLElement>("[data-metric]")].map((node) => [
          node.getAttribute("data-metric"),
          node.getAttribute("data-value"),
        ]),
      ),
    );
    expect(rendered).toEqual({
      mean: String(NORMAL.mean),
      "rms-ac": String(NORMAL.rms),
      vpp: String(NORMAL.vpp),
      band: String(NORMAL.bandRms),
    });
    const baselineRaw = await panel.evaluate((root) => ({
      rms: root.querySelector("[data-baseline-rms]")?.getAttribute("data-value"),
      vpp: root.querySelector("[data-baseline-vpp]")?.getAttribute("data-value"),
    }));
    expect(baselineRaw).toEqual({ rms: "0.001", vpp: "0.003" });
    await expect(panel.locator("[data-metric='rms-ac'] .ripple-card-value")).toHaveText(
      "2,12\u00A0мВ",
    );
    await expect(panel.locator("[data-chip='volts']")).toHaveText("некалиброванные вольты");

    const normal = await measure(page);
    expectClean(normal, "ready A");
    saveEvidence(width, "ready-a", normal);
    if (QA_DIR !== undefined) {
      await page.screenshot({ path: join(QA_DIR, `ripple-${width}-ready-a.png`) });
    }

    // 2) Недоступная ветка: слоты те же.
    await page.locator('tr[data-session="ripple-b"] [data-assign="a"]').click();
    await expect(panel).toHaveAttribute("data-session-id", "ripple-b");
    await expect(panel).toHaveAttribute("data-state", "ready");
    await expect(panel).toHaveAttribute("data-availability", "unavailable");
    const absent = await measure(page);
    expectClean(absent, "unavailable B");
    expect(absent.positions, "B: слоты не сдвинулись").toEqual(normal.positions);
    saveEvidence(width, "absent-b", absent);
    if (QA_DIR !== undefined) {
      await page.screenshot({ path: join(QA_DIR, `ripple-${width}-absent-b.png`) });
    }

    // 3) Длинные числа: слоты те же.
    await page.locator('tr[data-session="ripple-c"] [data-assign="a"]').click();
    await expect(panel).toHaveAttribute("data-session-id", "ripple-c");
    await expect(panel).toHaveAttribute("data-state", "ready");
    const long = await measure(page);
    expectClean(long, "long C");
    expect(long.positions, "C: слоты не сдвинулись").toEqual(normal.positions);
    saveEvidence(width, "long-c", long);
    if (QA_DIR !== undefined) {
      await page.screenshot({ path: join(QA_DIR, `ripple-${width}-long-c.png`) });
    }

    // 4) Представление спектра — вид тех же байтов, контролы неподвижны.
    await panel.locator('[data-ripple-mode="asd"]').click();
    await expect(panel.locator('[data-ripple-mode="asd"]')).toHaveAttribute("aria-pressed", "true");
    const asd = await measure(page);
    expectClean(asd, "asd C");
    expect(asd.positions, "ASD: контролы не сдвинулись").toEqual(normal.positions);
    saveEvidence(width, "asd-c", asd);
    if (QA_DIR !== undefined) {
      await page.screenshot({ path: join(QA_DIR, `ripple-${width}-asd-c.png`) });
    }
  });
}

for (const width of [1280, 1920]) {
  test(`V8-3 @${width}×720: реальные артефакты кампании — честная метка спектра и QC без обрезки`, async ({
    page,
  }) => {
    install(page);
    await page.setViewportSize({ width, height: 720 });
    await page.goto(`${BASE}?a=ripple-a&b=ripple-c`);
    const panel = page.locator("[data-ripple-panel]");
    await expect(panel).toHaveAttribute("data-state", "ready");
    await panel.scrollIntoViewIfNeeded();
    const normal = await measure(page);
    expectClean(normal, `ready A @${width}`);
    saveEvidence(width, "real-base", normal);

    // 1) Реальный clip-mismatch (31bea3ca…): длинный QC помещается в слот,
    //    полный текст и машинные коды достижимы, контролы не сдвинуты.
    await page.locator('tr[data-session="ripple-real-clip"] [data-assign="a"]').click();
    await expect(panel).toHaveAttribute("data-session-id", "ripple-real-clip");
    await expect(panel).toHaveAttribute("data-state", "ready");
    const clip = await measure(page);
    expectClean(clip, `real clip-mismatch @${width}`);
    expect(clip.qc.textLength, "clip-mismatch: QC-текст реальный, не пустой").toBeGreaterThan(70);
    expect(clip.qc.omitted, "clip-mismatch: дубль кода оценки убран").toContain(
      "clip_census_inconsistent",
    );
    expect(clip.positions, "clip-mismatch: контролы не сдвинулись").toEqual(normal.positions);
    await expect(panel).toHaveAttribute("data-spectrum", "unavailable");
    await expect(panel.locator("[data-ripple-qc]")).toHaveAttribute(
      "title",
      /clip_census_inconsistent/,
    );
    await expect(panel.locator("[data-role='chart-empty']")).toHaveAttribute(
      "data-reason",
      "unavailable",
    );
    saveEvidence(width, "real-clip", clip);
    if (QA_DIR !== undefined) {
      await page.screenshot({ path: join(QA_DIR, `ripple-${width}-real-clip.png`) });
    }

    // 2) Реальный constant (63a0ef56…): спектр ДОСТУПЕН, все уровни нулевые —
    //    подпись говорит правду и не называет доступное недоступным.
    await page.locator('tr[data-session="ripple-real-constant"] [data-assign="a"]').click();
    await expect(panel).toHaveAttribute("data-session-id", "ripple-real-constant");
    await expect(panel).toHaveAttribute("data-state", "ready");
    const zero = await measure(page);
    expectClean(zero, `real constant @${width}`);
    expect(zero.positions, "constant: контролы не сдвинулись").toEqual(normal.positions);
    await expect(panel).toHaveAttribute("data-spectrum", "available");
    await expect(panel.locator("[data-role='chart-empty']")).toHaveAttribute(
      "data-reason",
      "zero_floor",
    );
    const emptyText = (await panel.locator("[data-role='chart-empty']").textContent()) ?? "";
    expect(emptyText, "constant: доступный спектр не назван недоступным").not.toContain("недоступ");
    expect(emptyText, "constant: подпись не сериализует -Infinity").not.toContain("Infinity");
    saveEvidence(width, "real-constant", zero);
    if (QA_DIR !== undefined) {
      await page.screenshot({ path: join(QA_DIR, `ripple-${width}-real-constant.png`) });
    }
  });
}

for (const width of [1280, 1920]) {
  test(`V8-4 @${width}×720: 14 кодов причин — строка QC не обрезается молча`, async ({ page }) => {
    install(page);
    await page.setViewportSize({ width, height: 720 });
    await page.goto(`${BASE}?a=ripple-a&b=ripple-c`);
    const panel = page.locator("[data-ripple-panel]");
    await expect(panel).toHaveAttribute("data-state", "ready");
    await panel.scrollIntoViewIfNeeded();
    const normal = await measure(page);
    expectClean(normal, `ready A @${width}`);

    await page.locator('tr[data-session="ripple-many-codes"] [data-assign="a"]').click();
    await expect(panel).toHaveAttribute("data-session-id", "ripple-many-codes");
    await expect(panel).toHaveAttribute("data-state", "ready");
    const many = await measure(page);
    saveEvidence(width, "many-codes", many);
    if (QA_DIR !== undefined) {
      await page.screenshot({ path: join(QA_DIR, `ripple-${width}-many-codes.png`) });
    }

    // Слот QC не обрезает видимую строку ни по высоте, ни по ширине.
    expect(many.qc.scrollHeight, `QC @${width}: обрезки по высоте нет`).toBeLessThanOrEqual(
      many.qc.clientHeight + 1,
    );
    expect(many.qc.scrollWidth, `QC @${width}: обрезки по ширине нет`).toBeLessThanOrEqual(
      many.qc.clientWidth + 1,
    );
    // Строка называет ФАКТИЧЕСКОЕ число не показанных кодов.
    const hidden = Number(many.qc.hidden);
    expect(Number.isInteger(hidden), "data-qc-hidden — целое число").toBe(true);
    expect(hidden, "часть кодов не показана").toBeGreaterThan(0);
    expect(many.qc.text, "строка называет число не показанных кодов").toMatch(
      new RegExp(`ещё ${hidden} (код|кода|кодов) QC`),
    );
    expect(many.qc.text, "многоточие не прячет содержимое").not.toContain("...");
    expect(
      many.qc.hiddenCodes.split(" ").filter((code) => code !== "").length,
      "скрытых кодов ровно столько, сколько названо",
    ).toBe(hidden);
    // Полный текст и все машинные коды остаются в title.
    const title = (await panel.locator("[data-ripple-qc]").getAttribute("title")) ?? "";
    for (const code of MANY_CODES) {
      expect(title, `title сохраняет код ${code}`).toContain(code);
    }
    // Контролы не сдвинулись, страница не поехала.
    expect(many.positions, "контролы не сдвинулись").toEqual(normal.positions);
    expectClean(many, `many codes @${width}`);
  });
}

test("V8-2: 404 not_built и 409 stale_input — честные состояния, не пустой экран", async ({
  page,
}) => {
  const backend = installMockBackend(page);
  backend.seedCatalog(SESSIONS);
  for (const item of SESSIONS) {
    backend.seedSessionDetail(item.id, {
      name: item.id,
      manifest: { session_id: item.id },
      analysis: {},
      spectrum_available: true,
      waveform_available: false,
      ch2_available: false,
    });
  }
  backend.seedRipple("ripple-a", { reason: "not_built" }, 404);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto(`${BASE}?a=ripple-a&b=ripple-c`);
  const panel = page.locator("[data-ripple-panel]");
  await expect(panel).toHaveAttribute("data-state", "error");
  await expect(panel).toHaveAttribute("data-error", "not_built");
  await expect(panel.locator("[data-role='ripple-message']")).toContainText("не построен");
  await expect(panel.locator("[data-metric='rms-ac']")).toHaveAttribute("data-value", "null");

  backend.seedRipple(
    "ripple-a",
    { detail: "входные файлы изменились", reason: "stale_input" },
    409,
  );
  await page.locator('tr[data-session="ripple-b"] [data-assign="a"]').click();
  await page.locator('tr[data-session="ripple-a"] [data-assign="a"]').click();
  await expect(panel).toHaveAttribute("data-session-id", "ripple-a");
  await expect(panel).toHaveAttribute("data-state", "error");
  await expect(panel).toHaveAttribute("data-error", "conflict");
  await expect(panel).toHaveAttribute("data-reason", "stale_input");
  await expect(panel.locator("[data-role='ripple-message']")).toContainText(
    "входные файлы изменились",
  );
});
