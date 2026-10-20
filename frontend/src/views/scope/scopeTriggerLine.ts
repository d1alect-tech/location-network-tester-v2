/** Экранная линия триггера (задача 15, план (a)): DOM-оверлей поверх
 * .lnt-scope-viewport — окно экрана ±4·В/дел·probe (закон директивы
 * 2026-10-19: y = (0.5 − v/(2·windowHalf))·h; дефолт windowHalf = 5 В —
 * номинальная шкала дефолтного запуска). Drag с hit-полосой 44 px
 * пишет СУЩЕСТВУЮЩЕЕ поле #lnt-scope-level нативным change (живой
 * слушатель scopeTrigger применяет триггер — валидация и POST без
 * дублирования); пока поле в фокусе, drag его не затирает (контракт
 * зоны-карты). Клавиатура на линии = степпер: ←/→/↓/↑ ±0,1,
 * PgUp/PgDn ±1, Home/End ∓/±5. Поле → линия и линия → поле синхронны;
 * при running истина сервиса перерисовывает линию (стрелка — за кадром,
 * в активном drag — нет); drag-POST коалесцирован: change не чаще раза
 * в 100 мс и финалом по settle (r4-final f1); dispose снимает всё,
 * финализируя отложенный шаг. refresh() переставляет линию под сменившееся
 * окно (В/дел/пробник) — полоса зовёт его по клику зон ВЕРТ. */

import type { LiveWatchHandle, LiveWatchHandlers } from "../../api/types-live";
import { el } from "../../components/primitives/dom";

/** Домен поля уровня (серверный предел триггера): ±5 В. */
const FIELD_LIMIT_V = 5;
/** Дефолтная половина окна экрана, В: ±5 — номинал дефолтного запуска. */
const NOMINAL_WINDOW_HALF_V = 5;
/** Высота hit-полосы вокруг линии: 44 px (прототип v1.html). */
const HIT_BAND_PX = 44;

export interface ScopeTriggerLineOptions {
  viewport: HTMLElement;
  field: HTMLInputElement;
  /** Истина сервиса: onState при running перерисовывает линию. */
  live?: { watchFrames(handlers: LiveWatchHandlers): LiveWatchHandle };
  /** Половина окна экрана, В (±4·В/дел·probe); дефолт — номинал ±5. */
  windowHalfVolts?: () => number;
}

export interface ScopeTriggerLineHandle {
  /** Переставить линию под сменившееся окно (В/дел/пробник). */
  refresh(): void;
  dispose(): void;
}

/** Каденс drag-эмитов: не чаще раза в 100 мс, финал — по settle. */
const DRAG_EMIT_MS = 100;

function clampLevel(value: number, limit: number): number {
  return Math.max(-limit, Math.min(limit, value));
}

export function mountScopeTriggerLine(options: ScopeTriggerLineOptions): ScopeTriggerLineHandle {
  const { viewport, field } = options;
  const windowHalf = options.windowHalfVolts ?? (() => NOMINAL_WINDOW_HALF_V);
  let level = clampLevel(Number(field.value) || 0, FIELD_LIMIT_V);
  let dragging = false;
  /** Drag-коалесценция (r4-final f1): не-NULL — финал ждёт эмита. */
  let dragPending: number | null = null;
  let dragEmitTimer: ReturnType<typeof setTimeout> | null = null;

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
    const y = (0.5 - level / (2 * windowHalf())) * height;
    line.style.transform = `translateY(${y - HIT_BAND_PX / 2}px)`;
  }

  function writeField(value: number): void {
    // Контракт зоны: drag не пишет поле, пока оператор в нём печатает.
    if (document.activeElement === field) return;
    level = value;
    field.value = String(value);
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /** Эмит коалесцированного change: значение перезаписывается в поле —
   * heartbeat мог откатить текст между шагом и эмитом, финал обязан уйти
   * точным. */
  function emitDragChange(): void {
    if (dragPending === null) return;
    field.value = String(dragPending);
    dragPending = null;
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /** Drag-запись: поле и линия живые каждый шаг, change — коалесцирован
   * (первый шаг открывает окно 100 мс, финал — по settle). */
  function writeFieldDragged(value: number): void {
    if (document.activeElement === field) return;
    level = value;
    field.value = String(value);
    dragPending = value;
    repaint();
    if (dragEmitTimer === null) {
      dragEmitTimer = setTimeout(() => {
        dragEmitTimer = null;
        emitDragChange();
      }, DRAG_EMIT_MS);
    }
  }

  /** Settle (pointerup/pointercancel/dispose): финал уходит немедленно. */
  function flushDragChange(): void {
    if (dragEmitTimer !== null) {
      clearTimeout(dragEmitTimer);
      dragEmitTimer = null;
    }
    emitDragChange();
  }

  function onFieldInput(): void {
    const value = Number(field.value);
    if (field.value.trim() === "" || !Number.isFinite(value)) return;
    level = clampLevel(value, FIELD_LIMIT_V);
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
    const volts = (0.5 - (event.clientY - rect.top) / rect.height) * (2 * windowHalf());
    writeFieldDragged(clampLevel(Math.round(volts * 100) / 100, FIELD_LIMIT_V));
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
    // Settle: финальный уровень уходит немедленно, без окна таймера.
    flushDragChange();
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
    const next = step === "min" ? -FIELD_LIMIT_V : step === "max" ? FIELD_LIMIT_V : level + step;
    writeField(clampLevel(Math.round(next * 100) / 100, FIELD_LIMIT_V));
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
      // Активный drag владеет линией: SSE-истина вернётся по settle.
      if (dragging) return;
      // Истина сервиса — только при running; в покое поле есть истина.
      if (state.state === "running" && state.trigger !== null) {
        level = clampLevel(state.trigger.level_v, FIELD_LIMIT_V);
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
    refresh: repaint,
    dispose: () => {
      // Финал активного drag не теряется при демонтаже полосы.
      flushDragChange();
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
