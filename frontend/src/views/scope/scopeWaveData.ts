/** Подготовка рядов кадра для живой развёртки (сплит из scopeWaveform,
 * задача 16 — точка разбиения названа ДО кода): выравнивание пары каналов
 * payload-кадра (знак инверсии — знак КОПИИ, исходники не мутируются),
 * отбрасывание нечисловых отсчётов по общему индексу (правило
 * prepareAligned), подсчёт выхода за окно сетки и ОБЩЕЕ прореживание пары
 * min/max-огибающей (decimateMinMax) с объединением сохранённых индексов —
 * экстремумы обоих каналов остаются, ряды выровнены по общему X. Чистые
 * данные без DOM; рендер-запросы и режимы — в scopeWaveform. */

import type { LiveFramePayload } from "../../api/types-live";
import { decimateMinMax } from "../../components/charts/series";
import { POINT_BUDGETS } from "../../components/charts/viewModels";
import { windowHalfVolts } from "./scopeScale";
import type { ScopeDisplaySettings } from "./scopeScale";

/** Бюджет точек пары каналов развёртки (POINT_BUDGETS.waveform). */
export const WAVE_BUDGET = POINT_BUDGETS.waveform.default;

export interface WaveData {
  x: number[];
  ch1: number[];
  ch2: number[];
  xMin: number;
  xMax: number;
  nanCount: number;
  clipCount: number;
}

/** Общее прореживание пары каналов: min/max-огибающая каждого канала
 * (decimateMinMax), объединение сохранённых индексов — экстремумы обоих
 * каналов остаются, ряды выровнены по общему X. */
export function decimateUnion(data: WaveData): void {
  if (data.x.length <= WAVE_BUDGET) return;
  const indexByX = new Map<number, number>();
  for (let i = 0; i < data.x.length; i += 1) indexByX.set(data.x[i]!, i);
  const kept = new Set<number>();
  for (const channel of [data.ch1, data.ch2]) {
    for (const xValue of decimateMinMax(data.x, channel, WAVE_BUDGET).x) {
      const index = indexByX.get(xValue);
      if (index !== undefined) kept.add(index);
    }
  }
  const indices = [...kept].sort((a, b) => a - b);
  data.x = indices.map((index) => data.x[index]!);
  data.ch1 = indices.map((index) => data.ch1[index]!);
  data.ch2 = indices.map((index) => data.ch2[index]!);
}

/** Кадр -> выровненные копии рядов: знак инверсии, нулевые линии каналов
 * (groundChN — сдвиг ОТОБРАЖЕНИЯ, измерения не трогаются), отбрасывание
 * нечисловых по общему индексу (как prepareAligned), подсчёт выхода за
 * окно сетки (±4·В/дел). */
export function buildWaveData(
  frame: LiveFramePayload,
  settings: ScopeDisplaySettings,
): WaveData | null {
  const times = frame.ch1.time_s;
  const rawCh1 = frame.ch1.voltage_v;
  const rawCh2 = frame.ch2.voltage_v;
  const count = Math.min(times.length, rawCh1.length, rawCh2.length);
  if (count === 0) return null;
  const half = windowHalfVolts(settings.vDiv, settings.probe);
  const signCh1 = settings.invertCh1 ? -1 : 1;
  const signCh2 = settings.invertCh2 ? -1 : 1;
  const data: WaveData = {
    x: [],
    ch1: [],
    ch2: [],
    xMin: Number.POSITIVE_INFINITY,
    xMax: Number.NEGATIVE_INFINITY,
    nanCount: 0,
    clipCount: 0,
  };
  for (let i = 0; i < count; i += 1) {
    const t = times[i];
    const v1 = rawCh1[i];
    const v2 = rawCh2[i];
    if (t === undefined || v1 === undefined || v2 === undefined) {
      data.nanCount += 1;
      continue;
    }
    if (!Number.isFinite(t) || !Number.isFinite(v1) || !Number.isFinite(v2)) {
      data.nanCount += 1;
      continue;
    }
    const w1 = v1 * signCh1 + settings.groundCh1V;
    const w2 = v2 * signCh2 + settings.groundCh2V;
    if (Math.abs(w1) > half || Math.abs(w2) > half) data.clipCount += 1;
    data.x.push(t);
    data.ch1.push(w1);
    data.ch2.push(w2);
    if (t < data.xMin) data.xMin = t;
    if (t > data.xMax) data.xMax = t;
  }
  if (data.x.length === 0) return null;
  decimateUnion(data);
  return data;
}
