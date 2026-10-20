/** Живой режим единого мок-бэкенда (только e2e/spec): контракты routes_live.py.
 * Мутации требуют nonce (403 без него), повторный start — 409, config без
 * захвата — 409. Кадры синтетические (синус CH1/CH2); трасса SA — тон
 * 10 кГц по сетке запрошенной полосы, событие spectrum идёт за кадром при
 * настроенном контуре. frame_index растёт с каждым SSE-ответом — темп
 * каденции задаёт переподключение EventSource по retry: 150
 * (детерминированно, без гонок), как у JobStore.
 *
 * Heartbeat ЧЕСТНЫЙ (зеркало routes_live после фикса QA round4/F1): событие
 * состояния уходит только при СМЕНЕ состояния (событие перехода, как у
 * сервера) и повторяется окном из нескольких ответов — столько, чтобы
 * КАЖДЫЙ открытый EventSource (вкладка держит несколько: воркспейс,
 * кластер, статус) успел переподключиться с периодом retry: 150 и получить
 * событие, как получил бы его каждый открытый подписчик реального сервера.
 * Инъекция heartbeat с текущим состоянием в КАЖДЫЙ ответ (без связи с
 * переходом) маскировала отсутствие события перехода у живого сервера
 * (run-кластер оставался idle) — так мок больше не делает. */

import type {
  LiveChannelSeries,
  LiveFramePayload,
  LiveInstrumentState,
  LiveMode,
  LiveRipplePayload,
  LiveRippleStatus,
  LiveSaConfig,
  LiveSpectrumPayload,
  LiveStartRequest,
  LiveStatePayload,
  LiveTrigger,
} from "../api/types-live";
import { type MockHttpReply, type MockHttpRequest, failure, nonceRejected, ok } from "./mockHttp";

const LIVE_ALREADY_RUNNING = "живой режим уже запущен: сначала stop";
const LIVE_NOT_RUNNING = "живой режим не запущен: сначала start";
const LIVE_BUSY_MESSAGE = "устройство занято вкладкой";
const AUTO_TRIGGER: LiveTrigger = {
  level_v: 0,
  slope: "rising",
  source: "ch1",
  mode: "auto",
  auto_timeout_s: 0.2,
};

const FRAME_POINTS = 32;
/** Точек в мок-трассе SA: детерминированная сетка полосы свипа. */
const SPECTRUM_POINTS = 64;
/** Индекс сетки с тоном мока: пик всегда НА сетке — виден на графике. */
const TONE_INDEX = 8;
/** Ответов с heartbeat при смене состояния: событие перехода должно дойти
 * до каждого открытого подписчика; при ~3 стримах с периодом retry: 150
 * окно 12 ответов покрывает каждый минимум дважды. */
const ANNOUNCE_WINDOW_RESPONSES = 12;
/** Canned-числа риппла мока (как mockGolden: фиксированные, не «измеренные»):
 * синус ~50 мВ размаха. */
const RIPPLE_RMS_AC_V = 0.0354;
const RIPPLE_VPP_V = 0.1;
const RIPPLE_MEAN_V = 0.0012;
const RIPPLE_SPAN_S = 0.5;
const RIPPLE_RATE_HZ = 8_000_000;
const RIPPLE_SETTLE_SAMPLES = 8_000_000;
/** Шаг прогресса полного тракта на один SSE-ответ (монотонный, как сервис). */
const RIPPLE_PROGRESS_STEP = 50_000;

function series(phase: number, amplitude: number): LiveChannelSeries {
  const time_s: number[] = [];
  const voltage_v: number[] = [];
  for (let i = 0; i < FRAME_POINTS; i += 1) {
    time_s.push((i / FRAME_POINTS) * 0.001);
    voltage_v.push(amplitude * Math.sin((i / FRAME_POINTS) * Math.PI * 2 + phase));
  }
  return { time_s, voltage_v, point_count: FRAME_POINTS };
}

export class LiveStore {
  state: LiveInstrumentState = "idle";
  mode: LiveMode = "sim";
  frameIndex = 0;
  /** Кадров в одном SSE-ответе: темп каденции при переподключении. */
  framesPerResponse = 2;
  readonly startedRequests: Record<string, unknown>[] = [];
  readonly stopRequests: unknown[] = [];
  readonly configRequests: Record<string, unknown>[] = [];
  /** Действующий SA-контур (зеркало config): null — спектров нет. */
  saConfig: LiveSaConfig | null = null;
  /** Действующий триггер сервиса (зеркало start/config): SINGLE в кадре. */
  runningTrigger: LiveTrigger | null = null;
  /** Сценарий ripple-событий для спеки: очередь статусов, каждый уходит с
   * SSE-ответом при running; пустая очередь — повтор последнего статуса.
   * null — авто-цикл (первый ответ settling, дальше ready), как сервер. */
  rippleScript: readonly LiveRippleStatus[] | null = null;
  /** Последний статус риппла мока (stopped после stop — терминален). */
  private rippleStatus: LiveRippleStatus | null = null;
  private rippleEpoch = 0;
  private rippleProgress = 0;
  private rippleScriptIndex = 0;
  /** Последний анонсированный статус: смена — событие перехода. */
  private lastAnnouncedState: LiveInstrumentState | null = null;
  /** Осталось ответов с heartbeat текущего перехода (окно вещания). */
  private announceLeft = 0;

  statePayload(): LiveStatePayload {
    return {
      state: this.state,
      mode: this.mode,
      busy_reason: this.state === "running" ? LIVE_BUSY_MESSAGE : null,
      trigger: this.state === "running" ? (this.runningTrigger ?? AUTO_TRIGGER) : null,
    };
  }

  private framePayload(single: boolean): LiveFramePayload {
    this.frameIndex += 1;
    return {
      frame_index: this.frameIndex,
      triggered: single || this.frameIndex % 2 === 0,
      emitted_at_s: this.frameIndex / 30,
      dropped_samples: 0,
      skipped_frames: 0,
      sample_rate_hz: 8_000_000,
      frame_samples: 4096,
      decimated: true,
      calibration_used: false,
      ch1: series(0, 1),
      ch2: series(Math.PI / 2, 0.5),
    };
  }

  /** Трасса SA одного свипа: тон на сетке (видимый пик) + рябь от кадра. */
  private spectrumPayload(frame: LiveFramePayload): LiveSpectrumPayload {
    const config = this.saConfig;
    const frameIndex = frame.frame_index;
    const freq: number[] = [];
    const psdDb: number[] = [];
    const span = config === null ? 0 : config.band_high_hz - config.band_low_hz;
    const toneHz =
      config === null
        ? TONE_INDEX
        : config.band_low_hz + (span * TONE_INDEX) / (SPECTRUM_POINTS - 1);
    const width = Math.max(span, 1) / 40;
    for (let i = 0; i < SPECTRUM_POINTS; i += 1) {
      const f = config === null ? i : config.band_low_hz + (span * i) / (SPECTRUM_POINTS - 1);
      freq.push(f);
      const sigma = (f - toneHz) / width;
      psdDb.push(
        -75 +
          45 * Math.exp(-sigma * sigma) +
          ((frameIndex % 3) - 1) * 2 +
          Math.sin(i + frameIndex) * 0.5,
      );
    }
    return {
      frame_index: frameIndex,
      freq,
      psd_db: psdDb,
      peaks: [
        {
          frequency_hz: toneHz,
          level_db: -30,
          prominence_db: 45,
          q_factor: null,
        },
      ],
      meta: {
        enbw: 75,
        resolution: 125,
        window: config?.window ?? "hann",
        rbw: config?.rbw_hz ?? 50,
      },
    };
  }

  /** Тело SSE-потока: кадры, пока идёт захват; heartbeat — окном при СМЕНЕ
   * состояния: событие перехода, как у routes_live, должно дойти до каждого
   * открытого подписчика, а в мок-среде каждый EventSource живёт
   * переподключениями с периодом retry: 150 — окно покрывает их все.
   * Инъекция heartbeat в каждый ответ маскировала QA round4/F1. Кадр при
   * настроенном SA-контуре несёт и трассу спектра. Ripple-событие — одно на
   * ответ при running (контракт routes_live: независимо от кадров, темп свой);
   * stop — честный stopped ровно один раз (терминальный статус сервера).
   * SINGLE — контракт InstrumentService: ровно один сработавший кадр, затем
   * прибор освобождён (state=stopped); смена состояния анонсируется окном. */
  private framesBody(): string {
    let body = "retry: 150\n\n";
    if (this.state !== this.lastAnnouncedState) {
      this.lastAnnouncedState = this.state;
      this.announceLeft = ANNOUNCE_WINDOW_RESPONSES;
    }
    if (this.announceLeft > 0) {
      this.announceLeft -= 1;
      body += `event: heartbeat\ndata: ${JSON.stringify(this.statePayload())}\n\n`;
    }
    const ripple = this.rippleEvent();
    if (ripple !== null) body += ripple;
    const single = this.state === "running" && this.runningTrigger?.mode === "single";
    const limit = single ? 1 : this.framesPerResponse;
    for (let i = 0; i < limit && this.state === "running"; i += 1) {
      const frame = this.framePayload(single);
      body += `event: frame\nid: ${frame.frame_index}\ndata: ${JSON.stringify(frame)}\n\n`;
      if (this.saConfig !== null) {
        const spectrum = this.spectrumPayload(frame);
        body += `event: spectrum\nid: ${spectrum.frame_index}\ndata: ${JSON.stringify(spectrum)}\n\n`;
      }
    }
    if (single) this.state = "stopped";
    return body;
  }

  /** Одно ripple-событие на SSE-ответ (строгая схема models_ripple_live.py):
   * авто-цикл settling→ready или сценарий спеки; после stop — один stopped. */
  private rippleEvent(): string | null {
    if (this.state !== "running") {
      if (this.rippleStatus === null || this.rippleStatus === "stopped") return null;
      this.rippleStatus = "stopped";
      return this.rippleBody("stopped");
    }
    let status: LiveRippleStatus;
    const script = this.rippleScript;
    if (script !== null && script.length > 0) {
      const index = Math.min(this.rippleScriptIndex, script.length - 1);
      this.rippleScriptIndex += 1;
      status = script[index] ?? "ready";
    } else if (script !== null) {
      status = "ready";
    } else if (this.rippleStatus === null) {
      status = "settling";
    } else {
      status = "ready";
    }
    this.rippleStatus = status;
    return this.rippleBody(status);
  }

  /** Canned-снимок: числа только у ready, идентичности монотонны. */
  private rippleBody(status: LiveRippleStatus): string {
    const ready = status === "ready";
    if (status !== "stopped") this.rippleProgress += RIPPLE_PROGRESS_STEP;
    const payload: LiveRipplePayload = {
      status,
      reason_codes: ready
        ? []
        : status === "settling"
          ? ["settling_window"]
          : ["insufficient_samples"],
      epoch_id: this.rippleEpoch,
      config_id: "mock-cfg",
      continuity_id: 1,
      continuity_basis: "synthetic_exact",
      gap_count: 0,
      block_count: 3,
      dropped_blocks: 0,
      dropped_samples: 0,
      samples_received: this.rippleProgress,
      sample_progress: this.rippleProgress,
      ring_capacity_samples: 524_288,
      ring_sample_count: ready ? 4000 : 1000,
      ring_limited: false,
      settle_samples: RIPPLE_SETTLE_SAMPLES,
      settled: ready || status === "stopped",
      startup_discard_samples: 0,
      settling_basis: "capture_start_assuming_preconnected",
      settling_remaining_samples: ready ? 0 : RIPPLE_SETTLE_SAMPLES - this.rippleProgress,
      excluded_prefix_samples: RIPPLE_SETTLE_SAMPLES,
      span_start_sample: ready ? RIPPLE_SETTLE_SAMPLES : null,
      span_sample_count: ready ? 4000 : 0,
      span_duration_s: ready ? RIPPLE_SPAN_S : null,
      mean_v: ready ? RIPPLE_MEAN_V : null,
      rms_ac_v: ready ? RIPPLE_RMS_AC_V : null,
      vpp_v: ready ? RIPPLE_VPP_V : null,
      clipped_low: 0,
      clipped_high: 0,
      clip_count_scope: "current_span",
      sample_rate_hz: RIPPLE_RATE_HZ,
      ch1_range_v: 5,
      ch1_probe_multiplier: 1,
      calibration_used: false,
      voltage_label: "некалиброванные вольты",
      adapter: {
        topology_id: "series_c_at_dut_tip_x1_v1",
        cap_nf: 100,
        series_r_ohm: 0,
        probe_multiplier: 1,
        component_values_basis: "nominal",
        hardware_qualification: "unverified",
        transfer_status: "nominal_transfer_declared",
        rail_nominal_v: null,
        tau_s: 0.1,
        fc_hz: 1.5915,
        settling_s: 1,
        settle_samples: RIPPLE_SETTLE_SAMPLES,
        assumption_codes: ["one_pole_nominal_transfer", "settling_policy_10_tau"],
      },
    };
    return `event: ripple\ndata: ${JSON.stringify(payload)}\n\n`;
  }

  /** Маршруты живого режима; null — не наш путь. */
  route(request: MockHttpRequest): MockHttpReply | null {
    const { method, path } = request;
    if (path === "/api/live/state" && method === "GET") return ok(this.statePayload());
    if (path === "/api/live/start" && method === "POST") {
      if (!request.nonceOk) return nonceRejected();
      if (this.state === "running") return failure(409, { detail: LIVE_ALREADY_RUNNING });
      this.startedRequests.push(request.bodyJson<Record<string, unknown>>());
      this.runningTrigger = request.bodyJson<LiveStartRequest>().trigger ?? null;
      // Контракт бэкенда: старт сбрасывает SA-контур — конфиг задаётся заново.
      this.saConfig = null;
      // Новая эпоха риппла (RippleEngine.restart): пустой тракт, монотонный id.
      this.rippleEpoch += 1;
      this.rippleProgress = 0;
      this.rippleScriptIndex = 0;
      this.rippleStatus = null;
      this.state = "running";
      return ok(this.statePayload());
    }
    if (path === "/api/live/stop" && method === "POST") {
      if (!request.nonceOk) return nonceRejected();
      this.stopRequests.push(request.bodyJson<Record<string, unknown>>());
      this.state = "stopped";
      this.runningTrigger = null;
      return ok(this.statePayload());
    }
    if (path === "/api/live/config" && method === "POST") {
      if (!request.nonceOk) return nonceRejected();
      if (this.state !== "running") return failure(409, { detail: LIVE_NOT_RUNNING });
      const body = request.bodyJson<Record<string, unknown>>();
      this.configRequests.push(body);
      this.runningTrigger = request.bodyJson<LiveTrigger>();
      // Контракт models_live.py: sa отсутствует — контур не трогается;
      // явный null — выключает трассы.
      if ("sa" in body) this.saConfig = (body.sa as LiveSaConfig | null) ?? null;
      return ok(this.statePayload());
    }
    if (path === "/api/live/frames" && method === "GET") {
      return { status: 200, contentType: "text/event-stream", body: this.framesBody() };
    }
    return null;
  }
}

/** Точка входа мок-бэкенда (паттерн handleJobs/handleCatalog). */
export function handleLive(store: LiveStore, request: MockHttpRequest): MockHttpReply | null {
  return store.route(request);
}
