/** Статические секции и показания вкладки «Осциллограф» (Todo 7, Todo 10).
 * Панельная система V6 (kit.css §5.2, как settingsSections): section.panel >
 * .panel-hd/.panel-title + .panel-bd, показания — .readout-grid. Только
 * построение DOM из готовых данных и форматирование: без сети, без
 * состояния, без слушателей — интерактив остаётся в scopeWorkspace
 * (курсоры экрана — в scopeCursorSection). */

import type { LiveFramePayload, LiveInstrumentState } from "../../api/types-live";
import { el } from "../../components/primitives/dom";
import {
  formatDutyValue,
  formatFrequencyValue,
  formatMeasurement,
  formatPeriodValue,
  formatVoltsValue,
  measureSeries,
} from "./scopeMeasurements";

export const LIVE_STATE_TEXT: Record<LiveInstrumentState, string> = {
  idle: "не запущен",
  running: "запущен",
  stopped: "остановлен",
};

export interface ScopeStatusView {
  readonly root: HTMLElement;
  /** Строка состояния устройства (заполняет workspace из device.state()). */
  readonly deviceHost: HTMLElement;
  /** Строка «Живой режим: …» с data-live-state. */
  readonly stateLine: HTMLElement;
  /** Бейдж «Симуляция»: виден только при mode=sim. */
  readonly simBadge: HTMLElement;
  /** Причина занятости прибора (busy_reason), скрыта при null. */
  readonly busyLine: HTMLElement;
  /** Хост ошибок запуска/остановки (role=alert блоки). */
  readonly errorHost: HTMLElement;
  readonly runButton: HTMLButtonElement;
  readonly stopButton: HTMLButtonElement;
}

export function buildScopeStatusSection(): ScopeStatusView {
  const deviceHost = el("div", {
    className: "lnt-scope-device",
    attrs: { role: "status" },
  });
  const stateLine = el("p", {
    className: "t-body lnt-scope-state",
    text: "Живой режим: запрос статуса…",
  });
  const simBadge = el("span", { className: "lnt-scope-sim-badge", text: "Симуляция" });
  simBadge.hidden = true;
  const busyLine = el("p", { className: "t-compact lnt-scope-busy", text: "" });
  busyLine.hidden = true;
  const runButton = el("button", {
    className: "btn",
    text: "Запустить",
    attrs: { type: "button", id: "lnt-scope-run" },
  });
  const stopButton = el("button", {
    className: "btn btn-secondary",
    text: "Остановить",
    attrs: { type: "button", id: "lnt-scope-stop" },
  });
  stopButton.disabled = true;
  const errorHost = el("div", { className: "lnt-scope-error-host" });

  return {
    root: el("section", { className: "panel lnt-scope-section lnt-scope-status" }, [
      el("div", { className: "panel-hd" }, [
        el("h3", { className: "panel-title", text: "Прибор" }),
      ]),
      el("div", { className: "panel-bd" }, [
        deviceHost,
        el("div", { className: "lnt-scope-state-row" }, [stateLine, simBadge]),
        busyLine,
        el("div", { className: "form-actions" }, [runButton, stopButton]),
        errorHost,
      ]),
    ]),
    deviceHost,
    stateLine,
    simBadge,
    busyLine,
    errorHost,
    runButton,
    stopButton,
  };
}

export interface ScopeReadoutView {
  readonly root: HTMLElement;
  /** Индикатор соединения SSE: «передача данных» / «переподключение…». */
  readonly connection: HTMLElement;
  applyFrame(frame: LiveFramePayload): void;
}

export function buildScopeReadoutSection(): ScopeReadoutView {
  const frameCount = el("dd", { className: "t-mono lnt-scope-frame-count", text: "—" });
  const triggered = el("dd", { className: "t-compact lnt-scope-triggered", text: "—" });
  const rate = el("dd", { className: "t-compact lnt-scope-rate", text: "—" });
  const points = el("dd", { className: "t-compact lnt-scope-points", text: "—" });
  const dropped = el("dd", { className: "t-compact lnt-scope-dropped", text: "—" });
  const skipped = el("dd", { className: "t-compact lnt-scope-skipped", text: "—" });
  const calibration = el("dd", { className: "t-compact lnt-scope-calibration", text: "—" });
  const connection = el("p", {
    className: "t-compact lnt-scope-connection",
    text: "подключение…",
    attrs: { role: "status" },
  });

  const row = (label: string, value: HTMLElement): Node[] => [
    el("dt", { className: "readout-label", text: label }),
    value,
  ];

  return {
    root: el("section", { className: "panel lnt-scope-section lnt-scope-readout" }, [
      el("div", { className: "panel-hd" }, [el("h3", { className: "panel-title", text: "Поток" })]),
      el("div", { className: "panel-bd" }, [
        el(
          "dl",
          { className: "readout-grid" },
          row("кадр", frameCount)
            .concat(row("триггер", triggered))
            .concat(row("частота", rate))
            .concat(row("точек в кадре", points))
            .concat(row("потеряно прибором", dropped))
            .concat(row("пропущено панелью", skipped))
            .concat(row("вольты", calibration)),
        ),
        connection,
      ]),
    ]),
    connection,
    applyFrame(frame: LiveFramePayload): void {
      frameCount.textContent = String(frame.frame_index);
      triggered.textContent = frame.triggered ? "фронт пойман" : "AUTO-таймаут";
      rate.textContent = formatHz(frame.sample_rate_hz);
      points.textContent = String(frame.frame_samples);
      dropped.textContent = String(frame.dropped_samples);
      skipped.textContent = String(frame.skipped_frames);
      calibration.textContent = frame.calibration_used ? "по таблице АЦП" : "по номинальной шкале";
    },
  };
}

/** Показания измерений канала CH1 (Todo 10): чистый measureSeries +
 * форматтеры; null → «—» (нет измерения), никогда NaN. Порог фронта —
 * уровень триггера CH1 (или середина размаха без триггера). */
export interface ScopeMeasureView {
  readonly root: HTMLElement;
  applyFrame(frame: LiveFramePayload, levelV: number | null): void;
}

export function buildScopeMeasureSection(): ScopeMeasureView {
  const vpp = el("dd", { className: "t-mono lnt-scope-vpp", text: "—" });
  const vmax = el("dd", { className: "t-mono lnt-scope-vmax", text: "—" });
  const vmin = el("dd", { className: "t-mono lnt-scope-vmin", text: "—" });
  const rms = el("dd", { className: "t-mono lnt-scope-rms", text: "—" });
  const freq = el("dd", { className: "t-mono lnt-scope-freq", text: "—" });
  const period = el("dd", { className: "t-mono lnt-scope-period", text: "—" });
  const duty = el("dd", { className: "t-mono lnt-scope-duty", text: "—" });

  const row = (label: string, value: HTMLElement): Node[] => [
    el("dt", { className: "readout-label", text: label }),
    value,
  ];

  return {
    root: el("section", { className: "panel lnt-scope-section lnt-scope-measure" }, [
      el("div", { className: "panel-hd" }, [
        el("h3", { className: "panel-title", text: "Измерения CH1" }),
      ]),
      el("div", { className: "panel-bd" }, [
        el(
          "dl",
          { className: "readout-grid" },
          row("Vpp", vpp)
            .concat(row("Vmax", vmax))
            .concat(row("Vmin", vmin))
            .concat(row("VRMS", rms))
            .concat(row("f (фронт)", freq))
            .concat(row("T", period))
            .concat(row("D (высокий)", duty)),
        ),
        el("p", {
          className: "t-compact",
          text: "По отсчётам кадра CH1; АЦП 8 бит — уровни сырые, без калибровочных заявлений.",
        }),
      ]),
    ]),
    applyFrame(frame: LiveFramePayload, levelV: number | null): void {
      const m = measureSeries(frame.ch1, levelV);
      vpp.textContent = formatMeasurement(m.vppV, formatVoltsValue);
      vmax.textContent = formatMeasurement(m.vmaxV, formatVoltsValue);
      vmin.textContent = formatMeasurement(m.vminV, formatVoltsValue);
      rms.textContent = formatMeasurement(m.rmsV, formatVoltsValue);
      freq.textContent = formatMeasurement(m.frequencyHz, formatFrequencyValue);
      period.textContent = formatMeasurement(m.periodS, formatPeriodValue);
      duty.textContent = formatMeasurement(m.duty, formatDutyValue);
    },
  };
}

/** Баннер ошибки (role=alert): видимый русский текст, без подавления. */
export function errorBlock(text: string): HTMLElement {
  return el(
    "div",
    { className: "banner banner-inline lnt-scope-error", attrs: { role: "alert" } },
    [
      el("span", { className: "banner-glyph", text: "✕", attrs: { "aria-hidden": "true" } }),
      el("p", { className: "banner-msg", text }),
    ],
  );
}

function formatHz(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} МГц`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} кГц`;
  return `${Math.round(value)} Гц`;
}
