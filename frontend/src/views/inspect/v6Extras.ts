/** Шелл секции analysis-v2 (G7 «Disclosure-панели»): одна рамка панели,
 * шапка с вердиктом и сессией базы, два раскрытия — осциллограмма CH1 и
 * анализ сессии. Контракт B3: setPair(a, b) + destroy(); смену пары задаёт
 * рейка каталога (B2), своего выбора сессии у секции нет. */

import { LntApiClient } from "../../api/client";
import type { WaveformPayload } from "../../api/types-plots";
import { readChartTheme } from "../../components/charts/theme";
import type { ChartHandle } from "../../components/charts/types";
import { createUplotView } from "../../components/charts/uplotView";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { waveformToRequest } from "../../components/charts/viewModels";
import { el } from "../../components/primitives/dom";
import type { DetailLoader } from "./pairDetail";
import type { InspectSection } from "./section";
import { createW1Chrome } from "./w1Chrome";
import { NO_SESSION_SUMMARY } from "./w1Chrome";

export type V6ExtrasClient = {
  readonly plots: {
    waveform: (
      name: string,
      ch: "ch1",
      maxPoints?: number,
      o?: { readonly signal?: AbortSignal },
    ) => Promise<WaveformPayload>;
  };
};

export type V6ExtrasChrome = {
  readonly bar: HTMLElement;
  readonly root: HTMLElement;
  setSession(session: string | null): void;
  onSummary(listener: (text: string) => void): void;
  destroy(): void;
};

export type V6ExtrasChromeDeps = {
  readonly client: unknown;
  readonly detail?: DetailLoader;
  readonly sessionTypeOf?: (session: string) => string;
};

export type V6ExtrasOpts = {
  readonly client: V6ExtrasClient;
  readonly createView?: (options: UplotViewOptions) => ChartHandle;
  /** Общий загрузчик detail пары: секция не тянет метрики своим запросом. */
  readonly detail?: DetailLoader;
  /** Тип сессии из каталога инспекции (ITIC только у line_quality, CM/DM у cm_dm). */
  readonly sessionTypeOf?: (session: string) => string;
  readonly createChrome?: (deps: V6ExtrasChromeDeps) => V6ExtrasChrome;
};

export type V6ExtrasHandle = InspectSection;

const WAVE_SYNC = "v6-extras-ch1";
const WAVE_LABEL = "Осциллограмма CH1";
const W1_LABEL = "Анализ сессии (метрики и панели)";

function defaultCreateChrome(deps: V6ExtrasChromeDeps): V6ExtrasChrome {
  if (deps.client instanceof LntApiClient) {
    return createW1Chrome({
      client: deps.client,
      detail: deps.detail,
      sessionTypeOf: deps.sessionTypeOf,
    });
  }
  throw new TypeError("v6 extras default chrome needs LntApiClient");
}

export function createV6Extras(opts: V6ExtrasOpts): V6ExtrasHandle {
  const createView = opts.createView ?? createUplotView;
  const chrome = (opts.createChrome ?? defaultCreateChrome)({
    client: opts.client,
    detail: opts.detail,
    sessionTypeOf: opts.sessionTypeOf,
  });
  const theme = readChartTheme();
  const waveHost = el("div", { className: "v6-extras-wave" });
  const waveBody = el("div", { className: "av2-body" }, [waveHost]);
  const waveDetails = el(
    "details",
    { className: "av2-disclosure", attrs: { "data-extra": "waveform" } },
    [el("summary", { text: WAVE_LABEL }), waveBody],
  );
  const summaryValue = el("span", {
    className: "av2-sum-value",
    text: NO_SESSION_SUMMARY,
    attrs: { "data-role": "w1-sum-value" },
  });
  const w1Details = el("details", { className: "av2-disclosure", attrs: { "data-extra": "w1" } }, [
    el("summary", {}, [el("span", { className: "av2-sum-label", text: W1_LABEL }), summaryValue]),
    chrome.root,
  ]);
  const root = el(
    "section",
    {
      className: "panel analysis-v2 v6-extras lnt-w1-chrome",
      attrs: { "data-section": "analysis-v2", "aria-label": "Анализ v2" },
    },
    [chrome.bar, waveDetails, w1Details],
  );
  chrome.onSummary((text) => {
    summaryValue.textContent = text;
  });

  let session: string | null = null;
  let view: ChartHandle | null = null;
  let loadGen = 0;

  function ensureView(): ChartHandle {
    if (view !== null) return view;
    view = createView({ container: waveHost, syncKey: WAVE_SYNC });
    return view;
  }

  async function loadWaveform(): Promise<void> {
    if (!waveDetails.open) return;
    const name = session;
    if (name === null) return;
    loadGen += 1;
    const gen = loadGen;
    const payload = await opts.client.plots.waveform(name, "ch1");
    if (gen !== loadGen) return;
    ensureView().render(waveformToRequest(payload, { label: "CH1", color: theme.accentA }));
  }

  function onToggle(): void {
    void loadWaveform();
  }

  /** Вход содержимого на смене пары: 200ms ease-out, только transform/opacity.
   * Раскрытие/сворачивание панелей — частое действие, поэтому без анимации. */
  function replayEnter(): void {
    for (const node of [waveBody, chrome.root]) {
      node.classList.remove("is-enter");
      void node.offsetWidth;
      node.classList.add("is-enter");
    }
  }

  waveDetails.addEventListener("toggle", onToggle);

  return {
    root,
    setPair(a, _b) {
      const next = a === null || a === "" ? null : a;
      session = next;
      chrome.setSession(next);
      if (next === null) return;
      replayEnter();
      void loadWaveform();
    },
    destroy() {
      loadGen += 1;
      waveDetails.removeEventListener("toggle", onToggle);
      view?.destroy();
      view = null;
      chrome.destroy();
      root.remove();
    },
  };
}
