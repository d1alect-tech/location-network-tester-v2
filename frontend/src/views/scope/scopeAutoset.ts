/** «Автосет» (задача 15, план (b)): пересчёт по последнему кадру — модель
 * flat.html:2585-2597 (Rigol AUToscale): В/дел — наименьшее окно, где
 * размах влезает в 80 % полэкрана (windowHalfVolts, закон директивы
 * 2026-10-19); уровень — середина размаха с зажимом ±5; частота — окно ≈ 3
 * периода (frame_samples·f/3, ближайшая из манифеста). Guards модели закрыты
 * эхом: список ТОЛЬКО реально изменённых параметров или честное
 * «Автонастройка: нечего менять» — молчаливых no-op нет. Всегда
 * перезапуск (кластер Run). Управление — только живыми слушателями DOM
 * (scopeControlState); собственная подписка на кадры (зона-карта §8.10),
 * закрытие в dispose. */

import type { LiveApi } from "../../api/client-live";
import type { LiveFramePayload } from "../../api/types-live";
import { el } from "../../components/primitives/dom";
import { applyScopeControlTargets, readScopeControlState } from "./scopeControlState";
import type { ScopeControlHosts, ScopeControlTargets } from "./scopeControlState";
import { measureSeries } from "./scopeMeasurements";
import { SCOPE_SAMPLE_RATES_HZ } from "./scopeRateField";
import { DEFAULT_SCOPE_SETTINGS, VDIV_STEPS, windowHalfVolts } from "./scopeScale";
import { TRIGGER_LEVEL_LIMIT_V } from "./scopeTrigger";

export interface ScopeAutosetOptions {
  /** Группа [data-action="autoset"] зоны ИЗМЕР (кнопка живёт здесь). */
  host: HTMLElement;
  hosts: ScopeControlHosts;
  /** Собственная подписка на кадры: пересчёт по последнему кадру. */
  live: LiveApi;
  /** Перезапуск запуска: кластер (stop → свободен → run, либо run). */
  restart: () => void;
  /** Слот эха в статус-зоне полосы (10 px, эллипсис). */
  echo: HTMLElement;
}

export interface ScopeAutosetHandle {
  dispose(): void;
}

/** Цели по кадру; guard-случаи: нет кадра — безопасные значения, плоский
 * сигнал (vpp null) — только триггерные дефолты. */
function computeTargets(
  frame: LiveFramePayload | null,
  probe: number,
): Partial<ScopeControlTargets> {
  const targets: Partial<ScopeControlTargets> = {
    mode: "auto",
    source: "ch1",
    slope: "rising",
  };
  if (frame === null) {
    targets.vdiv = DEFAULT_SCOPE_SETTINGS.vDiv;
    targets.levelV = 0;
    return targets;
  }
  const m = measureSeries(frame.ch1, null);
  if (m.vppV === null) return targets;
  const peak = Math.max(Math.abs(m.vmaxV ?? 0), Math.abs(m.vminV ?? 0));
  // Фолбэк «сигнал слишком велик» (r4-final f2): самое широкое окно экрана
  // (наибольший windowHalfVolts). Подбор — НАИМЕНЬШИЙ влезающий шаг, выбор
  // не зависит от порядка VDIV_STEPS (мин по значению, не «последний
  // удовлетворяющий» — перевёрнутый список ловушку вскрывает).
  const widest = VDIV_STEPS.reduce((w, v) =>
    windowHalfVolts(v, probe) > windowHalfVolts(w, probe) ? v : w,
  );
  let pick: number | null = null;
  for (const v of VDIV_STEPS) {
    if (peak <= 0.8 * windowHalfVolts(v, probe) && (pick === null || v < pick)) pick = v;
  }
  targets.vdiv = pick ?? widest;
  targets.levelV = Math.max(
    -TRIGGER_LEVEL_LIMIT_V,
    Math.min(TRIGGER_LEVEL_LIMIT_V, ((m.vmaxV ?? 0) + (m.vminV ?? 0)) / 2),
  );
  const frequency = m.frequencyHz ?? 0;
  if (frequency > 0) {
    const target = (frame.frame_samples * frequency) / 3;
    let nearest = SCOPE_SAMPLE_RATES_HZ[0] ?? 0;
    for (const rate of SCOPE_SAMPLE_RATES_HZ) {
      if (Math.abs(rate - target) < Math.abs(nearest - target)) nearest = rate;
    }
    targets.rateHz = nearest;
  }
  return targets;
}

export function mountScopeAutoset(options: ScopeAutosetOptions): ScopeAutosetHandle {
  let lastFrame: LiveFramePayload | null = null;
  const button = el("button", {
    className: "lnt-live-action-btn",
    text: "Автосет",
    attrs: { type: "button" },
  });
  options.host.append(button);

  const stream = options.live.watchFrames({
    onFrame: (frame) => {
      lastFrame = frame;
    },
    onState: () => undefined,
    onConnection: () => undefined,
  });

  function run(): void {
    const state = readScopeControlState(options.hosts);
    const targets = computeTargets(lastFrame, state.probe ?? 1);
    const changes = applyScopeControlTargets(options.hosts, targets);
    // Клик опции частоты фокусирует чип — фокус возвращается кнопке.
    button.focus();
    options.echo.textContent =
      changes.length === 0
        ? "Автонастройка: нечего менять"
        : `Автонастройка: ${changes.map((change) => change.label).join(", ")}`;
    options.echo.hidden = false;
    // Всегда перезапуск: Run подхватит новые значения (guard-случаи тоже).
    options.restart();
  }

  button.addEventListener("click", run);

  return {
    dispose: () => {
      button.removeEventListener("click", run);
      stream.close();
      button.remove();
    },
  };
}
