/** Доменные типы артефактов анализа v2 (todo 42). Источники:
 * src/lnt/analysis_v2/engine.py (spectrogram.npz, events.json) и
 * src/lnt/events/models.py (CandidateEventDict). Имена полей — как в JSON. */

export interface CandidateEventPayload {
  start_sample: number;
  end_sample: number;
  peak_sample: number;
  start_time_s: number;
  end_time_s: number;
  peak_time_s: number;
  peak_value_v: number;
  polarity: string;
  dominant_band: string | null;
  excess_energy_v2_s: number;
  snr: number;
  qualification_status: string;
  boundary: boolean;
  clipped: boolean;
}

/** Ответ GET …/artifacts/{key}/events.json — срез движка events-ветки. */
export interface EventInventoryPayload {
  schema_version: number;
  sample_count: number;
  events: CandidateEventPayload[];
}

/** Уровень пирамиды спектрограммы, разобранный из spectrogram.npz. Форма
 * power_db бэкенда — (полосы, время): плоский индекс = f * timeBins + t. */
export interface SpectrogramLevel {
  timeS: Float64Array;
  frequencyHz: Float64Array;
  powerDb: Float32Array;
  timeBins: number;
  bands: number;
}
