/** Рабочая область «Эксперименты» (todo 43): список экспериментов, детали
 * с таймлайном протокола, участники с QC/исключениями и вкладки
 * «Сравнение» / «Тренды» / «Гипотезы». Монтируется аддитивным блоком
 * AppShell по образцу todo 39; при уходе с маршрута всё обрывается.
 * T11: вкладки — в experimentsTabs, синхронизация строк/метрики — в
 * experimentsSync; C3: здоровье, оверлей и загрузка деталей — в
 * experimentsDetailController; здесь каркас и список. */

import type { LntApiClient } from "../../api/client";
import { clearElement, el } from "../../components/primitives/dom";
import { errorWithRetry } from "../../components/primitives/stateViews";
import type { RouteStore } from "../../state/routeState";
import { ComparisonView } from "./comparisonView";
import { ExperimentWizard } from "./experimentWizard";
import { ExperimentsDetailController } from "./experimentsDetailController";
import { ExperimentsStore } from "./experimentsStore";
import { metricValue } from "./experimentsSync";
import { createExperimentsTabs } from "./experimentsTabs";
import { HypothesisView } from "./hypothesisView";
import { MemberTableView } from "./memberTableView";
import { createProtocolTimeline } from "./protocolTimeline";
import { TrendView } from "./trendView";
import "./experiments.css";

export interface ExperimentsWorkspaceOptions {
  client: LntApiClient;
  routes: RouteStore;
}

export function mountExperimentsWorkspace(
  container: HTMLElement,
  options: ExperimentsWorkspaceOptions,
): () => void {
  const { client, routes } = options;
  const store = new ExperimentsStore({ client });
  const timeline = createProtocolTimeline();
  const members = new MemberTableView({
    store,
    experimentId: "",
    healthBySession: new Map(),
    onInclusionChange: () => detailController.syncComparisonRows(),
  });
  const comparison = new ComparisonView({
    client,
    valueSource: async (sessionId, featureKey, signal) => {
      const detail = await client.plots.detail(sessionId, { signal });
      return metricValue(detail, featureKey);
    },
  });
  // Явный тип возврата разрывает цикл вывода trends ↔ detailController.
  const trendValue = async (sessionId: string, signal: AbortSignal): Promise<number | null> => {
    const detail = await client.plots.detail(sessionId, { signal });
    return metricValue(
      detail,
      String(
        detailController.currentDetail?.experiment.primary_estimands?.[0]?.feature_key ??
          "band_mid_total",
      ),
    );
  };
  const trends = new TrendView({ client, valueSource: trendValue });
  const hypotheses = new HypothesisView({ client });

  // --- левая колонка: список + создание -----------------------------------
  const listHost = el("div", {});
  const leftPane = el("div", { className: "lnt-exp-left" }, [
    el("h2", { className: "placeholder-title", text: "Эксперименты" }),
    el("div", { className: "lnt-exp-actions cmdbar lnt-exp-list-cmd" }, [
      el("button", {
        className: "lnt-btn lnt-btn-primary btn",
        text: "Новый эксперимент…",
        attrs: { type: "button", id: "lnt-exp-create" },
      }),
      el("button", {
        className: "lnt-btn btn-secondary",
        text: "Обновить",
        attrs: { type: "button", id: "lnt-exp-refresh" },
      }),
    ]),
    listHost,
  ]);

  // --- правая колонка: вкладки ---------------------------------------------
  const detailHost = el("div", {});
  const tabs = createExperimentsTabs(
    [
      { key: "overview", label: "Обзор", paneContent: [timeline.root, members.root] },
      { key: "compare", label: "Сравнение", paneContent: [] },
      { key: "trends", label: "Тренды", paneContent: [] },
      { key: "hypotheses", label: "Гипотезы", paneContent: [] },
    ],
    {
      onFirstAttach: (key, pane) => {
        if (key === "compare") pane.append(comparison.root);
        if (key === "trends") pane.append(trends.root);
        if (key === "hypotheses") pane.append(hypotheses.root);
      },
      onSelect: (key) => {
        if (key === "compare" && detailController.currentDetail !== null) {
          void detailController.runOverlay();
        }
      },
    },
  );
  const panes = tabs.panes;
  const detailController = new ExperimentsDetailController({
    client,
    store,
    timeline,
    members,
    comparison,
    trends,
    hypotheses,
    panes,
    detailHost,
    selectTab: (key) => tabs.select(key),
  });
  const rightPane = el("div", { className: "lnt-exp-right" }, [tabs.tabBar, ...panes.values()]);
  const root = el("div", { className: "lnt-exp-workspace app-body" }, [leftPane, rightPane]);
  container.append(root);
  // Начальное состояние вкладок: «Обзор» видима, остальные hidden (ленивость).
  tabs.select("overview");

  // Bootstrap до любых мутаций: nonce запуска обязателен для POST/PUT.
  void client.ensureReady().catch(() => undefined);

  const createButton = root.querySelector<HTMLButtonElement>("#lnt-exp-create");
  createButton?.addEventListener("click", () => {
    const wizard = new ExperimentWizard({
      client,
      onCreated: (experimentId) => {
        void refreshList().then(() => void loadDetail(experimentId));
        routes.replaceParams({ experiment: experimentId });
      },
    });
    root.prepend(wizard.root);
  });
  root
    .querySelector<HTMLButtonElement>("#lnt-exp-refresh")
    ?.addEventListener("click", () => void refreshList());

  let pendingDetailId: string | null = null;

  async function loadDetail(experimentId: string): Promise<void> {
    pendingDetailId = experimentId;
    await detailController.loadDetail(experimentId);
  }

  function renderListState(): void {
    const state = store.list.get();
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
    if (state.kind === "ready" && state.value.length === 0) {
      listHost.append(el("p", { className: "lnt-helper-text", text: "Экспериментов пока нет." }));
      return;
    }
    if (state.kind !== "ready") return;
    const list = el("ul", { className: "lnt-exp-list", attrs: { "aria-label": "Эксперименты" } });
    for (const item of state.value) {
      const id = String(item.experiment_id ?? "");
      const title = String(item.title ?? id);
      const li = el("li", { className: "lnt-exp-list-item" });
      const link = el("button", {
        className: "lnt-btn lnt-exp-open btn-quiet",
        text: `${title} (${id})`,
        attrs: { type: "button", "data-experiment-id": id },
      });
      link.addEventListener("click", () => {
        routes.replaceParams({ experiment: id });
        void loadDetail(id);
      });
      li.append(link);
      list.append(li);
    }
    listHost.append(list);
  }

  const unsubscribeList = store.list.subscribe(() => renderListState());
  const unsubscribeDetail = store.detail.subscribe((state) => {
    if (state.kind === "error") {
      timeline.setError(`Не удалось загрузить протокол: ${state.error.message}.`);
      clearElement(detailHost);
      const retryId = pendingDetailId ?? routes.get().params.experiment;
      detailHost.append(
        errorWithRetry(`Не удалось загрузить эксперимент: ${state.error.message}.`, () => {
          if (retryId) void loadDetail(retryId);
        }),
      );
    }
  });

  async function refreshList(): Promise<void> {
    await store.list.load("all");
  }
  void refreshList().then(() => {
    const preset = routes.get().params.experiment;
    if (preset) void loadDetail(preset);
  });

  return () => {
    unsubscribeList();
    unsubscribeDetail();
    comparison.abort();
    trends.abort();
    detailController.destroy();
  };
}
