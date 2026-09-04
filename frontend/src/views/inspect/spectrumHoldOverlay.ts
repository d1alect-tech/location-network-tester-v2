/** Max-hold оверлей спектра A/B (очередь B2): пунктирный след поверх запроса. */

import type { SpectrumPayload } from "../../api/types-plots";
import type { ChartPeak, ChartRenderRequest } from "../../components/charts/types";
import { maxHoldValuesForRequest, spectrumToRequest } from "../../components/charts/viewModels";
import type { SeriesStyle } from "../../components/charts/viewModels";

const DASH_HOLD: readonly [number, number] = [2, 3];
const UNITS = { kind: "psd" } as const;

/** Max-hold след поверх запроса: пунктир того же цвета, расстройка — без следа. */
export function withMaxHold(
  request: ChartRenderRequest,
  payload: SpectrumPayload,
  label: string,
  color: string,
): ChartRenderRequest {
  const values = maxHoldValuesForRequest(payload, request.x, UNITS, true);
  if (values === null) return request;
  return {
    ...request,
    series: [...request.series, { label: `${label} · max-hold`, values, color, dash: DASH_HOLD }],
  };
}

export function overlayRequest(
  payloadA: SpectrumPayload,
  payloadB: SpectrumPayload | null,
  styleA: SeriesStyle,
  styleB: SeriesStyle,
  peaks: readonly ChartPeak[],
): ChartRenderRequest {
  const requestA = withMaxHold(
    spectrumToRequest(payloadA, styleA, UNITS, true, peaks),
    payloadA,
    styleA.label,
    styleA.color,
  );
  const series = [...requestA.series];
  if (payloadB !== null) {
    const requestB = withMaxHold(
      spectrumToRequest(payloadB, styleB, UNITS, true, []),
      payloadB,
      styleB.label,
      styleB.color,
    );
    series.push(...requestB.series);
  }
  return { ...requestA, xLabel: "", xLog: true, series };
}
