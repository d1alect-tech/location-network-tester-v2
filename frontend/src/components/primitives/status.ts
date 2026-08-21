/** Статусы и прогресс: единая aria-live область, индикатор стадии задачи.
 * Объявления текстовые (не цветовые); русские формулировки стадий. */

import { el } from "./dom";

let politeRegion: HTMLElement | null = null;

function ensurePoliteRegion(): HTMLElement {
  if (politeRegion?.isConnected) return politeRegion;
  const existing = document.querySelector('[role="status"][aria-live="polite"]');
  if (existing instanceof HTMLElement) {
    politeRegion = existing;
    return existing;
  }
  const region = el("div", {
    className: "lnt-visually-hidden",
    attrs: { role: "status", "aria-live": "polite" },
  });
  document.body.append(region);
  politeRegion = region;
  return region;
}

/** Вежливое объявление для скринридера (одна общая live-область). */
export function announcePolite(text: string): void {
  ensurePoliteRegion().textContent = text;
}

export interface JobProgressHandle {
  root: HTMLElement;
  /** Стадия серии: «Запись: 2 из 5». */
  setStage(stage: string, index: number, total: number): void;
  /** Неопределённый прогресс с текстовым объявлением. */
  setIndeterminate(message: string): void;
  done(): void;
}

export function createJobProgress(): JobProgressHandle {
  const bar = el("div", {
    className: "lnt-progress-bar",
    attrs: { role: "progressbar", "aria-valuemin": "0" },
  });
  const text = el("span", { className: "lnt-progress-text" });
  const root = el("div", { className: "lnt-progress" }, [bar, text]);

  return {
    root,
    setStage: (stage, index, total) => {
      bar.setAttribute("aria-valuenow", String(index));
      bar.setAttribute("aria-valuemax", String(total));
      bar.removeAttribute("aria-busy");
      announcePolite(`${stage}: ${index} из ${total}`);
      text.textContent = `${stage}: ${index} из ${total}`;
    },
    setIndeterminate: (message) => {
      bar.removeAttribute("aria-valuenow");
      bar.removeAttribute("aria-valuemax");
      bar.setAttribute("aria-busy", "true");
      announcePolite(message);
      text.textContent = message;
    },
    done: () => {
      bar.removeAttribute("aria-busy");
      bar.setAttribute("aria-valuenow", "1");
      bar.setAttribute("aria-valuemax", "1");
      text.textContent = "Готово";
      announcePolite("Готово");
    },
  };
}
