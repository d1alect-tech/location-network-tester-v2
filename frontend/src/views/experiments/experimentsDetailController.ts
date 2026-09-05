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
  private readonly deps: ExperimentsDetailDeps;

  constructor(deps: ExperimentsDetailDeps) {
    this.deps = deps;
  }

  /** Карта health по session_id. Ошибка каталога поднимается наверх. */
  async loadHealth(): Promise<Map<string, string>> {
    const page = await this.deps.client.catalogSessions({ page_size: 200 });
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
    this.overlay?.destroy();
    const { client, panes, members } = this.deps;
    this.overlay = new SpectralOverlay((sessionId, signal) =>
      client.plots.spectrum(sessionId, undefined, { signal }),
    );
    panes.get("compare")?.querySelector(".lnt-exp-overlay")?.remove();
    panes.get("compare")?.append(this.overlay.root);
    const controller = new AbortController();
    await this.overlay.show(overlayGroups(members.getRows()), controller.signal);
  }

  /** Здоровье участников; при отказе каталога — outage-баннер с повтором. */
  private async applyHealth(
    detail: ExperimentDetail,
    experimentId: string,
  ): Promise<string | null> {
    const { members } = this.deps;
    try {
      const healthBySession = await this.loadHealth();
      members.setContext({
        experimentId: detail.experiment.experiment_id,
        healthBySession,
      });
      members.setMembers(detail.members);
      members.clearHealthOutage();
      return null;
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      const message = `Не удалось загрузить состояние здоровья сессий: ${reason}. Таблица участников показана без QC-вердиктов; повторите загрузку.`;
      members.setMembers([]);
      members.showHealthOutage(message, () => void this.loadDetail(experimentId));
      this.healthFailed = true;
      return message;
    }
  }

  async loadDetail(experimentId: string): Promise<void> {
    const { detailHost, timeline, store, hypotheses, selectTab } = this.deps;
    detailHost.replaceChildren(
      el("p", { className: "lnt-helper-text", text: "Загрузка эксперимента…" }),
    );
    timeline.setLoading();
    await store.detail.load(experimentId);
    const state = store.detail.get();
    if (state.kind !== "ready" || state.key !== experimentId) return;
    const detail = state.value as ExperimentDetail;
    this.currentDetail = detail;
    const wasFailed = this.healthFailed;
    const healthError = await this.applyHealth(detail, experimentId);
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

  destroy(): void {
    this.overlay?.destroy();
    this.overlay = null;
  }
}
