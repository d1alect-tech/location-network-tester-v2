/** Оверлей послесвечения живой развёртки (задача 22, директива GATE A
 * 2026-10-18): пассивный канвас ПОВЕРХ uPlot-канваса в фигуре развёртки
 * (НЕ второй рендер-стек, НЕ второй uPlot — pointer-events: none, drag
 * курсорных линий не задет), аккумулятор и режимы — scopePersistence.
 * Ячейки рисуются ВНУТРИ области построения uPlot (.u-over) — след
 * совпадает с трассой, оси не перекрываются; DPR-aware; без размеров
 * или контекста (jsdom) краска пропускается молча. Тумблер — секция
 * меню захвата (buildPersistenceMenuSection), ярлык состояния —
 * createPersistenceTag. НАКОПЛЕНИЕ — ОТОБРАЖЕНИЕ, НЕ ИЗМЕРЕНИЕ;
 * «аналоговый фосфор» в подписях НЕ обещается. */

import { el } from "../../components/primitives/dom";
import {
  PERSISTENCE_GRID_H,
  PERSISTENCE_GRID_W,
  PERSISTENCE_MODE_TEXT,
  type PersistenceMode,
  ScopePersistence,
  persistenceDecayFactor,
} from "./scopePersistence";
import { afterglowAlpha, cssTokenColor } from "./scopeScreenPaint";

export interface ScopeWavePersistenceHandle {
  readonly canvas: HTMLCanvasElement;
  setMode(mode: PersistenceMode): void;
  mode(): PersistenceMode;
  /** Шаг накопления: затухание по dt кадра (ПЕРЕД попаданиями — свежий
   *  кадр светится полным уровнем), оба канала, перерисовка оверлея. */
  accumulate(
    timeS: readonly number[],
    ch1: readonly number[],
    ch2: readonly number[],
    vMin: number,
    vMax: number,
    frameDtS: number,
  ): void;
  levelAt(x: number, y: number): number;
  lit(): number;
  clear(): void;
  destroy(): void;
}

/** Оверлей послесвечения фигуры развёртки: ПАССИВНЫЙ канвас поверх
 *  uPlot (позже корня графика в DOM, pointer-events: none — курсор и
 *  drag линий не задет). off — аккумулятор пуст, оверлей прозрачен. */
export function mountWavePersistence(figure: HTMLElement): ScopeWavePersistenceHandle {
  const canvas = el("canvas", {
    className: "lnt-scope-wave-persist",
    attrs: { "aria-hidden": "true", "data-wave-persistence": "", "data-persist-mode": "off" },
  });
  figure.append(canvas);
  const store = new ScopePersistence();
  let mode: PersistenceMode = "off";
  const repaint = (): void => paintWaveOverlay(canvas, store);
  return {
    canvas,
    setMode(next: PersistenceMode): void {
      mode = next;
      canvas.setAttribute("data-persist-mode", next);
      if (next === "off") {
        store.clear();
        repaint();
      }
    },
    mode: () => mode,
    accumulate(timeS, ch1, ch2, vMin, vMax, frameDtS) {
      if (mode === "off") return;
      store.decayByFactor(persistenceDecayFactor(mode, frameDtS));
      store.pushChannel(timeS, ch1, vMin, vMax);
      store.pushChannel(timeS, ch2, vMin, vMax);
      repaint();
    },
    levelAt: (x, y) => store.levelAt(x, y),
    lit: () => store.litCells(),
    clear() {
      store.clear();
      repaint();
    },
    destroy() {
      store.clear();
      canvas.remove();
    },
  };
}

/** Краска оверлея: ячейки аккумулятора → полупрозрачные прямоугольники
 *  цвета --lnt-accent ВНУТРИ области построения uPlot (.u-over) — оси
 *  не перекрываются, след совпадает с трассой. DPR-aware; без размеров
 *  или контекста (jsdom) кадр пропускается молча. */
function paintWaveOverlay(canvas: HTMLCanvasElement, store: ScopePersistence): void {
  const box = canvas.getBoundingClientRect();
  if (box.width <= 0 || box.height <= 0) return;
  const ctx = canvas.getContext("2d");
  if (ctx === null) return;
  const ratio = typeof devicePixelRatio === "number" && devicePixelRatio > 0 ? devicePixelRatio : 1;
  canvas.width = Math.round(box.width * ratio);
  canvas.height = Math.round(box.height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, box.width, box.height);
  const over = canvas.parentElement?.querySelector(".u-over");
  if (!(over instanceof HTMLElement)) return;
  const overBox = over.getBoundingClientRect();
  const left = Math.max(0, overBox.left - box.left);
  const top = Math.max(0, overBox.top - box.top);
  const width = Math.min(box.width - left, overBox.width);
  const height = Math.min(box.height - top, overBox.height);
  if (width <= 0 || height <= 0) return;
  const color = cssTokenColor(canvas, "--lnt-accent", "#5681ff");
  const styles: string[] = [];
  for (let level = 1; level <= 255; level += 1) {
    styles[level] = `rgba(${color.r}, ${color.g}, ${color.b}, ${afterglowAlpha(level).toFixed(3)})`;
  }
  const cellW = width / PERSISTENCE_GRID_W;
  const cellH = height / PERSISTENCE_GRID_H;
  const drawW = Math.max(1, Math.ceil(cellW));
  const drawH = Math.max(1, Math.ceil(cellH));
  for (let y = 0; y < PERSISTENCE_GRID_H; y += 1) {
    const pixelY = top + y * cellH;
    for (let x = 0; x < PERSISTENCE_GRID_W; x += 1) {
      const level = store.levelAt(x, y);
      if (level <= 0) continue;
      ctx.fillStyle = styles[level] as string;
      ctx.fillRect(left + x * cellW, pixelY, drawW, drawH);
    }
  }
}

export interface ScopePersistenceTag {
  readonly root: HTMLElement;
  paint(mode: PersistenceMode): void;
}

/** Ярлык состояния развёртки: режим + честная подпись (скрыт при off). */
export function createPersistenceTag(): ScopePersistenceTag {
  const root = el("p", {
    className: "t-compact lnt-scope-wave-tag",
    attrs: { "data-wave-persist": "off", hidden: "" },
  });
  return {
    root,
    paint(mode: PersistenceMode): void {
      root.setAttribute("data-wave-persist", mode);
      root.hidden = mode === "off";
      root.textContent =
        mode === "off"
          ? ""
          : `Послесвечение: ${PERSISTENCE_MODE_TEXT[mode]} — накопление: отображение, не измерение`;
    },
  };
}

export interface PersistenceMenuSectionOptions {
  readonly current: PersistenceMode;
  readonly onPick: (mode: PersistenceMode) => void;
}

const PERSISTENCE_MENU_OPTIONS: ReadonlyArray<{
  readonly value: PersistenceMode;
  readonly text: string;
}> = [
  { value: "off", text: PERSISTENCE_MODE_TEXT.off },
  { value: "short", text: PERSISTENCE_MODE_TEXT.short },
  { value: "long", text: PERSISTENCE_MODE_TEXT.long },
];

/** Секция «Послесвечение» меню захвата (задача 22): три опции, та же
 *  ария-грамматика aria-pressed, что у capture-рядов; накопление —
 *  отображение, не измерение («аналоговый фосфор» НЕ обещается). */
export function buildPersistenceMenuSection(options: PersistenceMenuSectionOptions): HTMLElement {
  let current = options.current;
  const buttons = new Map<PersistenceMode, HTMLButtonElement>();
  for (const option of PERSISTENCE_MENU_OPTIONS) {
    const node = el("button", {
      className: "lnt-live-capture-opt",
      text: option.text,
      attrs: {
        type: "button",
        "data-menu-persist": option.value,
        "aria-pressed": String(option.value === current),
      },
    });
    node.addEventListener("click", () => {
      if (current === option.value) return;
      current = option.value;
      for (const [value, button] of buttons) {
        button.setAttribute("aria-pressed", String(value === current));
      }
      options.onPick(option.value);
    });
    buttons.set(option.value, node);
  }
  return el(
    "div",
    { className: "lnt-live-capture-group", attrs: { "data-menu-section": "persist" } },
    [
      el("span", { className: "lnt-live-capture-hd", text: "Послесвечение (отображение)" }),
      el(
        "div",
        {
          className: "lnt-live-capture-row",
          attrs: { role: "group", "aria-label": "Послесвечение" },
        },
        [
          el("span", { className: "lnt-live-capture-row-label", text: "След" }),
          ...buttons.values(),
        ],
      ),
      el("p", {
        className: "t-compact lnt-live-capture-hint",
        text: "След прошлых кадров гаснет за ~0,5 / ~2 с; накопление — отображение, не измерение.",
      }),
    ],
  );
}
