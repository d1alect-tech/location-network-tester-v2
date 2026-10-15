/** Статус-модель вкладки «Спектроанализатор» (задача 16, зона-карта 13):
 * staged-реестр полосы SA — полоса и RBW стейджируются ТОЛЬКО при idle
 * (на ходу селекторы уходят конфигом saWorkspace: onChange → configSa →
 * POST /api/live/config — горячие, стейджингом не помечаются). Маркеры
 * «→ …» [data-live-mark] у контролов, строка «применится при следующем
 * запуске: …» [data-staged-line], pendingCount → бейдж run-кластера.
 * Переход в running переводит baseline к staged-целям и гасит маркеры
 * (снапшот применённого: Run читает селекторы воркспейса, ensureSaConfig
 * уводит их в прибор); подписка live-источника закрывается dispose —
 * вместе со слушателями хостов. Зеркало scopeStatus без триггер-ключей:
 * SA-триггера нет, состояние сервиса печатает saWorkspace. */

import type { LiveStatePayload } from "../../api/types-live";
import { DEFAULT_LIVE_SA_CONFIG } from "../../api/types-live";
import type { LiveStateSource } from "../../components/liveStrip/liveStrip";
import { el } from "../../components/primitives/dom";
import { formatHz } from "./saUnits";

const KEY_LABELS: Readonly<Record<string, string>> = {
  span: "Полоса",
  rbw: "RBW",
};

/** Полоса полей зоны ПОЛОСА: значение-строка «low–high» + подпись. */
function readSpan(host: HTMLElement): { value: string; text: string } | null {
  const low = host.querySelector<HTMLInputElement>("[data-sa-band-low]");
  const high = host.querySelector<HTMLInputElement>("[data-sa-band-high]");
  if (low === null || high === null) return null;
  const lowHz = Number(low.value);
  const highHz = Number(high.value);
  if (!Number.isFinite(lowHz) || !Number.isFinite(highHz) || lowHz < 0 || highHz <= lowHz) {
    // Мусорная полоса не стейджится: валидацию и ошибку держит воркспейс.
    return null;
  }
  return {
    value: `${lowHz}–${highHz}`,
    text: `${formatHz(lowHz)}–${formatHz(highHz)}`,
  };
}

function formatRbw(value: string): string {
  return `${value} Гц`;
}

export interface SaStatusHosts {
  /** Группа зоны ПОЛОСА (оба поля со степперами внутри). */
  span: HTMLElement;
  /** Группа зоны RBW (сегменты [data-sa-rbw]). */
  rbw: HTMLElement;
}

export interface SaStatusOptions {
  live: LiveStateSource;
  hosts: SaStatusHosts;
  /** pendingCount staged-реестра → бейдж run-кластера. */
  onPendingChange?: (count: number) => void;
}

export interface SaStatusHandle {
  /** Строка «применится при следующем запуске: …» (роль статуса). */
  readonly stagedLine: HTMLElement;
  dispose(): void;
}

export function mountSaStatus(options: SaStatusOptions): SaStatusHandle {
  const baseline: Record<string, string> = {
    span: `${DEFAULT_LIVE_SA_CONFIG.band_low_hz}–${DEFAULT_LIVE_SA_CONFIG.band_high_hz}`,
    rbw: String(DEFAULT_LIVE_SA_CONFIG.rbw_hz),
  };
  const staged = new Map<string, { value: string; text: string }>();
  let running = false;

  const stagedLine = el("p", {
    className: "lnt-live-staged-line",
    attrs: { "data-staged-line": "", role: "status", hidden: "" },
  });

  const markers = new Map<string, HTMLElement>();
  for (const key of ["span", "rbw"]) {
    const marker = el("span", {
      className: "lnt-live-mark",
      attrs: { "data-live-mark": key, hidden: "", "aria-hidden": "true" },
    });
    options.hosts[key as "span" | "rbw"].append(marker);
    markers.set(key, marker);
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
  }

  function markStaged(key: string, value: string, text: string): void {
    if (value === baseline[key]) staged.delete(key);
    else staged.set(key, { value, text });
    render();
  }

  const listeners: Array<[HTMLElement, string, (event: Event) => void]> = [];

  // RBW: клик сегмента — staged-цель при idle, на ходу — горячий конфиг.
  const rbwHandler = (event: Event): void => {
    if (running) return;
    const target = event.target instanceof HTMLElement ? event.target.closest("button") : null;
    const value = target?.getAttribute("data-value");
    if (value === null || value === undefined) return;
    markStaged("rbw", value, formatRbw(value));
  };
  options.hosts.rbw.addEventListener("click", rbwHandler);
  listeners.push([options.hosts.rbw, "click", rbwHandler]);

  // Полоса: нативный change полей (степперы пишут тем же событием).
  const spanHandler = (): void => {
    if (running) return;
    const span = readSpan(options.hosts.span);
    if (span === null) return;
    markStaged("span", span.value, span.text);
  };
  options.hosts.span.addEventListener("change", spanHandler);
  listeners.push([options.hosts.span, "change", spanHandler]);

  const stream = options.live.watchFrames({
    onConnection: () => undefined,
    onState: (state: LiveStatePayload) => {
      const nowRunning = state.state === "running";
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
    dispose: () => {
      for (const [host, type, handler] of listeners) host.removeEventListener(type, handler);
      stream.close();
    },
  };
}
