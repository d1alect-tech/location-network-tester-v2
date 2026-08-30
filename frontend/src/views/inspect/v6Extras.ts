/** Collapsible production extras under the v6 analysis band: lazy CH1 waveform + W1 chrome. */

import { LntApiClient } from "../../api/client";
import type { WaveformPayload } from "../../api/types-plots";
import { readChartTheme } from "../../components/charts/theme";
import type { ChartHandle } from "../../components/charts/types";
import { createUplotView } from "../../components/charts/uplotView";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { waveformToRequest } from "../../components/charts/viewModels";
import { el } from "../../components/primitives/dom";
import { createW1Chrome } from "./w1Chrome";

export type V6ExtrasClient = {
  readonly plots: {
    waveform: (
      name: string,
      ch: "ch1",
      q?: unknown,
      o?: { readonly signal?: AbortSignal },
    ) => Promise<WaveformPayload>;
  };
} & Record<string, unknown>;

export type V6ExtrasChrome = {
  readonly root: HTMLElement;
  destroy(): void;
};

export type V6ExtrasOpts = {
  readonly client: V6ExtrasClient;
  readonly createView?: (options: UplotViewOptions) => ChartHandle;
  readonly createChrome?: (options: { readonly client: unknown }) => V6ExtrasChrome;
};

export type V6ExtrasHandle = {
  readonly root: HTMLElement;
  setSession(session: string | null): void;
  destroy(): void;
};

const WAVE_SYNC = "v6-extras-ch1";

function defaultCreateChrome(options: { readonly client: unknown }): V6ExtrasChrome {
  if (options.client instanceof LntApiClient) {
    return createW1Chrome({ client: options.client });
  }
  throw new TypeError("v6 extras default chrome needs LntApiClient");
}

export function createV6Extras(opts: V6ExtrasOpts): V6ExtrasHandle {
  const createView = opts.createView ?? createUplotView;
  const chrome = (opts.createChrome ?? defaultCreateChrome)({ client: opts.client });
  const theme = readChartTheme();
  const waveHost = el("div", { className: "v6-extras-wave" });
  const waveDetails = el("details", { attrs: { "data-extra": "waveform" } }, [
    el("summary", { text: "Осциллограмма CH1" }),
    waveHost,
  ]);
  const w1Details = el("details", { attrs: { "data-extra": "w1" } }, [
    el("summary", { text: "Анализ сессии (метрики и панели)" }),
    chrome.root,
  ]);
  const root = el("div", { className: "v6-extras" }, [waveDetails, w1Details]);

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
    const gen = (loadGen += 1);
    const payload = await opts.client.plots.waveform(name, "ch1");
    if (gen !== loadGen) return;
    ensureView().render(waveformToRequest(payload, { label: "CH1", color: theme.accentA }));
  }

  function onToggle(): void {
    void loadWaveform();
  }

  waveDetails.addEventListener("toggle", onToggle);

  return {
    root,
    setSession(next) {
      session = next;
      void loadWaveform();
    },
    destroy() {
      loadGen += 1;
      waveDetails.removeEventListener("toggle", onToggle);
      view?.destroy();
      view = null;
      chrome.destroy();
    },
  };
}
