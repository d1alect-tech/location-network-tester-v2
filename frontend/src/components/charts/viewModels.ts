/** Модели графиков (todo 41): гонко-защищённая загрузка через
 * createResourceLoader, состояния в ChartShell и рендер в ChartHandle.
 * Модели не знают о uPlot — в тестах подставляется фальшивый хэндл. */

import { ApiError } from "../../api/errors";
import { isSessionDetailPayload } from "../../api/guards-plots";
import type {
  SessionDetailPayload,
  SpectrumPayload,
  WaveformChannel,
  WaveformPayload,
} from "../../api/types-plots";
import { SPECTRUM_MAX_POINTS, WAVEFORM_MAX_POINTS } from "../../api/types-plots";
import { createResourceLoader } from "../../state/resource";
import type { ChartShellHandle } from "../primitives/chartshell";
import { filterLogSafePairs, psdToAsd } from "./series";
import type { ChartHandle, ChartPeak, ChartRenderRequest } from "./types";

export type { WaveformChannel };

export interface PlotFetchers {
  detail(name: string, options?: { signal?: AbortSignal }): Promise<SessionDetailPayload>;
  spectrum(
    name: string,
    maxPoints?: number,
    options?: { signal?: AbortSignal },
  ): Promise<SpectrumPayload>;
  waveform(
    name: string,
    channel?: WaveformChannel,
    maxPoints?: number,
    options?: { signal?: AbortSignal },
  ): Promise<WaveformPayload>;
}

export interface SeriesStyle {
  color: string;
  dash?: readonly [number, number];
  marker?: string;
  label: string;
}

export interface SpectrumUnits {
  /** Плотность мощности В²/Гц или амплитудная В/√Гц (√PSD). */
  kind: "psd" | "asd";
}

export function spectrumToRequest(
  payload: SpectrumPayload,
  style: SeriesStyle,
  units: SpectrumUnits,
  logY: boolean,
  peaks: readonly ChartPeak[],
): ChartRenderRequest {
  const psd = payload.psd_v2_per_hz;
  const yValues = units.kind === "asd" ? psdToAsd(psd) : [...psd];
  // Лог-ось Y: детерминированная очистка пар; линейная — значения как есть.
  const pairs = logY
    ? filterLogSafePairs(payload.frequency_hz, yValues)
    : { x: payload.frequency_hz, y: yValues };
  return {
    xLabel: "Частота, Гц",
    yLabel: units.kind === "asd" ? "ASD, В/√Гц" : "PSD, В²/Гц",
    xLog: true,
    yLog: logY,
    x: pairs.x,
    series: [
      {
        label: style.label,
        values: pairs.y,
        color: style.color,
        dash: style.dash,
        marker: style.marker,
      },
    ],
    peaks,
  };
}

/** Max-hold значения под ось X готового запроса: та же фильтрация, что у mean.
 * Возвращает null, когда следа нет в payload или сетка разошлась с запросом. */
export function maxHoldValuesForRequest(
  payload: SpectrumPayload,
  requestX: readonly number[],
  units: SpectrumUnits,
  logY: boolean,
): number[] | null {
  const hold = payload.psd_max_hold_v2_per_hz;
  if (hold === undefined || hold.length !== payload.frequency_hz.length) return null;
  const yValues = units.kind === "asd" ? psdToAsd(hold) : [...hold];
  const pairs = logY
    ? filterLogSafePairs(payload.frequency_hz, yValues)
    : { x: payload.frequency_hz, y: yValues };
  if (pairs.x.length !== requestX.length) return null;
  for (const [index, x] of pairs.x.entries()) {
    if (x !== requestX[index]) return null;
  }
  return pairs.y;
}

export function waveformToRequest(
  payload: WaveformPayload,
  style: SeriesStyle,
): ChartRenderRequest {
  return {
    xLabel: "Время, с",
    yLabel: "Напряжение, В",
    x: payload.time_s,
    series: [
      {
        label: style.label,
        values: payload.voltage_v,
        color: style.color,
        dash: style.dash,
        marker: style.marker,
      },
    ],
  };
}

export interface CsvTarget {
  filename: string;
  csv: string;
}

export interface ChartModel {
  load(name: string): Promise<void>;
  /** Повторный рендер последних данных (переключение шкал/единиц). */
  rerender(): void;
  currentName(): string | null;
  buildCsv(): CsvTarget | null;
}

export interface ChartModelOptions<T> {
  shell: ChartShellHandle;
  handle: ChartHandle;
  fetch: (name: string, signal: AbortSignal) => Promise<T>;
  toRequest: (payload: T) => ChartRenderRequest;
  toCsv: (payload: T) => CsvTarget | null;
}

/** Универсальная модель: загрузка → оболочка (загрузка/ошибка/готово) → график.
 * Устаревший ответ отбрасывается ресурсным загрузчиком (resource.ts). */
export function createChartModel<T>(options: ChartModelOptions<T>): ChartModel {
  let lastPayload: T | null = null;
  let lastName: string | null = null;
  const toRequest = options.toRequest;

  const loader = createResourceLoader<T>(async (name, signal) => {
    const payload = await options.fetch(name, signal);
    return payload;
  });

  loader.subscribe((state) => {
    if (state.kind === "loading") {
      options.shell.setLoading();
      return;
    }
    if (state.kind === "error") {
      options.shell.setError(state.error.message, () => void loader.retry());
      return;
    }
    if (state.kind !== "ready") return;
    lastPayload = state.value;
    lastName = state.key;
    options.shell.setContent(options.handle.root);
    options.handle.render(toRequest(state.value));
  });

  return {
    load: (name) => loader.load(name),
    rerender: () => {
      if (lastPayload !== null) options.handle.render(toRequest(lastPayload));
    },
    currentName: () => lastName,
    buildCsv: () => (lastPayload === null ? null : options.toCsv(lastPayload)),
  };
}

/** Детальный анализ сессии с проверкой конверта (malformed → typed error). */
export async function fetchDetailStrict(
  fetchers: PlotFetchers,
  name: string,
  signal?: AbortSignal,
): Promise<SessionDetailPayload> {
  const detail = await fetchers.detail(name, { signal });
  if (!isSessionDetailPayload(detail)) throw new ApiError("parse");
  return detail;
}

/** Пики спектра из analysis (metrics.json v2); отсутствуют → пусто. */
export function peaksFromDetail(detail: SessionDetailPayload | null): ChartPeak[] {
  const analysis = detail?.analysis;
  if (analysis === null || analysis === undefined) return [];
  const spectrum = analysis.spectrum;
  if (typeof spectrum !== "object" || spectrum === null) return [];
  const peaks = (spectrum as { peaks?: unknown }).peaks;
  if (!Array.isArray(peaks)) return [];
  return peaks.filter(isChartPeak);
}

function isChartPeak(value: unknown): value is ChartPeak {
  if (typeof value !== "object" || value === null) return false;
  const peak = value as Record<string, unknown>;
  return (
    typeof peak.frequency_hz === "number" &&
    typeof peak.level_db === "number" &&
    typeof peak.prominence_db === "number" &&
    typeof peak.q_factor === "number"
  );
}

export const POINT_BUDGETS = { spectrum: SPECTRUM_MAX_POINTS, waveform: WAVEFORM_MAX_POINTS };
