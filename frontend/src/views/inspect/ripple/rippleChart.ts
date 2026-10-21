/** Рендер-запрос сохранённого ripple-спектра: PSD → 10·lg (В²/Гц),
 * ASD → хранимые В/√Гц на лог-оси. Нулевой DC-бин и нефинитные пары
 * отбрасываются; ни одного нового расчёта плотности здесь нет.
 *
 * Исход различает «спектр недоступен» и «спектр сохранён, но на лог-оси
 * нет ни одной конечной точки»: доступные данные никогда не помечаются
 * недоступными, а −Infinity не уходит ни в DOM, ни в title. */

import type { RippleArtifactPayload } from "../../../api/types-ripple";
import { psdToDb } from "../../../components/charts/series";
import type { ChartRenderRequest } from "../../../components/charts/types";

export type RippleSpectrumMode = "psd" | "asd";

export const RIPPLE_PSD_LABEL = "дБ (1 В²/Гц)";
export const RIPPLE_ASD_LABEL = "В/√Гц (лог)";

/** Машинная причина пустого слота графика. `zero_floor` — спектр доступен,
 * но каждый сохранённый уровень равен нулю; `no_log_points` — доступен,
 * однако конечной положительной точки для лог-оси не оказалось. */
export type RippleChartOutcome =
  | { readonly kind: "request"; readonly request: ChartRenderRequest }
  | { readonly kind: "unavailable" }
  | { readonly kind: "no_bins" }
  | { readonly kind: "zero_floor"; readonly bins: number }
  | { readonly kind: "no_log_points"; readonly bins: number };

export function chartOutcome(
  artifact: RippleArtifactPayload,
  mode: RippleSpectrumMode,
  color: string,
): RippleChartOutcome {
  const spectrum = artifact.spectrum;
  if (spectrum.availability !== "available") return { kind: "unavailable" };
  const stored = mode === "psd" ? spectrum.psd_v2_per_hz : spectrum.asd_v_per_sqrt_hz;
  const bins = stored.length;
  if (bins === 0) return { kind: "no_bins" };
  const source = mode === "psd" ? psdToDb(stored) : stored;
  const x: number[] = [];
  const y: number[] = [];
  const count = Math.min(spectrum.frequency_hz.length, bins);
  let zeros = 0;
  for (let index = 0; index < count; index += 1) {
    const frequency = spectrum.frequency_hz[index];
    const value = source[index];
    if (stored[index] === 0) zeros += 1;
    if (frequency === undefined || value === undefined) continue;
    if (!Number.isFinite(frequency) || frequency <= 0) continue;
    if (!Number.isFinite(value) || (mode === "asd" && value <= 0)) continue;
    x.push(frequency);
    y.push(value);
  }
  if (x.length === 0) {
    return zeros === count ? { kind: "zero_floor", bins } : { kind: "no_log_points", bins };
  }
  return {
    kind: "request",
    request: {
      xLabel: "Гц",
      yLabel: mode === "psd" ? RIPPLE_PSD_LABEL : RIPPLE_ASD_LABEL,
      xLog: true,
      yLog: mode === "asd",
      x,
      series: [{ label: mode === "psd" ? "PSD" : "ASD", values: y, color }],
    },
  };
}
