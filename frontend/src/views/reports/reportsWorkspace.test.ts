import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import type { RouteStore } from "../../state/routeState";
import { mountReportsWorkspace } from "./reportsWorkspace";

const UNITS = "В²/Гц";

function flush(ms = 0): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function flushAll(rounds = 12): Promise<void> {
  for (let i = 0; i < rounds; i += 1) await flush(0);
}

interface Harness {
  client: Record<string, unknown>;
  failBuildWith: Error | null;
  submit: ReturnType<typeof vi.fn>;
}

function makeHarness(featureKey = "band_mid_total"): Harness {
  const experiment = {
    experiment_id: "exp.demo",
    title: "Демо",
    revision: 1,
    protocol: { kind: "ab" },
    primary_estimands: [{ feature_key: featureKey }],
    steps: [
      { order: 1, condition_id: "cond_a", instruction: "a" },
      { order: 2, condition_id: "cond_b", instruction: "b" },
    ],
  };
  const members = [
    { session_id: "s-a", storage_ref: "s-a", role: "cond_a:u", condition_id: "cond_a", order: 1 },
    { session_id: "s-b", storage_ref: "s-b", role: "cond_b:u", condition_id: "cond_b", order: 2 },
  ];
  const envelope = {
    result_kind: "effect",
    result: {
      effect: {
        mean_effect: 1,
        median_effect: 1,
        robust_effect: 1,
        interval: { low: 0.5, high: 1.5, confidence_level: 0.95 },
        stored_differences: [1],
      },
      drift: null,
    },
    metadata: {
      units: UNITS,
      sampling_unit: "measurement_session",
      hierarchy: ["site"],
      n: 1,
      missing_count: 0,
      exclusions: [],
      estimator: "qualified_within_run_contrast",
      interval_method: "seeded_block_bootstrap_percentile_95",
      provenance: { experiment_id: "exp.demo", estimand: featureKey, job_id: "job-1" },
    },
  };
  const harness: Harness = {
    client: {},
    failBuildWith: null,
    submit: vi.fn(async () => {
      if (harness.failBuildWith !== null) throw harness.failBuildWith;
      return {
        schema_version: 1,
        version: 1,
        job_id: "job-1",
        kind: "research_analysis",
        status: "queued",
        stage: "queued",
        series_index: null,
        series_total: null,
        written_sessions: [],
        result: null,
        error_code: null,
        error_message: null,
      };
    }),
  };
  harness.client = {
    ensureReady: vi.fn(async () => undefined),
    research: {
      experiments: vi.fn(async () => ({ items: [experiment], next_cursor: null })),
      experiment: vi.fn(async () => experiment),
      members: vi.fn(async () => ({ items: members, next_cursor: null })),
      steps: vi.fn(async () => ({
        items: experiment.steps,
        next_cursor: null,
      })),
    },
    statistics: {
      submit: harness.submit,
      result: vi.fn(async () => envelope),
    },
    plots: {
      detail: vi.fn(async (sessionId: string) => ({
        name: sessionId,
        manifest: {},
        analysis: {
          metrics: { [featureKey]: 10 },
          ch1_input_reference: { status: "available", model_kind: "rc_shunt_v1" },
        },
        spectrum_available: true,
        waveform_available: false,
        ch2_available: false,
      })),
    },
    catalogSessions: vi.fn(async () => ({ items: [], next_cursor: null })),
    analysis: {
      recipes: vi.fn(async () => []),
    },
  };
  return harness;
}

function mount(harness: Harness): { container: HTMLElement; dispose: () => void } {
  const container = document.createElement("div");
  document.body.append(container);
  const routes = {
    get: () => ({ route: "reports", params: {} }),
    replaceParams: vi.fn(),
    subscribe: () => () => undefined,
  } as unknown as RouteStore;
  const dispose = mountReportsWorkspace(container, {
    client: harness.client as unknown as LntApiClient,
    routes,
  });
  return { container, dispose };
}

async function openDetail(container: HTMLElement): Promise<void> {
  await flushAll();
  const open = container.querySelector<HTMLButtonElement>("[data-experiment-id]");
  expect(open).not.toBeNull();
  open?.click();
  await flushAll();
}

/** Явные единицы для признака без известной единицы (band_mid_total). */
function fillUnits(container: HTMLElement, value = UNITS): void {
  const input = container.querySelector<HTMLInputElement>("#lnt-rep-units");
  expect(input).not.toBeNull();
  if (input) input.value = value;
}

function deferNextSubmit(harness: Harness): () => void {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const submit = harness.submit.getMockImplementation();
  harness.submit.mockImplementationOnce(async () => {
    await gate;
    if (submit === undefined) throw new Error("submit implementation is missing");
    return submit();
  });
  return release;
}

describe("mountReportsWorkspace error paths", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("failed build renders a typed error block with a working retry", async () => {
    // Given: сборка падает (сервер статистики недоступен)
    const harness = makeHarness();
    harness.failBuildWith = new Error("сервер статистики недоступен");
    const { container, dispose } = mount(harness);
    await openDetail(container);
    try {
      // When: оператор вводит единицы и нажимает «Собрать отчёт»
      fillUnits(container);
      container.querySelector<HTMLButtonElement>("#lnt-rep-build")?.click();
      await flushAll();

      // Then: видимый типизированный блок ошибки с повтором, а не тихий статус
      const banner = container.querySelector(".lnt-rep-error");
      expect(banner).not.toBeNull();
      expect(banner?.getAttribute("role")).toBe("alert");
      expect(banner?.hasAttribute("hidden")).toBe(false);
      expect(banner?.querySelector(".lnt-error-text")?.textContent).toContain(
        "сервер статистики недоступен",
      );
      const retry = banner?.querySelector<HTMLButtonElement>("button");
      expect(retry?.textContent).toContain("Повторить");

      // When: сервер поднялся, оператор жмёт «Повторить»
      harness.failBuildWith = null;
      retry?.click();
      await flushAll();

      // Then: отчёт собран, превью на месте
      expect(container.querySelector(".lnt-rep-preview")).not.toBeNull();
    } finally {
      dispose();
    }
  });

  it("empty workspace has no clickable build and explains the next step", async () => {
    // Given: рабочая область без выбранного эксперимента
    const harness = makeHarness();
    const { container, dispose } = mount(harness);
    try {
      await flushAll();

      // Then: кнопки сборки нет в DOM (кликнуть нечего — no-op невозможен),
      // а helper-текст называет следующий шаг
      expect(container.querySelector("#lnt-rep-build")).toBeNull();
      expect(container.textContent).toContain("Выберите эксперимент");
    } finally {
      dispose();
    }
  });

  it("keeps the title above the panes and invites into the empty detail", async () => {
    // Given: рабочая область без выбранного эксперимента
    const harness = makeHarness();
    const { container, dispose } = mount(harness);
    try {
      await flushAll();

      // Then: заголовок и описание — над панелями, а не в узкой левой колонке
      expect(container.querySelector(".lnt-rep-left .view-title")).toBeNull();
      expect(container.querySelector(".lnt-rep-header .view-title")?.textContent).toBe("Отчёты");
      expect(container.querySelector(".lnt-rep-header .view-desc")).not.toBeNull();

      // Then: пустая правая панель — оформленное приглашение, а не пустота
      const invitation = container.querySelector(".lnt-rep-right .lnt-rep-invitation");
      expect(invitation).not.toBeNull();
      expect(invitation?.textContent).toContain("Выберите эксперимент");
    } finally {
      dispose();
    }
  });

  it("hides the invitation once an experiment detail loads", async () => {
    // Given: эксперимент выбран
    const harness = makeHarness();
    const { container, dispose } = mount(harness);
    try {
      await openDetail(container);

      // Then: приглашение скрыто, детали на месте
      const invitation = container.querySelector<HTMLElement>(".lnt-rep-invitation");
      expect(invitation?.hidden).toBe(true);
      expect(container.querySelector(".lnt-rep-meta")).not.toBeNull();
    } finally {
      dispose();
    }
  });

  it("download button is disabled with a visible reason before a report is built", async () => {
    // Given: эксперимент выбран, но отчёт ещё не собран
    const harness = makeHarness();
    const { container, dispose } = mount(harness);
    await openDetail(container);
    try {
      // Then: выгрузка заблокирована с видимой причиной
      const download = container.querySelector<HTMLButtonElement>("#lnt-rep-download");
      expect(download?.disabled).toBe(true);
      expect(download?.title).toContain("отч");
      expect(container.textContent).toContain("Сначала соберите отчёт");
    } finally {
      dispose();
    }
  });

  it("failed download renders a typed error block with a working retry", async () => {
    // Given: отчёт собран, но выгрузка падает
    const harness = makeHarness();
    const { container, dispose } = mount(harness);
    await openDetail(container);
    try {
      fillUnits(container);
      container.querySelector<HTMLButtonElement>("#lnt-rep-build")?.click();
      await flushAll();
      expect(container.querySelector(".lnt-rep-preview")).not.toBeNull();

      let calls = 0;
      const urlRecord = URL as unknown as {
        createObjectURL?: unknown;
        revokeObjectURL?: unknown;
      };
      const prevCreate = urlRecord.createObjectURL;
      const prevRevoke = urlRecord.revokeObjectURL;
      urlRecord.createObjectURL = () => {
        calls += 1;
        if (calls === 1) throw new Error("не удалось создать файл");
        return "blob:mock-report";
      };
      urlRecord.revokeObjectURL = () => undefined;
      const clickSpy = vi
        .spyOn(HTMLAnchorElement.prototype, "click")
        .mockImplementation(() => undefined);
      try {
        // When
        container.querySelector<HTMLButtonElement>("#lnt-rep-download")?.click();
        await flushAll();

        // Then: типизированный блок ошибки выгрузки с повтором
        const banner = container.querySelector(".lnt-rep-error");
        expect(banner).not.toBeNull();
        expect(banner?.hasAttribute("hidden")).toBe(false);
        expect(banner?.querySelector(".lnt-error-text")?.textContent).toContain(
          "не удалось создать файл",
        );
        const retry = banner?.querySelector<HTMLButtonElement>("button");
        expect(retry?.textContent).toContain("Повторить");

        // When: повтор после восстановления
        retry?.click();
        await flushAll();
        expect(clickSpy).toHaveBeenCalled();
      } finally {
        const record = URL as unknown as {
          createObjectURL?: unknown;
          revokeObjectURL?: unknown;
        };
        record.createObjectURL = prevCreate;
        record.revokeObjectURL = prevRevoke;
        clickSpy.mockRestore();
      }
    } finally {
      dispose();
    }
  });
});

describe("mountReportsWorkspace units contract", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("prefills known metric units and demands explicit input for unknown ones", async () => {
    // Given: признак с известной единицей (needle_mean_v → V)
    const known = makeHarness("needle_mean_v");
    const mounted = mount(known);
    await openDetail(mounted.container);
    const knownInput = mounted.container.querySelector<HTMLInputElement>("#lnt-rep-units");
    expect(knownInput?.value).toBe("V");
    mounted.dispose();
    document.body.innerHTML = "";

    // Given: признак без известной единицы (band_mid_total)
    const unknown = makeHarness("band_mid_total");
    const second = mount(unknown);
    try {
      await openDetail(second.container);
      const input = second.container.querySelector<HTMLInputElement>("#lnt-rep-units");

      // Then: значение не выдумывается, поле требует явного ввода
      expect(input?.value).toBe("");
      expect(input?.placeholder).toContain("единицы");
    } finally {
      second.dispose();
    }
  });

  it("build without units for an unknown feature shows an error and never submits", async () => {
    // Given: band_mid_total без введённых единиц
    const harness = makeHarness("band_mid_total");
    const { container, dispose } = mount(harness);
    await openDetail(container);
    try {
      // When: оператор жмёт сборку, не заполнив единицы
      container.querySelector<HTMLButtonElement>("#lnt-rep-build")?.click();
      await flushAll();

      // Then: типизированная ошибка про единицы, POST статистики не выполнен
      const banner = container.querySelector(".lnt-rep-error");
      expect(banner?.hasAttribute("hidden")).toBe(false);
      expect(banner?.textContent).toContain("единицы");
      expect(harness.submit).not.toHaveBeenCalled();
    } finally {
      dispose();
    }
  });

  it("changing units after a build resets the stale preview and download", async () => {
    // Given: отчёт собран, выгрузка доступна
    const harness = makeHarness();
    const { container, dispose } = mount(harness);
    await openDetail(container);
    try {
      fillUnits(container);
      container.querySelector<HTMLButtonElement>("#lnt-rep-build")?.click();
      await flushAll();
      const download = container.querySelector<HTMLButtonElement>("#lnt-rep-download");
      expect(container.querySelector(".lnt-rep-preview")).not.toBeNull();
      expect(download?.disabled).toBe(false);

      // When: оператор меняет единицы
      const input = container.querySelector<HTMLInputElement>("#lnt-rep-units");
      if (input) {
        input.value = "V";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      await flushAll();

      // Then: старое превью и выгрузка сброшены — прежний файл не выдаётся за новый
      expect(container.querySelector(".lnt-rep-preview")).toBeNull();
      expect(download?.disabled).toBe(true);
      expect(container.textContent).toContain("Соберите отчёт заново");
      expect(container.querySelector("#lnt-rep-hint")?.textContent).toContain(
        "Соберите отчёт заново",
      );
    } finally {
      dispose();
    }
  });

  it("changing units during a build cancels stale output and allows rebuilding", async () => {
    const harness = makeHarness();
    const release = deferNextSubmit(harness);
    const { container, dispose } = mount(harness);
    await openDetail(container);
    try {
      fillUnits(container);
      const build = container.querySelector<HTMLButtonElement>("#lnt-rep-build");
      const download = container.querySelector<HTMLButtonElement>("#lnt-rep-download");
      build?.click();
      await flushAll();
      expect(harness.submit).toHaveBeenCalledTimes(1);
      expect(build?.disabled).toBe(true);

      const input = container.querySelector<HTMLInputElement>("#lnt-rep-units");
      if (input) {
        input.value = "V";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }

      expect(build?.disabled).toBe(false);
      expect(container.querySelector(".lnt-rep-preview")).toBeNull();
      expect(download?.disabled).toBe(true);
      expect(container.textContent).toContain("Соберите отчёт заново");

      release();
      await flushAll();
      expect(container.querySelector(".lnt-rep-preview")).toBeNull();
      expect(download?.disabled).toBe(true);

      build?.click();
      await flushAll();
      expect(harness.submit).toHaveBeenCalledTimes(2);
      expect(container.querySelector(".lnt-rep-preview")).not.toBeNull();
      expect(download?.disabled).toBe(false);
    } finally {
      dispose();
    }
  });

  it("ignores a pending result after the selected experiment is reloaded", async () => {
    const harness = makeHarness();
    const release = deferNextSubmit(harness);
    const { container, dispose } = mount(harness);
    await openDetail(container);
    try {
      fillUnits(container);
      container.querySelector<HTMLButtonElement>("#lnt-rep-build")?.click();
      await flushAll();
      expect(harness.submit).toHaveBeenCalledTimes(1);

      container.querySelector<HTMLButtonElement>("[data-experiment-id]")?.click();
      await flushAll();
      release();
      await flushAll();

      expect(container.querySelector(".lnt-rep-preview")).toBeNull();
      expect(container.querySelector<HTMLButtonElement>("#lnt-rep-download")?.disabled).toBe(true);
    } finally {
      dispose();
    }
  });

  it("ignores a pending result after disposal", async () => {
    const harness = makeHarness();
    const release = deferNextSubmit(harness);
    const { container, dispose } = mount(harness);
    await openDetail(container);
    fillUnits(container);
    container.querySelector<HTMLButtonElement>("#lnt-rep-build")?.click();
    await flushAll();
    expect(harness.submit).toHaveBeenCalledTimes(1);

    dispose();
    release();
    await flushAll();

    expect(container.querySelector(".lnt-rep-preview")).toBeNull();
    expect(container.querySelector<HTMLButtonElement>("#lnt-rep-download")?.disabled).toBe(true);
  });
});
