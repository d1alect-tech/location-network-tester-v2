/** Плагин аннотаций uPlot: вертикали пиков и полосы FWHM на подложке.
 * Полоса: f0 ± FWHM/2, где Q = f0/FWHM (контракт analysis.spectrum.peaks).
 * Доступная альтернатива — таблица пиков рядом с графиком. */

import type uPlot from "uplot";
import { el } from "../primitives/dom";
import type { ChartPeak } from "./types";

export interface PeaksPluginOptions {
  peaks: () => readonly ChartPeak[];
  /** Цвет вертикалей и полос из токенов. */
  color: string;
}

function bandBounds(peak: ChartPeak): [number, number] | null {
  const q = peak.q_factor;
  if (!Number.isFinite(q) || q <= 0) return null;
  const fwhm = peak.frequency_hz / q;
  return [peak.frequency_hz - fwhm / 2, peak.frequency_hz + fwhm / 2];
}

export function createPeaksPlugin(options: PeaksPluginOptions): uPlot.Plugin {
  return {
    hooks: {
      draw(self: uPlot): void {
        const peaks = options.peaks();
        if (peaks.length === 0) return;
        const ctx = self.ctx;
        const { top, height } = self.bbox;
        ctx.save();
        for (const peak of peaks) {
          if (!Number.isFinite(peak.frequency_hz)) continue;
          const x = self.valToPos(peak.frequency_hz, "x");
          // Полоса FWHM — полупрозрачный столбец на подложке.
          const bounds = bandBounds(peak);
          if (bounds !== null && bounds[1] > bounds[0]) {
            const left = self.valToPos(bounds[0], "x");
            const right = self.valToPos(bounds[1], "x");
            ctx.globalAlpha = 0.12;
            ctx.fillStyle = options.color;
            ctx.fillRect(left, top, right - left, height);
            ctx.globalAlpha = 1;
          }
          // Вертикаль маркера пика.
          ctx.strokeStyle = options.color;
          ctx.setLineDash([4, 3]);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x, top);
          ctx.lineTo(x, top + height);
          ctx.stroke();
        }
        ctx.restore();
      },
    },
  };
}

/** Доступная альтернатива аннотациям: список пиков текстом и таблицей. */
export function createPeaksSummary(peaks: readonly ChartPeak[]): HTMLElement {
  const caption = el("p", {
    className: "lnt-peaks-summary-caption",
    text:
      peaks.length === 0
        ? "Выраженных пиков не найдено"
        : `Аннотации спектра: ${peaks.length} пик(ов), полосы — ширина по уровню половинной мощности`,
  });
  const table = el("table", { className: "lnt-peaks-summary" });
  const head = el("thead");
  head.append(
    el("tr", {}, [
      el("th", { text: "Частота, Гц" }),
      el("th", { text: "Уровень, дБ" }),
      el("th", { text: "Q" }),
    ]),
  );
  table.append(head);
  const body = el("tbody");
  for (const peak of peaks) {
    body.append(
      el("tr", {}, [
        el("td", {
          text: peak.frequency_hz.toLocaleString("ru-RU", { maximumSignificantDigits: 6 }),
        }),
        el("td", { text: peak.level_db.toLocaleString("ru-RU", { maximumFractionDigits: 1 }) }),
        el("td", { text: peak.q_factor.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) }),
      ]),
    );
  }
  table.append(body);
  const root = el("div", { className: "lnt-peaks" }, [caption]);
  if (peaks.length > 0) root.append(table);
  return root;
}
