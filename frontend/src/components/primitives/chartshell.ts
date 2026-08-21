/** Оболочка графика-заглушки: заголовок, панель инструментов, оверлеи
 * состояний (загрузка/ошибка с повтором/пусто) и точка монтирования
 * для будущих uPlot/ECharts. Библиотеки графиков сюда не импортируются. */

import { clearElement, el } from "./dom";

export interface ChartShellOptions {
  title: string;
  onDownloadCsv?: () => void;
}

export interface ChartShellHandle {
  root: HTMLElement;
  /** Точка монтирования содержимого (график будет встроен позже). */
  body: HTMLElement;
  /** Слот для контролов рядом с заголовком. */
  toolbar: HTMLElement;
  setLoading(): void;
  setError(message: string, retry: () => void): void;
  setEmpty(message: string): void;
  setContent(content: Node): void;
}

function overlay(text: string): HTMLElement {
  return el("div", { className: "lnt-chart-overlay", text });
}

export function createChartShell(options: ChartShellOptions): ChartShellHandle {
  const title = el("h3", { className: "lnt-chart-title", text: options.title });
  const toolbar = el("div", { className: "lnt-chart-toolbar" });
  const header = el("div", { className: "lnt-chart-header" }, [title, toolbar]);

  if (options.onDownloadCsv) {
    const csv = el("button", {
      className: "lnt-btn",
      text: "Скачать CSV",
      attrs: { type: "button" },
    });
    csv.addEventListener("click", () => options.onDownloadCsv?.());
    header.append(csv);
  }

  const body = el("div", { className: "lnt-chart-body", attrs: { "aria-live": "polite" } });
  const root = el("section", { className: "lnt-chart" }, [header, body]);

  return {
    root,
    body,
    toolbar,
    setLoading: () => {
      clearElement(body);
      body.append(overlay("Загрузка…"));
    },
    setError: (message, retry) => {
      clearElement(body);
      const note = overlay("Ошибка загрузки");
      note.classList.add("lnt-chart-error");
      const detail = el("p", { className: "lnt-error-text", text: message });
      const retryButton = el("button", { className: "lnt-btn", text: "Повторить" });
      retryButton.addEventListener("click", () => retry());
      note.append(detail, retryButton);
      body.append(note);
    },
    setEmpty: (message) => {
      clearElement(body);
      body.append(overlay(message));
    },
    setContent: (content) => {
      clearElement(body);
      body.removeAttribute("aria-busy");
      body.append(content);
    },
  };
}
