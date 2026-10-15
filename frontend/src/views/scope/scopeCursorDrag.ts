/** Drag курсорных линий на uPlot-фигуре (задача 15, зона-карта §8.3):
 * линии рисует плагин scopeCursorPaint на канвасе фигуры, слайдеры
 * T1/T2/V1/V2 — скрытый leftover; позиционирование переносится на drag.
 * Hit-тест 4 линий по СВЕЖЕЙ геометрии (на каждый pointerdown — кадры
 * меняют окно осей), полоса 44 px; drag пишет ЖИВЫЕ слайдеры (value +
 * input-событие — слушатели scopeCursorSection живы), зажимы доли окна
 * [0..1] и вольт ±5. Стрелки под фокусом на фигуре двигают последний
 * потянутый курсор (клавиатурный эквивалент вместо скрытых слайдеров).
 * Выключенные курсоры (тумблер Выкл) и отсутствие графика — drag нет. */

/** Структурное подмножество uPlot, нужное для hit-теста линий. */
export interface CursorChartLike {
  readonly bbox: {
    readonly left: number;
    readonly top: number;
    readonly width: number;
    readonly height: number;
  };
  valToPos(value: number, scale: string): number;
  posToVal(pixel: number, scale: string): number;
  readonly scales: { x?: { min?: number; max?: number } | null };
}

export interface CursorSliders {
  t1: HTMLInputElement;
  t2: HTMLInputElement;
  v1: HTMLInputElement;
  v2: HTMLInputElement;
}

export interface ScopeCursorDragOptions {
  figure: HTMLElement;
  geometry: () => CursorChartLike | null;
  sliders: CursorSliders;
  enabled: () => boolean;
}

export interface ScopeCursorDragHandle {
  dispose(): void;
}

/** Полуширина hit-полосы вокруг линии: 44/2. */
const HIT_PX = 22;
/** Номинальный домен V-курсоров: ±5 В (в центах слайдера: ±500). */
const VOLTS_LIMIT = 5;

interface DragTarget {
  kind: "t" | "v";
  slider: HTMLInputElement;
}

export function mountScopeCursorDrag(options: ScopeCursorDragOptions): ScopeCursorDragHandle {
  const { figure, sliders } = options;
  let dragging: DragTarget | null = null;
  let last: DragTarget | null = null;

  figure.setAttribute("tabindex", "0");
  figure.setAttribute("role", "figure");
  figure.setAttribute("aria-label", "График развёртки: линии курсоров");

  function writeSlider(target: DragTarget, raw: number): void {
    const min = Number(target.slider.min);
    const max = Number(target.slider.max);
    const value = Math.max(min, Math.min(max, raw));
    if (String(value) === target.slider.value) return;
    target.slider.value = String(value);
    target.slider.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function roundToStep(raw: number, slider: HTMLInputElement): number {
    const step = Number(slider.step) || 1;
    return Math.round(raw / step) * step;
  }

  /** Позиции 4 линий в пикселях канваса (окно осей живого графика). */
  function linePositions(chart: CursorChartLike) {
    const xMin = chart.scales.x?.min;
    const xMax = chart.scales.x?.max;
    if (xMin === undefined || xMax === undefined || xMax <= xMin) return null;
    const xOfFraction = (fraction: number): number =>
      chart.valToPos(xMin + fraction * (xMax - xMin), "x");
    return {
      t1: xOfFraction((Number(sliders.t1.value) || 0) / 1000),
      t2: xOfFraction((Number(sliders.t2.value) || 0) / 1000),
      v1: chart.valToPos((Number(sliders.v1.value) || 0) / 100, "y"),
      v2: chart.valToPos((Number(sliders.v2.value) || 0) / 100, "y"),
    };
  }

  function hitTest(x: number, y: number): DragTarget | null {
    const chart = options.geometry();
    const positions = chart === null ? null : linePositions(chart);
    if (chart === null || positions === null) return null;
    const candidates: Array<{ target: DragTarget; distance: number }> = [
      { target: { kind: "t", slider: sliders.t1 }, distance: Math.abs(x - positions.t1) },
      { target: { kind: "t", slider: sliders.t2 }, distance: Math.abs(x - positions.t2) },
      { target: { kind: "v", slider: sliders.v1 }, distance: Math.abs(y - positions.v1) },
      { target: { kind: "v", slider: sliders.v2 }, distance: Math.abs(y - positions.v2) },
    ];
    candidates.sort((a, b) => a.distance - b.distance);
    const best = candidates[0];
    return best !== undefined && best.distance <= HIT_PX ? best.target : null;
  }

  function onPointerDown(event: PointerEvent): void {
    if (!options.enabled()) return;
    const hit = hitTest(event.clientX, event.clientY);
    if (hit === null) return;
    dragging = hit;
    last = hit;
    event.preventDefault();
    figure.focus();
    if (typeof figure.setPointerCapture === "function") {
      try {
        figure.setPointerCapture(event.pointerId);
      } catch {
        // Синтетический pointerId: флаг dragging ведёт drag.
      }
    }
  }

  function onPointerMove(event: PointerEvent): void {
    if (dragging === null) return;
    const chart = options.geometry();
    if (chart === null) return;
    if (dragging.kind === "t") {
      const fraction = (event.clientX - chart.bbox.left) / chart.bbox.width;
      const clamped = Math.max(0, Math.min(1, fraction));
      writeSlider(dragging, roundToStep(clamped * 1000, dragging.slider));
    } else {
      const volts = chart.posToVal(event.clientY, "y");
      const clamped = Math.max(-VOLTS_LIMIT, Math.min(VOLTS_LIMIT, volts));
      writeSlider(dragging, roundToStep(clamped * 100, dragging.slider));
    }
  }

  function onPointerEnd(): void {
    dragging = null;
  }

  /** Стрелки двигают последний потянутый курсор на его шаг. */
  function onKeyDown(event: KeyboardEvent): void {
    if (last === null || !options.enabled()) return;
    const step = Number(last.slider.step) || 1;
    const moves: Record<string, number> = {
      ArrowRight: step,
      ArrowLeft: -step,
      ArrowUp: step,
      ArrowDown: -step,
    };
    const move = moves[event.key];
    if (move === undefined) return;
    event.preventDefault();
    writeSlider(last, (Number(last.slider.value) || 0) + move);
  }

  figure.addEventListener("pointerdown", onPointerDown);
  figure.addEventListener("pointermove", onPointerMove);
  figure.addEventListener("pointerup", onPointerEnd);
  figure.addEventListener("pointercancel", onPointerEnd);
  figure.addEventListener("keydown", onKeyDown);

  return {
    dispose: () => {
      figure.removeEventListener("pointerdown", onPointerDown);
      figure.removeEventListener("pointermove", onPointerMove);
      figure.removeEventListener("pointerup", onPointerEnd);
      figure.removeEventListener("pointercancel", onPointerEnd);
      figure.removeEventListener("keydown", onKeyDown);
      figure.removeAttribute("tabindex");
      figure.removeAttribute("role");
      figure.removeAttribute("aria-label");
      dragging = null;
      last = null;
    },
  };
}
