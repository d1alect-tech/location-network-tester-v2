/** U2: полоса канала — индикатор Полоса/RBW/Окно/Детектор/Сегментов.
 *  Только чтение; форматирование честное (нули и мусор — в «—», не в нули).
 *  Детектор спектр-панели всегда «Среднее»: max-hold дорисован оверлеем
 *  без тоггла (spectrumHoldOverlay), грам-детекторы живут в gramBar. */

import "./channelbar.css";
import { el } from "../primitives/dom";

export type ChannelbarField = "band" | "rbw" | "window" | "detector" | "segments";

const FIELD_LABELS: Record<ChannelbarField, string> = {
  band: "Полоса",
  rbw: "RBW",
  window: "Окно",
  detector: "Детектор",
  segments: "Сегментов",
};

const FIELDS = Object.keys(FIELD_LABELS) as ChannelbarField[];

export const CHANNELBAR_DASH = "—";

export interface ChannelbarHandle {
  readonly root: HTMLElement;
  paint(fields: Readonly<Partial<Record<ChannelbarField, string | null>>>): void;
}

export function createChannelbar(): ChannelbarHandle {
  const values = new Map<ChannelbarField, HTMLElement>();
  const fields = FIELDS.map((field) => {
    const value = el("span", {
      className: "chbar-num",
      attrs: { "data-chbar": field },
      text: CHANNELBAR_DASH,
    });
    values.set(field, value);
    return el("span", { className: "chbar-field" }, [
      el("span", { className: "chbar-tag", text: FIELD_LABELS[field] }),
      value,
    ]);
  });
  const root = el(
    "div",
    { className: "channelbar", attrs: { role: "group", "aria-label": "Параметры канала" } },
    fields,
  );
  return {
    root,
    paint(next) {
      values.forEach((node, field) => {
        const text = next[field];
        node.textContent =
          text === undefined || text === null || text === "" ? CHANNELBAR_DASH : text;
      });
    },
  };
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function trimRu(value: number): string {
  return String(Math.round(value * 100) / 100).replace(".", ",");
}

/** Одно значение Гц в лучшей единице: «45 Гц», «3 кГц», «2,4 МГц». */
export function formatHz(hz: number): string {
  if (hz >= 1_000_000) return `${trimRu(hz / 1_000_000)} МГц`;
  if (hz >= 1_000) return `${trimRu(hz / 1_000)} кГц`;
  return `${trimRu(hz)} Гц`;
}

/** Диапазон «3 кГц – 3 МГц»: каждый конец в своей единице. null — нет данных. */
export function formatBandRange(
  lowHz: number | null | undefined,
  highHz: number | null | undefined,
): string | null {
  if (!isFiniteNumber(lowHz) || !isFiniteNumber(highHz)) return null;
  return `${formatHz(lowHz)} – ${formatHz(highHz)}`;
}

/** RBW из шага сетки (ENBW Ханна 1.5 — тот же множитель, что planeControl). */
export function formatChannelRbw(resolutionHz: number | null | undefined): string | null {
  if (!isFiniteNumber(resolutionHz) || resolutionHz <= 0) return null;
  return formatHz(1.5 * resolutionHz);
}
