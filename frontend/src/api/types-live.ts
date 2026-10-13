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

/** Подписка на живой поток (GET /api/live/frames): именованные события
 * frame/heartbeat и объявления состояния соединения. */
export interface LiveWatchHandlers {
  onFrame(frame: LiveFramePayload): void;
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
