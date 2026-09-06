/** U3: Δ-полоса B − A под спектром. Живопись по R3-A buildDeltaStrip, данные
 *  настоящие (пейлоады панели). Сетки индекс-совмещены, как peakDeltas.
 *  Сворачивание с памятью localStorage; дефолт — раскрыта. */

import type { SpectrumPayload } from "../../api/types-plots";
import { el } from "../../components/primitives/dom";
import "./deltaStrip.css";

export const DELTA_STRIP_STORAGE_KEY = "lnt.inspect.deltaStrip";
const RANGE_DB = 8;

export interface DeltaStripHandle {
  readonly root: HTMLElement;
  paint(a: SpectrumPayload | null, b: SpectrumPayload | null): void;
  isOpen(): boolean;
}

function cssVar(host: HTMLElement, name: string, fallback: string): string {
  const value = getComputedStyle(host).getPropertyValue(name).trim();
  return value === "" ? fallback : value;
}

function paintCanvas(
  canvas: HTMLCanvasElement,
  psdA: readonly number[],
  psdB: readonly number[],
): void {
  const ctx = canvas.getContext("2d");
  if (ctx === null) return;
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (width === 0 || height === 0) return;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  ctx.scale(dpr, dpr);

  const n = Math.min(psdA.length, psdB.length);
  const zeroY = height / 2;
  const yFor = (db: number): number =>
    zeroY - (Math.max(-RANGE_DB, Math.min(RANGE_DB, db)) / RANGE_DB) * (height / 2 - 2);

  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = cssVar(canvas, "--lnt-line", "#33383f");
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, zeroY);
  ctx.lineTo(width, zeroY);
  ctx.stroke();

  ctx.strokeStyle = cssVar(canvas, "--lnt-delta", "#b7a6ff");
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < n; i++) {
    const a = psdA[i];
    const b = psdB[i];
    if (typeof a !== "number" || typeof b !== "number" || !(a > 0) || !(b > 0)) continue;
    const delta = 10 * Math.log10(b / a);
    if (!Number.isFinite(delta)) continue;
    const x = n <= 1 ? 0 : (i / (n - 1)) * width;
    const y = yFor(delta);
    if (!started) {
      ctx.moveTo(x, y);
      started = true;
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();
}

function readOpen(): boolean {
  try {
    return window.localStorage.getItem(DELTA_STRIP_STORAGE_KEY) !== "closed";
  } catch {
    return true;
  }
}

function writeOpen(open: boolean): void {
  try {
    window.localStorage.setItem(DELTA_STRIP_STORAGE_KEY, open ? "open" : "closed");
  } catch {
    /* приватный режим: состояние живёт до перезагрузки */
  }
}

export function createDeltaStrip(): DeltaStripHandle {
  const canvas = el("canvas", {
    className: "delta-canvas",
    attrs: { "aria-hidden": "true", "data-delta-canvas": "" },
  }) as HTMLCanvasElement;
  const empty = el("div", {
    className: "delta-strip-empty",
    attrs: { "data-delta-empty": "" },
    text: "Выберите пару для Δ",
  });
  empty.hidden = true;
  const toggle = el("button", {
    className: "btn-quiet delta-strip-toggle",
    text: "Свернуть",
    attrs: { type: "button", "data-delta-toggle": "", "aria-expanded": "true" },
  }) as HTMLButtonElement;
  const body = el("div", { className: "delta-strip-bd" }, [canvas]);
  const root = el("section", { className: "delta-strip", attrs: { "data-delta-strip": "" } }, [
    el("div", { className: "delta-strip-hd" }, [
      el("span", { className: "delta-strip-label", text: "Δ = B − A, дБ · ±8" }),
      toggle,
    ]),
    body,
    empty,
  ]);

  let lastA: readonly number[] = [];
  let lastB: readonly number[] = [];

  function repaint(): void {
    paintCanvas(canvas, lastA, lastB);
  }

  function applyOpen(open: boolean): void {
    root.classList.toggle("is-closed", !open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = open ? "Свернуть" : "Развернуть";
    if (open) repaint();
  }

  toggle.addEventListener("click", () => {
    const open = !isOpen();
    writeOpen(open);
    applyOpen(open);
  });

  function isOpen(): boolean {
    return !root.classList.contains("is-closed");
  }

  // jsdom не знает ResizeObserver — там перерисовки по ресайзу нет, paint зовётся явно.
  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => {
      if (isOpen()) repaint();
    });
    observer.observe(canvas);
  }

  applyOpen(readOpen());

  return {
    root,
    isOpen,
    paint(a, b) {
      const hasPair = a !== null && b !== null;
      empty.hidden = hasPair;
      body.hidden = !hasPair;
      if (!hasPair) return;
      lastA = a.psd_v2_per_hz;
      lastB = b.psd_v2_per_hz;
      if (isOpen()) repaint();
    },
  };
}
