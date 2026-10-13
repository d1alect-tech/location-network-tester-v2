import "./v6.css";
import { LntApiClient } from "../../api/client";
import { createDeviceApi } from "../../api/client-device";
import { isAbortError } from "../../api/errors";
import type { CatalogQuery, CatalogSession } from "../../api/types";
import { createChannelbar } from "../../components/channelbar/channelbar";
import type { ChartHandle } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { el } from "../../components/primitives/dom";
import type { RouteStore } from "../../state/routeState";
import { EMPTY_METERS, createAnalysisBand } from "./analysisBand";
import { pickBootPair } from "./bootPick";
import { createCatalogColumn } from "./catalogColumn";
import type { LegacyRow } from "./catalogJoinedSource";
import { loadJoinedCatalog } from "./catalogJoinedSource";
import { cyclesFromMeters, paintChannelbarFromPayload } from "./channelbarPaint";
import { summarizeDelta } from "./deltaSummary";
import type { GramPairClient } from "./gramPair";
import { ticketToCaptureParams } from "./inspectTicket";
import type { AnalysisBandClient } from "./inspectV6Load";
import { loadAnalysisBand } from "./inspectV6Load";
import { createPairDetail } from "./pairDetail";
import { type PairLoadFailure, pairLoadOutcomeFrom, reasonFromError } from "./pairLoadOutcome";
import { createPairState } from "./pairState";
import { createPairbar } from "./pairbarV6";
import { buildSessionAlias, indexSessionMeta } from "./sessionAlias";
import { createSpectrumGramSection } from "./spectrumGramSection";
import type { SpectrumPanelClient } from "./spectrumPanelV6";
import { createV6Chrome } from "./v6Chrome";
import { wireInspectDeviceStatus } from "./v6DeviceStatus";
import type { V6ExtrasClient } from "./v6Extras";
import { createV6Extras } from "./v6Extras";

export type InspectV6Client = SpectrumPanelClient &
  AnalysisBandClient &
  GramPairClient &
  V6ExtrasClient & {
    catalogSessions(
      query?: CatalogQuery,
      options?: unknown,
    ): Promise<{ readonly items: readonly CatalogSession[] }>;
    legacySessions(options?: unknown): Promise<{ readonly sessions: readonly LegacyRow[] }>;
  };

export type InspectV6Opts = {
  readonly client: InspectV6Client;
  readonly routes: RouteStore;
  readonly createView?: (options: UplotViewOptions) => ChartHandle;
};

function paramId(params: Record<string, string>, key: string): string | undefined {
  const value = params[key];
  return value !== undefined && value !== "" ? value : undefined;
}

export async function mountInspectV6(
  container: HTMLElement,
  opts: InspectV6Opts,
): Promise<() => void> {
  const { client, routes } = opts;
  const sessionMap = new Map<string, CatalogSession>();
  const pair = createPairState();
  // B2: detail базы — один fetch на пару, общий для спектра, ленты и analysis-v2.
  // Взгляд AnalysisBandClient даёт строгий тип SessionDetailPayload (пересечение
  // клиентов иначе разрешает detail в широкий {analysis?}).
  const bandClient: AnalysisBandClient = client;
  const detailStore = createPairDetail((name, options) => bandClient.plots.detail(name, options));
  const sessionTypeOf = (id: string): string => sessionMap.get(id)?.session_type ?? "";
  const chrome = createV6Chrome({
    onCapture: (ticket) => {
      routes.navigate({ route: "capture", params: ticketToCaptureParams(ticket) });
    },
  });
  const stopDeviceStatus = wireInspectDeviceStatus(
    chrome,
    client instanceof LntApiClient ? createDeviceApi(client) : undefined,
  );
  const pairbar = createPairbar({
    onSwap: () => pair.swap(),
    onArm: (slot) => pair.arm(slot),
  });
  const catalogColumn = createCatalogColumn({
    client,
    pair,
    onPick: (id) => pair.pick(id),
  });
  const signalSection = createSpectrumGramSection({
    client,
    createView: opts.createView,
    detail: detailStore.load,
  });
  const analysisBand = createAnalysisBand();
  analysisBand.update({ meters: [...EMPTY_METERS], peaks: [] });
  analysisBand.paintDelta(null, null);
  analysisBand.paintPeaksDelta(null, null);
  // Задача 10 (D3): Δ-семейство (пики таблицы, Δ-полоса, Δср пары) считается
  // из пейлоадов ОТОБРАЖАЕМОЙ плоскости — тот же провод, что кормит соседний
  // график (onPayloads панели), а не отдельный scope-фетч ленты. Смена
  // плоскости перезабирает Δ тем же каналом; payload отсутствует — честное
  // «—» + причина из словаря задачи 3, без scope-plane fallback.
  signalSection.onPayloads((a, b, reason) => {
    analysisBand.paintPeaksDelta(a, b, reason);
    analysisBand.paintDelta(a, b);
    pairbar.setDelta(b === null ? null : summarizeDelta(a?.psd_v2_per_hz, b.psd_v2_per_hz));
  });
  const extras = createV6Extras({
    client,
    createView: opts.createView,
    detail: detailStore.load,
    sessionTypeOf,
    onJobBusy: (busy) => pairbar.setBusy(busy),
    // Задача 8 (D1e): успешная задача анализа перезабирает данные пары тем
    // же конвейером pair-load, что и смена пары (onPairChange — эффект
    // setPair; literal setPair на неизменной паре — no-op, см. pairState).
    onJobReload: () => {
      void onPairChange();
    },
    ...(client instanceof LntApiClient
      ? {}
      : {
          createChrome: () => ({
            bar: el("div", { className: "panel-hd av2-hd" }),
            root: el("div"),
            setSession() {},
            onSummary() {},
            destroy() {},
          }),
        }),
  });

  // U2: channel-bar первой строкой главной колонки.
  const channelbar = createChannelbar();
  const colCat = el("div", { className: "col-cat" }, [catalogColumn.root]);
  const colMain = el("div", { className: "col-main" }, [
    channelbar.root,
    signalSection.root,
    analysisBand.root,
    extras.root,
  ]);
  const body = el("div", { className: "app-body" }, [colCat, colMain]);
  const root = el("div", { className: "app-v6", attrs: { "data-density": "dense" } }, [
    pairbar.root,
    body,
    chrome.commandbar,
    chrome.errorBand,
  ]);
  container.append(root);

  let disposed = false;
  let pairGeneration = 0;
  let pairController = new AbortController();

  async function onPairChange(): Promise<void> {
    const gen = ++pairGeneration;
    pairController.abort();
    pairController = new AbortController();
    detailStore.reset();
    const { a, b } = pair.get();
    pairbar.setPair(
      a === null ? null : (sessionMap.get(a) ?? null),
      b === null ? null : (sessionMap.get(b) ?? null),
    );
    routes.replaceParams({ a: a ?? "", b: b ?? "" });
    if (a === null || a === "") return;
    chrome.hideError();
    pairbar.setDelta(null);
    paintChannelbarFromPayload(channelbar, null, null);
    analysisBand.update({ meters: [...EMPTY_METERS], peaks: [] });
    analysisBand.paintDelta(null, null);
    analysisBand.paintPeaksDelta(null, null);
    extras.setPair(null, null);
    try {
      const [, bandData] = await Promise.all([
        signalSection.setPair(a, b),
        loadAnalysisBand(client, a, pairController.signal, detailStore.load),
      ]);
      if (disposed || gen !== pairGeneration) return;
      analysisBand.update(bandData);
      const payloads = signalSection.payloads();
      paintChannelbarFromPayload(channelbar, payloads.a, cyclesFromMeters(bandData.meters));
      extras.setPair(a, b);
    } catch (error) {
      if (disposed || gen !== pairGeneration || isAbortError(error)) return;
      // no-excuse-ok: catch — inspect v6 pair-refresh boundary
      // D2: исход пары из единого словаря причин; reason уходит через
      // существующий сеттер ленты (canned-префикс + серверный detail 409/422).
      const outcome: PairLoadFailure = pairLoadOutcomeFrom(error);
      chrome.showError(outcome.reason);
    }
  }

  const unsubscribe = pair.subscribe(() => {
    pairbar.setArmed(pair.armed());
    void onPairChange();
  });

  async function boot(): Promise<void> {
    try {
      // Один reload кормит бут и рейл (B unified): include_paths даёт имена
      // каталогов для обоих ключей D1, legacySessions — analyzed для JOIN.
      const page = await loadJoinedCatalog(client);
      if (disposed) return;
      const alias = buildSessionAlias(page.sessions);
      // Мета слота пары ищется по обоим ключам D1: dir-name-строка с
      // duplicate_id не канонизируется (F-8), поэтому её ключ остаётся именем.
      for (const item of page.sessions) indexSessionMeta(sessionMap, item);
      await catalogColumn.reload();
      if (disposed) return;
      const params = routes.get().params;
      const fromRouteA = paramId(params, "a");
      const fromRouteB = paramId(params, "b");
      if (fromRouteA !== undefined || fromRouteB !== undefined) {
        // Deep-link/pick по обоим ключам D1: алиас канонизирует dir-name в id,
        // duplicate_id (F-8) остаётся именем каталога — setPair атомарно.
        pair.setPair({
          a: fromRouteA === undefined ? null : (alias.get(fromRouteA) ?? fromRouteA),
          b: fromRouteB === undefined ? null : (alias.get(fromRouteB) ?? fromRouteB),
        });
        return;
      }
      // Авто-выбор: первые ДВА проанализированных в именованном keyset-порядке
      // (JOIN, не health). Ноль кандидатов → null-пара, рейл покажет причины.
      pair.setPair(
        pickBootPair({
          sessions: page.sessions,
          analyzedByDir: page.analyzedByDir,
          invalidByDir: page.invalidByDir,
        }),
      );
    } catch (error) {
      // no-excuse-ok: catch — inspect v6 boot boundary
      chrome.showError(reasonFromError(error));
    }
  }

  await boot();

  return () => {
    disposed = true;
    pairGeneration += 1;
    pairController.abort();
    detailStore.dispose();
    stopDeviceStatus();
    unsubscribe();
    signalSection.destroy();
    extras.destroy();
    root.remove();
  };
}
