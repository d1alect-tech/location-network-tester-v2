/** B3: таблица маркеров спектра. Пики из detail().analysis, дельты A−B
 * по payload через readout, гармоники H2–H40 от сильнейшего пика,
 * СКЗ полосы (анализ либо оценка по дисплею). Уровни — дБ отн. 1 В²/Гц. */

import type { SpectrumPayload } from "../../api/types-plots";
import { clearElement, el } from "../../components/primitives/dom";
import type { MarkersPaintSource } from "./spectrumReadout";
import { DB_REF_LABEL, deltaAt, readoutAt, ruDb, ruHz } from "./spectrumReadout";

const MAX_HARMONIC_ORDER = 40;

export interface SpectrumMarkersTable {
  readonly root: HTMLElement;
  paint(source: MarkersPaintSource): void;
}

function recordOf(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

interface AnalysisPeak {
  frequency_hz: number;
  level_db: number;
}

function analysisPeaks(analysis: unknown): AnalysisPeak[] {
  const peaks = recordOf(recordOf(analysis)?.spectrum)?.peaks;
  if (!Array.isArray(peaks)) return [];
  const found: AnalysisPeak[] = [];
  for (const peak of peaks) {
    const record = recordOf(peak);
    const frequency_hz = record?.frequency_hz;
    const level_db = record?.level_db;
    if (typeof frequency_hz === "number" && typeof level_db === "number") {
      found.push({ frequency_hz, level_db });
    }
  }
  return found;
}

function strongestPeak(peaks: AnalysisPeak[]): AnalysisPeak | null {
  let best: AnalysisPeak | null = null;
  for (const peak of peaks) {
    if (best === null || peak.level_db > best.level_db) best = peak;
  }
  return best;
}

function bandRmsText(source: MarkersPaintSource): string {
  const fromAnalysis = recordOf(recordOf(source.analysis)?.spectrum)?.band_rms_v;
  if (typeof fromAnalysis === "number" && Number.isFinite(fromAnalysis) && fromAnalysis >= 0) {
    return `${ruHz.format(fromAnalysis)} В СКЗ`;
  }
  const df = source.payloadA.resolution_hz;
  if (typeof df !== "number" || !(df > 0)) return "—";
  let power = 0;
  for (const value of source.payloadA.psd_v2_per_hz) {
    if (value > 0 && Number.isFinite(value)) power += value * df;
  }
  if (!(power > 0)) return "—";
  return `${ruHz.format(Math.sqrt(power))} В СКЗ (оценка по дисплею)`;
}

function bandRangeText(payload: SpectrumPayload): string {
  const count = Math.min(payload.frequency_hz.length, payload.psd_v2_per_hz.length);
  if (count === 0) return "—";
  const first = payload.frequency_hz[0] ?? Number.NaN;
  const last = payload.frequency_hz[count - 1] ?? Number.NaN;
  if (!Number.isFinite(first) || !Number.isFinite(last)) return "—";
  return `${ruHz.format(first)}…${ruHz.format(last)} Гц`;
}

function markerRow(
  name: string,
  frequencyHz: number,
  source: MarkersPaintSource,
  withDelta: boolean,
): HTMLElement {
  const readout = readoutAt(source.payloadA, frequencyHz);
  const row = el("tr", {}, [
    el("td", { text: name }),
    el("td", {
      text: readout === null ? "—" : ruHz.format(readout.frequencyHz),
      attrs: { class: "num" },
    }),
    el("td", {
      text: readout === null ? "—" : `${ruDb.format(readout.levelDb)} ${DB_REF_LABEL}`,
      attrs: { class: "num" },
    }),
  ]);
  if (withDelta) {
    const delta = deltaAt(source.payloadA, source.payloadB, frequencyHz);
    row.append(
      el("td", {
        text: delta === null ? "—" : `${ruDb.format(delta)} дБ`,
        attrs: { class: "num" },
      }),
    );
  }
  return row;
}

export function createMarkersTable(): SpectrumMarkersTable {
  const root = el("section", {
    className: "spectrum-markers",
    attrs: { "data-spectrum-markers": "", "aria-label": "Маркеры спектра" },
  });

  return {
    root,
    paint(source) {
      clearElement(root);
      const withDelta = source.payloadB !== null;
      const table = el("table", { attrs: { "data-spectrum-markers-table": "" } });
      table.append(el("caption", { text: "Маркеры спектра" }));
      const header = el("tr", {}, [
        el("th", { text: "Маркер", attrs: { scope: "col" } }),
        el("th", { text: "Частота, Гц", attrs: { scope: "col" } }),
        el("th", { text: `Уровень, ${DB_REF_LABEL}`, attrs: { scope: "col" } }),
      ]);
      if (withDelta) header.append(el("th", { text: "Δ A−B, дБ", attrs: { scope: "col" } }));
      table.append(header);
      const peaks = analysisPeaks(source.analysis);
      if (peaks.length === 0) {
        table.append(
          el("tr", {}, [el("td", { text: "Пики не найдены", attrs: { colspan: "4" } })]),
        );
      }
      peaks.forEach((peak, index) => {
        table.append(markerRow(`Пик ${index + 1}`, peak.frequency_hz, source, withDelta));
      });
      const fundamental = strongestPeak(peaks);
      if (fundamental !== null) {
        const last =
          source.payloadA.frequency_hz[
            Math.min(source.payloadA.frequency_hz.length, source.payloadA.psd_v2_per_hz.length) - 1
          ] ?? 0;
        for (let order = 2; order <= MAX_HARMONIC_ORDER; order += 1) {
          const harmonicHz = order * fundamental.frequency_hz;
          if (harmonicHz > last) break;
          if (readoutAt(source.payloadA, harmonicHz) === null) continue;
          table.append(markerRow(`H${order}`, harmonicHz, source, withDelta));
        }
      }
      const bandRow = el("tr", {}, [
        el("td", { text: "СКЗ полосы" }),
        el("td", { text: bandRangeText(source.payloadA) }),
        el("td", { text: bandRmsText(source), attrs: { class: "num" } }),
      ]);
      if (withDelta) bandRow.append(el("td", { text: "—" }));
      table.append(bandRow);
      root.append(table);
    },
  };
}
