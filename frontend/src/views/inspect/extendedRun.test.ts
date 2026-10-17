import { describe, expect, it, vi } from "vitest";
import type { AnalysisRunSnapshot } from "../../api/types-analysis";
import type { FamilySummary } from "./characterizationFamily";
import {
  BUNDLE_FILES,
  EXTENDED_RECIPE_NAME,
  createExtendedRun,
  parseCharacterizationSummary,
} from "./extendedRun";
import type { ExtendedRunClient, ExtendedRunHandle } from "./extendedRun";
import { renderFamilyCards } from "./familyCards";
import { reasonCodeRu } from "./reasonCodes";

/* jsdom не реализует URL.createObjectURL; скачивание в тесте доходит до
 * saveBlob только на успешном повторе, поэтому заглушка нужна именно там. */
if (typeof URL.createObjectURL !== "function") {
  URL.createObjectURL = () => "blob:mock";
  URL.revokeObjectURL = () => undefined;
}

function snapshot(status: string, artifactKey: string | null): AnalysisRunSnapshot {
  return {
    job_id: "job-1",
    kind: "analysis",
    status,
    stage: "",
    completed: 1,
    total: 1,
    artifact_key: artifactKey,
    error: null,
  };
}

type FamilySpec = {
  readonly id: string;
  readonly status: string;
  /** Отсутствует ключ — payload без reason_codes (обратная совместимость). */
  readonly codes?: readonly string[];
  readonly qc?: { readonly passed: boolean; readonly codes: readonly string[] };
  readonly support?: {
    readonly storedCount: number;
    readonly missingCount: number;
    readonly selectionRule: string;
  };
  readonly band?: { readonly lowHz: number; readonly highHz: number };
  readonly window?: {
    readonly kind: string;
    readonly durationS: number;
    readonly sampleCount: number;
    readonly overlapFraction: number;
  };
  readonly inference?: {
    readonly estimateScope: string;
    readonly populationInference: string;
    readonly reasonCode: string | null;
  };
};

function payloadOf(overrides: Readonly<Record<number, FamilySpec>>): unknown {
  return {
    families: Array.from({ length: 18 }, (_, index) => {
      const spec: FamilySpec = overrides[index] ?? {
        id: `f${String(index + 1).padStart(2, "0")}_other`,
        status: "unavailable",
      };
      return {
        family_id: spec.id,
        status: spec.status,
        comparison_summary: index === 0 ? [{ name: "f1_hz", value: 50.01, unit: "Hz" }] : [],
        ...(spec.codes === undefined ? {} : { reason_codes: [...spec.codes] }),
        ...(spec.qc === undefined
          ? {}
          : { qc: { passed: spec.qc.passed, reason_codes: [...spec.qc.codes] } }),
        ...(spec.support === undefined
          ? {}
          : {
              support: {
                stored_count: spec.support.storedCount,
                missing_count: spec.support.missingCount,
                selection_rule: spec.support.selectionRule,
              },
            }),
        ...(spec.band === undefined
          ? {}
          : { band: { low_hz: spec.band.lowHz, high_hz: spec.band.highHz } }),
        ...(spec.window === undefined
          ? {}
          : {
              window: {
                kind: spec.window.kind,
                duration_s: spec.window.durationS,
                sample_count: spec.window.sampleCount,
                overlap_fraction: spec.window.overlapFraction,
              },
            }),
        ...(spec.inference === undefined
          ? {}
          : {
              inference: {
                estimate_scope: spec.inference.estimateScope,
                population_inference: spec.inference.populationInference,
                reason_code: spec.inference.reasonCode,
              },
            }),
      };
    }),
  };
}

type BareOverrides = {
  readonly id?: string;
  readonly status?: string;
  readonly reasonCodes?: readonly string[] | null;
};

/** Семейство без единого заполненного поля: все блоки — честные null. */
function bareFamily(overrides: BareOverrides = {}): FamilySummary {
  return {
    id: overrides.id ?? "f01_phase_cycle",
    status: overrides.status ?? "unavailable",
    reasonCodes: overrides.reasonCodes === undefined ? null : overrides.reasonCodes,
    qc: { passed: null, reasonCodes: null },
    support: { storedCount: null, missingCount: null, selectionRule: null },
    band: { lowHz: null, highHz: null },
    window: { kind: null, durationS: null, sampleCount: null, overlapFraction: null },
    inference: { estimateScope: null, populationInference: null, reasonCode: null },
  };
}

function cardsIn(handle: ExtendedRunHandle, group: string): readonly HTMLElement[] {
  return Array.from(
    handle.root.querySelectorAll<HTMLElement>(`[data-family-group="${group}"] [data-family-id]`),
  );
}

function cardOf(handle: ExtendedRunHandle, familyId: string): HTMLElement {
  const card = handle.root.querySelector<HTMLElement>(`[data-family-id="${familyId}"]`);
  expect(card).not.toBeNull();
  return card as HTMLElement;
}

function groupCount(handle: ExtendedRunHandle, group: string): string | null {
  return handle.root.querySelector(`[data-group-count="${group}"]`)?.textContent ?? null;
}

function jsonBytes(payload: unknown): ArrayBuffer {
  return new TextEncoder().encode(JSON.stringify(payload)).buffer as ArrayBuffer;
}

/** Клиент, у которого только скачивание артефакта падает: сводка отдаётся. */
function makeClient(downloadError: Error, payload: unknown = payloadOf({})): ExtendedRunClient {
  let summaryServed = false;
  return {
    ensureReady: async () => undefined,
    recipes: async () => [{ recipe_id: "rec-1", name: EXTENDED_RECIPE_NAME }],
    runAnalysis: async () => snapshot("running", null),
    runStatus: async () => snapshot("succeeded", "art-key"),
    artifactBytes: async () => {
      if (!summaryServed) {
        summaryServed = true;
        return jsonBytes(payload);
      }
      throw downloadError;
    },
  };
}

function mountHandle(client: ExtendedRunClient): ExtendedRunHandle {
  const handle = createExtendedRun({ client });
  document.body.replaceChildren(handle.root);
  handle.setSession("session-1");
  return handle;
}

async function runToDownloads(handle: ExtendedRunHandle): Promise<void> {
  handle.root
    .querySelector<HTMLButtonElement>(".lnt-w1-toolbar button")
    ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await vi.waitFor(() =>
    expect(handle.root.querySelectorAll("[data-bundle-file]")).toHaveLength(3),
  );
}

describe("createExtendedRun: скачивание артефактов", () => {
  it("показывает ошибку скачивания строкой с повтором, без необработанного отклонения", async () => {
    // Supersession: ошибка скачивания переехала из строки статуса прогона в
    // собственную строку role=alert рядом с кнопками (вариант «Карточки») и
    // получила рабочий повтор; утверждение про строку статуса снято.
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown): void => {
      unhandled.push(reason);
    };
    process.on("unhandledRejection", onUnhandled);
    try {
      let summaryServed = false;
      let npzAttempts = 0;
      const client: ExtendedRunClient = {
        ensureReady: async () => undefined,
        recipes: async () => [{ recipe_id: "rec-1", name: EXTENDED_RECIPE_NAME }],
        runAnalysis: async () => snapshot("running", null),
        runStatus: async () => snapshot("succeeded", "art-key"),
        artifactBytes: async (_session, _key, filename) => {
          if (filename === BUNDLE_FILES[0] && !summaryServed) {
            summaryServed = true;
            return jsonBytes(payloadOf({}));
          }
          npzAttempts += 1;
          if (npzAttempts === 1) throw new Error("404");
          return new ArrayBuffer(8);
        },
      };
      const handle = mountHandle(client);
      await runToDownloads(handle);
      const status = handle.root.querySelector<HTMLElement>('[role="status"]');

      // When: первый клик по артефакту массивов падает с 404.
      handle.root
        .querySelector<HTMLButtonElement>(`[data-bundle-file="${BUNDLE_FILES[1]}"]`)
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

      // Then: видима строка ошибки, строка статуса прогона не загрязнена.
      await vi.waitFor(() => {
        const row = handle.root.querySelector<HTMLElement>("[data-download-error]");
        expect(row?.textContent).toContain("404");
      });
      const errorRow = handle.root.querySelector<HTMLElement>("[data-download-error]");
      expect(errorRow?.textContent).toContain(BUNDLE_FILES[1]);
      expect(status?.textContent).not.toContain("404");

      // When: повтор.
      handle.root
        .querySelector<HTMLButtonElement>("[data-download-retry]")
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

      // Then: вторая попытка уходит, строка ошибки исчезает.
      await vi.waitFor(() => expect(npzAttempts).toBe(2));
      await vi.waitFor(() => expect(handle.root.querySelector("[data-download-error]")).toBeNull());
      await vi.waitFor(() => expect(unhandled).toEqual([]));
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });
});

describe("createExtendedRun: холодный старт без launch-nonce", () => {
  it("получает nonce через ensureReady до первого POST прогона", async () => {
    // Given: клиент без nonce — requireNonce бросил бы uninitialized на мутации.
    const order: string[] = [];
    let releaseReady = (): void => undefined;
    const ready = new Promise<void>((resolve) => {
      releaseReady = resolve;
    });
    const client: ExtendedRunClient = {
      ensureReady: async () => {
        order.push("ensureReady");
        await ready;
      },
      recipes: async () => {
        order.push("recipes");
        return [{ recipe_id: "rec-1", name: EXTENDED_RECIPE_NAME }];
      },
      runAnalysis: async () => {
        order.push("runAnalysis");
        return snapshot("running", null);
      },
      runStatus: async () => snapshot("succeeded", "art-key"),
      artifactBytes: async () => jsonBytes(payloadOf({})),
    };
    const handle = mountHandle(client);

    // When: холодный клик по кнопке расширенного прогона.
    handle.root
      .querySelector<HTMLButtonElement>(".lnt-w1-toolbar button")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    // Then: первым идёт ensureReady, и до его завершения мутация не уходит.
    await vi.waitFor(() => expect(order[0]).toBe("ensureReady"));
    expect(order).not.toContain("runAnalysis");
    releaseReady();
    await vi.waitFor(() => expect(order).toContain("runAnalysis"));
    handle.destroy();
  });
});

describe("сводка: карточки по статусам", () => {
  const MIXED = payloadOf({
    0: { id: "f01_phase_cycle", status: "available", codes: [] },
    1: {
      id: "f02_amplitude_time_shape",
      status: "partial",
      codes: ["baseline_unavailable"],
      support: { storedCount: 312, missingCount: 88, selectionRule: "declared_band_full_record" },
      band: { lowHz: 45, highHz: 2000 },
      window: { kind: "boxcar", durationS: 0.04, sampleCount: 819, overlapFraction: 0 },
    },
    2: {
      id: "f03_interharmonic_tracking",
      status: "partial",
      codes: ["artifact_limit"],
      support: { storedCount: 1840, missingCount: 256, selectionRule: "declared_band_full_record" },
      band: { lowHz: 3000, highHz: 200000 },
      window: { kind: "hann", durationS: 0.2, sampleCount: 40000, overlapFraction: 0.5 },
    },
    3: { id: "f04_multicycle_periodicity", status: "unavailable", codes: [] },
    5: {
      id: "f06_modulation_trajectories",
      status: "partial",
      codes: ["band_above_nyquist"],
      support: {
        storedCount: 7420,
        missingCount: 2820,
        selectionRule: "declared_band_full_record",
      },
      band: { lowHz: 30, highHz: 500 },
      window: { kind: "hann", durationS: 0.5, sampleCount: 10240, overlapFraction: 0.5 },
    },
    7: {
      id: "f08_transient_morphology",
      status: "partial",
      codes: ["too_few_samples"],
      support: { storedCount: 96, missingCount: 41, selectionRule: "event_window" },
      band: { lowHz: 45, highHz: 2000 },
      window: { kind: "boxcar", durationS: 0.04, sampleCount: 819, overlapFraction: 0 },
    },
    16: {
      id: "f17_cyclic_spectral_coherence",
      status: "unavailable",
      codes: ["cyclic_frequency_off_grid"],
    },
  });

  it("группирует семейства по статусу со счётчиками групп", async () => {
    // Given: реальная форма выдачи: 1 доступно, 4 частично, 13 недоступно.
    const handle = mountHandle(makeClient(new Error("404"), MIXED));

    // When
    await runToDownloads(handle);

    // Then
    await vi.waitFor(() => expect(cardsIn(handle, "unavailable")).toHaveLength(13));
    expect(cardsIn(handle, "available")).toHaveLength(1);
    expect(cardsIn(handle, "partial")).toHaveLength(4);
    expect(groupCount(handle, "available")).toBe("1 из 18");
    expect(groupCount(handle, "partial")).toBe("4 из 18");
    expect(groupCount(handle, "unavailable")).toBe("13 из 18");
    expect(handle.root.querySelector('[data-tally="available"]')?.textContent).toBe("1 доступно");
    expect(handle.root.querySelector('[data-tally="partial"]')?.textContent).toBe("4 частично");
    expect(handle.root.querySelector('[data-tally="unavailable"]')?.textContent).toBe(
      "13 недоступно",
    );
  });

  it("печатает RU-фразу из словаря reasonCodes рядом с сырым кодом", async () => {
    const handle = mountHandle(makeClient(new Error("404"), MIXED));
    await runToDownloads(handle);

    await vi.waitFor(() => expect(cardsIn(handle, "unavailable")).toHaveLength(13));
    const f17 = cardOf(handle, "f17_cyclic_spectral_coherence");
    expect(f17.textContent).toContain(reasonCodeRu("cyclic_frequency_off_grid"));
    expect(f17.textContent).toContain("cyclic_frequency_off_grid");
    const f02 = cardOf(handle, "f02_amplitude_time_shape");
    expect(f02.textContent).toContain(reasonCodeRu("baseline_unavailable"));
    expect(f02.textContent).toContain("baseline_unavailable");
  });

  it("семейству без кодов даёт честную фразу, доступному — фразу полного результата", async () => {
    const handle = mountHandle(makeClient(new Error("404"), MIXED));
    await runToDownloads(handle);

    await vi.waitFor(() => expect(cardsIn(handle, "available")).toHaveLength(1));
    const f01 = cardOf(handle, "f01_phase_cycle");
    expect(f01.textContent).toContain("Результат полный, QC пройден.");
    expect(f01.querySelector(".lnt-xr-code")).toBeNull();
    const f04 = cardOf(handle, "f04_multicycle_periodicity");
    expect(f04.textContent).toContain("Причина не сообщена в бандле.");
  });

  it("неизвестный код остаётся видимым через запасную фразу словаря", async () => {
    const payload = payloadOf({
      0: { id: "f01_phase_cycle", status: "available", codes: [] },
      5: { id: "f06_modulation_trajectories", status: "partial", codes: ["telemetry_v9_code"] },
    });
    const handle = mountHandle(makeClient(new Error("404"), payload));
    await runToDownloads(handle);

    await vi.waitFor(() => expect(cardsIn(handle, "partial")).toHaveLength(1));
    const card = cardOf(handle, "f06_modulation_trajectories");
    expect(card.textContent).toContain(reasonCodeRu("telemetry_v9_code"));
    expect(card.textContent).toContain("telemetry_v9_code");
  });

  it("богатое семейство несёт поддержку, полосу и окно на карточку", async () => {
    // Supersession: строка `<li>` «id: status — Причина: code» заменена
    // карточкой; те же данные проверяются полями карточки.
    const rich = payloadOf({
      0: { id: "f01_phase_cycle", status: "available", codes: [] },
      11: {
        id: "f12_spectral_kurtosis",
        status: "partial",
        codes: ["artifact_limit"],
        qc: { passed: false, codes: ["artifact_limit"] },
        support: {
          storedCount: 4096,
          missingCount: 12,
          selectionRule: "declared_band_full_record",
        },
        band: { lowHz: 3000, highHz: 200000 },
        window: { kind: "record", durationS: 1.5, sampleCount: 30720, overlapFraction: 0.5 },
      },
    });
    const handle = mountHandle(makeClient(new Error("404"), rich));
    await runToDownloads(handle);

    await vi.waitFor(() => expect(cardsIn(handle, "partial")).toHaveLength(1));
    const card = cardOf(handle, "f12_spectral_kurtosis");
    expect(card.textContent).toContain("Спектральный эксцесс");
    expect(card.textContent).toContain(reasonCodeRu("artifact_limit"));
    expect(card.textContent).toContain("поддержка 4096 / 12");
    expect(card.textContent).toContain("3000.0–200000.0 Гц");
    expect(card.textContent).toContain("1.5 с");
    expect(card.textContent).toContain("qc fail");
    expect(card.querySelector(".lnt-xr-bar-fill")).not.toBeNull();
  });

  it("держит длинный id сессии в шапке сводки без обрезания", async () => {
    const longSession = "cap-20260805-180623-very-long-suffix";
    const handle = createExtendedRun({ client: makeClient(new Error("404")) });
    document.body.replaceChildren(handle.root);
    handle.setSession(longSession);
    await runToDownloads(handle);

    await vi.waitFor(() => expect(cardsIn(handle, "unavailable")).toHaveLength(18));
    expect(handle.root.querySelector(".lnt-xr-note")?.textContent).toContain(longSession);
  });
});

describe("parseCharacterizationSummary: границы", () => {
  it("reads F01 f1_hz and all 18 family statuses", () => {
    const payload = payloadOf({
      0: { id: "f01_phase_cycle", status: "available", codes: [] },
      1: { id: "f02_amplitude_time_shape", status: "unavailable", codes: ["baseline_unavailable"] },
    });

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.f1Hz).toBeCloseTo(50.01, 5);
    expect(summary?.families).toHaveLength(18);
    // Контракт сводки расширен: кроме id/status/reasonCodes несутся qc, support,
    // band, window и inference. Бандл без этих блоков даёт честные null.
    expect(summary?.families[0]).toEqual({
      id: "f01_phase_cycle",
      status: "available",
      reasonCodes: [],
      qc: { passed: null, reasonCodes: null },
      support: { storedCount: null, missingCount: null, selectionRule: null },
      band: { lowHz: null, highHz: null },
      window: { kind: null, durationS: null, sampleCount: null, overlapFraction: null },
      inference: { estimateScope: null, populationInference: null, reasonCode: null },
    });
  });

  it("keeps reason codes verbatim in backend order", () => {
    const payload = payloadOf({
      0: { id: "f01_phase_cycle", status: "available", codes: [] },
      1: {
        id: "f03_interharmonic_tracking",
        status: "partial",
        codes: ["below_resolution", "peak_not_observed", "track_too_short"],
      },
    });

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.families[1]?.reasonCodes).toEqual([
      "below_resolution",
      "peak_not_observed",
      "track_too_short",
    ]);
  });

  it("reports null reason codes when the bundle omits them", () => {
    const payload = {
      families: Array.from({ length: 18 }, (_, index) => ({
        family_id: `f${String(index + 1).padStart(2, "0")}`,
        status: "unavailable",
        comparison_summary: [],
      })),
    };

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.families.every((family) => family.reasonCodes === null)).toBe(true);
  });

  it("rejects bundles without exactly 18 families", () => {
    expect(parseCharacterizationSummary({ families: [] })).toBeNull();
    expect(parseCharacterizationSummary(null)).toBeNull();
  });

  it("reports null F01 when the summary carries no f1_hz", () => {
    const payload = {
      families: Array.from({ length: 18 }, (_, index) => ({
        family_id: `f${String(index + 1).padStart(2, "0")}`,
        status: "unavailable",
        comparison_summary: [],
      })),
    };

    expect(parseCharacterizationSummary(payload)?.f1Hz).toBeNull();
  });
});

describe("parseCharacterizationSummary: богатая сводка", () => {
  const RICH: FamilySpec = {
    id: "f12_spectral_kurtosis",
    status: "partial",
    codes: ["artifact_limit"],
    qc: { passed: false, codes: ["artifact_limit"] },
    support: { storedCount: 4096, missingCount: 12, selectionRule: "declared_band_full_record" },
    band: { lowHz: 3000, highHz: 200000 },
    window: { kind: "record", durationS: 1.5, sampleCount: 30720, overlapFraction: 0.5 },
    inference: {
      estimateScope: "one_record",
      populationInference: "not_supported",
      reasonCode: "insufficient_frames",
    },
  };

  it("несёт reason_codes, qc, support, band, window и inference из payload", () => {
    // Given: реальная форма family_mapping из metadata_mapping.py.
    const payload = payloadOf({ 11: RICH });

    // When
    const summary = parseCharacterizationSummary(payload);

    // Then
    expect(summary?.families[11]).toEqual({
      id: "f12_spectral_kurtosis",
      status: "partial",
      reasonCodes: ["artifact_limit"],
      qc: { passed: false, reasonCodes: ["artifact_limit"] },
      support: { storedCount: 4096, missingCount: 12, selectionRule: "declared_band_full_record" },
      band: { lowHz: 3000, highHz: 200000 },
      window: { kind: "record", durationS: 1.5, sampleCount: 30720, overlapFraction: 0.5 },
      inference: {
        estimateScope: "one_record",
        populationInference: "not_supported",
        reasonCode: "insufficient_frames",
      },
    });
  });

  it("читает qc.reason_codes независимо от reason_codes семейства", () => {
    const payload = payloadOf({
      17: { ...RICH, id: "f18_bicoherence_triads", qc: { passed: false, codes: [] } },
    });

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.families[17]?.reasonCodes).toEqual(["artifact_limit"]);
    expect(summary?.families[17]?.qc).toEqual({ passed: false, reasonCodes: [] });
  });

  it("держит нулевые и дробные значения support, а не глотает их", () => {
    const payload = payloadOf({
      4: {
        ...RICH,
        id: "f05_phase_conditioned_statistics",
        support: { storedCount: 0, missingCount: 0, selectionRule: "all" },
        band: { lowHz: 47.5, highHz: 52.5 },
      },
    });

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.families[4]?.support).toEqual({
      storedCount: 0,
      missingCount: 0,
      selectionRule: "all",
    });
    expect(summary?.families[4]?.band).toEqual({ lowHz: 47.5, highHz: 52.5 });
  });

  it("отдаёт null вместо NaN, когда бэкенд прислал нечисловую границу полосы", () => {
    const payload = {
      families: Array.from({ length: 18 }, (_, index) => ({
        family_id: `f${String(index + 1).padStart(2, "0")}`,
        status: "unavailable",
        comparison_summary: [],
        band: index === 2 ? { low_hz: "47.5", high_hz: null } : undefined,
      })),
    };

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.families[2]?.band).toEqual({ lowHz: null, highHz: null });
  });

  it("не ломает разбор, когда support и band вовсе не пришли", () => {
    const payload = {
      families: Array.from({ length: 18 }, (_, index) => ({
        family_id: `f${String(index + 1).padStart(2, "0")}`,
        status: "unavailable",
        reason_codes: ["not_computed"],
        comparison_summary: index === 0 ? [{ name: "f1_hz", value: 50, unit: "Hz" }] : [],
      })),
    };

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.f1Hz).toBeCloseTo(50, 5);
    expect(summary?.families[3]?.support).toEqual({
      storedCount: null,
      missingCount: null,
      selectionRule: null,
    });
    expect(summary?.families[3]?.reasonCodes).toEqual(["not_computed"]);
  });
});

describe("familyCards: худшие случаи", () => {
  it("ноль семейств: три пустые группы и нулевые счётчики, без NaN", () => {
    const root = renderFamilyCards({ f1Hz: null, families: [] });

    expect(root.querySelectorAll("[data-family-group]")).toHaveLength(3);
    expect(root.querySelectorAll(".lnt-xr-empty")).toHaveLength(3);
    expect(root.querySelectorAll("[data-family-id]")).toHaveLength(0);
    expect(root.querySelector('[data-tally="available"]')?.textContent).toBe("0 доступно");
    expect(root.querySelector('[data-group-count="available"]')?.textContent).toBe("0 из 0");
    expect(root.textContent).toContain("н/д");
    expect(root.textContent).not.toContain("NaN");
  });

  it("одно семейство: одна карточка и две пустые группы", () => {
    const root = renderFamilyCards({
      f1Hz: 50.01,
      families: [bareFamily({ id: "f01_phase_cycle", status: "available", reasonCodes: [] })],
    });

    expect(root.querySelectorAll('[data-family-group="available"] [data-family-id]')).toHaveLength(
      1,
    );
    expect(root.querySelectorAll('[data-family-group="partial"] .lnt-xr-empty')).toHaveLength(1);
    expect(root.querySelectorAll('[data-family-group="unavailable"] .lnt-xr-empty')).toHaveLength(
      1,
    );
    expect(root.querySelector('[data-group-count="available"]')?.textContent).toBe("1 из 1");
  });

  it("семейство без полей: тихие тире, без полосы и без выдуманных чисел", () => {
    const root = renderFamilyCards({
      f1Hz: null,
      families: [bareFamily({ id: "f09_event_ordering" })],
    });
    const card = root.querySelector<HTMLElement>('[data-family-id="f09_event_ordering"]');

    expect(card).not.toBeNull();
    expect(card?.querySelector(".lnt-xr-bar")).toBeNull();
    expect(card?.textContent).toContain("поддержка —");
    expect(card?.textContent).toContain("qc —");
    expect(card?.textContent).toContain("Причины не сообщены в бандле.");
    expect(card?.textContent).not.toContain("NaN");
    expect(card?.textContent).not.toContain("undefined");
  });

  it("неизвестный статус получает собственную группу с сырым заголовком", () => {
    const root = renderFamilyCards({
      f1Hz: null,
      families: [bareFamily({ id: "f02_amplitude_time_shape", status: "degraded" })],
    });

    const group = root.querySelector('[data-family-group="degraded"]');
    expect(group).not.toBeNull();
    expect(group?.querySelector("h3")?.textContent).toBe("degraded");
    expect(group?.querySelectorAll("[data-family-id]")).toHaveLength(1);
  });
});
