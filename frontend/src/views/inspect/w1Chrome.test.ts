import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { SessionDetailPayload } from "../../api/types-plots";
import { createW1Chrome } from "./w1Chrome";
import { CTA_LABEL, MISSING_BANNER, NO_SESSION_SUMMARY, SESSION_CAPTION } from "./w1Chrome";

/** B2 (todo 13): сессию задаёт пара инспекции — у analysis-v2 нет своего
 * select и своего catalogSessions, detail приходит из общего загрузчика пары. */

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
  const requests: string[] = [];
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
      requests.push(path);
      const name = path.split("/").pop() ?? "";
      if (!(name in files)) throw new ApiError("http", { status: 404 });
      return files[name];
    }),
    rawFetch: vi.fn(async () => new Response("{}", { status: 404 })),
  };
  return { client: raw as unknown as LntApiClient, raw, requests };
}

function setup(files: Readonly<Record<string, unknown>>, cycles = 200) {
  const { client, raw, requests } = fakeClient(files, cycles);
  const sharedDetail = vi.fn(async (_name: string, _options?: { readonly signal?: AbortSignal }) =>
    detailPayload(cycles),
  );
  const summaries: string[] = [];
  const chrome = createW1Chrome({
    client,
    detail: sharedDetail,
    sessionTypeOf: () => "measurement",
  });
  chrome.onSummary((text) => summaries.push(text));
  document.body.append(chrome.bar, chrome.root);
  return { chrome, raw, requests, sharedDetail, summaries };
}

describe("createW1Chrome (B2: единый выбор сессии)", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("shows the base session as passive text: no select of its own", () => {
    // Given / When
    const { chrome } = setup({ [POINTER_FILE]: POINTER });

    // Then: второй источник выбора удалён, осталась подпись пары и CTA.
    expect(chrome.bar.querySelectorAll("select")).toHaveLength(0);
    expect(chrome.root.querySelectorAll("select")).toHaveLength(0);
    expect(chrome.bar.textContent).toContain(SESSION_CAPTION);
    expect(chrome.bar.querySelector("[data-session-id]")?.textContent).toBe("—");
    const cta = chrome.bar.querySelector<HTMLButtonElement>(".av2-cta");
    expect(cta?.textContent).toBe(CTA_LABEL);
    expect(cta?.disabled).toBe(true);
  });

  it("never calls catalogSessions and reads detail through the pair loader", async () => {
    // Given
    const { chrome, raw, sharedDetail } = setup({ [POINTER_FILE]: POINTER });

    // When
    chrome.setSession("sess-a");
    await vi.waitFor(() => expect(sharedDetail).toHaveBeenCalled());

    // Then
    expect(raw.catalogSessions).not.toHaveBeenCalled();
    expect(raw.plots.detail).not.toHaveBeenCalled();
    expect(sharedDetail).toHaveBeenCalledWith("sess-a", { signal: expect.any(AbortSignal) });
    expect(chrome.bar.querySelector("[data-session-id]")?.textContent).toBe("sess-a");
    expect(chrome.bar.querySelector<HTMLButtonElement>(".av2-cta")?.disabled).toBe(false);
  });

  it("publishes the collapsed-header summary with real counts", async () => {
    // Given: указатель на месте, записан только harmonics.json.
    const { chrome, summaries } = setup({
      [POINTER_FILE]: POINTER,
      "harmonics.json": HARMONICS,
    });

    // When
    chrome.setSession("sess-a");

    // Then
    await vi.waitFor(() => expect(summaries.at(-1)).toBe("панелей 1 · скаляров 2/4"));
    expect(summaries[0]).toBe(NO_SESSION_SUMMARY);
  });

  it("announces unwritten artifacts as chips instead of hiding them", async () => {
    // Given
    const { chrome } = setup({ [POINTER_FILE]: POINTER, "harmonics.json": HARMONICS });

    // When
    chrome.setSession("sess-a");

    // Then: пять отсутствующих артефактов названы, панель одна.
    await vi.waitFor(() =>
      expect(chrome.root.querySelectorAll("[data-absent-panel]")).toHaveLength(5),
    );
    const chips = [...chrome.root.querySelectorAll("[data-absent-panel]")].map((node) =>
      node.getAttribute("data-absent-panel"),
    );
    expect(chips).toEqual(["notching", "apd", "burst", "trends", "audio"]);
    expect(chrome.root.querySelector("[data-absent-panel=notching]")?.textContent).toContain(
      "нет артефакта",
    );
    expect(chrome.root.querySelectorAll('[data-panel="harmonics"]')).toHaveLength(1);
    expect(chrome.root.querySelector("[data-panel-key=harmonics]")?.textContent).toBe(
      "THD 0.04000",
    );
  });

  it("names the cycle floor when harmonics stay withheld", async () => {
    // Given: артефакт есть, циклов меньше минимума для лимита THD-V.
    const { chrome } = setup({ [POINTER_FILE]: POINTER, "harmonics.json": HARMONICS }, 47);

    // When
    chrome.setSession("sess-a");

    // Then
    await vi.waitFor(() =>
      expect(chrome.root.querySelector('[data-absent-tone="withheld"]')).not.toBeNull(),
    );
    expect(chrome.root.querySelector("[data-absent-panel=harmonics]")?.textContent).toContain(
      "недостаточно циклов (47 из 100)",
    );
    expect(chrome.root.querySelectorAll('[data-panel="harmonics"]')).toHaveLength(0);
  });

  it("shows the v1-only banner and no hollow panels", async () => {
    // Given: указателя анализа v2 нет.
    const { chrome } = setup({});

    // When
    chrome.setSession("sess-a");

    // Then
    await vi.waitFor(() =>
      expect(chrome.root.querySelector(".lnt-w1-banner")?.textContent).toBe(MISSING_BANNER),
    );
    const banner = chrome.root.querySelector(".lnt-w1-banner");
    expect(banner?.getAttribute("role")).toBe("status");
    expect(banner?.getAttribute("hidden")).toBeNull();
    expect(chrome.root.querySelectorAll(".lnt-w1-panel")).toHaveLength(0);
    expect(chrome.root.querySelectorAll("[data-absent-panel]")).toHaveLength(0);
    expect(chrome.bar.querySelector('[data-thd-verdict="legacy"]')).not.toBeNull();
  });

  it("keeps the verdict badge in the header, single per section", async () => {
    // Given
    const { chrome } = setup({ [POINTER_FILE]: POINTER, "harmonics.json": HARMONICS });

    // When
    chrome.setSession("sess-a");

    // Then: вердикт читается без раскрытия, бейдж один.
    await vi.waitFor(() => expect(chrome.bar.querySelector("[data-thd-verdict]")).not.toBeNull());
    expect(chrome.bar.querySelectorAll("[data-thd-verdict]")).toHaveLength(1);
    expect(chrome.root.querySelectorAll("[data-thd-verdict]")).toHaveLength(0);
    expect(chrome.bar.querySelector("[data-thd-verdict]")?.getAttribute("data-thd-verdict")).toBe(
      "pass",
    );
  });

  it("drops a stale load when the session changes again", async () => {
    // Given
    const { chrome, sharedDetail } = setup({ [POINTER_FILE]: POINTER });
    let first: AbortSignal | undefined;
    sharedDetail.mockImplementation(async (_name, options) => {
      first ??= options?.signal;
      return detailPayload(200);
    });
    // When: две быстрые смены сессии.
    chrome.setSession("sess-a");
    chrome.setSession("sess-b");
    await vi.waitFor(() =>
      expect(chrome.bar.querySelector("[data-session-id]")?.textContent).toBe("sess-b"),
    );

    // Then: запрос первой сессии отменён, в шапке только вторая.
    expect(first?.aborted).toBe(true);
    expect(chrome.bar.querySelector("[data-session-id]")?.getAttribute("data-session-id")).toBe(
      "sess-b",
    );
    expect(chrome.bar.querySelector("[data-session-id]")?.textContent).toBe("sess-b");
  });

  it("starts an analyze job for the pair base on CTA click", async () => {
    // Given
    const { chrome, raw } = setup({ [POINTER_FILE]: POINTER });
    chrome.setSession("sess-a");
    await vi.waitFor(() => expect(chrome.bar.querySelector(".av2-cta")).not.toBeNull());

    // When
    chrome.bar.querySelector<HTMLButtonElement>(".av2-cta")?.click();
    await vi.waitFor(() => expect(raw.jobs.start).toHaveBeenCalled());

    // Then
    expect(raw.ensureReady).toHaveBeenCalled();
    expect(raw.jobs.start).toHaveBeenCalledWith({ kind: "analyze", session_name: "sess-a" });
    expect(chrome.root.querySelector(".lnt-w1-job-rail")).not.toBeNull();
    expect(chrome.root.querySelector<HTMLElement>(".lnt-w1-job-rail")?.hidden).toBe(false);
  });
});
