import { isSessionDetailPayload } from "../../api/guards-plots";
import type { SessionDetailPayload, SpectrumPayload } from "../../api/types-plots";

export const EMPTY_SPECTRUM: SpectrumPayload = {
  frequency_hz: [],
  psd_v2_per_hz: [],
  point_count: 0,
};

/** Мост пиков (задача 9): РЕАЛЬНЫЙ detail-конверт сервера (payloads.py:77-87 —
 * манифест и честные флаги spectrum/waveform/ch2) проходит как есть; объект
 * без конверта → null: доступность НЕ выдумывается (unavailable, never
 * fabricated). Раньше здесь собирался fabricated-конверт manifest:{} +
 * spectrum_available:true; продакшн-провод панели (createPairDetail) всегда
 * приносит полный конверт, узкие стабы без конверта честно дают ноль пиков. */
export function detailForPeaks(raw: { readonly analysis?: unknown }): SessionDetailPayload | null {
  return isSessionDetailPayload(raw) ? raw : null;
}
