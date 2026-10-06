/** Блок THD-V инспектора: факт-значение, факт-сравнение с настроенным
 * пределом и полоса с меткой предела. Оценочных слов нет («норма»/«годен»
 * запрещены владельцем): сравнение описывает положение значения относительно
 * предела. Предел и порог окон — единственные в views/inspect/thdVerdict. */

import { el } from "../../components/primitives/dom";
import { THD_V_LIMIT } from "../inspect/thdVerdict";
import type { SessionMetrics } from "./contextMetrics";

const PERCENT = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const WHOLE = new Intl.NumberFormat("ru-RU");

/** Меньше ста окон гармоник — сравнение с пределом не выдаётся. */
export const THD_MIN_CYCLES = 100;

export type ThdCompare = "above" | "below" | "few" | "none";

export function limitPercentText(): string {
  return WHOLE.format(THD_V_LIMIT * 100);
}

export function thdCompareOf(metrics: SessionMetrics): ThdCompare {
  if (metrics.thdRatio === null) return "none";
  if (metrics.cycles === null || metrics.cycles < THD_MIN_CYCLES) return "few";
  return metrics.thdRatio > THD_V_LIMIT ? "above" : "below";
}

export function thdBadgeText(compare: ThdCompare): string {
  if (compare === "above") return `выше предела ${limitPercentText()} %`;
  if (compare === "below") return `ниже предела ${limitPercentText()} %`;
  if (compare === "few") return `окон гармоник меньше ${String(THD_MIN_CYCLES)}`;
  return "нет данных";
}

export function thdCaptionText(metrics: SessionMetrics, compare: ThdCompare): string {
  const base = `THD-V, ключевая метрика качества сети. Предел ${limitPercentText()} % — порог интерфейса.`;
  if (compare === "none") return `${base} Значение отсутствует: пропущенное не подменяется нулём.`;
  if (compare === "few" || metrics.cycles === null) return base;
  return `${base} Окон проанализировано: ${WHOLE.format(metrics.cycles)}.`;
}

/** Доля шкалы 0..2*предел; без значения полоса пуста, ноль не рисуется. */
export function thdBarScale(ratio: number | null, limit: number = THD_V_LIMIT): number {
  if (ratio === null) return 0;
  return Math.min(1, ratio / (limit * 2));
}

export function renderThdBlock(metrics: SessionMetrics): HTMLElement {
  const compare = thdCompareOf(metrics);
  const value = el("span", { className: "thd-value" });
  if (metrics.thdRatio === null) {
    value.textContent = "недоступно";
  } else {
    value.append(
      document.createTextNode(PERCENT.format(metrics.thdRatio * 100)),
      el("span", { className: "thd-unit", text: "%" }),
    );
  }
  const fill = el("span", { className: "thd-bar-fill" });
  fill.style.transform = `scaleX(${thdBarScale(metrics.thdRatio).toFixed(3)})`;
  const bar = el("span", { className: "thd-bar", attrs: { "aria-hidden": "true" } }, [
    fill,
    el("span", { className: "thd-limit-mark" }),
  ]);
  return el("div", { className: "insp-thd", attrs: { "data-thd-compare": compare } }, [
    el("div", { className: "thd-head" }, [
      value,
      el("span", {
        className: "thd-badge",
        text: thdBadgeText(compare),
        attrs: { "data-thd-badge": "" },
      }),
    ]),
    el("span", { className: "thd-caption", text: thdCaptionText(metrics, compare) }),
    bar,
  ]);
}
