/** Селекторы SA-конфигурации (Todo 14): RBW (10/30/50/100/300 Гц), окно
 * (пять известных — паритет MARKER_WINDOW_OPTIONS инспекции), детектор
 * (только KNOWN_DETECTORS; выборки нет), полоса start/stop. Геометрия
 * полосы и Найквист проверяет бэкенд (422) — локально отсекается только
 * явный мусор (пустая/отрицательная полоса). Без захвата панель
 * стейджится до запуска; на ходу изменения уходят POST /api/live/config. */

import type { LiveSaConfig, LiveSaDetector, LiveSaWindow } from "../../api/types-live";
import { el, nextId } from "../../components/primitives/dom";

/** Паритет RBW_OPTIONS_HZ бэкенда (psd/windows.py) и MARKER_RBW_OPTIONS. */
export const SA_RBW_OPTIONS = [10, 30, 50, 100, 300] as const;
/** Паритет KNOWN_WINDOWS бэкенда и MARKER_WINDOW_OPTIONS инспекции. */
export const SA_WINDOW_OPTIONS = [
  "hann",
  "flattop",
  "kaiser",
  "blackman",
  "rect",
] as const satisfies readonly LiveSaWindow[];
export const SA_WINDOW_LABELS: Record<LiveSaWindow, string> = {
  hann: "Ханн",
  flattop: "Флэт-топ",
  kaiser: "Кайзер",
  blackman: "Блэкман",
  rect: "Прямоугольное",
};
/** Паритет KNOWN_DETECTORS бэкенда (psd/models.py); sample-детектора нет. */
export const SA_DETECTOR_OPTIONS = [
  "mean",
  "rms",
  "max-hold",
  "min-hold",
] as const satisfies readonly LiveSaDetector[];
export const SA_DETECTOR_LABELS: Record<LiveSaDetector, string> = {
  mean: "Среднее",
  rms: "RMS",
  "max-hold": "Max-hold",
  "min-hold": "Min-hold",
};

export interface SaConfigSelectors {
  readonly root: HTMLElement;
  /** Текущая конфигурация; null — панель невалидна (полоса мусорная). */
  config(): LiveSaConfig | null;
}

export interface SaSelectorOptions {
  initial: LiveSaConfig;
  /** Валидное изменение (каждое — потенциальный config на ходу). */
  onChange(config: LiveSaConfig): void;
}

function parseEdge(raw: string): number | null {
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

export function buildSaConfigSection(options: SaSelectorOptions): SaConfigSelectors {
  const rbwId = nextId("sa-rbw");
  const rbwSelect = el("select", {
    className: "ctl",
    attrs: { id: rbwId, "data-sa-rbw": "" },
  });
  for (const value of SA_RBW_OPTIONS) {
    rbwSelect.append(el("option", { text: `${value} Гц`, attrs: { value: String(value) } }));
  }
  rbwSelect.value = String(options.initial.rbw_hz);

  const windowId = nextId("sa-window");
  const windowSelect = el("select", {
    className: "ctl",
    attrs: { id: windowId, "data-sa-window": "" },
  });
  for (const value of SA_WINDOW_OPTIONS) {
    windowSelect.append(el("option", { text: SA_WINDOW_LABELS[value], attrs: { value: value } }));
  }
  windowSelect.value = options.initial.window;

  const detectorId = nextId("sa-detector");
  const detectorSelect = el("select", {
    className: "ctl",
    attrs: { id: detectorId, "data-sa-detector": "" },
  });
  for (const value of SA_DETECTOR_OPTIONS) {
    detectorSelect.append(
      el("option", { text: SA_DETECTOR_LABELS[value], attrs: { value: value } }),
    );
  }
  detectorSelect.value = options.initial.detector;

  const lowId = nextId("sa-band-low");
  const lowInput = el("input", {
    className: "ctl",
    attrs: {
      id: lowId,
      "data-sa-band-low": "",
      type: "number",
      inputmode: "decimal",
      min: "0",
      step: "1000",
      value: String(options.initial.band_low_hz),
    },
  });
  const highId = nextId("sa-band-high");
  const highInput = el("input", {
    className: "ctl",
    attrs: {
      id: highId,
      "data-sa-band-high": "",
      type: "number",
      inputmode: "decimal",
      min: "0",
      step: "1000",
      value: String(options.initial.band_high_hz),
    },
  });
  const error = el("p", {
    className: "lnt-sa-error-text",
    text: "",
    attrs: { role: "alert" },
  });
  error.hidden = true;

  function current(): LiveSaConfig | null {
    const low = parseEdge(lowInput.value);
    const high = parseEdge(highInput.value);
    if (low === null || high === null || high <= low) return null;
    return {
      rbw_hz: Number(rbwSelect.value),
      window: windowSelect.value as LiveSaWindow,
      band_low_hz: low,
      band_high_hz: high,
      detector: detectorSelect.value as LiveSaDetector,
    };
  }

  function commit(): void {
    const config = current();
    if (config === null) {
      error.hidden = false;
      error.textContent = "Полоса пуста: начало должно быть ≥ 0 и меньше конца.";
      return;
    }
    error.hidden = true;
    error.textContent = "";
    options.onChange(config);
  }

  for (const node of [rbwSelect, windowSelect, detectorSelect, lowInput, highInput]) {
    node.addEventListener("change", commit);
  }

  const root = el("section", { className: "panel lnt-sa-section lnt-sa-config" }, [
    el("div", { className: "panel-hd" }, [
      el("h3", { className: "panel-title", text: "Настройки анализа" }),
    ]),
    el("div", { className: "panel-bd" }, [
      el("div", { className: "lnt-sa-config-grid" }, [
        el("label", { className: "lnt-sa-field", text: "RBW", attrs: { for: rbwId } }, [rbwSelect]),
        el("label", { className: "lnt-sa-field", text: "Окно", attrs: { for: windowId } }, [
          windowSelect,
        ]),
        el("label", { className: "lnt-sa-field", text: "Детектор", attrs: { for: detectorId } }, [
          detectorSelect,
        ]),
        el(
          "label",
          { className: "lnt-sa-field", text: "Начало полосы, Гц", attrs: { for: lowId } },
          [lowInput],
        ),
        el(
          "label",
          { className: "lnt-sa-field", text: "Конец полосы, Гц", attrs: { for: highId } },
          [highInput],
        ),
      ]),
      el("p", {
        className: "t-compact",
        text: "Границы полосы против Найквиста проверяет сервер (422 — панель покажет ошибку).",
      }),
      error,
    ]),
  ]);

  return {
    root,
    config(): LiveSaConfig | null {
      return current();
    },
  };
}
