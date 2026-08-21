/** Сборка uPlot-workbench маршрута «Инспекция» (todo 41).
 * Связанные графики: спектр A, спектр Б (сравнение), осциллограмма CH1 —
 * общая sync-группа курсора и диапазонов X; сводка под курсором;
 * CSV-альтернатива; панель приведения ко входу из analysis. */

import type { LntApiClient } from "../../api/client";
import type { CatalogPage } from "../../api/types";
import type { SessionDetailPayload } from "../../api/types-plots";
import { createChartShell } from "../primitives/chartshell";
import { el } from "../primitives/dom";
import { createPeaksPlugin, createPeaksSummary } from "./annotations";
import { downloadCsv } from "./csvDownload";
import { createReadout } from "./readout";
import type { ReadoutHandle } from "./readout";
import { readChartTheme } from "./theme";
import { MARKER_A, MARKER_B } from "./types";
import type { ChartHandle, ChartPeak } from "./types";
import { createUplotView } from "./uplotView";
import type { UplotViewOptions } from "./uplotView";
import {
  createChartModel,
  peaksFromDetail,
  spectrumToRequest,
  waveformToRequest,
} from "./viewModels";
import type { SeriesStyle } from "./viewModels";

const SYNC_KEY = "lnt-workbench-charts";

export interface WorkbenchHandle {
  root: HTMLElement;
  /** Открыть сессию в роли A или B (тесты и клавиатурный сценарий). */
  openSession(name: string, role?: "a" | "b"): Promise<void>;
  destroy(): void;
}

export interface WorkbenchOptions {
  client: Pick<LntApiClient, "catalogSessions" | "plots">;
  /** Подмена uPlot-вью в тестах (jsdom без канвы). */
  createView?: (options: UplotViewOptions) => ChartHandle;
}

function csvOf(headers: string[], x: readonly number[], y: readonly number[]): string {
  const rows: string[] = [];
  const count = Math.min(x.length, y.length);
  for (let i = 0; i < count; i += 1) {
    const xi = x[i];
    const yi = y[i];
    if (xi !== undefined && yi !== undefined) rows.push(`${xi},${yi}`);
  }
  return [headers.join(","), ...rows].join("\n");
}

function labeled(label: string, control: HTMLElement): HTMLElement {
  return el("label", { className: "lnt-field-inline" }, [
    el("span", { className: "lnt-label-text", text: label }),
    control,
  ]);
}

function csvButton(onClick: () => void): HTMLElement {
  const button = el("button", {
    className: "lnt-btn lnt-btn-small",
    text: "Скачать CSV",
    attrs: { type: "button" },
  });
  button.addEventListener("click", onClick);
  return button;
}

function fillSessions(
  select: HTMLSelectElement,
  page: CatalogPage | null,
  placeholder: string,
): void {
  select.replaceChildren(el("option", { text: placeholder, attrs: { value: "" } }));
  if (page === null) return;
  for (const session of page.items) {
    const title = session.label === null ? session.id : `${session.id} · ${session.label}`;
    select.append(el("option", { text: title, attrs: { value: session.id } }));
  }
}

/** Панель «Приведение ко входу»: статус/причина/модель из metrics.json v2. */
function renderInputReference(host: HTMLElement, source: unknown): void {
  host.replaceChildren();
  const info =
    typeof source === "object" && source !== null ? (source as Record<string, unknown>) : null;
  if (info === null) {
    host.append(
      el("p", { className: "lnt-helper-text", text: "Приведение ко входу: нет данных анализа." }),
    );
    return;
  }
  const available = info.status === "available";
  const reason = typeof info.reason_code === "string" ? ` (${info.reason_code})` : "";
  const summary = el("p", {
    className: "lnt-input-ref-status",
    text: available
      ? `Спектр приведён ко входу · модель ${String(info.model_kind ?? "—")}`
      : `Спектр не приведён ко входу${reason}`,
  });
  const bins =
    typeof info.qualified_bin_count === "number" && typeof info.total_bin_count === "number"
      ? `Квалифицировано бинов: ${info.qualified_bin_count} из ${info.total_bin_count}`
      : "Квалификация бинов недоступна";
  host.append(summary, el("p", { className: "lnt-helper-text", text: bins }));
}

export function createChartsWorkbench(options: WorkbenchOptions): WorkbenchHandle {
  const theme = readChartTheme();
  const viewFactory = options.createView ?? createUplotView;
  const plots = options.client.plots;
  const viewState = { units: "psd" as "psd" | "asd", logY: true };
  let catalog: CatalogPage | null = null;
  const peaksCache: Record<"a" | "b", ChartPeak[]> = { a: [], b: [] };
  let lastDetailA: SessionDetailPayload | null = null;

  const styleA: SeriesStyle = {
    label: "Сессия А",
    color: theme.accentA,
    marker: MARKER_A,
  };
  const styleB: SeriesStyle = {
    label: "Сессия Б",
    color: theme.accentB,
    marker: MARKER_B,
    dash: [6, 4],
  };

  const spectrumShellA = createChartShell({ title: "Спектр мощности (А)" });
  const spectrumShellB = createChartShell({ title: "Спектр мощности (Б — сравнение)" });
  const waveformShell = createChartShell({ title: "Осциллограмма CH1" });

  const readout: ReadoutHandle = createReadout("Частота, Гц", "PSD, В²/Гц", [styleA]);

  function cursorBridge(handle: () => ChartHandle | undefined) {
    return (index: number | null): void => {
      const chart = handle();
      if (chart === undefined) return;
      const data = chart.getData();
      if (!Array.isArray(data)) return;
      const xs = data[0];
      if (index === null || !Array.isArray(xs)) {
        readout.update({ xValue: null, values: [] });
        return;
      }
      const xValue = xs[index];
      const values: (number | null)[] = [];
      for (let s = 1; s < data.length; s += 1) {
        const column = data[s];
        const value = Array.isArray(column) ? column[index] : undefined;
        values.push(typeof value === "number" ? value : null);
      }
      readout.update({
        xValue: typeof xValue === "number" ? xValue : null,
        values,
      });
    };
  }

  const handles: { a: ChartHandle | null; b: ChartHandle | null; wave: ChartHandle | null } = {
    a: null,
    b: null,
    wave: null,
  };
  handles.a = viewFactory({
    container: spectrumShellA.body,
    syncKey: SYNC_KEY,
    onCursor: cursorBridge(() => handles.a ?? undefined),
    peaksPlugin: createPeaksPlugin({ peaks: () => peaksCache.a, color: theme.accentA }),
  });
  handles.b = viewFactory({
    container: spectrumShellB.body,
    syncKey: SYNC_KEY,
    onCursor: cursorBridge(() => handles.b ?? undefined),
  });
  handles.wave = viewFactory({
    container: waveformShell.body,
    syncKey: SYNC_KEY,
    onCursor: cursorBridge(() => handles.wave ?? undefined),
  });

  const spectrumModelA = createChartModel({
    shell: spectrumShellA,
    handle: handles.a,
    fetch: (name, signal) => plots.spectrum(name, undefined, { signal }),
    toRequest: (payload) =>
      spectrumToRequest(payload, styleA, { kind: viewState.units }, viewState.logY, peaksCache.a),
    toCsv: (payload) => ({
      filename: `spectrum-a-${payload.point_count}.csv`,
      csv: csvOf(["frequency_hz", "psd_v2_per_hz"], payload.frequency_hz, payload.psd_v2_per_hz),
    }),
  });
  const spectrumModelB = createChartModel({
    shell: spectrumShellB,
    handle: handles.b,
    fetch: (name, signal) => plots.spectrum(name, undefined, { signal }),
    toRequest: (payload) =>
      spectrumToRequest(payload, styleB, { kind: viewState.units }, viewState.logY, []),
    toCsv: (payload) => ({
      filename: `spectrum-b-${payload.point_count}.csv`,
      csv: csvOf(["frequency_hz", "psd_v2_per_hz"], payload.frequency_hz, payload.psd_v2_per_hz),
    }),
  });
  const waveformModel = createChartModel({
    shell: waveformShell,
    handle: handles.wave,
    fetch: (name, signal) => plots.waveform(name, "ch1", undefined, { signal }),
    toRequest: (payload) => waveformToRequest(payload, styleA),
    toCsv: (payload) => ({
      filename: `waveform-ch1-${payload.point_count}.csv`,
      csv: csvOf(["time_s", "voltage_v"], payload.time_s, payload.voltage_v),
    }),
  });
  spectrumShellA.toolbar.append(csvButton(() => fire(spectrumModelA)));
  spectrumShellB.toolbar.append(csvButton(() => fire(spectrumModelB)));
  waveformShell.toolbar.append(csvButton(() => fire(waveformModel)));

  function fire(model: ReturnType<typeof createChartModel>): void {
    const target = model.buildCsv();
    if (target !== null) downloadCsv(target.filename, target.csv);
  }

  // --- Управление ---------------------------------------------------------
  const selectA = el("select", { className: "lnt-select", attrs: { "aria-label": "Сессия А" } });
  const selectB = el("select", {
    className: "lnt-select",
    attrs: { "aria-label": "Сессия Б для сравнения" },
  });
  fillSessions(selectA, null, "Выберите сессию А");
  fillSessions(selectB, null, "Выберите сессию Б");
  const unitSelect = el("select", {
    className: "lnt-select",
    attrs: { "aria-label": "Единицы спектра" },
  });
  for (const [value, text] of [
    ["psd", "PSD, В²/Гц"],
    ["asd", "ASD, В/√Гц"],
  ] as const) {
    const option = el("option", { text, attrs: { value } });
    if (value === "psd") option.selected = true;
    unitSelect.append(option);
  }
  const logToggle = el("input", {
    className: "lnt-checkbox",
    attrs: { type: "checkbox", id: "charts-log-y" },
  });
  logToggle.checked = true;

  const controls = el("div", { className: "lnt-workbench-controls" }, [
    labeled("Сессия А", selectA),
    labeled("Сессия Б", selectB),
    labeled("Единицы", unitSelect),
    labeled("Лог Y", logToggle),
  ]);

  const peaksSummaryHost = el("div", { className: "lnt-peaks-host" });
  const inputRefPanel = el("div", { className: "lnt-input-ref" });
  const root = el("div", { className: "lnt-workbench" }, [
    controls,
    inputRefPanel,
    spectrumShellA.root,
    peaksSummaryHost,
    readout.root,
    spectrumShellB.root,
    waveformShell.root,
  ]);
  spectrumShellB.setEmpty("Для сравнения выберите сессию Б");
  waveformShell.setEmpty("Выберите сессию, чтобы построить осциллограмму");

  async function openDetail(role: "a" | "b", name: string): Promise<void> {
    try {
      const detail = await plots.detail(name);
      peaksCache[role] = peaksFromDetail(detail);
      if (role === "a") {
        lastDetailA = detail;
        renderInputReference(inputRefPanel, detail.analysis?.ch1_input_reference);
        peaksSummaryHost.replaceChildren(createPeaksSummary(peaksCache.a));
      }
    } catch {
      peaksCache[role] = [];
    }
  }

  const workbench: WorkbenchHandle = {
    root,
    openSession: async (name, role = "a") => {
      if (name === "") return;
      await openDetail(role, name);
      if (role === "a") {
        await spectrumModelA.load(name);
        if (lastDetailA?.waveform_available === true) await waveformModel.load(name);
        readout.setSeries([styleA]);
      } else {
        await spectrumModelB.load(name);
        readout.setSeries([styleA, styleB]);
      }
    },
    destroy: () => {
      handles.a?.destroy();
      handles.b?.destroy();
      handles.wave?.destroy();
    },
  };

  selectA.addEventListener("change", () => void workbench.openSession(selectA.value, "a"));
  selectB.addEventListener("change", () => void workbench.openSession(selectB.value, "b"));
  unitSelect.addEventListener("change", () => {
    viewState.units = unitSelect.value === "asd" ? "asd" : "psd";
    spectrumModelA.rerender();
    spectrumModelB.rerender();
  });
  logToggle.addEventListener("change", () => {
    viewState.logY = logToggle.checked;
    spectrumModelA.rerender();
    spectrumModelB.rerender();
  });

  void options.client
    .catalogSessions()
    .then((page) => {
      catalog = page;
      fillSessions(selectA, catalog, "Выберите сессию А");
      fillSessions(selectB, catalog, "Выберите сессию Б");
    })
    .catch(() => {
      /* Каталог недоступен: селекты остаются с подсказкой выбора. */
    });

  return workbench;
}
