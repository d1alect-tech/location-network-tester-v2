/** Доменные типы графиков и деталей сессии: контракты src/lnt/ui/payloads.py.
 * Сервер применяет min/max-децимацию; исходные данные сессии не меняются. */

/** Плоскость спектра: scope (осциллограф) либо input-referred (вход CH1). */
export type SpectrumPlane = "scope" | "input-referred";

export interface SpectrumPayload {
  frequency_hz: number[];
  psd_v2_per_hz: number[];
  point_count: number;
  /** RBW-контракт шкалы (ADD-ключи): df полной сетки и полоса анализа. */
  resolution_hz?: number | null;
  band_low_hz?: number | null;
  band_high_hz?: number | null;
  /** B3: окно Welch и ENBW из анализа (ADD-ключи, старые клиенты целы). */
  window?: string | null;
  enbw_hz?: number | null;
}

/** GET /api/sessions/{name}/spectrum-input-referred: excess-PSD на входе CH1. */
export interface InputReferredSpectrumPayload {
  frequency_hz: number[];
  input_referred_excess_psd_v2_per_hz: number[];
  point_count: number;
  status: string | null;
  reason_code: string | null;
  qualified_bin_count: number;
  total_bin_count: number;
  resolution_hz: number | null;
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
