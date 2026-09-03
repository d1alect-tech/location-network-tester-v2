/** Рабочая область «Эксперименты» (todo 43): список экспериментов, детали
 * с таймлайном протокола, участники с QC/исключениями и вкладки
 * «Сравнение» / «Тренды» / «Гипотезы». Монтируется аддитивным блоком
 * AppShell по образцу todo 39; при уходе с маршрута всё обрывается. */

import type { LntApiClient } from "../../api/client";
import type { SessionDetailPayload } from "../../api/types-plots";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import type { RouteStore } from "../../state/routeState";
import { ComparisonView } from "./comparisonView";
import { protocolLabel } from "./experimentModel";
import { ExperimentWizard } from "./experimentWizard";
import { ExperimentsStore } from "./experimentsStore";
import type { ExperimentDetail } from "./experimentsStore";
import { HypothesisView } from "./hypothesisView";
import { currentState } from "./memberQc";
import { MemberTableView } from "./memberTableView";
import type { MemberRow } from "./memberTableView";
import { createProtocolTimeline } from "./protocolTimeline";
import { SpectralOverlay } from "./spectralOverlay";
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
    onInclusionChange: () => syncComparisonRows(),
  });
  const comparison = new ComparisonView({
    client,
    valueSource: async (sessionId, featureKey, signal) => {
      const detail = await client.plots.detail(sessionId, { signal });
      return metricValue(detail, featureKey);
    },
  });
  let overlay: SpectralOverlay | null = null;
  const trends = new TrendView({
    client,
    valueSource: async (sessionId, signal) => {
      const detail = await client.plots.detail(sessionId, { signal });
      return metricValue(
        detail,
        String(currentDetail?.experiment.primary_estimands?.[0]?.feature_key ?? "band_mid_total"),
      );
    },
  });
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
  const tabs = new Map<string, HTMLElement>();
  const panes = new Map<string, HTMLElement>();
  function makeTab(key: string, label: string, paneContent: HTMLElement[]): HTMLButtonElement {
    const button = el("button", {
      className: "lnt-btn lnt-cat-tab snav-item",
      text: label,
      attrs: { type: "button", role: "tab", "data-exp-tab": key },
    });
    const pane = el(
      "div",
      { attrs: { role: "tabpanel", "aria-label": label }, className: "lnt-exp-pane panel" },
      paneContent,
    );
    button.addEventListener("click", () => selectTab(key));
    tabs.set(key, button);
    panes.set(key, pane);
    return button;
  }
  /** Ленивая подгрузка тяжёлых панелей: монтируем содержимое вкладки
   * при первом визите, а не вместе с рабочей областью. */
  const attachedPanes = new Set<string>(["overview"]);
  function attachPane(key: string): void {
    if (attachedPanes.has(key)) return;
    attachedPanes.add(key);
    if (key === "compare") panes.get("compare")?.append(comparison.root);
    if (key === "trends") panes.get("trends")?.append(trends.root);
    if (key === "hypotheses") panes.get("hypotheses")?.append(hypotheses.root);
  }
  function selectTab(key: string): void {
    attachPane(key);
    for (const [tabKey, button] of tabs) {
      const active = tabKey === key;
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.classList.toggle("lnt-cat-tab-active", active);
      button.classList.toggle("is-active", active);
    }
    for (const [paneKey, pane] of panes) pane.hidden = paneKey !== key;
    if (key === "compare" && currentDetail !== null) void runOverlay();
  }
  const tabBar = el(
    "div",
    {
      className: "lnt-cat-tabs tabbar",
      attrs: { role: "tablist", "aria-label": "Разделы эксперимента" },
    },
    [
      makeTab("overview", "Обзор", [timeline.root, members.root]),
      makeTab("compare", "Сравнение", []),
      makeTab("trends", "Тренды", []),
      makeTab("hypotheses", "Гипотезы", []),
    ],
  );
  const rightPane = el("div", { className: "lnt-exp-right" }, [tabBar, ...panes.values()]);
  const root = el("div", { className: "lnt-exp-workspace app-body" }, [leftPane, rightPane]);
  container.append(root);
  // Начальное состояние вкладок: «Обзор» видима, остальные hidden (ленивость).
  selectTab("overview");

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

  let currentDetail: ExperimentDetail | null = null;

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
        el("p", { className: "lnt-helper-text", text: `Ошибка загрузки: ${state.error.message}` }),
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

  async function loadHealth(sessions: string[]): Promise<Map<string, string>> {
    try {
      const page = await client.catalogSessions({ page_size: 200 });
      const map = new Map<string, string>();
      for (const session of page.items) map.set(session.id, String(session.health ?? "ok"));
      return map;
    } catch {
      return new Map(sessions.map((id) => [id, "health_unavailable"]));
    }
  }

  function memberRows(): MemberRow[] {
    return members.getRows();
  }

  function syncComparisonRows(): void {
    if (!currentDetail) return;
    comparison.setContext(currentDetail, memberRows());
    updateTrendRows();
  }

  function updateTrendRows(): void {
    if (!currentDetail) return;
    const rows = memberRows()
      .filter((row) => currentState(row.inclusion) !== "excluded")
      .map((row) => ({
        sessionId: row.sessionId,
        condition: row.conditionId,
        order: row.order,
        value: null,
        timestamp: null,
      }));
    trends.setRows(
      rows,
      String(currentDetail.experiment.primary_estimands?.[0]?.feature_key ?? ""),
    );
  }

  async function runOverlay(): Promise<void> {
    if (!currentDetail) return;
    overlay?.destroy();
    overlay = new SpectralOverlay((sessionId, signal) =>
      client.plots.spectrum(sessionId, undefined, { signal }),
    );
    panes.get("compare")?.querySelector(".lnt-exp-overlay")?.remove();
    panes.get("compare")?.append(overlay.root);
    const groups = new Map<string, string[]>();
    for (const row of memberRows()) {
      if (currentState(row.inclusion) === "excluded") continue;
      const list = groups.get(row.conditionId) ?? [];
      list.push(row.sessionId);
      groups.set(row.conditionId, list);
    }
    const controller = new AbortController();
    await overlay.show(
      [...groups.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([label, ids]) => ({ label, sessionIds: ids })),
      controller.signal,
    );
  }

  async function loadDetail(experimentId: string): Promise<void> {
    detailHost.replaceChildren(
      el("p", { className: "lnt-helper-text", text: "Загрузка эксперимента…" }),
    );
    timeline.setLoading();
    await store.detail.load(experimentId);
    const state = store.detail.get();
    if (state.kind !== "ready" || state.key !== experimentId) return;
    currentDetail = state.value as ExperimentDetail;
    const healths = await loadHealth(memberRows().map((row) => row.sessionId));
    members.setContext({
      experimentId: state.value.experiment.experiment_id,
      healthBySession: healths,
    });
    members.setMembers(state.value.members);
    timeline.setSteps(
      state.value.steps.map((step) => ({
        order: typeof step.order === "number" ? step.order : Number(step.order),
        condition_id: String(step.condition_id ?? "?"),
        instruction: String(step.instruction ?? ""),
      })),
      protocolLabel(String(state.value.experiment.protocol?.kind ?? "aba")),
    );
    hypotheses.linkContext = {
      experimentId: state.value.experiment.experiment_id,
      estimand: String(state.value.experiment.primary_estimands?.[0]?.feature_key ?? ""),
    };
    syncComparisonRows();
    detailHost.replaceChildren();
    announcePolite(`Эксперимент ${state.value.experiment.experiment_id} открыт`);
    selectTab("overview");
  }

  const unsubscribeList = store.list.subscribe(() => renderListState());
  const unsubscribeDetail = store.detail.subscribe((state) => {
    if (state.kind === "error") {
      detailHost.replaceChildren(
        el("p", { className: "lnt-helper-text", text: `Ошибка загрузки: ${state.error.message}` }),
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
    overlay?.destroy();
  };
}

function metricValue(detail: SessionDetailPayload, featureKey: string): number | null {
  const analysis = detail.analysis;
  if (typeof analysis !== "object" || analysis === null) return null;
  const metrics = (analysis as Record<string, unknown>).metrics;
  if (typeof metrics === "object" && metrics !== null) {
    const direct = (metrics as Record<string, unknown>)[featureKey];
    if (typeof direct === "number") return direct;
  }
  const flat = (analysis as Record<string, unknown>)[featureKey];
  return typeof flat === "number" ? flat : null;
}
