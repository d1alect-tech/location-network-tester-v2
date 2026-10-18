/** Математ-трасса CH1−CH2 (задача 16, выбрано GATE A 2026-10-18): разность
 * каналов (В) из payload кадра — ТРЕТЬЯ серия существующего uPlot-стека
 * развёртки (второй стек не заводится). Разность — ОТОБРАЖАЕМЫХ рядов
 * (после знака инверсии каналов): трасса совпадает с тем, что нарисовано.
 * Ярлык честности — размах ряда разности + «АЦП 8 бит, трасса просмотра»:
 * калибровка каналов НЕ заявляется (граница владельца: unavailable, never
 * fabricated). Измерения CH1 (scopeMeasureConfig) не меняются; readout-ряд
 * в сетку измерений НЕ добавлен (решение по геометрии: ряды грида —
 * пользовательские тумблеры контракта lnt.live.meas.v1, ряд режима туда не
 * смешивается; ярлык живёт в существующей строке ярлыков развёртки
 * [data-wave-math], прецеденты ФНЧ/послесвечения — без нового DOM-блока).
 * Тумблер — local-семейство зоны ИЗМЕР полосы (#lnt-scope-math). */

import type { ChartTheme } from "../../components/charts/theme";
import type { ChartRenderSeries } from "../../components/charts/types";
import { createLiveSeg } from "../../components/liveStrip/liveSeg";
import type { LiveSegHandle } from "../../components/liveStrip/liveSeg";
import { formatVoltsValue } from "./scopeMeasurements";

/** Подпись серии и тумблера (минус — U+2212, как в постановке задачи). */
export const MATH_TRACE_LABEL = "CH1−CH2";

/** Подпись честности: разность просмотра, не калиброванное измерение. */
export const MATH_TRACE_HINT = "АЦП 8 бит, трасса просмотра";

/** Отличие не только цветом (DESIGN.md): короткий пунктир + маркер-треуг. */
export const MATH_DASH: readonly [number, number] = [2, 3];
export const MATH_MARKER = "▲";

/** Поэлементная разность двух рядов (В); длина — по короткому ряду. */
export function mathDiffVolts(ch1: readonly number[], ch2: readonly number[]): number[] {
  const count = Math.min(ch1.length, ch2.length);
  const diff: number[] = [];
  for (let i = 0; i < count; i += 1) {
    diff.push((ch1[i] ?? 0) - (ch2[i] ?? 0));
  }
  return diff;
}

/** Размах (Vpp) ряда разности: max − min по конечным отсчётам; null —
 * конечных нет. Параболическое уточнение не применяется: размах подписи
 * честен как размах отображаемых отсчётов, без лишней точности. */
export function mathVppV(values: readonly number[]): number | null {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    if (value < min) min = value;
    if (value > max) max = value;
  }
  if (min === Number.POSITIVE_INFINITY) return null;
  return max - min;
}

/** Текст ярлыка развёртки: подпись + размах (если ряд есть) + честность. */
export function mathTagText(vppV: number | null): string {
  const range = vppV === null ? "" : ` — размах ${formatVoltsValue(vppV)}`;
  return `${MATH_TRACE_LABEL}${range} — ${MATH_TRACE_HINT}`;
}

/** Серия разности для рендер-запроса общего стека: токен delta (трассы
 * дельт), короткий пунктир, маркер-треугольник. */
export function mathTraceSeries(values: readonly number[], theme: ChartTheme): ChartRenderSeries {
  return {
    label: MATH_TRACE_LABEL,
    values,
    color: theme.delta,
    dash: MATH_DASH,
    marker: MATH_MARKER,
  };
}

/** Тумблер «CH1−CH2» зоны ИЗМЕР: local-семейство (Вкл/Выкл), контрактный
 * id для ре-парента полосой; клик по нажатому — no-op (скин liveSeg). */
export function buildMathTraceToggle(onPick: (on: boolean) => void): LiveSegHandle {
  return createLiveSeg(
    {
      key: "math",
      kind: "local",
      aria: "Трасса CH1−CH2",
      options: [
        { value: "off", text: "Выкл" },
        { value: "on", text: "Вкл" },
      ],
      current: "off",
      groupAttrs: { id: "lnt-scope-math" },
    },
    (value) => onPick(value === "on"),
  );
}
