/** Перетаскивание выбранного маркера в координатах CSS-поля uPlot. */
import type { SaMarkerLine } from "./saSpectrum";

interface MarkerGeometry {
  readonly over: HTMLElement;
  valToPos(value: number, scale: string): number;
  posToVal(pixel: number, scale: string): number;
}

interface SaMarkerDragOptions {
  readonly figure: HTMLElement;
  geometry(): MarkerGeometry | null;
  markers(): readonly SaMarkerLine[];
  select(id: number): void;
  move(id: number, frequencyHz: number): void;
  remove(id: number): void;
}

export function mountSaMarkerDrag(options: SaMarkerDragOptions): { dispose(): void } {
  const { figure } = options;
  let active: number | null = null;
  let dragging = false;
  let suppressClick = false;
  let pointerId: number | null = null;
  figure.tabIndex = 0;
  // role application: клавиши (стрелки/Delete) должны доходить до canvas-виджета;
  // aria-label на div без роли axe считает запрещённым атрибутом.
  figure.setAttribute("role", "application");
  figure.setAttribute("aria-label", "Спектр: перетащите маркер, Delete удаляет выбранный");

  function down(event: PointerEvent): void {
    if (event.buttons !== 1) return;
    suppressClick = false;
    const chart = options.geometry();
    if (chart === null) return;
    const rect = chart.over.getBoundingClientRect();
    if (event.clientY < rect.top || event.clientY > rect.bottom) return;
    const x = event.clientX - rect.left;
    const marker = [...options.markers()].sort(
      (a, b) =>
        Math.abs(x - chart.valToPos(a.frequencyHz, "x")) -
        Math.abs(x - chart.valToPos(b.frequencyHz, "x")),
    )[0];
    if (marker === undefined || Math.abs(x - chart.valToPos(marker.frequencyHz, "x")) > 22) return;
    active = marker.id;
    dragging = true;
    suppressClick = true;
    pointerId = event.pointerId;
    options.select(marker.id);
    event.preventDefault();
    event.stopImmediatePropagation();
    figure.focus({ preventScroll: true });
    if (event instanceof PointerEvent) figure.setPointerCapture(event.pointerId);
  }

  function move(event: PointerEvent): void {
    if (!dragging || active === null) return;
    const chart = options.geometry();
    if (chart === null) return;
    const rect = chart.over.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
    options.move(active, chart.posToVal(x, "x"));
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function end(): void {
    if (pointerId !== null && figure.hasPointerCapture?.(pointerId))
      figure.releasePointerCapture(pointerId);
    dragging = false;
    pointerId = null;
  }

  function click(event: MouseEvent): void {
    if (!suppressClick) return;
    suppressClick = false;
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function mouse(event: MouseEvent): void {
    if (!dragging) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function key(event: KeyboardEvent): void {
    if (active === null || event.target !== figure) return;
    if (event.key === "Delete" || event.key === "Backspace") {
      options.remove(active);
      active = null;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      const chart = options.geometry();
      const marker = options.markers().find((item) => item.id === active);
      if (chart === null || marker === undefined) return;
      const pixel = chart.valToPos(marker.frequencyHz, "x") + (event.key === "ArrowLeft" ? -8 : 8);
      options.move(active, chart.posToVal(pixel, "x"));
    } else return;
    event.preventDefault();
  }

  figure.addEventListener("pointerdown", down, true);
  figure.addEventListener("pointermove", move, true);
  figure.addEventListener("pointerup", end);
  figure.addEventListener("pointercancel", end);
  figure.addEventListener("mousedown", mouse, true);
  figure.addEventListener("click", click, true);
  figure.addEventListener("keydown", key);
  return {
    dispose() {
      end();
      figure.removeEventListener("pointerdown", down, true);
      figure.removeEventListener("pointermove", move, true);
      figure.removeEventListener("pointerup", end);
      figure.removeEventListener("pointercancel", end);
      figure.removeEventListener("mousedown", mouse, true);
      figure.removeEventListener("click", click, true);
      figure.removeEventListener("keydown", key);
    },
  };
}
