/** Экран осциллографа (Todo 11; задача 14 — тумблер liveSeg): панель
 * .lnt-scope-screen — вьюпорт с двумя канвас-слоями (послесвечение ПОД
 * трассой кадра; uPlot-волна тодо 8 встанет поверх) и управление: тумблер
 * «Послесвечение» Выкл|Вкл (память localStorage, замена чекбокса внутри
 * scopeScreen) и ползунок истории с кнопкой «Живой». Диапазон экрана ±5 В
 * (дефолт live-старта; V/div привяжет тодо 8). Пока экран прокручен назад,
 * кадры продолжают писаться в историю, послесвечение заморожено. Сторы
 * бюджета ограничены (scopePersistence/scopeHistory); наблюдатель ресайза
 * отключается dispose(). */

import type { LiveFramePayload } from "../../api/types-live";
import { createLiveSeg } from "../../components/liveStrip/liveSeg";
import { el } from "../../components/primitives/dom";
import { ScopeHistory } from "./scopeHistory";
import { ScopePersistence } from "./scopePersistence";
import { DEFAULT_SCOPE_SETTINGS, windowHalfVolts } from "./scopeScale";
import type { ScopeDisplaySettings } from "./scopeScale";
import { paintScopePersistence, paintScopeTrace } from "./scopeScreenPaint";

export const SCOPE_PERSISTENCE_STORAGE_KEY = "lnt.scope.persistence";

export interface ScopeScreenHandle {
  readonly root: HTMLElement;
  /** Вьюпорт экрана — хост оверлея линии триггера (НЕ ре-парент). */
  readonly viewport: HTMLElement;
  /** Подпись кадров (.lnt-scope-screen-note) — хост полосы (ре-парент). */
  readonly screenNote: HTMLElement;
  /** Слайдер истории (#lnt-scope-history) — хост полосы (ре-парент). */
  readonly history: HTMLInputElement;
  /** Кнопка «Живой» (#lnt-scope-live) — хост полосы (ре-парент). */
  readonly live: HTMLButtonElement;
  /** Тумблер послесвечения (#lnt-scope-persist) — хост полосы (ре-парент). */
  readonly persist: HTMLElement;
  applyFrame(frame: LiveFramePayload, settings: ScopeDisplaySettings): void;
  /** Экранные настройки (В/дел/пробник/нулевые линии): перерисовка истории. */
  applySettings(settings: ScopeDisplaySettings): void;
  isPersistenceOn(): boolean;
  historyOffset(): number;
  dispose(): void;
}

function readPersistenceOn(): boolean {
  try {
    return window.localStorage.getItem(SCOPE_PERSISTENCE_STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

function writePersistenceOn(on: boolean): void {
  try {
    window.localStorage.setItem(SCOPE_PERSISTENCE_STORAGE_KEY, on ? "on" : "off");
  } catch {
    /* приватный режим: состояние живёт до перезагрузки */
  }
}

function framesWord(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return "кадр";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "кадра";
  return "кадров";
}

export interface ScopeScreenOptions {
  /** Оверлей стекла (todo 9: живой чип риппла) — абсолютный слой поверх
   * канвасов, нулевой след в раскладке (паттерн screen-note/edge-ghost). */
  overlay?: Node;
}

export function buildScopeScreen(options: ScopeScreenOptions = {}): ScopeScreenHandle {
  const persistenceCanvas = el("canvas", {
    className: "lnt-scope-persistence",
    attrs: { "aria-hidden": "true", "data-scope-persistence": "" },
  });
  const traceCanvas = el("canvas", {
    className: "lnt-scope-screen-trace",
    attrs: { "aria-hidden": "true", "data-scope-screen-trace": "" },
  });
  const note = el("p", { className: "t-compact lnt-scope-screen-note", text: "кадров нет" });
  const viewport = el("div", { className: "lnt-scope-viewport" }, [
    persistenceCanvas,
    traceCanvas,
    note,
    ...(options.overlay !== undefined ? [options.overlay] : []),
  ]);

  const slider = el("input", {
    className: "lnt-scope-history-slider",
    attrs: {
      type: "range",
      id: "lnt-scope-history",
      min: "0",
      max: "0",
      step: "1",
      value: "0",
      "aria-label": "История кадров",
      "aria-valuetext": "живой кадр",
    },
  });
  const liveButton = el("button", {
    className: "btn btn-secondary",
    text: "Живой",
    attrs: { type: "button", id: "lnt-scope-live" },
  });
  liveButton.disabled = true;
  let persistenceOn = readPersistenceOn();
  const persistSeg = createLiveSeg(
    {
      key: "persist",
      kind: "local",
      aria: "Послесвечение",
      options: [
        { value: "on", text: "Вкл" },
        { value: "off", text: "Выкл" },
      ],
      current: persistenceOn ? "on" : "off",
      groupAttrs: { id: "lnt-scope-persist" },
    },
    (value) => {
      persistenceOn = value === "on";
      writePersistenceOn(persistenceOn);
      if (!persistenceOn) {
        persistence.clear();
        paintScopePersistence(persistenceCanvas, persistence);
      }
    },
  );
  const controls = el("div", { className: "lnt-scope-screen-controls" }, [
    el("div", { className: "lnt-scope-screen-toggle" }, [persistSeg.root]),
    el("div", { className: "lnt-scope-screen-history" }, [
      el("span", { className: "t-compact lnt-scope-history-label", text: "История" }),
      slider,
      liveButton,
    ]),
  ]);

  const root = el("section", { className: "panel lnt-scope-section lnt-scope-screen" }, [
    el("div", { className: "panel-hd" }, [el("h3", { className: "panel-title", text: "Экран" })]),
    el("div", { className: "panel-bd" }, [viewport, controls]),
  ]);

  const history = new ScopeHistory();
  const persistence = new ScopePersistence();
  let offset = 0;
  let settings: ScopeDisplaySettings = { ...DEFAULT_SCOPE_SETTINGS };

  function applyNote(): void {
    const frame = history.view(offset);
    if (frame === null) {
      note.textContent = "кадров нет";
      return;
    }
    note.textContent =
      offset === 0
        ? `кадр ${frame.frameIndex} · живой`
        : `кадр ${frame.frameIndex} · ${offset} ${framesWord(offset)} назад`;
  }

  function repaintTrace(): void {
    paintScopeTrace(traceCanvas, history.view(offset), settings);
  }

  function applyOffset(next: number): void {
    const bound = Math.max(0, Math.min(history.frameCount() - 1, next));
    offset = bound;
    slider.value = String(bound);
    slider.setAttribute(
      "aria-valuetext",
      bound === 0 ? "живой кадр" : `${bound} ${framesWord(bound)} назад`,
    );
    liveButton.disabled = bound === 0;
    repaintTrace();
    applyNote();
  }

  function applyFrame(frame: LiveFramePayload, next: ScopeDisplaySettings): void {
    settings = next;
    history.push(frame);
    slider.max = String(Math.max(0, history.frameCount() - 1));
    if (offset > 0) {
      // Прокрутка назад: экран заморожен, история пишет дальше.
      return;
    }
    repaintTrace();
    if (persistenceOn) {
      const halfSpan = windowHalfVolts(settings.vDiv, settings.probe);
      persistence.decay();
      persistence.pushChannel(
        frame.ch1.time_s,
        frame.ch1.voltage_v.map((v) => v * (settings.invertCh1 ? -1 : 1) + settings.groundCh1V),
        -halfSpan,
        halfSpan,
      );
      persistence.pushChannel(
        frame.ch2.time_s,
        frame.ch2.voltage_v.map((v) => v * (settings.invertCh2 ? -1 : 1) + settings.groundCh2V),
        -halfSpan,
        halfSpan,
      );
      paintScopePersistence(persistenceCanvas, persistence);
    }
    applyNote();
  }

  function applySettings(next: ScopeDisplaySettings): void {
    settings = next;
    persistence.clear();
    repaintTrace();
    if (persistenceOn) paintScopePersistence(persistenceCanvas, persistence);
  }

  slider.addEventListener("input", () => {
    applyOffset(Number.parseInt(slider.value, 10) || 0);
  });
  liveButton.addEventListener("click", () => applyOffset(0));

  // jsdom не знает ResizeObserver — там перерисовки по ресайзу нет.
  let observer: ResizeObserver | null = null;
  if (typeof ResizeObserver !== "undefined") {
    observer = new ResizeObserver(() => {
      repaintTrace();
      if (persistenceOn) paintScopePersistence(persistenceCanvas, persistence);
    });
    observer.observe(viewport);
  }

  return {
    root,
    viewport,
    screenNote: note,
    history: slider,
    live: liveButton,
    persist: persistSeg.root,
    applyFrame,
    applySettings,
    isPersistenceOn: () => persistenceOn,
    historyOffset: () => offset,
    dispose: () => observer?.disconnect(),
  };
}
