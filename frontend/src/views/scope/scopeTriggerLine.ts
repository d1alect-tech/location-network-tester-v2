/** Экранная линия триггера (задача 15, план (a)): DOM-оверлей поверх
 * .lnt-scope-viewport — номинальная шкала экрана ±5 В (та же пропорция,
 * что у paintScopeTrace: y = (0.5 − v/span)·h). Drag с hit-полосой 44 px
 * пишет СУЩЕСТВУЮЩЕЕ поле #lnt-scope-level нативным change (живой
 * слушатель scopeTrigger применяет триггер — валидация и POST без
 * дублирования); пока поле в фокусе, drag его не затирает (контракт
 * зоны-карты). Клавиатура на линии = степпер: ←/→/↓/↑ ±0,1,
 * PgUp/PgDn ±1, Home/End ∓/±5. Поле → линия и линия → поле синхронны;
 * при running истина сервиса перерисовывает линию (стрелка — за кадром);
 * dispose снимает всё. */

import type { LiveWatchHandle, LiveWatchHandlers } from "../../api/types-live";
import { el } from "../../components/primitives/dom";

/** Номинальный размах экрана: −5..+5 В (SCOPE_VOLTS_SPAN экрана). */
const VOLTS_SPAN = 10;
/** Высота hit-полосы вокруг линии: 44 px (прототип v1.html). */
const HIT_BAND_PX = 44;

export interface ScopeTriggerLineOptions {
  viewport: HTMLElement;
  field: HTMLInputElement;
  /** Истина сервиса: onState при running перерисовывает линию. */
  live?: { watchFrames(handlers: LiveWatchHandlers): LiveWatchHandle };
}

export interface ScopeTriggerLineHandle {
  dispose(): void;
}

function clampLevel(value: number, limit: number): number {
  return Math.max(-limit, Math.min(limit, value));
}

export function mountScopeTriggerLine(options: ScopeTriggerLineOptions): ScopeTriggerLineHandle {
  const { viewport, field } = options;
  let level = clampLevel(Number(field.value) || 0, VOLTS_SPAN / 2);
  let dragging = false;

  const line = el("div", {
    className: "lnt-scope-trig-line",
    attrs: {
      "data-trigger-line": "",
      tabindex: "0",
      role: "slider",
      "aria-label": "Уровень триггера, линия на экране",
      "aria-valuemin": "-5",
      "aria-valuemax": "5",
    },
  });
  const bar = el("span", { className: "lnt-scope-trig-line-bar" });
  const tag = el("span", {
    className: "lnt-scope-trig-line-tag",
    text: "ТРГ",
    attrs: { "aria-hidden": "true" },
  });
  line.append(bar, tag);
  viewport.append(line);

  function repaint(): void {
    line.setAttribute("aria-valuenow", String(level));
    line.setAttribute("aria-valuetext", `${level} В`);
    const height = viewport.getBoundingClientRect().height;
    if (height <= 0) return;
    const y = (0.5 - level / VOLTS_SPAN) * height;
    line.style.transform = `translateY(${y - HIT_BAND_PX / 2}px)`;
  }

  function writeField(value: number): void {
    // Контракт зоны: drag не пишет поле, пока оператор в нём печатает.
    if (document.activeElement === field) return;
    level = value;
    field.value = String(value);
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function onFieldInput(): void {
    const value = Number(field.value);
    if (field.value.trim() === "" || !Number.isFinite(value)) return;
    level = clampLevel(value, VOLTS_SPAN / 2);
    repaint();
  }

  function onPointerDown(event: PointerEvent): void {
    if (event.buttons !== 0 && event.button !== 0 && event.buttons !== 1) return;
    dragging = true;
    event.preventDefault();
    if (typeof line.setPointerCapture === "function") {
      try {
        line.setPointerCapture(event.pointerId);
      } catch {
        // Синтетический pointerId: флаг dragging ведёт drag (прототип core4).
      }
    }
  }

  function onPointerMove(event: PointerEvent): void {
    if (!dragging) return;
    const rect = viewport.getBoundingClientRect();
    if (rect.height <= 0) return;
    const volts = (0.5 - (event.clientY - rect.top) / rect.height) * VOLTS_SPAN;
    writeField(clampLevel(Math.round(volts * 100) / 100, VOLTS_SPAN / 2));
  }

  function onPointerEnd(event: PointerEvent): void {
    if (!dragging) return;
    dragging = false;
    if (typeof line.releasePointerCapture === "function") {
      try {
        line.releasePointerCapture(event.pointerId);
      } catch {
        // Захвата не было — нечего отпускать.
      }
    }
  }

  /** Клавиатура линии — эквивалент степпера уровня (v1.html). */
  function onKeyDown(event: KeyboardEvent): void {
    const steps: Record<string, number | "min" | "max"> = {
      ArrowUp: 0.1,
      ArrowRight: 0.1,
      ArrowDown: -0.1,
      ArrowLeft: -0.1,
      PageUp: 1,
      PageDown: -1,
      Home: "min",
      End: "max",
    };
    const step = steps[event.key];
    if (step === undefined) return;
    event.preventDefault();
    const next = step === "min" ? -VOLTS_SPAN / 2 : step === "max" ? VOLTS_SPAN / 2 : level + step;
    writeField(clampLevel(Math.round(next * 100) / 100, VOLTS_SPAN / 2));
  }

  line.addEventListener("pointerdown", onPointerDown);
  line.addEventListener("pointermove", onPointerMove);
  line.addEventListener("pointerup", onPointerEnd);
  line.addEventListener("pointercancel", onPointerEnd);
  line.addEventListener("keydown", onKeyDown);
  field.addEventListener("input", onFieldInput);
  field.addEventListener("change", onFieldInput);

  const stream = options.live?.watchFrames({
    onState: (state) => {
      // Истина сервиса — только при running; в покое поле есть истина.
      if (state.state === "running" && state.trigger !== null) {
        level = clampLevel(state.trigger.level_v, VOLTS_SPAN / 2);
        repaint();
      } else {
        onFieldInput();
      }
    },
    onConnection: () => undefined,
  });

  let observer: ResizeObserver | null = null;
  if (typeof ResizeObserver === "function") {
    observer = new ResizeObserver(() => repaint());
    observer.observe(viewport);
  }
  repaint();

  return {
    dispose: () => {
      observer?.disconnect();
      stream?.close();
      line.removeEventListener("pointerdown", onPointerDown);
      line.removeEventListener("pointermove", onPointerMove);
      line.removeEventListener("pointerup", onPointerEnd);
      line.removeEventListener("pointercancel", onPointerEnd);
      line.removeEventListener("keydown", onKeyDown);
      field.removeEventListener("input", onFieldInput);
      field.removeEventListener("change", onFieldInput);
      line.remove();
    },
  };
}
