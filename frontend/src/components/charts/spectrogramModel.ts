/** Модель ограниченной спектрограммы (todo 42): кап ячеек 524000 из бенча
 * (frontend/bench/DECISION.md), точные запросы тайлов по границам окна,
 * гонко-защита поколение+Abort (паттерн src/state/resource.ts), матрица CSV
 * и сводка видимого окна. Обзор 2048×1024 никогда не отображается целиком. */

import { TileError } from "./tileError";

/** Зафиксированный бенчем кап ячеек вьюпорта (commit 1d97229). */
export const TILE_CELL_CAP = 524_000;

export interface SpectrogramLevel {
  timeS: Float64Array;
  frequencyHz: Float64Array;
  powerDb: Float32Array;
  timeBins: number;
  bands: number;
}

export interface TileWindow {
  /** Полуоткрытые границы по ячейкам [t0,t1)×[f0,f1). */
  t0: number;
  t1: number;
  f0: number;
  f1: number;
}

export interface TileRequest {
  key: string;
  window: TileWindow;
  cells: number;
}

export interface BandSummary {
  hz: number;
  db: number;
}

export interface WindowSummary {
  tStartS: number;
  tEndS: number;
  fLowHz: number;
  fHighHz: number;
  cells: number;
  minDb: number;
  maxDb: number;
  meanDb: number;
  nanShare: number;
  eventCount: number;
  topBands: readonly BandSummary[];
}

/** Значение ячейки уровня; NaN — явное отсутствие покрытия. */
export function levelValueAt(level: SpectrogramLevel, t: number, f: number): number {
  return level.powerDb[f * level.timeBins + t] as number;
}

/** Кап проверяется ДО любой отрисовки: хранимый обзор больше капа целиком
 * не рендерится — только тайл в пределах капа. */
export function assertLevelWithinCap(level: SpectrogramLevel): void {
  const cells = level.timeBins * level.bands;
  if (cells > TILE_CELL_CAP) {
    throw new TileError("tile_too_large", { detail: `(запрошено ${cells})` });
  }
}

function lowerIndex(values: Float64Array, value: number): number {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if ((values[mid] as number) < value) low = mid + 1;
    else high = mid;
  }
  return low;
}

function finalizeRequest(window: TileWindow): TileRequest {
  const cells = (window.t1 - window.t0) * (window.f1 - window.f0);
  if (cells > TILE_CELL_CAP) {
    throw new TileError("tile_too_large", { detail: `(запрошено ${cells})` });
  }
  if (cells <= 0) throw new TileError("empty_window");
  return { key: `t${window.t0}-${window.t1}xf${window.f0}-${window.f1}`, window, cells };
}

/** Точный запрос тайла: окно значений → целочисленные границы ячеек.
 * Границы полуоткрытые, клампятся в размер уровня; ключ канонический.
 * Окно вне уровня (начало за последним бином) — явная empty_window. */
export function tileRequestForRange(
  level: SpectrogramLevel,
  tStartS: number,
  tEndS: number,
  fLowHz: number,
  fHighHz: number,
): TileRequest {
  const clamp = (index: number, size: number): number => Math.min(Math.max(0, index), size);
  const t0 = clamp(lowerIndex(level.timeS, tStartS), level.timeBins);
  const f0 = clamp(lowerIndex(level.frequencyHz, fLowHz), level.bands);
  if (t0 >= level.timeBins || f0 >= level.bands) throw new TileError("empty_window");
  return finalizeRequest({
    t0,
    t1: Math.max(
      Math.min(clamp(lowerIndex(level.timeS, tEndS), level.timeBins), level.timeBins),
      t0 + 1,
    ),
    f0,
    f1: Math.max(
      Math.min(clamp(lowerIndex(level.frequencyHz, fHighHz), level.bands), level.bands),
      f0 + 1,
    ),
  });
}

/** Полный уровень как стартовый тайл (сервер уже выбрал размер пирамиды). */
export function fullLevelRequest(level: SpectrogramLevel): TileRequest {
  return finalizeRequest({ t0: 0, t1: level.timeBins, f0: 0, f1: level.bands });
}

/** Срез уровня под запрос: ровно bbox-ячейки, без ссылок на весь массив. */
export function sliceTile(
  level: SpectrogramLevel,
  request: TileRequest,
): { times: Float64Array; freqs: Float64Array; values: Float32Array } {
  const { t0, t1, f0, f1 } = request.window;
  const width = t1 - t0;
  const values = new Float32Array(width * (f1 - f0));
  for (let f = f0; f < f1; f += 1) {
    for (let t = t0; t < t1; t += 1) {
      values[(f - f0) * width + (t - t0)] = levelValueAt(level, t, f);
    }
  }
  return { times: level.timeS.slice(t0, t1), freqs: level.frequencyHz.slice(f0, f1), values };
}

export type TileState<T> =
  | { kind: "idle" }
  | { kind: "loading"; request: TileRequest }
  | { kind: "ready"; request: TileRequest; value: T }
  | { kind: "error"; request: TileRequest | null; error: unknown };

type TileListener<T> = (state: TileState<T>) => void;

/** Гонко-защита загрузки тайла: устаревший ответ отбрасывается, прежний
 * полёт обрывается AbortController'ом (расширение паттерна resource.ts). */
export function createTileLoader<T>(
  fetcher: (request: TileRequest, signal: AbortSignal) => Promise<T>,
) {
  let generation = 0;
  let controller = new AbortController();
  let state: TileState<T> = { kind: "idle" };
  const listeners = new Set<TileListener<T>>();

  function set(next: TileState<T>): void {
    state = next;
    for (const listener of listeners) listener(next);
  }

  return {
    get: (): TileState<T> => state,
    subscribe(listener: TileListener<T>): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async load(request: TileRequest): Promise<void> {
      const gen = ++generation;
      controller.abort();
      controller = new AbortController();
      set({ kind: "loading", request });
      try {
        const value = await fetcher(request, controller.signal);
        if (gen !== generation) return; // устаревший ответ — игнорируем целиком
        set({ kind: "ready", request, value });
      } catch (error) {
        if (gen !== generation || isAbort(error)) return; // замещён новый запрос
        set({ kind: "error", request: null, error });
      }
    },
    dispose: () => {
      generation += 1;
      controller.abort();
      listeners.clear();
    },
  };
}

function isAbort(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { name?: unknown }).name === "AbortError"
  );
}
