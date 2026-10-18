/** Программный ФНЧ полосы пропускания перед отрисовкой (задача 24,
 * директива GATE A 2026-10-18): режимы Полная / ~5 МГц / ~1 МГц —
 * клиентская фильтрация payload-кадра (бэкенд не трогается, кадр уже
 * несёт сэмплы). Механика: окно-ящик длины L = round(fs/эфф_частота /
 * срез) со скользящим средним + прореживание шагом L/2 (≥ 2 точки на
 * период среза — без алиасных биений). Аналитика: DC-усиление окна
 * равно 1 (среднее констант не меняется); усиление синуса f —
 * |sin(π·f·L/fs) / (L·sin(π·f/fs))|; первый спектральный нуль на
 * fs/L ≈ срезу. Эффективная частота сэмплов считается по медианному
 * шагу time_s (payload прорежен сервером — sample_rate_hz здесь не
 * источник истины); fs ≤ среза — нечего фильтровать, кадр проходит
 * как есть (те же ссылки, ноль аллокаций). Фильтр — ОТОБРАЖЕНИЕ:
 * измерения (Vpp/RMS/частота) считаются по НЕфильтрованным отсчётам
 * (математика measureSeries не меняется), point_count ряда
 * переписывается под отображаемый ряд, метаданные кадра — нет.
 * ПОДПИСЬ ЧЕСТНОСТИ (рядом с тумблером и в ярлыке состояния):
 * «программный фильтр, не аналоговый предел» — Hantek 6022API
 * programmable analog BW не имеет (проверено: src/lnt/scope_io.py);
 * «предел полосы 20 МГц» и обещания железа НЕ пишутся никогда. */

import type { LiveChannelSeries, LiveFramePayload } from "../../api/types-live";
import { el } from "../../components/primitives/dom";

export type BwFilterMode = "full" | "5mhz" | "1mhz";

/** Обязательная подпись честности (тумблер + ярлык состояния). */
export const BW_FILTER_HINT = "программный фильтр, не аналоговый предел";

export const BW_MODE_TEXT: Record<BwFilterMode, string> = {
  full: "Полная",
  "5mhz": "~5 МГц",
  "1mhz": "~1 МГц",
};

const MODE_CUTOFF_HZ: Record<Exclude<BwFilterMode, "full">, number> = {
  "5mhz": 5_000_000,
  "1mhz": 1_000_000,
};

export interface FilteredSeries {
  readonly timeS: readonly number[];
  readonly voltageV: readonly number[];
}

/** Эффективная частота сэмплов ряда: 1 / медианный шаг time_s.
 *  Неконечные и неположительные шаги пропускаются; < 2 точек — 0. */
export function effectiveSampleRateHz(timeS: readonly number[]): number {
  if (timeS.length < 2) return 0;
  const steps: number[] = [];
  for (let i = 1; i < timeS.length; i += 1) {
    const step = (timeS[i] as number) - (timeS[i - 1] as number);
    if (Number.isFinite(step) && step > 0) steps.push(step);
  }
  if (steps.length === 0) return 0;
  steps.sort((a, b) => a - b);
  return 1 / (steps[steps.length >> 1] as number);
}

/** Окно усреднения: round(fs/срез); 1 = фильтровать нечего. */
function smoothingWindow(timeS: readonly number[], cutoffHz: number): number {
  const fs = effectiveSampleRateHz(timeS);
  if (fs <= 0 || cutoffHz <= 0) return 1;
  return Math.max(1, Math.round(fs / cutoffHz));
}

/** Сглаживание окном-ящиком + прореживание шагом L/2. Выход содержит
 *  только ПОЛНЫЕ окна (первый индекс L-1, последний сэмпл — хвост);
 *  окно ≤ 1 или ряд короче окна — вход теми же ссылками (no-op).
 *  Входы не мутируются; неконечные значения окна дают NaN на выходе
 *  (выравнивание рядов отбросит их, как в prepareAligned). */
export function filterSeries(
  timeS: readonly number[],
  voltageV: readonly number[],
  cutoffHz: number,
): FilteredSeries {
  const count = Math.min(timeS.length, voltageV.length);
  const window = smoothingWindow(timeS, cutoffHz);
  if (count < 2 || window <= 1 || count <= window) {
    return { timeS, voltageV };
  }
  const stride = Math.max(1, window >> 1);
  const first = window - 1;
  const indices: number[] = [];
  for (let i = first; i < count; i += stride) indices.push(i);
  if ((indices.at(-1) as number) !== count - 1) indices.push(count - 1);
  const outTime: number[] = [];
  const outVolts: number[] = [];
  for (const index of indices) {
    let sum = 0;
    for (let k = index - window + 1; k <= index; k += 1) sum += voltageV[k] as number;
    outTime.push(timeS[index] as number);
    outVolts.push(sum / window);
  }
  return { timeS: outTime, voltageV: outVolts };
}

function filteredSeries(source: LiveChannelSeries, filtered: FilteredSeries): LiveChannelSeries {
  if (filtered.timeS === source.time_s) return source;
  return {
    ...source,
    time_s: [...filtered.timeS],
    voltage_v: [...filtered.voltageV],
    point_count: filtered.timeS.length,
  };
}

/** Фильтр кадра для ОТОБРАЖЕНИЯ: новый объект кадра с фильтрованными
 *  рядами; метаданные захвата (sample_rate_hz, frame_samples…) не
 *  переписываются. full или fs ≤ среза — тот же кадр без аллокаций. */
export function filterLiveFrame(frame: LiveFramePayload, mode: BwFilterMode): LiveFramePayload {
  if (mode === "full") return frame;
  const cutoff = MODE_CUTOFF_HZ[mode];
  const ch1 = filterSeries(frame.ch1.time_s, frame.ch1.voltage_v, cutoff);
  const ch2 = filterSeries(frame.ch2.time_s, frame.ch2.voltage_v, cutoff);
  if (ch1.timeS === frame.ch1.time_s && ch2.timeS === frame.ch2.time_s) return frame;
  return { ...frame, ch1: filteredSeries(frame.ch1, ch1), ch2: filteredSeries(frame.ch2, ch2) };
}

export interface BwMenuSectionOptions {
  readonly current: BwFilterMode;
  readonly onPick: (mode: BwFilterMode) => void;
}

const BW_MENU_OPTIONS: ReadonlyArray<{ readonly value: BwFilterMode; readonly text: string }> = [
  { value: "full", text: BW_MODE_TEXT.full },
  { value: "5mhz", text: BW_MODE_TEXT["5mhz"] },
  { value: "1mhz", text: BW_MODE_TEXT["1mhz"] },
];

/** Секция «Полоса» меню захвата: три опции (та же ария-грамматика
 *  aria-pressed, что у capture-рядов) + подпись честности. Локальный
 *  контрол отображения — не поле полосы, манифест не растёт. */
export function buildBwFilterMenuSection(options: BwMenuSectionOptions): HTMLElement {
  let current = options.current;
  const buttons = new Map<BwFilterMode, HTMLButtonElement>();
  for (const option of BW_MENU_OPTIONS) {
    const node = el("button", {
      className: "lnt-live-capture-opt",
      text: option.text,
      attrs: {
        type: "button",
        "data-menu-bw": option.value,
        "aria-pressed": String(option.value === current),
      },
    });
    node.addEventListener("click", () => {
      if (current === option.value) return;
      current = option.value;
      for (const [value, button] of buttons) {
        button.setAttribute("aria-pressed", String(value === current));
      }
      options.onPick(option.value);
    });
    buttons.set(option.value, node);
  }
  return el("div", { className: "lnt-live-capture-group", attrs: { "data-menu-section": "bw" } }, [
    el("span", { className: "lnt-live-capture-hd", text: "Полоса (отображение)" }),
    el(
      "div",
      { className: "lnt-live-capture-row", attrs: { role: "group", "aria-label": "Полоса" } },
      [el("span", { className: "lnt-live-capture-row-label", text: "ФНЧ" }), ...buttons.values()],
    ),
    el("p", {
      className: "t-compact lnt-live-capture-hint",
      text: `~5 МГц / ~1 МГц — ${BW_FILTER_HINT}; измерения — по нефильтрованным отсчётам.`,
    }),
  ]);
}
