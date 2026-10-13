/** Статические секции вкладки «Спектроанализатор» (Todo 14): статус
 * прибора и владения (Run/Stop, как scopeSections) и показания потока SA
 * (свип, метаданные трассы, топ-пик, счётчик свипов склада). Панельная
 * система V6 (kit.css §5.2): section.panel > .panel-hd/.panel-title +
 * .panel-bd, показания — .readout-grid. Только построение DOM из готовых
 * данных и форматирование: без сети, без состояния, без слушателей. */

import type { LiveInstrumentState, LiveSpectrumPayload } from "../../api/types-live";
import { el } from "../../components/primitives/dom";

export const LIVE_STATE_TEXT: Record<LiveInstrumentState, string> = {
  idle: "не запущен",
  running: "запущен",
  stopped: "остановлен",
};

export interface SaStatusView {
  readonly root: HTMLElement;
  readonly deviceHost: HTMLElement;
  readonly stateLine: HTMLElement;
  readonly simBadge: HTMLElement;
  readonly busyLine: HTMLElement;
  readonly errorHost: HTMLElement;
  readonly runButton: HTMLButtonElement;
  readonly stopButton: HTMLButtonElement;
}

export function buildSaStatusSection(): SaStatusView {
  const deviceHost = el("div", {
    className: "lnt-sa-device",
    attrs: { role: "status" },
  });
  const stateLine = el("p", {
    className: "t-body lnt-sa-state",
    text: "Живой режим: запрос статуса…",
  });
  const simBadge = el("span", { className: "lnt-sa-sim-badge", text: "Симуляция" });
  simBadge.hidden = true;
  const busyLine = el("p", { className: "t-compact lnt-sa-busy", text: "" });
  busyLine.hidden = true;
  const runButton = el("button", {
    className: "btn",
    text: "Запустить",
    attrs: { type: "button", id: "lnt-sa-run" },
  });
  const stopButton = el("button", {
    className: "btn btn-secondary",
    text: "Остановить",
    attrs: { type: "button", id: "lnt-sa-stop" },
  });
  stopButton.disabled = true;
  const errorHost = el("div", { className: "lnt-sa-error-host" });

  return {
    root: el("section", { className: "panel lnt-sa-section lnt-sa-status" }, [
      el("div", { className: "panel-hd" }, [
        el("h3", { className: "panel-title", text: "Прибор" }),
      ]),
      el("div", { className: "panel-bd" }, [
        deviceHost,
        el("div", { className: "lnt-sa-state-row" }, [stateLine, simBadge]),
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

export interface SaReadoutView {
  readonly root: HTMLElement;
  readonly connection: HTMLElement;
  applySpectrum(payload: LiveSpectrumPayload, sweeps: number): void;
}

export function buildSaReadoutSection(): SaReadoutView {
  const sweep = el("dd", { className: "t-mono lnt-sa-sweep", text: "—" });
  const sweeps = el("dd", { className: "t-compact lnt-sa-sweeps", text: "—" });
  const rbw = el("dd", { className: "t-compact lnt-sa-rbw", text: "—" });
  const resolution = el("dd", { className: "t-compact lnt-sa-resolution", text: "—" });
  const enbw = el("dd", { className: "t-compact lnt-sa-enbw", text: "—" });
  const window = el("dd", { className: "t-compact lnt-sa-window", text: "—" });
  const peak = el("dd", { className: "t-mono lnt-sa-peak", text: "—" });
  const connection = el("p", {
    className: "t-compact lnt-sa-connection",
    text: "подключение…",
    attrs: { role: "status" },
  });

  const row = (label: string, value: HTMLElement): Node[] => [
    el("dt", { className: "readout-label", text: label }),
    value,
  ];

  return {
    root: el("section", { className: "panel lnt-sa-section lnt-sa-readout" }, [
      el("div", { className: "panel-hd" }, [el("h3", { className: "panel-title", text: "Поток" })]),
      el("div", { className: "panel-bd" }, [
        el(
          "dl",
          { className: "readout-grid" },
          row("свип", sweep)
            .concat(row("свипов в складе", sweeps))
            .concat(row("RBW", rbw))
            .concat(row("разрешение", resolution))
            .concat(row("ENBW", enbw))
            .concat(row("окно", window))
            .concat(row("топ-пик", peak)),
        ),
        el("p", {
          className: "t-compact",
          text: "Уровни — дБ (отн. 1 В²/Гц) по проводу; трассы считаются на клиенте, сервер их не хранит.",
        }),
        connection,
      ]),
    ]),
    connection,
    applySpectrum(payload, sweepCount): void {
      sweep.textContent = String(payload.frame_index);
      sweeps.textContent = String(sweepCount);
      rbw.textContent = formatHz(payload.meta.rbw);
      resolution.textContent = formatHz(payload.meta.resolution);
      enbw.textContent = formatHz(payload.meta.enbw);
      window.textContent = payload.meta.window;
      const top = payload.peaks[0];
      peak.textContent =
        top === undefined ? "—" : `${formatHz(top.frequency_hz)} · ${top.level_db.toFixed(1)} дБ`;
    },
  };
}

/** Баннер ошибки (role=alert): видимый русский текст, без подавления. */
export function errorBlock(text: string): HTMLElement {
  return el("div", { className: "banner banner-inline lnt-sa-error", attrs: { role: "alert" } }, [
    el("span", { className: "banner-glyph", text: "✕", attrs: { "aria-hidden": "true" } }),
    el("p", { className: "banner-msg", text }),
  ]);
}

function formatHz(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} МГц`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} кГц`;
  return `${Math.round(value)} Гц`;
}
