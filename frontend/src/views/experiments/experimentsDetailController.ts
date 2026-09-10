/** Контроллер деталей эксперимента (C3-лист, выделен из experimentsWorkspace):
 * здоровье сессий, строки участников, спектральный оверлей и загрузка деталей.
 * Тихий catch здоровья убран: недоступный каталог даёт outage-баннер с
 * повтором, а не синтетический вердикт health_unavailable.
 * Зависит только от видов вкладок и стора, никогда от AppShell. */

import type { LntApiClient } from "../../api/client";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import type { ComparisonView } from "./comparisonView";
import { protocolLabel } from "./experimentModel";
import type { ExperimentDetail, ExperimentsStore } from "./experimentsStore";
import { overlayGroups, syncComparisonAndTrends } from "./experimentsSync";
import type { HypothesisView } from "./hypothesisView";
import type { MemberTableView } from "./memberTableView";
import type { ProtocolTimelineHandle } from "./protocolTimeline";
import { SpectralOverlay } from "./spectralOverlay";
import type { TrendView } from "./trendView";

export interface ExperimentsDetailDeps {
  client: LntApiClient;
  store: ExperimentsStore;
  timeline: ProtocolTimelineHandle;
  members: MemberTableView;
  comparison: ComparisonView;
  trends: TrendView;
  hypotheses: HypothesisView;
  panes: Map<string, HTMLElement>;
  detailHost: HTMLElement;
  selectTab: (key: string) => void;
}

export class ExperimentsDetailController {
  currentDetail: ExperimentDetail | null = null;
  private healthFailed = false;
  private overlay: SpectralOverlay | null = null;
  private overlayController = new AbortController();
  private loadController = new AbortController();
  private generation = 0;
  private readonly deps: ExperimentsDetailDeps;

  constructor(deps: ExperimentsDetailDeps) {
    this.deps = deps;
  }

  /** Карта health по session_id. Ошибка каталога поднимается наверх. */
  async loadHealth(signal?: AbortSignal): Promise<Map<string, string>> {
    const page = await this.deps.client.catalogSessions({ page_size: 200 }, { signal });
    const map = new Map<string, string>();
    for (const session of page.items) map.set(session.id, String(session.health ?? "ok"));
    return map;
  }

  syncComparisonRows(): void {
    const { comparison, trends, members } = this.deps;
    syncComparisonAndTrends(comparison, trends, this.currentDetail, members.getRows());
  }

  async runOverlay(): Promise<void> {
    if (!this.currentDetail) return;
    this.overlayController.abort();
    this.overlayController = new AbortController();
    this.overlay?.destroy();
    const { client, panes, members } = this.deps;
    this.overlay = new SpectralOverlay((sessionId, signal) =>
      client.plots.spectrum(sessionId, undefined, { signal }),
    );
    panes.get("compare")?.querySelector(".lnt-exp-overlay")?.remove();
    panes.get("compare")?.append(this.overlay.root);
    await this.overlay.show(overlayGroups(members.getRows()), this.overlayController.signal);
  }

  /** Здоровье участников; при отказе каталога — outage-баннер с повтором. */
  private async applyHealth(
    detail: ExperimentDetail,
    experimentId: string,
    generation: number,
    signal: AbortSignal,
  ): Promise<string | null | undefined> {
    const { members } = this.deps;
    try {
      const healthBySession = await this.loadHealth(signal);
      if (!this.isCurrent(generation, signal)) return undefined;
      members.setContext({
        experimentId: detail.experiment.experiment_id,
        healthBySession,
      });
      members.setMembers(detail.members);
      members.clearHealthOutage();
      return null;
    } catch (error) {
      if (!this.isCurrent(generation, signal)) return undefined;
      const reason = error instanceof Error ? error.message : String(error);
      const message = `Не удалось загрузить состояние здоровья сессий: ${reason}. Таблица участников показана без QC-вердиктов; повторите загрузку.`;
      members.setMembers([]);
      members.showHealthOutage(message, () => void this.loadDetail(experimentId));
      this.healthFailed = true;
      return message;
    }
  }

  async loadDetail(experimentId: string): Promise<void> {
    const generation = ++this.generation;
    this.loadController.abort();
    this.loadController = new AbortController();
    const signal = this.loadController.signal;
    this.overlayController.abort();
    this.overlay?.destroy();
    this.overlay = null;
    const { detailHost, timeline, store, hypotheses, members, comparison, selectTab } = this.deps;
    this.currentDetail = null;
    comparison.abort();
    hypotheses.linkContext = null;
    members.clearHealthOutage();
    members.setMembers([]);
    detailHost.replaceChildren(
      el("p", { className: "lnt-helper-text", text: "Загрузка эксперимента…" }),
    );
    timeline.setLoading();
    await store.detail.load(experimentId);
    if (!this.isCurrent(generation, signal)) return;
    const state = store.detail.get();
    if (state.kind !== "ready" || state.key !== experimentId) return;
    const detail = state.value as ExperimentDetail;
    this.currentDetail = detail;
    const wasFailed = this.healthFailed;
    const healthError = await this.applyHealth(detail, experimentId, generation, signal);
    if (healthError === undefined || !this.isCurrent(generation, signal)) return;
    const healthRecovered = healthError === null && wasFailed;
    if (healthRecovered) this.healthFailed = false;
    timeline.setSteps(
      detail.steps.map((step) => ({
        order: typeof step.order === "number" ? step.order : Number(step.order),
        condition_id: String(step.condition_id ?? "?"),
        instruction: String(step.instruction ?? ""),
      })),
      protocolLabel(String(detail.experiment.protocol?.kind ?? "aba")),
    );
    hypotheses.linkContext = {
      experimentId: detail.experiment.experiment_id,
      estimand: String(detail.experiment.primary_estimands?.[0]?.feature_key ?? ""),
    };
    this.syncComparisonRows();
    detailHost.replaceChildren();
    if (healthError !== null) announcePolite(healthError);
    else if (healthRecovered) announcePolite("Состояние здоровья сессий обновлено");
    else announcePolite(`Эксперимент ${detail.experiment.experiment_id} открыт`);
    selectTab("overview");
  }

  private isCurrent(generation: number, signal: AbortSignal): boolean {
    return generation === this.generation && !signal.aborted;
  }

  destroy(): void {
    this.generation += 1;
    this.loadController.abort();
    this.overlayController.abort();
    this.overlay?.destroy();
    this.overlay = null;
    this.currentDetail = null;
    this.deps.hypotheses.linkContext = null;
  }
}
