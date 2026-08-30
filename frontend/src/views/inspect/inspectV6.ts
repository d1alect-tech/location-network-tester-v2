import "./v6.css";
import { LntApiClient } from "../../api/client";
import type { CatalogQuery, CatalogSession } from "../../api/types";
import type { ChartHandle } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { el } from "../../components/primitives/dom";
import type { RouteStore } from "../../state/routeState";
import { createAnalysisBand } from "./analysisBand";
import { createCatalogColumn } from "./catalogColumn";
import type { GramPairClient } from "./gramPair";
import { wireInspectV6Gram } from "./inspectV6Gram";
import type { AnalysisBandClient } from "./inspectV6Load";
import { loadAnalysisBand } from "./inspectV6Load";
import { createPairbar } from "./pairbarV6";
import { createPairState } from "./pairState";
import type { SpectrumPanelClient } from "./spectrumPanelV6";
import { createSpectrumPanel } from "./spectrumPanelV6";
import { createV6Chrome } from "./v6Chrome";
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
  };

export type InspectV6Opts = {
  readonly client: InspectV6Client;
  readonly routes: RouteStore;
  readonly createView?: (options: UplotViewOptions) => ChartHandle;
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Неизвестная ошибка";
}

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
  const chrome = createV6Chrome({
    onCapture: () => {
      routes.navigate({ route: "capture", params: {} });
    },
  });
  const pairbar = createPairbar({ onSwap: () => pair.swap() });
  const catalogColumn = createCatalogColumn({
    client,
    pair,
    onPick: (id) => pair.pick(id),
  });
  const spectrumPanel = createSpectrumPanel({
    client,
    createView: opts.createView,
  });
  const analysisBand = createAnalysisBand();
  const extras = createV6Extras({
    client,
    createView: opts.createView,
    ...(client instanceof LntApiClient
      ? {}
      : {
          createChrome: () => ({
            root: el("div"),
            destroy() {},
          }),
        }),
  });
  const gram = wireInspectV6Gram({
    client,
    spectrumPanel,
    createView: opts.createView,
  });

  const colCat = el("div", { className: "col-cat" }, [catalogColumn.root]);
  const colMain = el("div", { className: "col-main" }, [
    spectrumPanel.root,
    analysisBand.root,
    extras.root,
  ]);
  const body = el("div", { className: "app-body" }, [colCat, colMain]);
  const root = el("div", { className: "app-v6" }, [
    pairbar.root,
    body,
    chrome.commandbar,
    chrome.errorBand,
  ]);
  container.append(root);

  let disposed = false;

  async function onPairChange(): Promise<void> {
    const { a, b } = pair.get();
    pairbar.setPair(
      a === null ? null : (sessionMap.get(a) ?? null),
      b === null ? null : (sessionMap.get(b) ?? null),
    );
    routes.replaceParams({ a: a ?? "", b: b ?? "" });
    if (a === null || a === "") return;
    chrome.hideError();
    try {
      await Promise.all([
        spectrumPanel.load(a, b),
        loadAnalysisBand(client, a, b).then((data) => analysisBand.update(data)),
        gram.refresh(a, b),
      ]);
      extras.setSession(a);
    } catch (error) {
      // no-excuse-ok: catch — inspect v6 pair-refresh boundary
      chrome.showError(errorMessage(error));
    }
  }

  const unsubscribe = pair.subscribe(() => {
    void onPairChange();
  });

  async function boot(): Promise<void> {
    try {
      const page = await client.catalogSessions({ page_size: 200 });
      if (disposed) return;
      for (const item of page.items) sessionMap.set(item.id, item);
      await catalogColumn.reload();
      if (disposed) return;
      const params = routes.get().params;
      const fromRouteA = paramId(params, "a");
      const fromRouteB = paramId(params, "b");
      if (fromRouteA !== undefined) pair.pick(fromRouteA);
      if (fromRouteB !== undefined) pair.pick(fromRouteB);
      if (pair.get().a !== null) return;
      const first = page.items[0];
      const second = page.items[1];
      if (first !== undefined) pair.pick(first.id);
      if (second !== undefined) pair.pick(second.id);
    } catch (error) {
      // no-excuse-ok: catch — inspect v6 boot boundary
      chrome.showError(errorMessage(error));
    }
  }

  await boot();

  return () => {
    disposed = true;
    unsubscribe();
    gram.dispose();
    spectrumPanel.destroy();
    extras.destroy();
    root.remove();
  };
}
