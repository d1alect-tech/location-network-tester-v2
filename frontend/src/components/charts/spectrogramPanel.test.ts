/** W2: post-capture spectrogram A copy and missing-npz empty state. */

import { beforeEach, describe, expect, it } from "vitest";

import { ApiError } from "../../api/errors";
import type { CatalogPage } from "../../api/types";
import { createSpectrogramPanel } from "./spectrogramPanel";

const LABEL = "спектрограмма записи";

const CATALOG: CatalogPage = {
  items: [
    {
      id: "capture-001",
      health: "ok",
      created_utc: "2026-08-01T10:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "bad",
      label: "стенд-А",
      storage_path: null,
    },
  ],
  next_cursor: null,
};

function missingClient(): Pick<
  import("../../api/client").LntApiClient,
  "catalogSessions" | "analysis"
> {
  return {
    catalogSessions: async () => CATALOG,
    analysis: {
      artifactBytes: async () => {
        throw new ApiError("http", { status: 404 });
      },
      events: async () => {
        throw new ApiError("http", { status: 404 });
      },
      recipes: async () => [],
    },
  };
}

describe("панель спектрограммы записи", () => {
  let host: HTMLElement;

  beforeEach(() => {
    document.body.replaceChildren();
    host = document.createElement("div");
    document.body.append(host);
  });

  it("shows recording spectrogram copy on title, aria and empty state", async () => {
    const panel = createSpectrogramPanel({ client: missingClient() });
    host.append(panel.root);
    await Promise.resolve();

    expect(panel.root.querySelector(".lnt-chart-title")?.textContent).toBe(LABEL);
    expect(panel.root.querySelector(".lnt-spec-chart")?.getAttribute("aria-label")).toBe(LABEL);
    expect(panel.root.querySelector(".lnt-spec-status")?.textContent).toBe(LABEL);
  });

  it("does not put realtime copy in visible spectrogram UI strings", async () => {
    const panel = createSpectrogramPanel({ client: missingClient() });
    host.append(panel.root);
    await Promise.resolve();
    const copy = (panel.root.textContent ?? "").toLowerCase();
    expect(copy).not.toContain("realtime");
    expect(copy).not.toContain("реалтайм");
  });

  it("shows a not-found banner with working retry on npz 404", async () => {
    let bytesCalls = 0;
    const client = missingClient();
    const counting = {
      ...client,
      analysis: {
        ...client.analysis,
        artifactBytes: async (): Promise<ArrayBuffer> => {
          bytesCalls += 1;
          throw new ApiError("http", { status: 404 });
        },
      },
    };
    const panel = createSpectrogramPanel({ client: counting });
    host.append(panel.root);
    await Promise.resolve();
    await Promise.resolve();
    const select = panel.root.querySelector(
      'select[aria-label="Сессия спектрограммы"]',
    ) as HTMLSelectElement;
    const input = panel.root.querySelector(
      'input[aria-label="Ключ артефакта анализа"]',
    ) as HTMLInputElement;
    const build = panel.root.querySelector("button.lnt-btn") as HTMLButtonElement;
    select.value = "capture-001";
    input.value = "art-missing";
    build.click();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    const status = panel.root.querySelector(".lnt-spec-status");
    const banner = panel.root.querySelector(".lnt-spec-error:not([hidden])");
    expect(status?.textContent).toBe(LABEL);
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toMatch(/не найден/i);
    const retry = banner?.querySelector("button") as HTMLButtonElement;
    expect(retry?.textContent).toBe("Повторить");
    const before = bytesCalls;
    expect(before).toBeGreaterThan(0);
    retry.click();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(bytesCalls).toBeGreaterThan(before);
    panel.destroy();
  });

  it("keeps true aborts silent", async () => {
    const client = missingClient();
    const aborting = {
      ...client,
      analysis: {
        ...client.analysis,
        artifactBytes: async (): Promise<ArrayBuffer> => {
          const error = new Error("aborted");
          error.name = "AbortError";
          throw error;
        },
        events: async (): Promise<never> => {
          const error = new Error("aborted");
          error.name = "AbortError";
          throw error;
        },
      },
    };
    const panel = createSpectrogramPanel({ client: aborting });
    host.append(panel.root);
    await Promise.resolve();
    await Promise.resolve();
    const select = panel.root.querySelector(
      'select[aria-label="Сессия спектрограммы"]',
    ) as HTMLSelectElement;
    const input = panel.root.querySelector(
      'input[aria-label="Ключ артефакта анализа"]',
    ) as HTMLInputElement;
    const build = panel.root.querySelector("button.lnt-btn") as HTMLButtonElement;
    select.value = "capture-001";
    input.value = "art-missing";
    build.click();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(panel.root.querySelector(".lnt-spec-error:not([hidden])")).toBeNull();
    panel.destroy();
  });
});

describe("CSV-кнопки пустого состояния (U3: no-op → disabled-with-reason)", () => {
  let host: HTMLElement;

  beforeEach(() => {
    document.body.replaceChildren();
    host = document.createElement("div");
    document.body.append(host);
  });

  function csvButton(panel: { root: HTMLElement }, label: string): HTMLButtonElement {
    const found = [...panel.root.querySelectorAll("button")].find(
      (node) => node.textContent === label,
    );
    if (!(found instanceof HTMLButtonElement)) throw new Error(`кнопка «${label}» не найдена`);
    return found;
  }

  it("matrix button is disabled with a visible reason before any tile", async () => {
    const panel = createSpectrogramPanel({ client: missingClient() });
    host.append(panel.root);
    await Promise.resolve();

    const matrix = csvButton(panel, "Скачать матрицу CSV");
    expect(matrix.disabled).toBe(true);
    expect(matrix.title).toContain("спектрограмм");
    const hint = panel.root.querySelector(".lnt-spec-csv-hint");
    expect(hint?.textContent).toContain("спектрограмм");
    panel.destroy();
  });

  it("summary button is disabled with a visible reason before any tile", async () => {
    const panel = createSpectrogramPanel({ client: missingClient() });
    host.append(panel.root);
    await Promise.resolve();

    const summary = csvButton(panel, "Скачать сводку CSV");
    expect(summary.disabled).toBe(true);
    expect(summary.title).toContain("спектрограмм");
    const hint = panel.root.querySelector(".lnt-spec-csv-hint");
    expect(hint?.textContent).toContain("спектрограмм");
    panel.destroy();
  });
});

describe("каталог сессий панели спектрограммы", () => {
  let host: HTMLElement;

  beforeEach(() => {
    document.body.replaceChildren();
    host = document.createElement("div");
    document.body.append(host);
  });

  it("shows an error banner with retry when the catalog fails to load", async () => {
    const catalogSessions = async (): Promise<CatalogPage> => {
      throw new Error("offline");
    };
    const panel = createSpectrogramPanel({
      client: { ...missingClient(), catalogSessions },
    });
    host.append(panel.root);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    const banner = panel.root.querySelector(".lnt-spec-error:not([hidden])");
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain("сессий");
    expect(banner?.querySelector("button")?.textContent).toBe("Повторить");
    expect(panel.root.querySelectorAll("select option")).toHaveLength(0);
    panel.destroy();
  });

  it("retry reloads the session catalog", async () => {
    let calls = 0;
    const catalogSessions = async (): Promise<CatalogPage> => {
      calls += 1;
      if (calls === 1) throw new Error("offline");
      return CATALOG;
    };
    const panel = createSpectrogramPanel({
      client: { ...missingClient(), catalogSessions },
    });
    host.append(panel.root);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(calls).toBe(1);

    const retry = panel.root.querySelector(
      ".lnt-spec-error:not([hidden]) button",
    ) as HTMLButtonElement;
    expect(retry).toBeInstanceOf(HTMLButtonElement);
    retry.click();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(calls).toBe(2);
    const options = [...panel.root.querySelectorAll("select option")].map(
      (option) => option.textContent,
    );
    expect(options).toContain("capture-001");
    expect(panel.root.querySelector(".lnt-spec-error:not([hidden])")).toBeNull();
    panel.destroy();
  });
});
