/** Числовая форма окна спектрограммы (C2-лист): tStart/tEnd/fLow/fHigh
 * + кнопка «Обновить окно» — ТОЧНЫЙ bbox-запрос и нецветовая альтернатива
 * матрице (DESIGN.md §4.5). Вынесена из spectrogramPanel.ts без изменения
 * поведения; лист без обратного импорта панели. */

import { el } from "../primitives/dom";
import { tileRequestForRange } from "./spectrogramModel";
import type { SpectrogramLevel, TileRequest } from "./spectrogramModel";
import { labeledField, numberInput } from "./spectrogramSetup";

export interface SpectrogramWindowFormDeps {
  getLevel(): SpectrogramLevel | null;
  applyTile(request: TileRequest): Promise<void> | void;
  showError(message: string): void;
}

export interface SpectrogramWindowFormHandle {
  tStart: HTMLInputElement;
  tEnd: HTMLInputElement;
  fLow: HTMLInputElement;
  fHigh: HTMLInputElement;
  applyWindowButton: HTMLButtonElement;
  /** Поля в порядке панели: 4 labeledField + кнопка. */
  fields: HTMLElement[];
  syncFromWindow(t0s: number, t1s: number, f0hz: number, f1hz: number): void;
}

export function createSpectrogramWindowForm(
  deps: SpectrogramWindowFormDeps,
): SpectrogramWindowFormHandle {
  // Числовая форма окна — ТОЧНЫЙ bbox-запрос и нецветовая альтернатива матрице.
  const tStart = numberInput("Начало окна, с");
  const tEnd = numberInput("Конец окна, с");
  const fLow = numberInput("Нижняя граница окна, Гц");
  const fHigh = numberInput("Верхняя граница окна, Гц");
  const applyWindowButton = el("button", {
    className: "lnt-btn lnt-btn-small",
    text: "Обновить окно",
    attrs: { type: "button" },
  });
  applyWindowButton.addEventListener("click", () => {
    const level = deps.getLevel();
    if (level === null) return deps.showError("Сначала постройте спектрограмму.");
    try {
      void deps.applyTile(
        tileRequestForRange(
          level,
          Number(tStart.value),
          Number(tEnd.value),
          Number(fLow.value),
          Number(fHigh.value),
        ),
      );
    } catch (error) {
      deps.showError(error instanceof Error ? error.message : String(error));
    }
  });

  function syncFromWindow(t0s: number, t1s: number, f0hz: number, f1hz: number): void {
    tStart.value = String(t0s);
    tEnd.value = String(t1s);
    fLow.value = String(f0hz);
    fHigh.value = String(f1hz);
  }

  return {
    tStart,
    tEnd,
    fLow,
    fHigh,
    applyWindowButton,
    fields: [
      labeledField("Начало, с", tStart),
      labeledField("Конец, с", tEnd),
      labeledField("От, Гц", fLow),
      labeledField("До, Гц", fHigh),
      applyWindowButton,
    ],
    syncFromWindow,
  };
}
