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
}

function makeHarness(): Harness {
  const harness: Harness = { client: {}, failBuildWith: null };
  const experiment = {
    experiment_id: "exp.demo",
    title: "Демо",
    revision: 1,
    protocol: { kind: "ab" },
    primary_estimands: [{ feature_key: "band_mid_total" }],
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
      provenance: { experiment_id: "exp.demo", estimand: "band_mid_total", job_id: "job-1" },
    },
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
      result: vi.fn(async () => envelope),
    },
    plots: {
      detail: vi.fn(async (sessionId: string) => ({
        name: sessionId,
        manifest: {},
        analysis: {
          metrics: { band_mid_total: 10 },
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
      // When: оператор нажимает «Собрать отчёт»
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
        const urlRecord = URL as unknown as {
          createObjectURL?: unknown;
          revokeObjectURL?: unknown;
        };
        urlRecord.createObjectURL = prevCreate;
        urlRecord.revokeObjectURL = prevRevoke;
        clickSpy.mockRestore();
      }
    } finally {
      dispose();
    }
  });
});
