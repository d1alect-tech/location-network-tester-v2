/** Настройка отображения измерений (задача 23, директива GATE A
 * 2026-10-18). Точка сплита: модуль ПОГЛОЩАЕТ measure-ряды —
 * buildScopeMeasureSection + ScopeMeasureView переезжают из
 * scopeSections.ts (233 чистых LOC, запас 17 — не растим) вместе с
 * фильтром видимости рядов. Состояние — localStorage lnt.live.meas.v1
 * (прецедент themePreference): JSON «только выключенные ряды», мусор =
 * все включены, неизвестные ключи игнорируются, приват-режим — в памяти.
 * Тумблеры живут РЯДОМ С РИДАУТОМ, не в меню захвата — по геометрии:
 * панель меню открывается вверх и на 1280×625 упирается в бюджет ~450 px
 * (capture-блок уже занимает его), рельс не растёт по высоте (стейдж-
 * доминирование ≥ 60% на 625). Подпись ряда dt СТАНОВИТСЯ тумблером
 * (прецедент компактных чекбоксов рельса: инверсии CH1/CH2), высота
 * панели измерений не меняется. Скрытый ряд = выключен пользователем,
 * НЕ «н/д»: недоступные значения у ВИДИМЫХ рядов остаются «—»
 * (unavailable, never fabricated), выключенные просто не рендерятся. */

import type { LiveFramePayload } from "../../api/types-live";
import { createLiveSeg } from "../../components/liveStrip/liveSeg";
import { el } from "../../components/primitives/dom";
import {
  type ScopeMeasurement,
  formatDutyValue,
  formatFrequencyValue,
  formatMeasurement,
  formatPeriodValue,
  formatVoltsValue,
  measureSeries,
} from "./scopeMeasurements";

export type MeasureRowKey = "vpp" | "vmax" | "vmin" | "rms" | "freq" | "period" | "duty";

export const MEASURE_STORAGE_KEY = "lnt.live.meas.v1";

const ROW_KEYS: readonly MeasureRowKey[] = ["vpp", "vmax", "vmin", "rms", "freq", "period", "duty"];

function isMeasureRowKey(value: unknown): value is MeasureRowKey {
  return typeof value === "string" && (ROW_KEYS as readonly string[]).includes(value);
}

export interface MeasureRowState {
  enabled(key: MeasureRowKey): boolean;
  set(key: MeasureRowKey, on: boolean): void;
  /** Подписка на изменения: секция применяет видимость и чекбоксы. */
  subscribe(listener: () => void): () => void;
}

function readDisabled(win: Window): Set<MeasureRowKey> {
  const disabled = new Set<MeasureRowKey>();
  try {
    const raw = win.localStorage.getItem(MEASURE_STORAGE_KEY);
    if (raw === null) return disabled;
    const data: unknown = JSON.parse(raw);
    if (typeof data !== "object" || data === null) return disabled;
    for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
      if (isMeasureRowKey(key) && value === false) disabled.add(key);
    }
  } catch {
    /* мусорный JSON: все ряды включены */
  }
  return disabled;
}

/** Состояние видимости рядов ридаута (lnt.live.meas.v1). */
export function createMeasureRowState(win: Window = window): MeasureRowState {
  const disabled = readDisabled(win);
  const listeners = new Set<() => void>();
  const persist = (): void => {
    try {
      if (disabled.size === 0) win.localStorage.removeItem(MEASURE_STORAGE_KEY);
      else {
        const data: Record<string, false> = {};
        for (const key of disabled) data[key] = false;
        win.localStorage.setItem(MEASURE_STORAGE_KEY, JSON.stringify(data));
      }
    } catch {
      /* приватный режим: выбор живёт в памяти */
    }
  };
  return {
    enabled: (key) => !disabled.has(key),
    set(key, on): void {
      if (on) disabled.delete(key);
      else disabled.add(key);
      persist();
      for (const listener of [...listeners]) listener();
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

interface MeasureRowDesc {
  readonly key: MeasureRowKey;
  readonly label: string;
  readonly valueKey: keyof ScopeMeasurement;
  readonly format: (value: number) => string;
}

const MEASURE_ROWS: readonly MeasureRowDesc[] = [
  { key: "vpp", label: "Vpp", valueKey: "vppV", format: formatVoltsValue },
  { key: "vmax", label: "Vmax", valueKey: "vmaxV", format: formatVoltsValue },
  { key: "vmin", label: "Vmin", valueKey: "vminV", format: formatVoltsValue },
  { key: "rms", label: "VRMS", valueKey: "rmsV", format: formatVoltsValue },
  { key: "freq", label: "f (фронт)", valueKey: "frequencyHz", format: formatFrequencyValue },
  { key: "period", label: "T", valueKey: "periodS", format: formatPeriodValue },
  { key: "duty", label: "D (высокий)", valueKey: "duty", format: formatDutyValue },
];

export interface ScopeMeasureView {
  readonly root: HTMLElement;
  readonly toggle: HTMLElement;
  applyFrame(frame: LiveFramePayload, levelV: number | null): void;
}

export function buildScopeMeasureSection(rows: MeasureRowState): ScopeMeasureView {
  const cells = new Map<MeasureRowKey, { term: HTMLElement; value: HTMLElement }>();
  const gridChildren: Node[] = [];
  for (const desc of MEASURE_ROWS) {
    const check = el("input", { attrs: { type: "checkbox", "data-measure-toggle": desc.key } });
    check.checked = rows.enabled(desc.key);
    check.addEventListener("change", () => rows.set(desc.key, check.checked));
    // Подпись ряда = его тумблер: dt > label (семантика dl жива, высота грида
    // не меняется — чекбокс внутри подписи, прецедент инверсий CH1/CH2).
    const term = el("dt", {}, [
      el("label", { className: "readout-label lnt-scope-measure-row" }, [
        check,
        el("span", { text: desc.label }),
      ]),
    ]);
    const value = el("dd", { className: `t-mono lnt-scope-${desc.key}`, text: "—" });
    cells.set(desc.key, { term, value });
    gridChildren.push(term, value);
  }
  const grid = el("dl", { className: "readout-grid" }, gridChildren);

  const applyVisibility = (): void => {
    for (const desc of MEASURE_ROWS) {
      const cell = cells.get(desc.key);
      if (cell === undefined) continue;
      const on = rows.enabled(desc.key);
      // Тумблер (подпись) остаётся доступным — выключенный ряд можно вернуть;
      // не рендерится только значение (dd), НЕ «н/д» в сетке.
      cell.value.hidden = !on;
      const check = cell.term.querySelector("input");
      if (check instanceof HTMLInputElement) check.checked = on;
    }
  };
  applyVisibility();
  rows.subscribe(applyVisibility);

  const measureSeg = createLiveSeg(
    {
      key: "measure",
      kind: "local",
      aria: "Измерения",
      options: [
        { value: "on", text: "Вкл" },
        { value: "off", text: "Выкл" },
      ],
      current: "on",
      groupAttrs: { id: "lnt-scope-measure" },
    },
    (value) => {
      grid.hidden = value === "off";
    },
  );

  return {
    root: el("section", { className: "panel lnt-scope-section lnt-scope-measure" }, [
      el("div", { className: "panel-hd" }, [
        el("h3", { className: "panel-title", text: "Измерения CH1" }),
      ]),
      el("div", { className: "panel-bd" }, [
        measureSeg.root,
        grid,
        el("p", {
          className: "t-compact",
          text: "По отсчётам кадра CH1; АЦП 8 бит — уровни сырые, без калибровочных заявлений.",
        }),
      ]),
    ]),
    toggle: measureSeg.root,
    applyFrame(frame: LiveFramePayload, levelV: number | null): void {
      const measurement = measureSeries(frame.ch1, levelV);
      for (const desc of MEASURE_ROWS) {
        const cell = cells.get(desc.key);
        if (cell === undefined) continue;
        const raw = measurement[desc.valueKey];
        cell.value.textContent = formatMeasurement(raw, desc.format);
      }
    },
  };
}
