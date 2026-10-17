import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { WaveformPayload } from "../../api/types-plots";
import type { SessionDetailPayload } from "../../api/types-plots";
import { REASON_NO_ARTIFACT } from "./pairLoadOutcome";
import { createV6Extras } from "./v6Extras";
import type { V6ExtrasChrome } from "./v6Extras";
import { createW1Chrome } from "./w1Chrome";

/** Задача 7 (G1/Q3 = A): причина отсутствия analysis-v2 уходит отдельным
 * сеттером onAbsenceReason (onSummary отвергнут вердиктом — переписывает
 * два точных toBe) и рендерится сиблингом счётчика в свёрнутой шапке. */

const HARMONICS = {
  windows: [{ index: 0, start_time_s: 0, thd: 0.04, fundamental_rms: 230 }],
};
const POINTER = { recipe_id: "default", artifact_key: "art-meas" };
const POINTER_FILE = ".lnt-default-analysis.json";

function detailPayload(cycles: number): SessionDetailPayload {
  return {
    name: "sess-a",
    manifest: {},
    analysis: { needle: { needle_sigma_ratio: 0.35, cycles_analyzed: cycles } },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

function fakeClient(files: Readonly<Record<string, unknown>>, cycles = 200) {
  const raw = {
    plots: { detail: vi.fn(async () => detailPayload(cycles)) },
    analysis: {
      artifactBytes: vi.fn(async () => new ArrayBuffer(0)),
      recipes: vi.fn(async () => []),
      runAnalysis: vi.fn(async () => ({ job_id: "j", status: "running" })),
      runStatus: vi.fn(async () => ({ job_id: "j", status: "succeeded" })),
    },
    ensureReady: vi.fn(async () => undefined),
    jobs: { start: vi.fn(async () => ({ status: "succeeded", result: {} })) },
    catalogSessions: vi.fn(async () => ({ items: [], next_cursor: null })),
    requestJson: vi.fn(async (_method: string, path: string) => {
      const name = path.split("/").pop() ?? "";
      if (!(name in files)) throw new ApiError("http", { status: 404 });
      return files[name];
    }),
    rawFetch: vi.fn(async () => new Response("{}", { status: 404 })),
  };
  return raw as unknown as LntApiClient;
}

function setupChrome(files: Readonly<Record<string, unknown>>) {
  const client = fakeClient(files);
  const reasons: Array<string | null> = [];
  const chrome = createW1Chrome({
    client,
    detail: async () => detailPayload(200),
    sessionTypeOf: () => "measurement",
  });
  chrome.onAbsenceReason((reason) => reasons.push(reason));
  document.body.append(chrome.bar, chrome.root);
  return { chrome, reasons };
}

describe("createW1Chrome: причина отсутствия v2 (сеттер onAbsenceReason)", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("emits the dictionary reason on the no-pointer path", async () => {
    // Given: указателя анализа v2 нет.
    const { chrome, reasons } = setupChrome({});

    // When
    chrome.setSession("sess-a");

    // Then: фраза словаря задачи 3, без четвёртого диалекта.
    await vi.waitFor(() => expect(reasons.at(-1)).toBe(REASON_NO_ARTIFACT));
  });

  it("emits null when the pointer is on place, and on session reset", async () => {
    // Given
    const { chrome, reasons } = setupChrome({
      [POINTER_FILE]: POINTER,
      "harmonics.json": HARMONICS,
    });

    // When
    chrome.setSession("sess-a");
    await vi.waitFor(() =>
      expect(chrome.root.querySelector('[data-panel="harmonics"]')).not.toBeNull(),
    );

    // Then: анализ есть — причины нет; сброс сессии тоже гасит узел.
    expect(reasons.at(-1)).toBeNull();
    chrome.setSession(null);
    expect(reasons.at(-1)).toBeNull();
  });
});

const WAVE: WaveformPayload = {
  channel: "ch1",
  time_s: [0, 1],
  voltage_v: [0.1, 0.2],
  point_count: 2,
};

function fakeChrome(): V6ExtrasChrome & { publish(reason: string | null): void } {
  const bar = document.createElement("div");
  const root = document.createElement("div");
  let listener: ((reason: string | null) => void) | null = null;
  return {
    bar,
    root,
    setSession() {},
    onSummary() {},
    onAbsenceReason(next) {
      listener = next;
    },
    destroy() {},
    publish(reason) {
      listener?.(reason);
    },
  };
}

describe("createV6Extras: сиблинг причины в свёрнутой шапке", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("renders the reason node as a hidden sibling of the summary counter", async () => {
    // Given: хром с сеттером onAbsenceReason.
    const chrome = fakeChrome();
    const extras = createV6Extras({
      client: { plots: { waveform: vi.fn().mockResolvedValue(WAVE) } },
      createView: () => ({
        root: document.createElement("div"),
        render() {},
        applyTheme() {},
        getData: () => null,
        destroy() {},
      }),
      createChrome: () => chrome,
    });
    document.body.append(extras.root);
    const w1 = extras.root.querySelector('[data-extra="w1"]');
    if (!(w1 instanceof HTMLDetailsElement)) throw new Error("w1 details missing");

    // Then: узел живёт в <summary> рядом со счётчиком, исходно скрыт.
    const reason = w1.querySelector("[data-role=w1-absence-reason]");
    expect(reason).not.toBeNull();
    expect(w1.querySelector("[data-role=w1-sum-value] + [data-role=w1-absence-reason]")).toBe(
      reason,
    );
    expect(reason?.hasAttribute("hidden")).toBe(true);
    expect(w1.open).toBe(false);

    // When: хром публикует причину словаря.
    chrome.publish(REASON_NO_ARTIFACT);

    // Then: узел виден без раскрытия, текст — из словаря.
    expect(reason?.hasAttribute("hidden")).toBe(false);
    expect(reason?.textContent).toBe(REASON_NO_ARTIFACT);

    // When: причина уходит (анализ появился).
    chrome.publish(null);
    expect(reason?.hasAttribute("hidden")).toBe(true);
    expect(reason?.textContent).toBe("");
  });
});
