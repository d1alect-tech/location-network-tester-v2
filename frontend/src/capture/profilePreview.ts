/** Панель предпросмотра профиля: точный снимок метаданных, которые сохранит
 * захват. Базовая сессия видима у всех режимов, которые её используют. */

import { el } from "../components/primitives/dom";
import { buildJobRequest, validateCaptureForm } from "./modes";
import type { CaptureFormValues, CaptureModeDef, CaptureSource } from "./modes";

function row(term: string, value: string): HTMLElement {
  return el("div", { className: "capture-preview-row readout-cell" }, [
    el("dt", { className: "capture-preview-term readout-label", text: term }),
    el("dd", { className: "capture-preview-value readout-value", text: value }),
  ]);
}

/** Перестраивает содержимое панели под текущий режим и значения формы.
 * Показывает ровно те поля запроса, что уйдут в бэкенд (контракт models.py). */
export function renderProfilePreview(
  container: HTMLElement,
  mode: CaptureModeDef,
  values: CaptureFormValues,
  source: CaptureSource,
): void {
  const { valid } = validateCaptureForm(values);
  const list = el("dl", { className: "capture-preview-list readout-grid" });
  list.append(
    row("Источник", source === "simulator" ? "Симулятор (синтетика)" : "Осциллограф Hantek 6022BE"),
  );
  list.append(row("Тип сессии", mode.sessionTypeRu));
  list.append(row("Вход CH1", mode.ch1SetupRu));
  list.append(row("Каналы", String(mode.channels)));

  if (valid === null) {
    list.append(row("Параметры записи", "исправьте ошибки формы"));
    clearAndAppend(container, [
      el("h3", { className: "capture-section-title panel-title", text: "Профиль записи" }),
      list,
    ]);
    return;
  }

  if (source === "simulator") {
    list.append(row("Профиль симуляции", valid.profile));
  }
  list.append(row("Длительность", `${valid.durationS} с`));
  list.append(row("Частота дискретизации", `${valid.sampleRateHz} Гц`));
  if (source === "device") {
    list.append(row("Диапазон CH1", `${valid.rangeV} В`));
  }
  if (mode.selfNoise) {
    list.append(row("Самошум", "да (входы терминированы)"));
  }
  if (mode.usesBaseline) {
    // Базовая линия никогда не прячется у режимов, которые её используют.
    list.append(row("Базовая сессия", valid.baselineSession ?? "— (не выбрана)"));
  }
  list.append(row("Метка", valid.label ?? "—"));
  const series =
    valid.repeat > 1
      ? `${valid.repeat} повторов, интервал ${valid.intervalS} с`
      : "одиночная запись";
  list.append(row("Серия/протокол", series));

  // Точная форма запроса — то же, что уйдёт в POST /api/jobs.
  const request = buildJobRequest(mode, valid, source);
  const requestLine = el("p", {
    className: "capture-preview-request cell-wrap",
    text: `POST /api/jobs → kind: ${request.kind}${source === "device" ? `, input: ${mode.input}` : ""}`,
  });

  clearAndAppend(container, [
    el("h3", { className: "capture-section-title panel-title", text: "Профиль записи" }),
    list,
    requestLine,
  ]);
}

function clearAndAppend(container: HTMLElement, children: Node[]): void {
  while (container.firstChild) container.removeChild(container.firstChild);
  for (const child of children) container.append(child);
}
