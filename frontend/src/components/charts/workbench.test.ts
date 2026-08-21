/** Тесты сборки workbench (todo 41): русские метки, каталог в селектах,
 * стили A/B на рендер-запросах, сводка пиков, CSV-кнопки (jsdom, без канвы). */

import { beforeEach, describe, expect, it } from "vitest";
import type { LntApiClient } from "../../api/client";
import type { CatalogPage } from "../../api/types";
import type { ChartHandle, ChartRenderRequest } from "./types";
import type { UplotViewOptions } from "./uplotView";
import { createChartsWorkbench } from "./workbench";

const CATALOG: CatalogPage = {
  items: [
    {
      id: "capture-001",
      health: "ok",
      created_utc: "2026-08-01T10:00:00Z",
      source: null,
      session_type: "capture",
      profile: "bad",
      label: "стенд-А",
      storage_path: null,
    },
    {
      id: "capture-002",
      health: "ok",
      created_utc: "2026-08-02T10:00:00Z",
      source: null,
      session_type: "capture",
      profile: "quiet",
      label: null,
      storage_path: null,
    },
  ],
  next_cursor: null,
};

const DETAIL = {
  name: "capture-001",
  manifest: {},
  analysis: {
    spectrum: {
      peaks: [{ frequency_hz: 22_400, level_db: -20.5, prominence_db: 12.3, q_factor: 8.1 }],
    },
    ch1_input_reference: { status: "unavailable", reason_code: "manifest_schema_v1" },
  },
  spectrum_available: true,
  waveform_available: true,
  ch2_available: false,
};

const SPECTRUM = {
  frequency_hz: [100, 1000, 10_000],
  psd_v2_per_hz: [1e-4, 1e-2, 1e-6],
  point_count: 3,
};

const WAVEFORM = {
  channel: "ch1" as const,
  time_s: [0, 0.5, 1],
  voltage_v: [0.1, -0.2, 0.3],
  point_count: 3,
};

interface FakeView extends ChartHandle {
  options: UplotViewOptions;
  renders: unknown[];
}

function makeFakeViewFactory() {
  const views: FakeView[] = [];
  const factory = (viewOptions: UplotViewOptions): ChartHandle => {
    const root = document.createElement("div");
    root.className = `fake-view-${views.length}`;
    viewOptions.container.append(root);
    const handle: FakeView = {
      options: viewOptions,
      root,
      renders: [],
      render(request) {
        this.renders.push(request);
      },
      applyTheme() {},
      getData: () => null,
      destroy() {},
    };
    views.push(handle);
    return handle;
  };
  return { factory, views };
}

function makeClient(
  plotOverrides: Partial<LntApiClient["plots"]> = {},
): Pick<LntApiClient, "catalogSessions" | "plots"> {
  const base = {
    detail: async () => DETAIL,
    spectrum: async (_name: string, _maxPoints?: number) => SPECTRUM,
    waveform: async () => WAVEFORM,
  };
  return {
    catalogSessions: async () => CATALOG,
    plots: { ...base, ...plotOverrides } as LntApiClient["plots"],
  };
}

describe("createChartsWorkbench", () => {
  let host: HTMLElement;

  beforeEach(() => {
    document.body.textContent = "";
    host = document.createElement("div");
    document.body.append(host);
  });

  function setup(client = makeClient()) {
    const { factory, views } = makeFakeViewFactory();
    const workbench = createChartsWorkbench({ client, createView: factory });
    host.append(workbench.root);
    return { views, workbench };
  }

  it("монтируется с русскими метками и тремя оболочками графиков", () => {
    setup();
    expect(host.textContent).toContain("Спектр мощности (А)");
    expect(host.textContent).toContain("Спектр мощности (Б — сравнение)");
    expect(host.textContent).toContain("Осциллограмма CH1");
    expect(host.textContent).toContain("Значение под курсором");
    const selects = [...host.querySelectorAll("select")];
    expect(selects.length).toBeGreaterThanOrEqual(3);
  });

  it("наполняет селекты из каталога сессий", async () => {
    setup();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    const selectA = host.querySelector<HTMLSelectElement>('select[aria-label="Сессия А"]');
    expect(selectA?.options.length).toBe(3);
    expect(selectA?.options[1]?.textContent).toBe("capture-001 · стенд-А");
  });

  it("открытие сессии A рендерит спектр, осциллограмму и сводку пиков", async () => {
    const { views, workbench } = setup();
    await workbench.openSession("capture-001", "a");
    // views[0] спектр A, views[1] спектр B (пусто), views[2] осциллограмма.
    const spectrumA = views[0] as FakeView;
    expect(spectrumA.renders.length).toBeGreaterThan(0);
    const last = spectrumA.renders.at(-1) as ChartRenderRequest;
    expect(last.x).toEqual(SPECTRUM.frequency_hz);
    expect(last.series[0]?.color).toBeTypeOf("string");
    expect(host.textContent).toContain("Аннотации спектра: 1 пик(ов)");
    expect(host.textContent).toContain("22400".replace("000", " тыс.") === "" ? "" : "22\u00a0400");
  });

  it("стиль Б — янтарный пунктирный ряд с квадратом при сравнении", async () => {
    const { views, workbench } = setup();
    await workbench.openSession("capture-001", "a");
    await workbench.openSession("capture-002", "b");
    const spectrumB = views[1] as FakeView;
    const request = spectrumB.renders.at(-1) as ChartRenderRequest;
    expect(request.series[0]?.dash).toEqual([6, 4]);
    expect(request.series[0]?.marker).toBe("■");
    const amberApplied = /#ffb000|#b25e00/.test(String(request.series[0]?.color));
    expect(amberApplied).toBe(true);
  });

  it("панель приведения ко входу показывает причину недоступности", async () => {
    const { workbench } = setup();
    await workbench.openSession("capture-001", "a");
    expect(host.textContent).toContain("не приведён ко входу");
    expect(host.textContent).toContain("manifest_schema_v1");
  });

  it("CSV-кнопка формирует файл из текущих данных", async () => {
    const urls: string[] = [];
    URL.createObjectURL = (blob: Blob): string => {
      expect(blob.size).toBeGreaterThan(0);
      urls.push(`blob:${urls.length}`);
      return urls[urls.length - 1] ?? "blob:0";
    };
    URL.revokeObjectURL = () => undefined;
    HTMLAnchorElement.prototype.click = () => undefined;
    const { workbench } = setup();
    await workbench.openSession("capture-001", "a");
    await workbench.openSession("capture-002", "b");
    const buttons = [...host.querySelectorAll("button")].filter((b) =>
      b.textContent?.includes("CSV"),
    );
    expect(buttons.length).toBe(3);
    for (const button of buttons) button.click();
    expect(urls.length).toBe(3);
  });

  it("ошибка загрузки спектра показывает состояние ошибки, не пустую канву", async () => {
    const client = makeClient({
      spectrum: async () => {
        throw new Error("сеть недоступна");
      },
    });
    const { views, workbench } = setup(client);
    await workbench.openSession("capture-001", "a");
    expect(host.querySelector(".lnt-chart-error")).not.toBeNull();
    expect(host.textContent).toContain("Ошибка загрузки");
    expect((views[0] as FakeView).renders.length).toBe(0);
  });
});
