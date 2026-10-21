/** Доменные типы живого режима (источник: src/lnt/ui/models_live.py).
 * Имена полей совпадают с JSON бэкенда. Статус — ДВА независимых поля:
 * state (idle|running|stopped — InstrumentService) и mode (real|sim —
 * объявленное происхождение отсчётов); панель не смешивает их и не выводит
 * режим из состояния. time_s канала — секунды от начала окна кадра (t0=0). */

export type LiveMode = "real" | "sim";

export type LiveInstrumentState = "idle" | "running" | "stopped";

export type LiveTriggerSlope = "rising" | "falling";

export type LiveTriggerSource = "ch1" | "ch2";

export type LiveTriggerMode = "auto" | "normal" | "single";

/** Триггер живого потока: зеркало TriggerConfig (instrument/trigger.py). */
export interface LiveTrigger {
  level_v: number;
  slope: LiveTriggerSlope;
  source: LiveTriggerSource;
  mode: LiveTriggerMode;
  auto_timeout_s: number;
}

/** Тело POST /api/live/start: каденс, диапазон CH1, пробник, триггер. */
export interface LiveStartRequest {
  sample_rate_hz: number;
  ch1_range_v: number;
  ch1_probe_multiplier: number;
  trigger: LiveTrigger;
}

/** Ответ GET /api/live/state и событий heartbeat (маршруты управления). */
export interface LiveStatePayload {
  state: LiveInstrumentState;
  mode: LiveMode;
  busy_reason: string | null;
  trigger: LiveTrigger | null;
}

/** Прореженный ряд канала кадра: секунды от начала кадра и вольты. */
export interface LiveChannelSeries {
  time_s: number[];
  voltage_v: number[];
  point_count: number;
}

/** Кадр события frame: одно SSE-событие, каналы прорежены после вольт. */
export interface LiveFramePayload {
  frame_index: number;
  triggered: boolean;
  emitted_at_s: number;
  dropped_samples: number;
  skipped_frames: number;
  sample_rate_hz: number;
  frame_samples: number;
  decimated: boolean;
  calibration_used: boolean;
  ch1: LiveChannelSeries;
  ch2: LiveChannelSeries;
}

/** Зеркало дефолтов InstrumentService (8 МГц dual, ±5 В, AUTO 0.2 с):
 * скелет вкладки запускает живой режим без своих настроек; конкретика
 * появится с формой триггера (последующие очереди). */
export const DEFAULT_LIVE_START_REQUEST: LiveStartRequest = {
  sample_rate_hz: 8_000_000,
  ch1_range_v: 5,
  ch1_probe_multiplier: 1,
  trigger: {
    level_v: 0,
    slope: "rising",
    source: "ch1",
    mode: "auto",
    auto_timeout_s: 0.2,
  },
};

/** Детектор трасс SA: зеркало KNOWN_DETECTORS (psd/models.py); выборки
 * (sample) в MVP нет — только эти четыре. */
export type LiveSaDetector = "mean" | "rms" | "max-hold" | "min-hold";
/** Окно SA: пять известных (паритет MARKER_WINDOW_OPTIONS инспекции). */
export type LiveSaWindow = "hann" | "flattop" | "kaiser" | "blackman" | "rect";

/** SA-конфигурация живого режима: зеркало SaConfig (instrument/sa.py).
 * Границы (Найквист, геометрия полосы) проверяет бэкенд (422). */
export interface LiveSaConfig {
  rbw_hz: number;
  window: LiveSaWindow;
  band_low_hz: number;
  band_high_hz: number;
  detector: LiveSaDetector;
}

/** Дефолт SA-конфигурации вкладки: RBW/окно/детектор — дефолты домена
 * (50 Гц, hann, mean), полоса — до Найквиста дефолтного старта 8 МГц. */
export const DEFAULT_LIVE_SA_CONFIG: LiveSaConfig = {
  rbw_hz: 50,
  window: "hann",
  band_low_hz: 0,
  band_high_hz: 4_000_000,
  detector: "mean",
};

/** Пик трассы SA: частота, уровень, prominence и Q (до прореживания). */
export interface LiveSaPeak {
  frequency_hz: number;
  level_db: number;
  prominence_db: number;
  q_factor: number | null;
}

/** Метаданные трассы SA: ENBW, разрешение сетки, окно и выбранный RBW. */
export interface LiveSaMeta {
  enbw: number;
  resolution: number;
  window: string;
  rbw: number;
}

/** Трасса SA одного свипа (событие spectrum): одна серия в дБ и пики
 * полного разрешения. psd_db = 10·log10(PSD В²/Гц). */
export interface LiveSpectrumPayload {
  frame_index: number;
  freq: number[];
  psd_db: number[];
  peaks: LiveSaPeak[];
  meta: LiveSaMeta;
}

/** Статус живого риппла (RippleStatus, instrument/ripple_types.py):
 * числа есть только у ready. */
export type LiveRippleStatus = "settling" | "unavailable" | "ready" | "stopped";

/** База непрерывности полного тракта (ripple_types.py). */
export type LiveRippleContinuityBasis = "host_contiguous_unverified" | "synthetic_exact";

/** Основание окна установления (ripple_types.py). */
export type LiveRippleSettlingBasis = "capture_start_assuming_preconnected" | "settling_unknown";

/** Провенанс AC-адаптера в каждом событии ripple (RippleAdapterView):
 * номинальный preset, а не обнаруженное железо. */
export interface LiveRippleAdapterPayload {
  topology_id: string;
  cap_nf: number;
  series_r_ohm: number;
  probe_multiplier: number;
  component_values_basis: string;
  hardware_qualification: string;
  transfer_status: string;
  rail_nominal_v: number | null;
  tau_s: number | null;
  fc_hz: number | null;
  settling_s: number | null;
  settle_samples: number | null;
  assumption_codes: string[];
}

/** Событие ripple (models_ripple_live.py): метрики полного тракта CH1
 * отдельным именованным SSE-событием. Числа — только при status=ready;
 * схема ЖИВАЯ, отдельна от артефакта ripple.json. */
export interface LiveRipplePayload {
  status: LiveRippleStatus;
  reason_codes: string[];
  epoch_id: number;
  config_id: string;
  continuity_id: number;
  continuity_basis: LiveRippleContinuityBasis;
  gap_count: number;
  block_count: number;
  dropped_blocks: number;
  dropped_samples: number;
  samples_received: number;
  sample_progress: number;
  ring_capacity_samples: number;
  ring_sample_count: number;
  ring_limited: boolean;
  settle_samples: number | null;
  settled: boolean;
  startup_discard_samples: number;
  settling_basis: LiveRippleSettlingBasis;
  settling_remaining_samples: number | null;
  excluded_prefix_samples: number | null;
  span_start_sample: number | null;
  span_sample_count: number;
  span_duration_s: number | null;
  mean_v: number | null;
  rms_ac_v: number | null;
  vpp_v: number | null;
  clipped_low: number;
  clipped_high: number;
  clip_count_scope: "current_span";
  sample_rate_hz: number;
  ch1_range_v: number;
  ch1_probe_multiplier: number;
  calibration_used: boolean;
  voltage_label: "некалиброванные вольты";
  adapter: LiveRippleAdapterPayload;
}

/** Тело POST /api/live/config: триггер целиком + опциональный SA-контур.
 * sa отсутствует — контур не трогается; явный null — выключает. */
export interface LiveConfigRequest extends LiveTrigger {
  sa?: LiveSaConfig | null;
}

/** Подписка на живой поток (GET /api/live/frames): именованные события
 * frame/spectrum/ripple/heartbeat и объявления состояния соединения. Вкладка
 * подписывается на нужные ей события — прочие необязательны. onRipple получает
 * валидный снимок либо null (битое событие) — потребитель гасит числа. */
export interface LiveWatchHandlers {
  onFrame?(frame: LiveFramePayload): void;
  onSpectrum?(spectrum: LiveSpectrumPayload): void;
  onRipple?(payload: LiveRipplePayload | null): void;
  onState(state: LiveStatePayload): void;
  onConnection(kind: "live" | "reconnecting"): void;
}

export interface LiveWatchHandle {
  close(): void;
}

/** Планировщики SSE внедряются: тесты идут на fake timers и fake
 * EventSource (jsdom не реализует EventSource). */
export interface LiveSseDeps {
  eventSourceCtor?: typeof EventSource;
  setTimeoutFn?: (handler: () => void, timeout: number) => unknown;
  clearTimeoutFn?: (handle: unknown) => void;
  /** Сколько мс ждать событий после сбоя до fallback-опроса статуса. */
  staleTimeoutMs?: number;
}
