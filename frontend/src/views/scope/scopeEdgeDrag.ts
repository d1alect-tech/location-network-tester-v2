/** Edge-drag В/дел (задача 19, GATE A 2026-10-18): drag верхней кромки
 * «экрана» — стекла осциллографа И фигуры развёртки — меняет В/дел
 * тремя детентами таблицы VDIV_STEPS (5/1/0.5; вверх — крупнее, вниз —
 * мельче, на концах таблицы зажим), эхо в зоне ВЕРТ видно без клика:
 * В/дел пишет ТО ЖЕ поле через writeVDiv (живой слушатель листа —
 * staged-грамматика полосы наследуется, манифест НЕ трогается: кромка —
 * не контроль полосы). АРБИТРАЖ ТРЁХ УКАЗАТЕЛЕЙ — кромка > линия триггера
 * > курсорные линии: слушатель кромки стоит в CAPTURE-фазе на общем
 * предке (корень воркспейса) и гасит событие ДО листовых слушателей —
 * существующие списатели scopeCursorDrag/scopeTriggerLine НЕ правятся
 * (порядок закодирован фазами события; проверено их же тестами без
 * правок + контрактом ниже). Ghost-репетиция hover — пунктир + значение
 * (текущее на hover, детент в drag), ОДИН элемент на обе поверхности,
 * без анимации: PRM-политика — никаких transition/animation/transform.
 * Slop 4 px: клик без движения ничего не пишет; детент — каждые 32 px. */

import { el } from "../../components/primitives/dom";
import { VDIV_STEPS, formatVDiv } from "./scopeScale";

/** Полоса захвата у верхней кромки поверхности (px). */
const EDGE_HIT_PX = 12;
/** Порог движения до первого детента (px): клик кромки — не запись. */
const SLOP_PX = 4;
/** Шаг детента: смена В/дел на каждые столько px перетаскивания. */
const DETENT_PX = 32;

export interface ScopeEdgeDragOptions {
  /** Общий предок поверхностей (корень воркспейса): capture-фаза. */
  host: HTMLElement;
  /** Поверхности «экрана»: стекло (линия триггера) + фигура (курсоры). */
  surfaces: readonly HTMLElement[];
  readVDiv: () => number;
  writeVDiv: (value: number) => void;
}

export interface ScopeEdgeDragHandle {
  dispose(): void;
}

interface EdgeDragState {
  surface: HTMLElement;
  startY: number;
  startIndex: number;
  lastWritten: number;
}

/** Позиция в таблице В/дел; неизвестное значение — крупный шаг. */
function vdivIndex(value: number): number {
  const index = VDIV_STEPS.indexOf(value);
  return index === -1 ? 0 : index;
}

function formatGhost(value: number): string {
  return formatVDiv(value);
}

export function mountScopeEdgeDrag(options: ScopeEdgeDragOptions): ScopeEdgeDragHandle {
  const { host, surfaces } = options;
  // Ghost один на обе поверхности: переносится родителем по hover/drag.
  const ghostValue = el("span", { className: "lnt-scope-edge-ghost-value", text: "" });
  const ghost = el(
    "div",
    { className: "lnt-scope-edge-ghost", attrs: { "aria-hidden": "true", hidden: "" } },
    [ghostValue],
  );
  let drag: EdgeDragState | null = null;

  /** Поверхность, чья верхняя кромка под указателем. */
  function hitSurface(x: number, y: number): HTMLElement | null {
    for (const surface of surfaces) {
      const rect = surface.getBoundingClientRect();
      if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.top + EDGE_HIT_PX) {
        return surface;
      }
    }
    return null;
  }

  function showGhost(surface: HTMLElement, text: string): void {
    if (ghost.parentElement !== surface) surface.append(ghost);
    ghostValue.textContent = text;
    ghost.hidden = false;
  }

  function hideGhost(): void {
    ghost.hidden = true;
    for (const surface of surfaces) surface.removeAttribute("data-edge-hover");
  }

  function onPointerDown(event: PointerEvent): void {
    if (event.buttons !== 1) return;
    if (event.target instanceof Element && event.target.closest("[data-ground]")) return;
    const surface = hitSurface(event.clientX, event.clientY);
    if (surface === null) {
      // Жест не кромки (например, drag линии): репетиция гасится.
      hideGhost();
      return;
    }
    // Кромка выше линий триггера и курсоров: событие гасится здесь,
    // листовые слушатели (линия на стекле, drag на фигуре) его не видят.
    event.preventDefault();
    event.stopPropagation();
    const startIndex = vdivIndex(options.readVDiv());
    drag = { surface, startY: event.clientY, startIndex, lastWritten: startIndex };
    if (typeof host.setPointerCapture === "function") {
      try {
        host.setPointerCapture(event.pointerId);
      } catch {
        // Синтетический pointerId: состояние drag ведёт жест до pointerup.
      }
    }
    showGhost(surface, formatGhost(VDIV_STEPS[startIndex] ?? options.readVDiv()));
  }

  function onPointerMove(event: PointerEvent): void {
    if (drag !== null) {
      const dy = event.clientY - drag.startY;
      if (Math.abs(dy) < SLOP_PX) return;
      const steps = Math.trunc(dy / DETENT_PX);
      const next = Math.max(0, Math.min(VDIV_STEPS.length - 1, drag.startIndex + steps));
      if (next !== drag.lastWritten) {
        drag.lastWritten = next;
        const value = VDIV_STEPS[next];
        if (value !== undefined) options.writeVDiv(value);
      }
      const pending = VDIV_STEPS[drag.lastWritten] ?? options.readVDiv();
      showGhost(drag.surface, formatGhost(pending));
      return;
    }
    // Hover-репетиция — только без зажатых кнопок (чужой drag не подсвечен).
    if (event.buttons !== 0) return;
    const surface = hitSurface(event.clientX, event.clientY);
    if (surface === null) {
      hideGhost();
      return;
    }
    for (const other of surfaces) {
      if (other === surface) other.setAttribute("data-edge-hover", "");
      else other.removeAttribute("data-edge-hover");
    }
    showGhost(surface, formatGhost(options.readVDiv()));
  }

  function onPointerEnd(event: PointerEvent): void {
    if (drag === null) return;
    drag = null;
    // Кромка ещё под указателем — репетиция остаётся, иначе скрыта.
    const surface = hitSurface(event.clientX, event.clientY);
    if (surface === null) hideGhost();
    else showGhost(surface, formatGhost(options.readVDiv()));
  }

  host.addEventListener("pointerdown", onPointerDown, true);
  host.addEventListener("pointermove", onPointerMove, true);
  host.addEventListener("pointerup", onPointerEnd, true);
  host.addEventListener("pointercancel", onPointerEnd, true);

  return {
    dispose(): void {
      host.removeEventListener("pointerdown", onPointerDown, true);
      host.removeEventListener("pointermove", onPointerMove, true);
      host.removeEventListener("pointerup", onPointerEnd, true);
      host.removeEventListener("pointercancel", onPointerEnd, true);
      drag = null;
      hideGhost();
      ghost.remove();
    },
  };
}
