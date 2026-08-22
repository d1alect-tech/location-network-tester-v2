/** Подготовка данных и UI-примитивы панели спектрограммы (todo 42):
 * разбор NPZ в уровень, политика стартового тайла (наибольшее окно
 * в пределах капа 524000 ячеек) и мелкие фабрики контролов. */

import { el } from "../primitives/dom";
import { TILE_CELL_CAP } from "./spectrogramModel";
import type { SpectrogramLevel, TileRequest } from "./spectrogramModel";
import { TileError } from "./tileError";

/** Разбор массивов NPZ-артефакта в уровень: power_db формы (полосы, время). */
export function levelFromNpz(arrays: Map<string, { data: ArrayBuffer }>): SpectrogramLevel {
  const timeS = new Float64Array(arrays.get("time_s")?.data ?? new ArrayBuffer(0));
  const frequencyHz = new Float64Array(arrays.get("frequency_hz")?.data ?? new ArrayBuffer(0));
  const powerDb = new Float32Array(arrays.get("power_db")?.data ?? new ArrayBuffer(0));
  return { timeS, frequencyHz, powerDb, timeBins: timeS.length, bands: frequencyHz.length };
}

/** Стартовый тайл: весь уровень при ≤ капа, иначе все времена × доступные полосы.
 * Обзор 2048×1024 (~2 млн ячеек) целиком не рендерится никогда. */
export function initialTileRequest(level: SpectrogramLevel): TileRequest {
  if (level.timeBins === 0 || level.bands === 0) throw new TileError("empty_window");
  const bands =
    level.timeBins * level.bands <= TILE_CELL_CAP
      ? level.bands
      : Math.max(1, Math.floor(TILE_CELL_CAP / level.timeBins));
  const f1 = Math.min(bands, level.bands);
  return {
    key: `t0-${level.timeBins}xf0-${f1}`,
    window: { t0: 0, t1: level.timeBins, f0: 0, f1 },
    cells: level.timeBins * f1,
  };
}

export function fillSessions(
  select: HTMLSelectElement,
  items: readonly { id: string }[],
  placeholder: string,
): void {
  select.replaceChildren(el("option", { text: placeholder, attrs: { value: "" } }));
  for (const item of items) {
    select.append(el("option", { text: item.id, attrs: { value: item.id } }));
  }
}

export function numberInput(label: string): HTMLInputElement {
  return el("input", {
    className: "lnt-input",
    attrs: { type: "number", step: "any", "aria-label": label },
  }) as HTMLInputElement;
}

export function labeledField(label: string, control: HTMLElement): HTMLElement {
  return el("label", { className: "lnt-field-inline" }, [
    el("span", { className: "lnt-label-text", text: label }),
    control,
  ]);
}

/** Индексы (в глобальном массиве) событий, чьи пики попадают в окно тайла. */
export function visibleMarkerIndices(
  level: SpectrogramLevel | null,
  events: readonly { peak_time_s: number }[],
  request: TileRequest,
): number[] {
  if (level === null || level.timeBins === 0) return [];
  const start = level.timeS[request.window.t0] as number;
  const end = level.timeS[Math.max(0, request.window.t1 - 1)] as number;
  const ids: number[] = [];
  for (const [index, event] of events.entries()) {
    if (event.peak_time_s >= start && event.peak_time_s <= end) ids.push(index);
  }
  return ids;
}
