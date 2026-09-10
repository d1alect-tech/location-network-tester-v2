import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import type { CatalogSession } from "../../api/types";
import type { SessionDetailPayload, SpectrumPayload, WaveformPayload } from "../../api/types-plots";
import type { ChartHandle } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { RouteStore } from "../../state/routeState";
import { mountInspectV6 } from "./inspectV6";

function session(id: string, label: string): CatalogSession {
  return {
    id,
    health: "ok",
    created_utc: "2026-08-28T10:00:00Z",
    source: "hardware",
    session_type: "capture",
    profile: "lab",
    label,
  };
}

const SESSION_A = session("sess-a", "Alpha");
const SESSION_B = session("sess-b", "Beta");

const SPECTRUM: SpectrumPayload = {
  frequency_hz: [100, 1000],
  psd_v2_per_hz: [1e-4, 1e-6],
  point_count: 2,
};

const DETAIL: SessionDetailPayload = {
  name: "sess-a",
  manifest: {},
  analysis: {},
  spectrum_available: true,
  waveform_available: false,
  ch2_available: false,
};

const WAVE: WaveformPayload = {
  channel: "ch1",
  time_s: [0, 1],
  voltage_v: [0.1, 0.2],
  point_count: 2,
};

function fakeClient() {
  return {
    catalogSessions: async () => ({ items: [SESSION_A, SESSION_B], next_cursor: null }),
    plots: {
      spectrum: async () => SPECTRUM,
      detail: async () => DETAIL,
      waveform: async () => WAVE,
    },
    analysis: {
      artifactBytes: async () => new ArrayBuffer(0),
    },
    requestJson: async () => {
      throw new ApiError("http", { status: 404 });
    },
  };
}

function fakeCreateView(): (options: UplotViewOptions) => ChartHandle {
  return (options) => {
    const root = document.createElement("div");
    options.container.append(root);
    return {
      root,
      render() {},
      applyTheme() {},
      getData: () => [],
      destroy() {},
    };
  };
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe("mountInspectV6", () => {
  const cleanups: Array<() => void> = [];

  afterEach(() => {
    for (const cleanup of cleanups) cleanup();
    cleanups.length = 0;
    document.body.replaceChildren();
  });

  it("mounts the v6 grid with chrome, pairbar, catalog, spectrum, analysis, extras", async () => {
    // Given
    const container = document.createElement("div");
    document.body.append(container);

    // When
    const cleanup = await mountInspectV6(container, {
      client: fakeClient(),
      routes: new RouteStore(),
      createView: fakeCreateView(),
    });
    cleanups.push(cleanup);
    await flush();

    // Then
    const root = container.querySelector(".app-v6");
    expect(root).toBeInstanceOf(HTMLElement);
    expect(root?.querySelector(".hdr")).toBeNull();
    expect(root?.querySelector(".statusbar")).toBeNull();
    expect(root?.querySelector(".pairbar")).toBeInstanceOf(HTMLElement);
    const body = root?.querySelector(".app-body");
    expect(body?.querySelector(".col-cat")).toBeInstanceOf(HTMLElement);
    expect(body?.querySelector(".col-main")).toBeInstanceOf(HTMLElement);
    const main = body?.querySelector(".col-main");
    expect(main?.querySelector('[data-showcase="spectrum"]')).toBeInstanceOf(HTMLElement);
    expect(main?.querySelector(".analysis-band")).toBeInstanceOf(HTMLElement);
    expect(main?.querySelector(".v6-extras")).toBeInstanceOf(HTMLElement);
    expect(root?.querySelector(".cmdbar")).toBeInstanceOf(HTMLElement);
  });

  it("auto-picks the first two catalog sessions into pair slots A and B", async () => {
    // Given
    const container = document.createElement("div");
    document.body.append(container);

    // When
    const cleanup = await mountInspectV6(container, {
      client: fakeClient(),
      routes: new RouteStore(),
      createView: fakeCreateView(),
    });
    cleanups.push(cleanup);
    await flush();

    // Then
    const pairbar = container.querySelector(".pairbar");
    expect(pairbar?.querySelector('[data-pair="a"]')).toBeInstanceOf(HTMLElement);
    expect(pairbar?.querySelector('[data-pair="b"]')).toBeInstanceOf(HTMLElement);
    expect(pairbar?.querySelector('[data-pair="a"] .pair-name')?.textContent).toBe("Alpha");
    expect(pairbar?.querySelector('[data-pair="b"] .pair-name')?.textContent).toBe("Beta");
  });

  it.each(["resolve", "reject"] as const)(
    "ignores a stale first-pair analysis %s after the auto-picked pair completes",
    async (outcome) => {
      let settle!: (detail: SessionDetailPayload) => void;
      let fail!: (error: Error) => void;
      const staleDetail = new Promise<SessionDetailPayload>((resolve, reject) => {
        settle = resolve;
        fail = reject;
      });
      let detailCall = 0;
      const currentDetail: SessionDetailPayload = {
        ...DETAIL,
        analysis: { needle: { cycles_analyzed: 222 } },
      };
      const client = {
        ...fakeClient(),
        plots: {
          ...fakeClient().plots,
          detail: vi.fn(async () => {
            detailCall += 1;
            if (detailCall === 2) return staleDetail;
            return detailCall >= 4 ? currentDetail : DETAIL;
          }),
        },
      };
      const container = document.createElement("div");
      document.body.append(container);
      const cleanup = await mountInspectV6(container, {
        client,
        routes: new RouteStore(),
        createView: fakeCreateView(),
      });
      cleanups.push(cleanup);

      await vi.waitFor(() => {
        expect(container.querySelector('[data-chbar="segments"]')?.textContent).toBe("222");
      });
      if (outcome === "resolve") settle(DETAIL);
      else fail(new Error("старый запрос упал"));
      await flush();

      expect(container.querySelector('[data-chbar="segments"]')?.textContent).toBe("222");
      expect(container.querySelector('[data-pair="b"] .pair-name')?.textContent).toBe("Beta");
      expect(container.querySelector<HTMLElement>("[data-inspect-error]")?.hidden).toBe(true);
    },
  );

  it("removes the v6 root when cleanup runs", async () => {
    // Given
    const container = document.createElement("div");
    document.body.append(container);
    const cleanup = await mountInspectV6(container, {
      client: fakeClient(),
      routes: new RouteStore(),
      createView: fakeCreateView(),
    });
    await flush();
    expect(container.querySelector(".app-v6")).toBeInstanceOf(HTMLElement);

    // When
    cleanup();

    // Then
    expect(container.querySelector(".app-v6")).toBeNull();
  });
});
