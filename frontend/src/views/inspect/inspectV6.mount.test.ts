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
  // Mount-мир: обе сессии проанализированы (legacy analyzed=true по dir-ключу
  // с запасным id) — иначе boot по JOIN честно выберет null-пару.
  const analyzed = (name: string) => ({ name, status: "valid", error: null, analyzed: true });
  return {
    catalogSessions: async () => ({ items: [SESSION_A, SESSION_B], next_cursor: null }),
    legacySessions: async () => ({ sessions: [analyzed("sess-a"), analyzed("sess-b")] }),
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
    "drops a stale pair refresh %s once the newer pair completes",
    async (outcome) => {
      // Given: boot грузит пару по двум вызовам detail; первый висячий.
      // stale: ручной pick во время загрузки делает поколение 1 устаревшим.
      // Свежий hash: предыдущие тест файла оставляют ?a=… в общем jsdom-окне,
      // RouteStore конструируется по нему — deep-link boot сломал бы расклад гонки.
      window.location.hash = "";
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
            // B2: один fetch на пару — первый вызов это первая пара, и её
            // поздний ответ обязан быть проигнорирован.
            if (detailCall === 1) return staleDetail;
            return currentDetail;
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

      // When: пользователь жмёт «А» второй строки, пока грузится первая
      // пара — поколение 1 (a=sess-a, b=sess-b) устаревает, побеждает
      // поколение 2 (a=sess-b, b=null): A переставлен на вторую строку,
      // detail дергается дважды, выигрывает второй ответ.
      const rows = container.querySelectorAll("tr[data-session]");
      const secondRow = rows[1];
      if (!(secondRow instanceof HTMLElement)) throw new Error("no second row");
      const assignA = secondRow.querySelector('[data-assign="a"]');
      if (!(assignA instanceof HTMLElement)) throw new Error("no assign button a");
      assignA.click();

      await vi.waitFor(() => {
        expect(container.querySelector('[data-chbar="segments"]')?.textContent).toBe("222");
      });
      if (outcome === "resolve") settle(DETAIL);
      else fail(new Error("старый запрос упал"));
      await flush();

      expect(container.querySelector('[data-chbar="segments"]')?.textContent).toBe("222");
      expect(container.querySelector('[data-pair="a"] .pair-name')?.textContent).toBe("Beta");
      expect(container.querySelector<HTMLElement>("[data-inspect-error]")?.hidden).toBe(true);
    },
  );

  it("fetches the base detail once per atomic boot pair: spectrum, band and analysis-v2 share it", async () => {
    // Given: каталог из двух проанализированных — boot делает ОДИН setPair.
    const bandDetail: SessionDetailPayload = {
      ...DETAIL,
      analysis: { needle: { cycles_analyzed: 130 } },
    };
    const detail = vi.fn(async () => bandDetail);
    const client = {
      ...fakeClient(),
      plots: { ...fakeClient().plots, detail },
    };
    const container = document.createElement("div");
    document.body.append(container);

    // When
    const cleanup = await mountInspectV6(container, {
      client,
      routes: new RouteStore(),
      createView: fakeCreateView(),
    });
    cleanups.push(cleanup);
    await vi.waitFor(() => {
      expect(container.querySelector('[data-chbar="segments"]')?.textContent).toBe("130");
    });
    await flush();

    // Then: один detail на атомарный setPair, а не по одному на потребителя.
    expect(detail).toHaveBeenCalledTimes(1);
  });

  it("F-1: deep-link по имени каталога наполняет слот пары метой каталога", async () => {
    // Given: каталог несёт manifest id; имя каталога видно только в storage_path
    // (include_paths). Шов захвата и ручные ссылки несут имя каталога (f3 F-1).
    const row: CatalogSession = {
      ...SESSION_A,
      id: "syn-quiet-seed777",
      label: "стенд-А",
      storage_path: "/root/dirname-differs",
    };
    const client = {
      ...fakeClient(),
      catalogSessions: async () => ({ items: [row], next_cursor: null }),
    };
    window.location.hash = "#/inspect?a=dirname-differs";
    const container = document.createElement("div");
    document.body.append(container);

    // When
    const cleanup = await mountInspectV6(container, {
      client,
      routes: new RouteStore(),
      createView: fakeCreateView(),
    });
    cleanups.push(cleanup);
    cleanups.push(() => {
      window.location.hash = "";
    });
    await vi.waitFor(() => {
      expect(container.querySelector('[data-pair="a"] .pair-name')?.textContent).toBe("стенд-А");
    });

    // Then: мета слота та же, что дал бы переход по manifest id.
    expect(container.querySelector('[data-pair="a"] .pair-meta')?.textContent).toContain(
      "2026-08-28",
    );
  });

  it("F-8: dir-name строки duplicate_id не канонизируется в неоднозначный id", async () => {
    // Given: две строки каталога с одним manifest id (health duplicate_id).
    // Запрос по id даёт 409 «идентификатор сессии неоднозначен», по имени
    // каталога — 200 (D1). Шов захвата несёт имя каталога.
    const dupRow = (dir: string, label: string): CatalogSession => ({
      ...SESSION_A,
      id: "syn-quiet-seed6022",
      health: "duplicate_id",
      label,
      storage_path: `/root/${dir}`,
    });
    const rows = [dupRow("sim-quiet-a", "дубль-А"), dupRow("sim-quiet-b", "дубль-Б")];
    const detailKeys: string[] = [];
    const client = {
      ...fakeClient(),
      catalogSessions: async () => ({ items: rows, next_cursor: null }),
      plots: {
        ...fakeClient().plots,
        detail: async (name: string) => {
          detailKeys.push(name);
          if (name === "syn-quiet-seed6022") throw new ApiError("conflict", { status: 409 });
          return { ...DETAIL, name };
        },
      },
    };
    window.location.hash = "#/inspect?a=sim-quiet-a";
    const container = document.createElement("div");
    document.body.append(container);

    // When
    const cleanup = await mountInspectV6(container, {
      client,
      routes: new RouteStore(),
      createView: fakeCreateView(),
    });
    cleanups.push(cleanup);
    cleanups.push(() => {
      window.location.hash = "";
    });

    // Then: слот пары наполнен метой своей строки, а не прочерком.
    await vi.waitFor(() => {
      expect(container.querySelector('[data-pair="a"] .pair-name')?.textContent).toBe("дубль-А");
    });
    expect(detailKeys.length).toBeGreaterThan(0);
    expect(detailKeys.every((key) => key === "sim-quiet-a")).toBe(true);
    expect(container.querySelector<HTMLElement>("[data-inspect-error]")?.hidden).toBe(true);
  });

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

  /** Задача 3 (D2/C5): ошибка pair-load уходит в ленту через существующий
   * сеттер showError; reason = canned-префикс + серверный detail. */
  function failingClient(error: unknown) {
    return {
      ...fakeClient(),
      plots: {
        ...fakeClient().plots,
        detail: async (): Promise<SessionDetailPayload> => {
          throw error;
        },
      },
    };
  }

  it("задача 3: 409 с detail на pair-load — detail виден в ленте после canned-префикса", async () => {
    // Given: detail базы отвечает 409 с серверным detail (дубль идентификатора).
    const detailText = "идентификатор сессии неоднозначен: 'syn-quiet-seed6022'";
    const conflict = new ApiError("conflict", { status: 409, detail: detailText });
    const container = document.createElement("div");
    document.body.append(container);

    // When
    const cleanup = await mountInspectV6(container, {
      client: failingClient(conflict),
      routes: new RouteStore(),
      createView: fakeCreateView(),
    });
    cleanups.push(cleanup);

    // Then: лента видна, текст = canned-префикс + пробел + detail (точный порядок).
    await vi.waitFor(() => {
      expect(container.querySelector<HTMLElement>("[data-inspect-error]")?.hidden).toBe(false);
    });
    const band = container.querySelector<HTMLElement>("[data-inspect-error]");
    expect(band?.textContent).toBe(`${conflict.message} ${detailText}`);
    expect(band?.textContent).not.toContain("undefined");
  });

  it("задача 3: 500 без detail — честный failed из словаря, без «undefined» и без краша", async () => {
    // Given: сервер вернул 500 с пустым телом — detail нет.
    const serverError = new ApiError("http", { status: 500 });
    const container = document.createElement("div");
    document.body.append(container);

    // When
    const cleanup = await mountInspectV6(container, {
      client: failingClient(serverError),
      routes: new RouteStore(),
      createView: fakeCreateView(),
    });
    cleanups.push(cleanup);

    // Then: только canned-префикс; вид смонтирован и жив.
    await vi.waitFor(() => {
      expect(container.querySelector<HTMLElement>("[data-inspect-error]")?.hidden).toBe(false);
    });
    const band = container.querySelector<HTMLElement>("[data-inspect-error]");
    expect(band?.textContent).toBe(serverError.message);
    expect(band?.textContent).not.toContain("undefined");
    expect(container.querySelector(".app-v6")).toBeInstanceOf(HTMLElement);
  });
});
