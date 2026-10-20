/** Нулевые линии каналов (директива владельца 2026-10-19): ручки «1»/«2» на
 * левой кромке фигуры развёртки — drag перемещает 0 В КАЖДОГО канала по
 * отдельности (сдвиг ОТОБРАЖЕНИЯ: измерения и триггер считаются по payload
 * и сдвига не видят). Паттерн scopeCursorDrag: hit по свежей геометрии,
 * pointer-capture на фигуре, стрелки на ручке — шаг ±деление/20, двойной
 * клик — сброс канала в 0 В. Арбитраж указателей: ручка слушает target-фазу
 * на самой себе (stopPropagation гасит листовые слушатели фигуры — drag
 * курсоров не видит жеста), кромка В/дел (capture-фаза на корне воркспейса)
 * выше — её полоса у верхней кромки с ручками не пересекается. repaint()
 * переставляет ручки под живую геометрию (кадр/ресайз/смена В/дел). */

import { el } from "../../components/primitives/dom";

export type ScopeGroundChannel = "ch1" | "ch2";

export interface ScopeGroundLineOptions {
  figure: HTMLElement;
  read(): { ch1V: number; ch2V: number };
  write(channel: ScopeGroundChannel, volts: number): void;
  /** Половина окна экрана, В — зажим ручек внутри сетки. */
  windowHalf(): number;
}

export interface ScopeGroundLineHandle {
  /** Переставить ручки под живую геометрию (кадр/ресайз/смена В/дел). */
  repaint(): void;
  dispose(): void;
}

/** Высота ручки, px (a11y-таргет 44 держит ширина фигуры + tabindex). */
const HANDLE_PX = 44;
/** Шаг клавиатуры: деление/20 (окно/8 → ±окно/160 за нажатие). */
const KEY_STEP_DIVISIONS = 80;

/** Квантование по шагу клавиатуры: НЕ фиксированные 1 мВ — на 10 мВ/дел
 *  половина шага 0.5 мВ иначе округлялась в -0 и стрелка «вниз» не
 *  двигала линию. */
function quantize(value: number, step: number): number {
  const snapped = Math.round(value / step) * step;
  return Object.is(snapped, -0) ? 0 : Number(snapped.toFixed(6));
}

export function mountScopeGroundLine(options: ScopeGroundLineOptions): ScopeGroundLineHandle {
  const { figure } = options;
  const groundOf = (channel: ScopeGroundChannel): number =>
    channel === "ch1" ? options.read().ch1V : options.read().ch2V;

  const handles: Record<ScopeGroundChannel, HTMLButtonElement> = {
    ch1: groundHandle("ch1", "1", "Нулевая линия CH1"),
    ch2: groundHandle("ch2", "2", "Нулевая линия CH2"),
  };
  figure.append(handles.ch1, handles.ch2);
  let dragging: ScopeGroundChannel | null = null;
  let pointerId: number | null = null;
  // Свой счётчик двойного нажима: PointerEvent.detail в Chromium всегда 0,
  // а preventDefault на pointerdown гасит dblclick браузера.
  let lastPressAt = 0;
  let lastPressY = Number.NaN;
  let lastPressChannel: ScopeGroundChannel | null = null;

  function groundHandle(
    channel: ScopeGroundChannel,
    text: string,
    aria: string,
  ): HTMLButtonElement {
    const node = el("button", {
      className: `lnt-scope-ground lnt-scope-ground-${channel}`,
      text,
      attrs: {
        type: "button",
        role: "slider",
        "aria-orientation": "vertical",
        "data-ground": channel,
        "aria-label": `${aria}, вольты на экране`,
        title: `${aria} — тяните, двойной клик сбрасывает`,
        "aria-valuemin": "-5",
        "aria-valuemax": "5",
        "aria-valuenow": "0",
      },
    });
    node.addEventListener("pointerdown", (event) => {
      if (event.buttons !== 1) return;
      // Двойной клик — сброс канала: preventDefault на pointerdown гасит
      // совместимые mouse-события, поэтому dblclick в браузере не придёт —
      // второй нажим отслеживаем отдельно для каждого канала.
      const now = Date.now();
      const twice =
        channel === lastPressChannel &&
        now - lastPressAt < 400 &&
        Math.abs(event.clientY - lastPressY) < 6;
      lastPressAt = twice ? 0 : now;
      lastPressY = event.clientY;
      lastPressChannel = twice ? null : channel;
      if (twice) {
        dragging = null;
        if (pointerId !== null && figure.hasPointerCapture?.(pointerId)) {
          figure.releasePointerCapture(pointerId);
        }
        pointerId = null;
        event.preventDefault();
        event.stopPropagation();
        options.write(channel, 0);
        repaint();
        return;
      }
      dragging = channel;
      pointerId = event.pointerId;
      event.preventDefault();
      event.stopPropagation();
      node.focus({ preventScroll: true });
      if (event instanceof PointerEvent) figure.setPointerCapture(event.pointerId);
    });
    node.addEventListener("dblclick", () => {
      options.write(channel, 0);
      repaint();
    });
    node.addEventListener("keydown", (event) => {
      const step = options.windowHalf() / KEY_STEP_DIVISIONS;
      const moves: Record<string, number> = {
        ArrowUp: step,
        ArrowRight: step,
        ArrowDown: -step,
        ArrowLeft: -step,
      };
      const move = moves[event.key];
      if (move === undefined) return;
      event.preventDefault();
      event.stopPropagation();
      const half = options.windowHalf();
      const next = Math.max(-half, Math.min(half, groundOf(channel) + move));
      options.write(channel, quantize(next, step));
      repaint();
    });
    return node;
  }

  function onPointerMove(event: PointerEvent): void {
    if (dragging === null) return;
    const rect = figure.getBoundingClientRect();
    if (rect.height <= 0) return;
    const volts = (0.5 - (event.clientY - rect.top) / rect.height) * 2 * options.windowHalf();
    const half = options.windowHalf();
    const clamped = Math.max(-half, Math.min(half, volts));
    options.write(dragging, quantize(clamped, half / KEY_STEP_DIVISIONS));
    repaint();
  }

  function onPointerEnd(): void {
    if (pointerId !== null && figure.hasPointerCapture?.(pointerId)) {
      figure.releasePointerCapture(pointerId);
    }
    dragging = null;
    pointerId = null;
  }

  figure.addEventListener("pointermove", onPointerMove);
  figure.addEventListener("pointerup", onPointerEnd);
  figure.addEventListener("pointercancel", onPointerEnd);

  let observer: ResizeObserver | null = null;
  if (typeof ResizeObserver !== "undefined") {
    observer = new ResizeObserver(() => repaint());
    observer.observe(figure);
  }

  function repaint(): void {
    const rect = figure.getBoundingClientRect();
    const half = options.windowHalf();
    for (const channel of ["ch1", "ch2"] as const) {
      const node = handles[channel];
      const volts = groundOf(channel);
      node.setAttribute("aria-valuenow", String(volts));
      node.setAttribute("aria-valuetext", `${volts} В`);
      node.setAttribute("aria-valuemin", String(-half));
      node.setAttribute("aria-valuemax", String(half));
      const y = Math.max(
        0,
        Math.min(rect.height - HANDLE_PX, (0.5 - volts / (2 * half)) * rect.height - HANDLE_PX / 2),
      );
      node.style.transform = `translateY(${y}px)`;
    }
  }

  repaint();

  return {
    repaint,
    dispose(): void {
      onPointerEnd();
      observer?.disconnect();
      figure.removeEventListener("pointermove", onPointerMove);
      figure.removeEventListener("pointerup", onPointerEnd);
      figure.removeEventListener("pointercancel", onPointerEnd);
      handles.ch1.remove();
      handles.ch2.remove();
      dragging = null;
    },
  };
}
