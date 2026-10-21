/** Рендер-запрос сохранённого ripple-спектра: PSD → 10·lg (В²/Гц),
 * ASD → хранимые В/√Гц на лог-оси. Нулевой DC-бин и нефинитные пары
 * отбрасываются; ни одного нового расчёта плотности здесь нет. */

import type { RippleArtifactPayload } from "../../../api/types-ripple";
import { psdToDb } from "../../../components/charts/series";
import type { ChartRenderRequest } from "../../../components/charts/types";

export type RippleSpectrumMode = "psd" | "asd";

export const RIPPLE_PSD_LABEL = "дБ (1 В²/Гц)";
export const RIPPLE_ASD_LABEL = "В/√Гц (лог)";

export function chartRequest(
  artifact: RippleArtifactPayload,
  mode: RippleSpectrumMode,
  color: string,
): ChartRenderRequest | null {
  const spectrum = artifact.spectrum;
  if (spectrum.availability !== "available") return null;
  const source = mode === "psd" ? psdToDb(spectrum.psd_v2_per_hz) : spectrum.asd_v_per_sqrt_hz;
  const x: number[] = [];
  const y: number[] = [];
  const count = Math.min(spectrum.frequency_hz.length, source.length);
  for (let index = 0; index < count; index += 1) {
    const frequency = spectrum.frequency_hz[index];
    const value = source[index];
    if (frequency === undefined || value === undefined) continue;
    if (!Number.isFinite(frequency) || frequency <= 0) continue;
    if (!Number.isFinite(value) || (mode === "asd" && value <= 0)) continue;
    x.push(frequency);
    y.push(value);
  }
  if (x.length === 0) return null;
  return {
    xLabel: "Гц",
    yLabel: mode === "psd" ? RIPPLE_PSD_LABEL : RIPPLE_ASD_LABEL,
    xLog: true,
    yLog: mode === "asd",
    x,
    series: [{ label: mode === "psd" ? "PSD" : "ASD", values: y, color }],
  };
}
