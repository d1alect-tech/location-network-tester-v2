/** Таймлайн шагов протокола (todo 43): упорядоченная визуализация steps
 * эксперимента. Порядок берётся из поля order бэкенда; состояние — текст
 * и номер, без цветовых подсказок. */

import { clearElement, el } from "../../components/primitives/dom";

export interface TimelineStep {
  readonly order: number;
  readonly condition_id: string;
  readonly instruction: string;
}

export interface ProtocolTimelineHandle {
  root: HTMLElement;
  setSteps(steps: readonly TimelineStep[], kindLabel: string): void;
  setLoading(): void;
  setError(message: string): void;
}

function sortSteps(steps: readonly TimelineStep[]): TimelineStep[] {
  return [...steps].sort((a, b) => a.order - b.order);
}

export function createProtocolTimeline(): ProtocolTimelineHandle {
  const list = el("ol", {
    className: "lnt-exp-timeline",
    attrs: { "aria-label": "Шаги протокола" },
  });
  const heading = el("h3", { className: "lnt-exp-subtitle", text: "Протокол" });
  const kindBadge = el("span", { className: "lnt-exp-kind-badge", text: "" });
  const header = el("div", { className: "lnt-exp-timeline-header" }, [heading, kindBadge]);
  const status = el("p", { className: "lnt-helper-text", attrs: { role: "status" } });
  const root = el("section", { className: "lnt-exp-timeline-section" }, [header, status, list]);

  return {
    root,
    setSteps: (steps, kindLabel) => {
      clearElement(list);
      status.textContent = `Шагов в протоколе: ${String(steps.length)}`;
      kindBadge.textContent = kindLabel;
      for (const step of sortSteps(steps)) {
        const badge = el("span", {
          className: "lnt-exp-step-order",
          text: String(step.order),
          attrs: { "aria-hidden": "true" },
        });
        const condition = el("span", {
          className: "lnt-exp-step-condition",
          text: step.condition_id,
        });
        const text = el("span", { className: "lnt-exp-step-instruction", text: step.instruction });
        const item = el("li", { className: "lnt-exp-step" }, [badge, condition, text]);
        item.setAttribute("aria-label", `Шаг ${String(step.order)}: ${step.instruction}`);
        list.append(item);
      }
    },
    setLoading: () => {
      clearElement(list);
      status.textContent = "Загрузка протокола…";
    },
    setError: (message) => {
      clearElement(list);
      status.textContent = message;
    },
  };
}
