/** Статус-модель вкладки «Осциллограф» (задача 14, зона-карта 13):
 * staged-реестр полосы — В/дел/пробник/частота стейджируются всегда (уходят
 * со следующим Run), триггер (режим/источник/фронт) — только при idle (на
 * ходу он горячий: конфиг уходит живыми слушателями воркспейса). Маркеры
 * «→ …» [data-live-mark] у контролов, глобальная строка «применится при
 * следующем запуске: …» [data-staged-line], pendingCount → бейдж run-кластера,
 * индикатор тайминга триггера [data-trig-state] «в приборе» / «при
 * запуске». Переход в running переводит baseline к staged-целям и гасит
 * маркеры (снапшот применённого); подписка live-источника закрывается
 * dispose — вместе со слушателями хостов. */

import type { LiveStatePayload } from "../../api/types-live";
import { DEFAULT_LIVE_START_REQUEST } from "../../api/types-live";
import { paintLiveChip } from "../../components/liveStrip/liveChip";
import type { LiveStateSource } from "../../components/liveStrip/liveStrip";
import { el } from "../../components/primitives/dom";
import { rateLabelHz } from "./scopeRateField";
import { DEFAULT_SCOPE_SETTINGS, formatVDiv } from "./scopeScale";

const KEY_LABELS: Readonly<Record<string, string>> = {
  vdiv: "В/дел",
  probe: "Пробник",
  rate: "Частота",
  trigmode: "Триггер",
  trigsource: "Источник",
  trigslope: "Фронт",
};

/** Горячий контур: триггер на ходу уходит конфигом — стейджинга нет. */
const TRIG_KEYS = new Set(["trigmode", "trigsource", "trigslope"]);

const FORMATS: Readonly<Record<string, (value: string) => string>> = {
  vdiv: (value) => formatVDiv(Number(value)),
  probe: (value) => `×${value}`,
  rate: (value) => rateLabelHz(Number(value)),
};

export interface ScopeStatusHosts {
  vdiv: HTMLElement;
  probe: HTMLElement;
  rate: HTMLElement;
  trigMode: HTMLElement;
  trigSource: HTMLElement;
  trigSlope: HTMLElement;
}

export interface ScopeStatusOptions {
  live: LiveStateSource;
  hosts: ScopeStatusHosts;
  /** pendingCount staged-реестра → бейдж run-кластера. */
  onPendingChange?: (count: number) => void;
}

export interface ScopeStatusHandle {
  /** Строка «применится при следующем запуске: …» (роль статуса). */
  readonly stagedLine: HTMLElement;
  /** Индикатор тайминга триггера «в приборе» / «при запуске». */
  readonly trigState: HTMLElement;
  dispose(): void;
}

interface HostBinding {
  host: HTMLElement;
  key: string;
  attr: string;
  format?: (value: string) => string;
}

export function mountScopeStatus(options: ScopeStatusOptions): ScopeStatusHandle {
  const baseline: Record<string, string> = {
    vdiv: String(DEFAULT_SCOPE_SETTINGS.vDiv),
    probe: String(DEFAULT_LIVE_START_REQUEST.ch1_probe_multiplier),
    rate: String(DEFAULT_LIVE_START_REQUEST.sample_rate_hz),
    trigmode: DEFAULT_LIVE_START_REQUEST.trigger.mode,
    trigsource: DEFAULT_LIVE_START_REQUEST.trigger.source,
    trigslope: DEFAULT_LIVE_START_REQUEST.trigger.slope,
  };
  const staged = new Map<string, { value: string; text: string }>();
  let running = false;

  const stagedLine = el("p", {
    className: "lnt-live-staged-line",
    attrs: { "data-staged-line": "", role: "status", hidden: "" },
  });
  const trigState = el("span", {
    className: "lnt-live-trig-state",
    attrs: { "data-trig-state": "", "data-readonly": "" },
    text: "при запуске",
  });

  const bindings: HostBinding[] = [
    { host: options.hosts.vdiv, key: "vdiv", attr: "data-value", format: FORMATS.vdiv },
    { host: options.hosts.probe, key: "probe", attr: "data-value", format: FORMATS.probe },
    { host: options.hosts.rate, key: "rate", attr: "data-value", format: FORMATS.rate },
    { host: options.hosts.trigMode, key: "trigmode", attr: "data-trigger-mode" },
    { host: options.hosts.trigSource, key: "trigsource", attr: "data-trigger-source" },
    { host: options.hosts.trigSlope, key: "trigslope", attr: "data-trigger-slope" },
  ];
  const markers = new Map<string, HTMLElement>();
  for (const binding of bindings) {
    const marker = el("span", {
      className: "lnt-live-mark",
      attrs: { "data-live-mark": binding.key, hidden: "", "aria-hidden": "true" },
    });
    binding.host.append(marker);
    markers.set(binding.key, marker);
  }

  function render(): void {
    for (const [key, marker] of markers) {
      const entry = staged.get(key);
      marker.textContent = entry === undefined ? "" : `→ ${entry.text}`;
      marker.hidden = entry === undefined;
    }
    const parts = [...staged].map(([key, entry]) => `${KEY_LABELS[key] ?? key} ${entry.text}`);
    stagedLine.textContent =
      parts.length === 0 ? "" : `применится при следующем запуске: ${parts.join(", ")}`;
    stagedLine.hidden = parts.length === 0;
    options.onPendingChange?.(staged.size);
    paintLiveChip(options.hosts.vdiv, baseline.vdiv ?? null, staged.get("vdiv")?.value ?? null);
    paintLiveChip(options.hosts.rate, baseline.rate ?? null, staged.get("rate")?.value ?? null);
  }

  function markStaged(key: string, value: string, text: string): void {
    if (value === baseline[key]) staged.delete(key);
    else staged.set(key, { value, text });
    render();
  }

  const listeners: Array<[HTMLElement, (event: Event) => void]> = [];
  for (const binding of bindings) {
    const handler = (event: Event): void => {
      if (TRIG_KEYS.has(binding.key) && running) return;
      const target = event.target instanceof HTMLElement ? event.target.closest("button") : null;
      if (target === null) return;
      const value = target.getAttribute(binding.attr);
      if (value === null) return;
      const text =
        binding.format !== undefined ? binding.format(value) : (target.textContent ?? "");
      markStaged(binding.key, value, text);
    };
    binding.host.addEventListener("click", handler);
    listeners.push([binding.host, handler]);
  }

  const stream = options.live.watchFrames({
    onConnection: () => undefined,
    onState: (state: LiveStatePayload) => {
      const nowRunning = state.state === "running";
      trigState.textContent = nowRunning ? "в приборе" : "при запуске";
      if (nowRunning && !running) {
        // Снапшот применённого: staged-цели ушли в прибор — маркеры гаснут.
        for (const [key, entry] of staged) baseline[key] = entry.value;
        staged.clear();
        render();
      }
      running = nowRunning;
    },
  });

  render();
  return {
    stagedLine,
    trigState,
    dispose: () => {
      for (const [host, handler] of listeners) host.removeEventListener("click", handler);
      stream.close();
    },
  };
}
