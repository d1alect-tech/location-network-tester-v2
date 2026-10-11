/** B3-секция «Спектр + спектрограмма» (G5, todo 9): одна секция, одна шапка,
 * собранная группами с подписями — Вид / Спектр / Спектрограмма. Кластер грама
 * не исчезает в режиме спектра: его состояние читается всегда (приглушённо).
 * Заём слотов снят: органы грама создаёт грам-модуль, хозяин DOM — секция. */

import type { SpectrumPayload } from "../../api/types-plots";
import type { ChartHandle } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { el } from "../../components/primitives/dom";
import type { GramPairClient } from "./gramPair";
import { createGramSection } from "./inspectV6Gram";
import type { InspectSection } from "./section";
import type {
  SpectrumHeaderParts,
  SpectrumPanelClient,
  SpectrumPanelHandle,
} from "./spectrumPanelV6";
import { createSpectrumPanel } from "./spectrumPanelV6";

export type SpectrumGramClient = SpectrumPanelClient & GramPairClient;

export type SpectrumGramSectionHandle = InspectSection & {
  setPair(a: string | null, b: string | null): Promise<void>;
  payloads(): { readonly a: SpectrumPayload | null; readonly b: SpectrumPayload | null };
};

export type SpectrumGramSectionOpts = {
  readonly client: SpectrumGramClient;
  readonly createView?: (options: UplotViewOptions) => ChartHandle;
  /** B2: общий загрузчик detail пары инспекции. */
  readonly detail?: (
    name: string,
    o?: { readonly signal?: AbortSignal },
  ) => Promise<{ readonly analysis?: unknown }>;
};

function cluster(key: string, caption: string, body: HTMLElement): HTMLElement {
  return el("div", { className: "signal-cluster", attrs: { "data-signal-cluster": key } }, [
    el("span", { className: "signal-cluster-cap", text: caption }),
    body,
  ]);
}

export function createSpectrumGramSection(
  opts: SpectrumGramSectionOpts,
): SpectrumGramSectionHandle {
  const gramToolbar = el("div", {
    className: "signal-cluster-bd",
    attrs: { "data-gram-bar": "" },
  });
  const gramCanvasHost = el("div", { className: "gram", attrs: { "data-gram-host": "" } });
  const viewBody = el("span", { className: "signal-cluster-bd" });
  const spectrumBody = el("span", { className: "signal-cluster-bd" });
  const viewCluster = cluster("view", "Вид", viewBody);
  const spectrumCluster = cluster("spectrum", "Спектр", spectrumBody);
  const gramCluster = cluster("gram", "Спектрограмма", gramToolbar);

  function composeHeader(parts: SpectrumHeaderParts): HTMLElement {
    viewBody.append(parts.viewToggle);
    spectrumBody.append(parts.planeToggle, parts.rbw, parts.selectors);
    return el("div", { className: "panel-hd signal-hd" }, [
      viewCluster,
      spectrumCluster,
      gramCluster,
    ]);
  }

  // B2: detail базы приходит из общего загрузчика пары — подменяем его в
  // клиенте панелей, чтобы спектр, лента и analysis-v2 не тянули метрики врозь.
  const panelClient: SpectrumPanelClient =
    opts.detail === undefined
      ? opts.client
      : { plots: { ...opts.client.plots, detail: opts.detail } };

  const panel: SpectrumPanelHandle = createSpectrumPanel({
    client: panelClient,
    createView: opts.createView,
    slots: { gramBar: gramToolbar, gramHost: gramCanvasHost },
    composeHeader,
  });
  panel.root.setAttribute("data-section", "spectrum-gram");
  const body = panel.root.querySelector<HTMLElement>(".panel-bd") ?? null;
  if (body !== null) body.classList.add("signal-bd");

  const gram = createGramSection({
    client: opts.client,
    toolbarHost: gramToolbar,
    canvasHost: gramCanvasHost,
  });

  // Частое действие (тумблер вида) — без анимации: только атрибут активной группы.
  panel.onViewChange((view) => {
    gramCluster.toggleAttribute("data-active", view === "gram");
    spectrumCluster.toggleAttribute("data-active", view === "spectrum");
  });
  spectrumCluster.toggleAttribute("data-active", true);

  function replayEnter(): void {
    if (body === null) return;
    body.classList.remove("is-enter");
    void body.offsetWidth;
    body.classList.add("is-enter");
  }

  return {
    root: panel.root,
    async setPair(a, b) {
      if (a === null || a === "") return;
      await Promise.all([panel.load(a, b), gram.refresh(a, b)]);
      replayEnter();
    },
    payloads: () => panel.payloads(),
    destroy() {
      gram.dispose();
      panel.destroy();
    },
  };
}
