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
import "./w1SumReason.css";

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
  /** Причина отсутствия анализа v2 в свёрнутой шапке (задача 7, G1/Q3 = A).
   * Опционален: стаб inspectV6 и фейки тестов его не несут. */
  onAbsenceReason?(listener: (reason: string | null) => void): void;
  destroy(): void;
};

export type V6ExtrasChromeDeps = {
  readonly client: unknown;
  readonly detail?: DetailLoader;
  readonly sessionTypeOf?: (session: string) => string;
  readonly onJobBusy?: (busy: boolean) => void;
  /** Успешная задача анализа: хост перезабирает данные пары (задача 8). */
  readonly onJobReload?: () => void;
};

export type V6ExtrasOpts = {
  readonly client: V6ExtrasClient;
  readonly createView?: (options: UplotViewOptions) => ChartHandle;
  /** Общий загрузчик detail пары: секция не тянет метрики своим запросом. */
  readonly detail?: DetailLoader;
  /** Тип сессии из каталога инспекции (ITIC только у line_quality, CM/DM у cm_dm). */
  readonly sessionTypeOf?: (session: string) => string;
  readonly createChrome?: (deps: V6ExtrasChromeDeps) => V6ExtrasChrome;
  readonly onJobBusy?: (busy: boolean) => void;
  /** Успешная задача анализа: данные пары перезабираются тем же конвейером
   * pair-load (задача 8, D1e) — без ручного перевыбора. */
  readonly onJobReload?: () => void;
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
      onJobBusy: deps.onJobBusy,
      onJobReload: deps.onJobReload,
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
    onJobBusy: opts.onJobBusy,
    onJobReload: opts.onJobReload,
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
  // G1/Q3 = A: причина отсутствия v2 — сиблинг счётчика в самой <summary>,
  // виден без раскрытия (закрытый details прячет всё, кроме summary).
  const summaryReason = el("span", {
    className: "av2-sum-reason",
    attrs: { "data-role": "w1-absence-reason" },
  });
  summaryReason.hidden = true;
  const w1Details = el("details", { className: "av2-disclosure", attrs: { "data-extra": "w1" } }, [
    el("summary", {}, [
      el("span", { className: "av2-sum-label", text: W1_LABEL }),
      summaryValue,
      summaryReason,
    ]),
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
  chrome.onAbsenceReason?.((reason) => {
    summaryReason.textContent = reason ?? "";
    summaryReason.hidden = reason === null;
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
