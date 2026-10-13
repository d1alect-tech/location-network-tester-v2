/** Живой режим единого мок-бэкенда (только e2e/spec): контракты routes_live.py.
 * Мутации требуют nonce (403 без него), повторный start — 409, config без
 * захвата — 409. Кадры синтетические (синус CH1/CH2), frame_index растёт с
 * каждым SSE-ответом — темп каденции задаёт переподключение EventSource по
 * retry: 150 (детерминированно, без гонок), как у JobStore. */

import type {
  LiveChannelSeries,
  LiveFramePayload,
  LiveInstrumentState,
  LiveMode,
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
  /** Действующий триггер сервиса (зеркало start/config): SINGLE в кадре. */
  runningTrigger: LiveTrigger | null = null;

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

  /** Тело SSE-потока: heartbeat статуса + кадры, пока идёт захват.
   * SINGLE — контракт InstrumentService: ровно один сработавший кадр,
   * затем прибор освобождён (state=stopped); дальше только heartbeat. */
  private framesBody(): string {
    let body = "retry: 150\n\n";
    body += `event: heartbeat\ndata: ${JSON.stringify(this.statePayload())}\n\n`;
    const single = this.state === "running" && this.runningTrigger?.mode === "single";
    const limit = single ? 1 : this.framesPerResponse;
    for (let i = 0; i < limit && this.state === "running"; i += 1) {
      const frame = this.framePayload(single);
      body += `event: frame\nid: ${frame.frame_index}\ndata: ${JSON.stringify(frame)}\n\n`;
    }
    if (single) this.state = "stopped";
    return body;
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
      this.configRequests.push(request.bodyJson<Record<string, unknown>>());
      this.runningTrigger = request.bodyJson<LiveTrigger>();
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
