/** Панель live-спектрограммы раздела «Захват»: section.panel на V6-классах.
 * Подписка на жизненный цикл — через onSnapshot() из captureView
 * (attachStream/dispose), sse и jobTimeline не затрагиваются. */

import type { PlotsApi } from "../api/client-jobs";
import type { JobSnapshot } from "../api/types-jobs";
import { el } from "../components/primitives/dom";
import { type LiveKind, createLivePoller } from "./spectrogramLivePoller";
import { buildSpectrogramLiveRenderer } from "./spectrogramLiveRenderer";

export interface LivePanelHandle {
  readonly root: HTMLElement;
  onSnapshot(snapshot: JobSnapshot | null): void;
  dispose(): void;
}

export function createSpectrogramLivePanel(deps: {
  plots: Pick<PlotsApi, "spectrum">;
}): LivePanelHandle {
  const renderer = buildSpectrogramLiveRenderer();
  const empty = el("p", {
    className: "livegram-empty t-compact",
    attrs: { "data-livegram-empty": "" },
    text: "Нет данных спектра — запустите запись или дождитесь завершения задачи.",
  });
  const session = el("p", {
    className: "livegram-session t-compact num cell-wrap",
    attrs: { "data-livegram-session": "" },
  });
  session.hidden = true;

  const poller = createLivePoller(deps.plots, {
    onColumn: (frequencyHz, psdDb) => {
      renderer.pushSpectrumColumn(frequencyHz, psdDb);
    },
    onSession: (name, kind: LiveKind) => {
      empty.hidden = true;
      session.hidden = false;
      session.textContent = kind === "live" ? `Live · ${name}` : `Сессия ${name}`;
    },
    onEmpty: () => {
      // Колонки уже накоплены — не затираем полотно, только держим подпись.
      if (renderer.columnCount() === 0) {
        empty.hidden = false;
        session.hidden = true;
      }
    },
  });

  const head = el("div", { className: "panel-hd" }, [
    el("h2", { className: "panel-title", text: "Спектрограмма" }),
  ]);
  head.append(renderer.bar);
  const body = el("div", { className: "panel-bd", attrs: { "data-live-spectrogram": "" } }, [
    renderer.host,
    session,
    empty,
  ]);
  const root = el(
    "section",
    {
      className: "capture-livegram panel",
      attrs: { "aria-label": "Спектрограмма записи" },
    },
    [head, body],
  );

  // Пустое состояние видимо сразу: данных нет, пока не пришёл первый столбец.
  poller.notifySnapshot(null);

  return {
    root,
    onSnapshot(snapshot) {
      poller.notifySnapshot(snapshot);
    },
    dispose() {
      poller.dispose();
      renderer.dispose();
    },
  };
}
