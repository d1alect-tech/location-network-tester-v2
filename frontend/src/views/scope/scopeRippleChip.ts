/** Живой чип риппла в осциллографе (todo 9): read-only строка в панели
 * «Поток». Читает ИМЕНОВАННОЕ событие ripple (полный тракт CH1, todo 6),
 * математики на клиенте нет — числа приходят готовыми и только при
 * status=ready. Состояния честные: settling без чисел (только прогресс),
 * unavailable/остановлен — прочерк, никогда NaN. Свежесть чисел — ТОЛЬКО
 * по событиям ripple: таймер гасит числа, если событий нет (потеря потока,
 * смерть сервера). Ошибка транспорта (onerror) гасит числа сразу; сам
 * реконнект (onopen), кадры и heartbeat возраст риппла не обновляют и числа
 * не возвращают — это делает только следующее событие ripple. Геометрия
 * стабильна: каждое меняющееся значение сидит в слоте с фиксированной
 * минимальной шириной (scope.css), смена текста не двигает соседей.
 * GAP-6 (task 8): маркер базиса компонент адаптера («номинал»/«измерено
 * оператором», неизвестный литерал — прочерк) рядом с adapter-фактами и
 * постоянная подсказка «живые числа используют номинальную модель
 * адаптера» (D8). Декларация в живую — будущая работа (OQ5), здесь её нет. */

import type { LiveRipplePayload, LiveStatePayload } from "../../api/types-live";
import { el } from "../../components/primitives/dom";

/** Свежесть снимка ready: сервер шлёт событие каждые 0.25 с; 2 с — 8 пропусков. */
const DEFAULT_STALE_MS = 2000;

const STATE_TEXT: Record<string, string> = {
  settling: "установление",
  unavailable: "недоступно",
  ready: "готов",
  stopped: "остановлен",
  stale: "нет данных",
};

export interface ScopeRippleChipOptions {
  /** Порог свежести чисел, мс. */
  staleTimeoutMs?: number;
  /** Инъекция планировщиков: детерминированные тесты без глобальных fake timers. */
  setTimeoutFn?: (handler: () => void, timeout: number) => unknown;
  clearTimeoutFn?: (handle: unknown) => void;
}

export interface ScopeRippleChipHandle {
  readonly root: HTMLElement;
  /** Валидный снимок события ripple; null — битое событие, числа гаснут. */
  apply(payload: LiveRipplePayload | null): void;
  /** Ошибка транспорта: числа гаснут до следующего события ripple.
   * Идентичности эпохи сохраняются — откат и дубли по-прежнему отсекаются. */
  invalidate(): void;
  /** Состояние владения из onState: переход в running = новая эпоха —
   * старые числа гаснут; повторный running (heartbeat) чип не трогает. */
  applyLiveState(state: LiveStatePayload): void;
  dispose(): void;
}

interface SlotView {
  readonly state: HTMLElement;
  readonly progress: HTMLElement;
  readonly rms: HTMLElement;
  readonly vpp: HTMLElement;
  readonly window: HTMLElement;
  readonly adapter: HTMLElement;
  readonly basis: HTMLElement;
  readonly label: HTMLElement;
  readonly modelHint: HTMLElement;
}

export function mountScopeRippleChip(options: ScopeRippleChipOptions = {}): ScopeRippleChipHandle {
  const staleTimeoutMs = options.staleTimeoutMs ?? DEFAULT_STALE_MS;
  const setTimeoutFn = options.setTimeoutFn ?? ((fn, ms) => setTimeout(fn, ms));
  const clearTimeoutFn = options.clearTimeoutFn ?? ((handle) => clearTimeout(handle as number));

  const valueSlot = (attr: string, className: string): HTMLElement =>
    el("span", {
      className: `lnt-scope-ripple-val ${className}`,
      attrs: { [attr]: "", "data-readonly": "" },
      text: "—",
    });
  const slots: SlotView = {
    state: valueSlot("data-ripple-state", "lnt-scope-ripple-state"),
    progress: valueSlot("data-ripple-progress", "lnt-scope-ripple-progress"),
    rms: valueSlot("data-ripple-rms", "lnt-scope-ripple-rms"),
    vpp: valueSlot("data-ripple-vpp", "lnt-scope-ripple-vpp"),
    window: valueSlot("data-ripple-window", "lnt-scope-ripple-window"),
    adapter: valueSlot("data-ripple-adapter", "lnt-scope-ripple-adapter"),
    basis: valueSlot("data-ripple-basis", "lnt-scope-ripple-basis"),
    label: el("span", {
      className: "lnt-scope-ripple-label",
      attrs: { "data-ripple-label": "", "data-readonly": "" },
      text: "полные отсчёты, некалиброванные вольты",
    }),
    modelHint: el("span", {
      className: "lnt-scope-ripple-label",
      attrs: { "data-ripple-model-hint": "", "data-readonly": "" },
      text: "живые числа используют номинальную модель адаптера",
    }),
  };
  const metric = (label: string, slot: HTMLElement): HTMLElement =>
    el("span", { className: "lnt-scope-ripple-metric" }, [
      el("span", { className: "lnt-scope-ripple-metric-key", text: label }),
      slot,
    ]);
  const root = el(
    "p",
    {
      className: "lnt-scope-wave-tag lnt-scope-ripple",
      attrs: { "data-ripple-chip": "", "data-readonly": "" },
    },
    [
      el("span", { className: "lnt-scope-ripple-key", text: "Риппл:" }),
      slots.state,
      slots.progress,
      metric("RMS AC", slots.rms),
      metric("Vpp", slots.vpp),
      metric("окно", slots.window),
      metric("адаптер", slots.adapter),
      metric("базис", slots.basis),
      slots.label,
      slots.modelHint,
    ],
  );

  let data: LiveRipplePayload | null = null;
  let stale = false;
  let timerHandle: unknown = null;
  let lastEpoch = 0;
  let lastContinuity = 0;
  let lastProgress = 0;
  let running: boolean | null = null;

  /** Сброс к нейтрали: числа и идентичности эпохи не переживают старт. */
  function reset(): void {
    data = null;
    stale = false;
    lastEpoch = 0;
    lastContinuity = 0;
    lastProgress = 0;
    disarmStaleTimer();
    render();
  }

  function armStaleTimer(): void {
    disarmStaleTimer();
    timerHandle = setTimeoutFn(() => {
      timerHandle = null;
      if (data !== null && data.status === "ready" && !stale) {
        stale = true;
        render();
      }
    }, staleTimeoutMs);
  }

  function disarmStaleTimer(): void {
    if (timerHandle !== null) {
      clearTimeoutFn(timerHandle);
      timerHandle = null;
    }
  }

  /** Транспорт потерян: числа и прогресс гаснут, провенанс последнего
   * снимка остаётся. Эпоха не сбрасывается: следующее событие той же эпохи
   * вернёт числа, а откат (старая эпоха/непрерывность/прогресс) — нет.
   * Терминальный stopped уже без чисел и остаётся последним честным статусом. */
  function invalidate(): void {
    disarmStaleTimer();
    if (data === null || data.status === "stopped") return;
    stale = true;
    render();
  }

  /** Устаревший снимок (прошлая эпоха/непрерывность/прогресс) не рисуется. */
  function isRegression(payload: LiveRipplePayload): boolean {
    if (payload.epoch_id < lastEpoch) return true;
    if (payload.epoch_id === lastEpoch && payload.continuity_id < lastContinuity) return true;
    return (
      payload.epoch_id === lastEpoch &&
      payload.continuity_id === lastContinuity &&
      payload.sample_progress < lastProgress
    );
  }

  function render(): void {
    if (data === null) {
      slots.state.textContent = "—";
      slots.progress.textContent = "—";
      slots.rms.textContent = "—";
      slots.vpp.textContent = "—";
      slots.window.textContent = "—";
      slots.adapter.textContent = "—";
      slots.basis.textContent = "—";
      return;
    }
    const showValues = data.status === "ready" && !stale;
    slots.state.textContent = stale ? (STATE_TEXT.stale ?? "—") : (STATE_TEXT[data.status] ?? "—");
    slots.progress.textContent =
      !stale && data.status === "settling" && data.settling_remaining_samples !== null
        ? `осталось ~${formatSeconds(data.settling_remaining_samples / data.sample_rate_hz)}`
        : "—";
    slots.rms.textContent = showValues ? formatVolts(data.rms_ac_v) : "—";
    slots.vpp.textContent = showValues ? formatVolts(data.vpp_v) : "—";
    slots.window.textContent =
      showValues && data.span_duration_s !== null ? formatSeconds(data.span_duration_s) : "—";
    slots.adapter.textContent = formatAdapter(data.adapter);
    // Базис — провенанс, как адаптер: не зависит от свежести чисел.
    slots.basis.textContent = formatBasis(data.adapter.component_values_basis);
  }

  function apply(payload: LiveRipplePayload | null): void {
    if (payload === null) {
      // Битое событие: числа гаснут, провенанс остаётся — поток жив.
      if (data !== null && data.status === "ready" && !stale) {
        stale = true;
        render();
        disarmStaleTimer();
      }
      return;
    }
    if (isRegression(payload)) return;
    data = payload;
    stale = false;
    lastEpoch = payload.epoch_id;
    lastContinuity = payload.continuity_id;
    lastProgress = payload.sample_progress;
    render();
    // Свежесть охраняет только числа: stopped — терминален, таймер не нужен.
    if (payload.status === "ready") armStaleTimer();
    else disarmStaleTimer();
  }

  return {
    root,
    apply,
    invalidate,
    applyLiveState: (state) => {
      const nowRunning = state.state === "running";
      if (nowRunning && running !== true) reset();
      running = nowRunning;
    },
    dispose: () => {
      disarmStaleTimer();
    },
  };
}

/** Вольты чипа: суб-вольтовые — мВ с десятыми (риппл мал по природе). */
function formatVolts(value: number | null): string {
  if (value === null) return "—";
  if (Math.abs(value) >= 1) return `${value.toFixed(3)} В`;
  return `${(value * 1000).toFixed(1)} мВ`;
}

/** Секунды чипа: окно и остаток установления. */
function formatSeconds(value: number): string {
  if (value >= 1) return `${value.toFixed(1)} с`;
  return `${Math.round(value * 1000)} мс`;
}

/** Параметры номинального адаптера: видны рядом с числами. */
function formatAdapter(adapter: LiveRipplePayload["adapter"]): string {
  const cap = Number.isInteger(adapter.cap_nf) ? String(adapter.cap_nf) : adapter.cap_nf.toFixed(1);
  const series = Number.isInteger(adapter.series_r_ohm)
    ? String(adapter.series_r_ohm)
    : adapter.series_r_ohm.toFixed(1);
  return `${cap} нФ · ${series} Ом · ×${adapter.probe_multiplier}`;
}

/** Маркер базиса компонент: объявленный номинал или значения, измеренные
 * оператором. Неизвестный литерал — прочерк, выдуманный ярлык запрещён. */
function formatBasis(basis: string): string {
  if (basis === "nominal") return "номинал";
  if (basis === "operator_measured") return "измерено оператором";
  return "—";
}
