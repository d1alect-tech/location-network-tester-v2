/** Рабочая область «Отчёты» (#/reports): выбор эксперимента → сборка отчёта
 * из существующих контрактов бэкенда → превью с provenance → выгрузка .md.
 * Готовых HTTP-маршрутов отчётов у бэкенда нет, поэтому превью и файл
 * собираются клиентом из statistics-runs/деталей сессий — без выдуманных
 * эндпоинтов; это явно указано в интерфейсе. */

import type { LntApiClient } from "../../api/client";
import type { OpenRecord } from "../../api/types-research";
import { clearElement, el } from "../../components/primitives/dom";
import { errorWithRetry } from "../../components/primitives/stateViews";
import { announcePolite } from "../../components/primitives/status";
import type { RouteStore } from "../../state/routeState";
import { protocolLabel } from "../experiments/experimentModel";
import type { ExperimentDetail } from "../experiments/experimentsStore";
import { REPORT_EXPORT_FORMAT, buildReportFilename, downloadMarkdown } from "./reportExport";
import { previewBlock } from "./reportPreview";
import { createReportsHeader, createReportsInvitation } from "./reportsHeader";
import { ReportsStore } from "./reportsStore";
import { createWorkspaceStatusBlock, degradedReportMessage } from "./reportsWorkspaceStatus";
import "./reports.css";

export interface ReportsWorkspaceOptions {
  client: LntApiClient;
  routes: RouteStore;
}

export function mountReportsWorkspace(
  container: HTMLElement,
  options: ReportsWorkspaceOptions,
): () => void {
  const { client, routes } = options;
  const store = new ReportsStore({ client });
  const listHost = el("div", {});
  const detailHost = el("div", { className: "lnt-rep-detail" });
  const unitsInput = el("input", {
    className: "ctl lnt-input",
    attrs: { type: "text", id: "lnt-rep-units", value: "В²/Гц", "aria-label": "Единицы измерения" },
  });
  const buildButton = el("button", {
    className: "btn lnt-btn lnt-btn-primary",
    text: "Собрать отчёт",
    attrs: {
      type: "button",
      id: "lnt-rep-build",
      disabled: "disabled",
      title: "Сначала выберите эксперимент слева",
      "aria-describedby": "lnt-rep-hint",
    },
  });
  const downloadButton = el("button", {
    className: "btn btn-secondary lnt-btn",
    text: "Скачать отчёт (.md)",
    attrs: {
      type: "button",
      id: "lnt-rep-download",
      disabled: "disabled",
      "data-export-format": REPORT_EXPORT_FORMAT,
      title: "Станет доступна после сборки отчёта",
      "aria-describedby": "lnt-rep-hint",
    },
  });
  const { statusHost, errorBanner, setStatus, showError, setPendingRetry } =
    createWorkspaceStatusBlock();
  const buildHint = el("p", {
    className: "lnt-hint",
    text: "Сначала выберите эксперимент слева — кнопка «Собрать отчёт» станет доступна.",
    attrs: { id: "lnt-rep-hint" },
  });

  const leftPane = el("div", { className: "lnt-rep-left" }, [
    el("div", { className: "lnt-exp-actions" }, [
      el("button", {
        className: "btn btn-secondary lnt-btn",
        text: "Обновить",
        attrs: { type: "button", id: "lnt-rep-refresh" },
      }),
    ]),
    listHost,
  ]);
  const invitation = createReportsInvitation();
  const rightPane = el("div", { className: "lnt-rep-right" }, [
    invitation,
    buildHint,
    statusHost,
    errorBanner,
    detailHost,
  ]);
  const workspace = el("div", { className: "lnt-rep-workspace" }, [leftPane, rightPane]);
  const root = el("div", { className: "lnt-rep" }, [createReportsHeader(), workspace]);
  container.append(root);

  void client.ensureReady().catch((error: unknown) => {
    const reason = error instanceof Error ? error.message : String(error);
    setPendingRetry(() => void refreshList());
    showError(`Сервер недоступен: ${reason}. Проверьте соединение и повторите.`);
  });

  let currentDetail: ExperimentDetail | null = null;
  let currentMarkdown: string | null = null;
  let pendingReportId: string | null = null;

  root.querySelector("#lnt-rep-refresh")?.addEventListener("click", () => void refreshList());
  buildButton.addEventListener("click", () => void build());
  downloadButton.addEventListener("click", download);

  function renderListState(): void {
    const state = store.experiments.get();
    clearElement(listHost);
    if (state.kind === "loading") {
      listHost.append(
        el("p", { className: "lnt-helper-text", text: "Загрузка списка экспериментов…" }),
      );
      return;
    }
    if (state.kind === "error") {
      listHost.append(
        errorWithRetry(
          `Не удалось загрузить список экспериментов: ${state.error.message}.`,
          () => void refreshList(),
        ),
      );
      return;
    }
    if (state.kind !== "ready") return;
    if (state.value.length === 0) {
      listHost.append(
        el("p", {
          className: "lnt-helper-text",
          text: "Экспериментов пока нет. Создайте их в разделе «Эксперименты».",
        }),
      );
      return;
    }
    const list = el("ul", {
      className: "lnt-exp-list",
      attrs: { "aria-label": "Эксперименты для отчётов" },
    });
    for (const item of state.value) {
      const id = String(item.experiment_id ?? "");
      const title = String(item.title ?? id);
      const li = el("li", { className: "lnt-exp-list-item" });
      const open = el("button", {
        className: "btn btn-secondary lnt-btn lnt-exp-open",
        text: `${title} (${id})`,
        attrs: { type: "button", "data-experiment-id": id },
      });
      open.addEventListener("click", () => {
        routes.replaceParams({ experiment: id });
        void loadDetailInto(id);
      });
      li.append(open);
      list.append(li);
    }
    listHost.append(list);
  }

  async function loadDetailInto(experimentId: string): Promise<void> {
    pendingReportId = experimentId;
    invitation.hidden = true;
    clearElement(detailHost);
    detailHost.append(el("p", { className: "lnt-helper-text", text: "Загрузка эксперимента…" }));
    await store.detail.load(experimentId);
    const state = store.detail.get();
    if (state.kind !== "ready" || state.key !== experimentId) {
      clearElement(detailHost);
      if (state.kind === "error") {
        detailHost.append(
          errorWithRetry(`Не удалось загрузить эксперимент: ${state.error.message}.`, () => {
            if (pendingReportId) void loadDetailInto(pendingReportId);
          }),
        );
      }
      return;
    }
    currentDetail = state.value;
    currentMarkdown = null;
    downloadButton.disabled = true;
    downloadButton.title = "Станет доступна после сборки отчёта";
    setStatus("Сначала соберите отчёт: выгрузка станет доступна после сборки.");
    const experiment = state.value.experiment as OpenRecord;
    clearElement(detailHost);
    detailHost.append(
      el("h3", { className: "lnt-exp-subtitle", text: String(experiment.title ?? experimentId) }),
      el("p", {
        className: "lnt-rep-meta",
        text: `План: ${protocolLabel(String((experiment.protocol as OpenRecord | undefined)?.kind ?? ""))} · участников: ${String(state.value.members.length)}`,
      }),
      el("div", { className: "lnt-exp-actions" }, [
        el("label", { className: "field lnt-field-inline", attrs: { for: "lnt-rep-units" } }, [
          el("span", { className: "field-label lnt-label-text", text: "Единицы" }),
          unitsInput,
        ]),
        buildButton,
        downloadButton,
      ]),
    );
    buildButton.disabled = false;
    buildButton.title = "Собрать отчёт из данных бэкенда";
    buildHint.textContent =
      "Эксперимент выбран. Нажмите «Собрать отчёт», затем проверьте ограничения перед выгрузкой.";
  }

  async function build(): Promise<void> {
    if (currentDetail === null) {
      showError("Нет выбранного эксперимента для сборки. Сначала выберите эксперимент слева.");
      return;
    }
    setPendingRetry(() => void build());
    buildButton.disabled = true;
    errorBanner.setAttribute("hidden", "");
    setStatus("Сборка отчёта: расчёт статистики на сервере…");
    try {
      const result = await store.buildReport(currentDetail, { units: unitsInput.value });
      currentMarkdown = result.markdown;
      detailHost.querySelector(".lnt-rep-preview")?.remove();
      detailHost.append(previewBlock(result.draft));
      downloadButton.disabled = false;
      downloadButton.title = "Скачать собранный отчёт (.md)";
      buildHint.textContent = "Отчёт собран. Проверьте ограничения, затем скачайте файл.";
      setStatus("Отчёт собран. Проверьте ограничения перед выгрузкой.");
      const degraded = degradedReportMessage(result.draft.limitations);
      if (degraded !== null) return showError(degraded);
      announcePolite("Отчёт собран");
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      setStatus("Сборка не выполнена.");
      showError(
        `Сборка не выполнена: ${reason}. Проверьте соединение и повторите.`,
        () => void build(),
      );
    } finally {
      buildButton.disabled = false;
    }
  }

  function download(): void {
    if (currentMarkdown === null || currentDetail === null) {
      showError("Нет собранного отчёта для выгрузки. Сначала соберите отчёт.");
      return;
    }
    setPendingRetry(() => download());
    try {
      const experimentId = String(currentDetail.experiment.experiment_id);
      downloadMarkdown(currentMarkdown, buildReportFilename(experimentId));
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      showError(`Выгрузка не выполнена: ${reason}. Проверьте соединение и повторите.`);
    }
  }

  const refreshList = (): Promise<void> => store.experiments.load("all");
  const unsubscribe = store.experiments.subscribe(() => renderListState());
  void refreshList().then(() => {
    const preset = routes.get().params.experiment;
    if (preset) void loadDetailInto(preset);
  });

  return () => {
    unsubscribe();
    store.abort();
  };
}
