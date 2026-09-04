/** T12: три мелкие фичи, каждая своим RED→GREEN.
 * (1) warn/info-баннеры захвата/каталога на тонах T10;
 * (2) pairbar A/B/A условий эксперимента;
 * (3) кнопка .md-экспорта отчёта (задел previewBlock .md-блок).
 * Классы строго V6-kit; селекторы существующих спек не трогаем
 * (только читаем их через новые атрибуты/тоны). */

import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "./api/client";
import type { JobSnapshot } from "./api/types-jobs";
import { createCaptureView } from "./capture/captureView";
import { RouteStore } from "./state/routeState";
import { createComparisonViewFixtures } from "./t12Helpers";
import { renderErrorBanner } from "./views/catalog/catalogListRows";
import { ComparisonView } from "./views/experiments/comparisonView";
import { buildReportFilename, downloadMarkdown } from "./views/reports/reportExport";
import { mountReportsWorkspace } from "./views/reports/reportsWorkspace";

function runningSnapshot(): JobSnapshot {
  return {
    schema_version: 1,
    version: 9,
    job_id: "job-t12",
    kind: "capture",
    status: "running",
    stage: "simulating",
    series_index: 1,
    series_total: 1,
    written_sessions: [],
    result: null,
    error_code: null,
    error_message: null,
  } as unknown as JobSnapshot;
}

function busyCaptureClient(): LntApiClient {
  const snapshot = runningSnapshot();
  return {
    bootstrap: async () => undefined,
    currentNonce: "t12-nonce",
    jobs: {
      list: async () => ({ items: [] }),
      start: async () => snapshot,
      get: async () => snapshot,
    },
  } as unknown as LntApiClient;
}

function startButtonOf(root: HTMLElement): HTMLButtonElement {
  const button = [...root.querySelectorAll("button")].find(
    (node) => node.textContent === "Запустить запись",
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error("нет кнопки «Запустить запись»");
  return button;
}

describe("T12.1: warn/info-баннеры захвата и каталога", () => {
  it("занятый захват — warn-полоса .banner-warn (текст и .capture-alert пинятся)", async () => {
    // Given: задача уже выполняется (первый старт ушёл в running)
    const realEventSource = (globalThis as Record<string, unknown>).EventSource;
    (globalThis as Record<string, unknown>).EventSource = class {
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      addEventListener(): void {}
      close(): void {}
    };
    const view = createCaptureView(busyCaptureClient());
    try {
      const start = startButtonOf(view.root);
      start.click();
      await vi.waitFor(() => {
        expect(view.root.querySelector(".capture-timeline")?.textContent).toContain("выполняется");
      });

      // When: повторный старт при активной задаче
      start.click();
      await vi.waitFor(() => {
        expect(view.root.querySelector(".capture-alert")?.textContent).toContain(
          "Задача ещё выполняется",
        );
      });

      // Then: тот же алёрт, но warn-тон T10 (не err), роль status
      const alert = view.root.querySelector(".capture-alert");
      expect(alert?.classList.contains("banner-warn")).toBe(true);
      expect(alert?.classList.contains("banner-err")).toBe(false);
      expect(alert?.getAttribute("role")).toBe("status");
    } finally {
      view.dispose();
      view.root.remove();
      (globalThis as Record<string, unknown>).EventSource = realEventSource;
    }
  });

  it("каталог: warn-баннер — .banner-inline.banner-warn с ролью status", () => {
    // Given / When
    const banner = renderErrorBanner("Конфликт ревизий.", () => undefined, "warn");

    // Then: тон-предупреждение T10, текст и глиф не только цветом
    expect(banner.classList.contains("banner")).toBe(true);
    expect(banner.classList.contains("banner-inline")).toBe(true);
    expect(banner.classList.contains("banner-warn")).toBe(true);
    expect(banner.classList.contains("is-warn")).toBe(false);
    expect(banner.getAttribute("role")).toBe("status");
    expect(banner.textContent).toContain("Конфликт ревизий.");
  });

  it("каталог: info-баннер — .banner-inline.banner-info с ролью status", () => {
    // Given / When
    const banner = renderErrorBanner("Список обновлён.", () => undefined, "info");

    // Then: тон-подсказка T10 на акценте
    expect(banner.classList.contains("banner-inline")).toBe(true);
    expect(banner.classList.contains("banner-info")).toBe(true);
    expect(banner.classList.contains("is-info")).toBe(false);
    expect(banner.getAttribute("role")).toBe("status");
    expect(banner.textContent).toContain("Список обновлён.");
  });

  it("каталог: пин — ошибка по умолчанию без тона, роль alert (селектор спек цел)", () => {
    // Given / When
    const banner = renderErrorBanner("Ошибка загрузки.", () => undefined);

    // Then: существующий контракт ошибки не меняется
    expect(banner.classList.contains("banner")).toBe(true);
    expect(banner.classList.contains("banner-inline")).toBe(true);
    expect(banner.classList.contains("lnt-cat-error")).toBe(true);
    expect(banner.getAttribute("role")).toBe("alert");
  });
});

describe("T12.2: pairbar A/B/A условий эксперимента", () => {
  it("A/B/A — три слота А/Б/А2 с условиями, N и дельтой", () => {
    // Given: эксперимент A/B/A с включёнными участниками
    const view = new ComparisonView({ client: {} as LntApiClient, valueSource: async () => null });
    const { detail, rows } = createComparisonViewFixtures("aba");

    // When
    view.setContext(detail, rows);

    // Then: полоса пары — по условиям в порядке шагов протокола
    const pairbar = view.root.querySelector(".pairbar");
    expect(pairbar).not.toBeNull();
    const slots = pairbar?.querySelectorAll(".pair-slot") ?? [];
    expect(slots).toHaveLength(3);
    expect(slots[0]?.querySelector(".pair-role")?.textContent).toBe("A");
    expect(slots[1]?.querySelector(".pair-role")?.textContent).toBe("Б");
    expect(slots[2]?.querySelector(".pair-role")?.textContent).toBe("A2");
    expect(slots[0]?.querySelector(".pair-name")?.textContent).toBe("cond_a1");
    expect(slots[0]?.getAttribute("data-condition")).toBe("cond_a1");
    expect(slots[0]?.querySelector(".pair-meta")?.textContent).toContain("N=");
    expect(pairbar?.querySelector(".pair-delta")).not.toBeNull();
    expect(pairbar?.getAttribute("aria-label")).toContain("A/B/A");
    view.root.remove();
  });

  it("A/B — два слота А/Б, исключённые не входят в N", () => {
    // Given
    const view = new ComparisonView({ client: {} as LntApiClient, valueSource: async () => null });
    const { detail, rows } = createComparisonViewFixtures("ab");

    // When
    view.setContext(detail, rows);

    // Then
    const slots = view.root.querySelectorAll(".pairbar .pair-slot");
    expect(slots).toHaveLength(2);
    expect(slots[0]?.getAttribute("data-condition")).toBe("cond_a");
    expect(slots[1]?.getAttribute("data-condition")).toBe("cond_b");
    // В cond_b двое включены (исключённый не считается)
    expect(slots[1]?.querySelector(".pair-meta")?.textContent).toBe("N=2");
    view.root.remove();
  });
});

describe("T12.3: кнопка .md-экспорта отчёта", () => {
  it("имя файла выгрузки — report-<id>.md, мусор из id вычищен", () => {
    expect(buildReportFilename("exp.aba.demo")).toBe("report-exp.aba.demo.md");
    expect(buildReportFilename("exp/with space|pipe")).toBe("report-exp-with-space-pipe.md");
  });

  it("downloadMarkdown кладёт тот же markdown в <a download> и объявляет", () => {
    // Given
    const created = URL.createObjectURL;
    const revoked: string[] = [];
    const clicked: string[] = [];
    URL.createObjectURL = () => "blob:t12";
    URL.revokeObjectURL = (url: string) => {
      revoked.push(url);
    };
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this.getAttribute("download") ?? "");
    });
    try {
      // When
      downloadMarkdown("# Отчёт", "report-exp.aba.demo.md");

      // Then
      expect(clicked).toEqual(["report-exp.aba.demo.md"]);
      expect(revoked).toEqual(["blob:t12"]);
    } finally {
      URL.createObjectURL = created;
      clickSpy.mockRestore();
    }
  });

  it("кнопка выгрузки — V6-kit, disabled до сборки, формат помечен", async () => {
    // Given: один эксперимент в списке
    const host = document.createElement("div");
    const routes = new RouteStore();
    const experiment = {
      experiment_id: "exp.t12",
      title: "T12",
      protocol: { kind: "aba" },
    };
    const client = {
      ensureReady: async () => undefined,
      research: {
        experiments: async () => ({ items: [experiment] }),
        experiment: async () => experiment,
        members: async () => ({ items: [] }),
        steps: async () => ({ items: [] }),
      },
    } as unknown as LntApiClient;
    const dispose = mountReportsWorkspace(host, { client, routes });
    try {
      await vi.waitFor(() => {
        expect(host.querySelector(".lnt-exp-open")).not.toBeNull();
      });
      (host.querySelector(".lnt-exp-open") as HTMLButtonElement).click();
      await vi.waitFor(() => {
        expect(host.querySelector("#lnt-rep-download")).not.toBeNull();
      });
      // Then: пин #lnt-rep-download цел, кнопка выключена до сборки
      const download = host.querySelector("#lnt-rep-download");
      expect(download).not.toBeNull();
      expect(download?.getAttribute("data-export-format")).toBe("md");
      expect((download as HTMLButtonElement).disabled).toBe(true);
      expect(download?.classList.contains("btn")).toBe(true);
    } finally {
      dispose();
      routes.dispose();
      host.remove();
    }
  });
});
