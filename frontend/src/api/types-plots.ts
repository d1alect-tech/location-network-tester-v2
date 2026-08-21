/** Доменные типы графиков и деталей сессии: контракты src/lnt/ui/payloads.py.
 * Сервер применяет min/max-децимацию; исходные данные сессии не меняются. */

export interface SpectrumPayload {
  frequency_hz: number[];
  psd_v2_per_hz: number[];
  point_count: number;
}

export type WaveformChannel = "ch1" | "ch2";

export interface WaveformPayload {
  channel: WaveformChannel;
  time_s: number[];
  voltage_v: number[];
  point_count: number;
}

/** Ответ GET /api/sessions/{name}: манифест и анализ — открытые JSON-объекты
 * бэкенда (schema v1/v2), поэтому типизированы как records без уточнения. */
export interface SessionDetailPayload {
  name: string;
  manifest: Record<string, unknown>;
  analysis: Record<string, unknown> | null;
  spectrum_available: boolean;
  waveform_available: boolean;
  ch2_available: boolean;
}

export const SPECTRUM_MAX_POINTS = { min: 16, max: 20_000, default: 5_000 } as const;
export const WAVEFORM_MAX_POINTS = { min: 16, max: 4_000, default: 4_000 } as const;
