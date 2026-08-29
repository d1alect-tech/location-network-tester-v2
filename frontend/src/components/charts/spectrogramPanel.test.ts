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

  it("keeps empty state on npz 404 instead of crashing into an error banner", async () => {
    const panel = createSpectrogramPanel({ client: missingClient() });
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

    const status = panel.root.querySelector(".lnt-spec-status");
    const banner = panel.root.querySelector(".lnt-spec-error");
    expect(status?.textContent).toBe(LABEL);
    expect(banner?.hasAttribute("hidden")).toBe(true);
  });
});
