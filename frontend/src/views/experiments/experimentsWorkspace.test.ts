/** U2: тихий catch здоровья в experimentsWorkspace маскировал outage под
 * QC-вердикт. RED: падает, пока loadHealth синтезирует health_unavailable
 * вместо outage-баннера с повтором. */

import { afterEach, describe, expect, it } from "vitest";
import { LntApiClient } from "../../api/client";
import { RouteStore } from "../../state/routeState";
import { mountExperimentsWorkspace } from "./experimentsWorkspace";

const CONFIG = {
  root: "C:\\lnt-sessions-test",
  profiles: [],
  defaults: {
    simulate: { duration_s: 2.4, sample_rate_hz: 20_000_000, seed: 7, repeat: 1, interval_s: 0 },
    capture: { duration_s: 2.4, sample_rate_hz: 20_000_000, range_v: 5, repeat: 1, interval_s: 0 },
    ranges: [5],
  },
  build_id: "test-build",
  mutation_nonce: "test-nonce",
  static_asset_hash: "test-hash",
  static_assets: {},
};

const EXPERIMENT = {
  experiment_id: "exp-1",
  title: "Синтетика",
  protocol: { kind: "aba" },
  primary_estimands: [{ feature_key: "band_mid_total" }],
};

const MEMBERS = [{ session_id: "sess-1", role: "unit", condition_id: "cond_a", order: 1 }];

const STEPS = [{ order: 1, condition_id: "cond_a", instruction: "база" }];

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function catalogSession() {
  return {
    id: "sess-1",
    health: "ok",
    created_utc: "2026-08-01T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "quiet",
    label: "первая",
  };
}

interface StubFlags {
  catalogFails: boolean;
}

function stubFetch(flags: StubFlags): typeof fetch {
  return (async (input: string | URL | Request) => {
    const url = String(input);
    const json = (body: unknown, status = 200): Response =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    if (url.startsWith("/api/config")) return json(CONFIG);
    if (url.startsWith("/api/catalog/sessions")) {
      return flags.catalogFails
        ? json({ detail: "каталог недоступен" }, 500)
        : json({ items: [catalogSession()], next_cursor: null });
    }
    if (url === "/api/v2/experiments?page_size=200") {
      return json({ items: [EXPERIMENT], next_cursor: null });
    }
    if (url === "/api/v2/experiments/exp-1") return json(EXPERIMENT);
    if (url.startsWith("/api/v2/experiments/exp-1/members")) {
      return json({ items: MEMBERS, next_cursor: null });
    }
    if (url.startsWith("/api/v2/experiments/exp-1/steps")) {
      return json({ items: STEPS, next_cursor: null });
    }
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

async function flush(): Promise<void> {
  for (let i = 0; i < 30; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 30; i += 1) await Promise.resolve();
}

function politeRegion(): HTMLElement | null {
  return document.querySelector('[role="status"][aria-live="polite"]');
}

describe("experimentsWorkspace health outage (U2)", () => {
  const cleanups: Array<() => void> = [];

  afterEach(() => {
    for (const cleanup of cleanups) cleanup();
    cleanups.length = 0;
    document.body.replaceChildren();
  });

  it("health failure shows outage alert with retry instead of fake verdicts; retry recovers", async () => {
    // Given: каталог здоровья недоступен.
    const flags: StubFlags = { catalogFails: true };
    const container = document.createElement("div");
    document.body.append(container);
    cleanups.push(
      mountExperimentsWorkspace(container, {
        client: new LntApiClient(stubFetch(flags)),
        routes: new RouteStore(),
      }),
    );
    await flush();
    const openButton = container.querySelector('[data-experiment-id="exp-1"]');
    expect(openButton).toBeInstanceOf(HTMLElement);
    (openButton as HTMLElement).click();
    await flush();

    // Then: outage-баннер с повтором, никаких выдуманных вердиктов.
    const members = container.querySelector(".lnt-exp-members");
    expect(members).toBeInstanceOf(HTMLElement);
    const alert = members?.querySelector('[role="alert"]');
    expect(alert?.textContent).toMatch(/не удалось загрузить/i);
    const retry = [...(members?.querySelectorAll("button") ?? [])].find(
      (button) => button.textContent === "Повторить",
    );
    expect(retry).toBeInstanceOf(HTMLButtonElement);
    expect(document.body.textContent).not.toContain("health_unavailable");
    expect(politeRegion()?.textContent).toMatch(/не удалось загрузить/i);

    // When: каталог ожил, оператор жмёт повтор.
    flags.catalogFails = false;
    retry?.click();
    await flush();

    // Then: баннер убран, настоящий QC-вердикт, объявление о восстановлении.
    expect(members?.querySelector('[role="alert"]')).toBeNull();
    expect(members?.textContent).toContain("QC пройден");
    expect(politeRegion()?.textContent).toMatch(/обновлено/i);
  });

  it("keeps the newest detail when health requests finish out of order", async () => {
    window.history.replaceState(null, "", "#/experiments");
    const healthRequests: Deferred<Response>[] = [];
    const json = (body: unknown): Response =>
      new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
    const experiment1 = { ...EXPERIMENT, steps: [{ order: 1, condition_id: "cond-1" }] };
    const experiment2 = {
      ...EXPERIMENT,
      experiment_id: "exp-2",
      title: "Сравнение",
      steps: [{ order: 1, condition_id: "cond-2" }],
    };
    const fetchImpl = (async (input: string | URL | Request) => {
      const url = String(input);
      if (url.startsWith("/api/config")) return json(CONFIG);
      if (url.startsWith("/api/catalog/sessions")) {
        const request = deferred<Response>();
        healthRequests.push(request);
        return request.promise;
      }
      if (url === "/api/v2/experiments?page_size=200") {
        return json({ items: [experiment1, experiment2], next_cursor: null });
      }
      if (url === "/api/v2/experiments/exp-1") return json(experiment1);
      if (url === "/api/v2/experiments/exp-2") return json(experiment2);
      const id = url.includes("exp-2") ? "2" : "1";
      if (url.includes("/members")) {
        return json({
          items: [{ session_id: `sess-${id}`, role: "unit", condition_id: `cond-${id}`, order: 1 }],
          next_cursor: null,
        });
      }
      if (url.includes("/steps")) {
        return json({
          items: [{ order: 1, condition_id: `cond-${id}`, instruction: `протокол-${id}` }],
          next_cursor: null,
        });
      }
      return json({ detail: "неизвестный маршрут" });
    }) as typeof fetch;
    const container = document.createElement("div");
    document.body.append(container);
    cleanups.push(
      mountExperimentsWorkspace(container, {
        client: new LntApiClient(fetchImpl),
        routes: new RouteStore(),
      }),
    );
    await flush();

    container.querySelector<HTMLButtonElement>('[data-experiment-id="exp-1"]')?.click();
    await flush();
    expect(healthRequests).toHaveLength(1);
    container.querySelector<HTMLButtonElement>('[data-experiment-id="exp-2"]')?.click();
    await flush();
    expect(healthRequests).toHaveLength(2);

    healthRequests[1]?.resolve(
      json({ items: [{ ...catalogSession(), id: "sess-2" }], next_cursor: null }),
    );
    await flush();
    healthRequests[0]?.resolve(json({ items: [catalogSession()], next_cursor: null }));
    await flush();

    expect(container.querySelector(".lnt-exp-member-table")?.textContent).toContain("sess-2");
    expect(container.querySelector(".lnt-exp-member-table")?.textContent).not.toContain("sess-1");
    expect(container.querySelector(".lnt-exp-timeline")?.textContent).toContain("протокол-2");
    container.querySelector<HTMLButtonElement>('[data-exp-tab="compare"]')?.click();
    expect(container.querySelector(".pairbar")?.textContent).toContain("cond-2");
    expect(container.querySelector(".pairbar")?.textContent).not.toContain("cond-1");
    container.querySelector<HTMLButtonElement>('[data-exp-tab="hypotheses"]')?.click();
    container.querySelector<HTMLButtonElement>(".lnt-exp-hypotheses button")?.click();
    expect(container.querySelector(".lnt-exp-hypothesis-form")?.textContent).toContain("exp-2");
    expect(container.querySelector(".lnt-exp-hypothesis-form")?.textContent).not.toContain("exp-1");
  });

  it("mounts a retryable detail error in the right pane", async () => {
    let detailRequests = 0;
    const fetchImpl = (async (input: string | URL | Request) => {
      const url = String(input);
      const json = (body: unknown, status = 200): Response =>
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        });
      if (url.startsWith("/api/config")) return json(CONFIG);
      if (url === "/api/v2/experiments?page_size=200") {
        return json({ items: [EXPERIMENT], next_cursor: null });
      }
      if (url === "/api/v2/experiments/exp-1") {
        detailRequests += 1;
        return json({ detail: "деталь недоступна" }, 500);
      }
      if (url.includes("/members")) return json({ items: MEMBERS, next_cursor: null });
      if (url.includes("/steps")) return json({ items: STEPS, next_cursor: null });
      return json({ items: [catalogSession()], next_cursor: null });
    }) as typeof fetch;
    const container = document.createElement("div");
    document.body.append(container);
    cleanups.push(
      mountExperimentsWorkspace(container, {
        client: new LntApiClient(fetchImpl),
        routes: new RouteStore(),
      }),
    );
    await flush();

    container.querySelector<HTMLButtonElement>('[data-experiment-id="exp-1"]')?.click();
    await flush();

    const rightPane = container.querySelector(".lnt-exp-right");
    expect(rightPane?.querySelector('[role="alert"]')?.textContent).toMatch(
      /не удалось загрузить эксперимент/i,
    );
    expect(
      [...(rightPane?.querySelectorAll("button") ?? [])].some((button) =>
        button.textContent?.includes("Повторить"),
      ),
    ).toBe(true);
    const retry = [...(rightPane?.querySelectorAll("button") ?? [])].find((button) =>
      button.textContent?.includes("Повторить"),
    );
    retry?.click();
    await flush();
    expect(detailRequests).toBe(2);
  });

  it("opens one modal wizard, traps focus, and restores the trigger on Escape", async () => {
    const container = document.createElement("div");
    document.body.append(container);
    cleanups.push(
      mountExperimentsWorkspace(container, {
        client: new LntApiClient(stubFetch({ catalogFails: false })),
        routes: new RouteStore(),
      }),
    );
    await flush();
    const trigger = container.querySelector<HTMLButtonElement>("#lnt-exp-create");
    expect(trigger).toBeInstanceOf(HTMLButtonElement);
    trigger?.focus();
    trigger?.click();
    trigger?.click();
    await flush();

    const dialogs = document.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"]');
    expect(dialogs).toHaveLength(1);
    const dialog = dialogs[0];
    expect(dialog?.contains(document.activeElement)).toBe(true);
    expect(container.hasAttribute("inert")).toBe(true);
    const focusable = [...(dialog?.querySelectorAll<HTMLElement>("button, input, select") ?? [])];
    const first = focusable.find((element) => !element.hasAttribute("disabled"));
    const last = [...focusable].reverse().find((element) => !element.hasAttribute("disabled"));
    last?.focus();
    last?.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    expect(document.activeElement).toBe(first);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(container.hasAttribute("inert")).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });

  it("does not apply an in-flight detail after workspace disposal", async () => {
    const healthRequest = deferred<Response>();
    const json = (body: unknown): Response =>
      new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
    const fetchImpl = (async (input: string | URL | Request) => {
      const url = String(input);
      if (url.startsWith("/api/config")) return json(CONFIG);
      if (url.startsWith("/api/catalog/sessions")) return healthRequest.promise;
      if (url === "/api/v2/experiments?page_size=200") {
        return json({ items: [EXPERIMENT], next_cursor: null });
      }
      if (url === "/api/v2/experiments/exp-1") return json(EXPERIMENT);
      if (url.includes("/members")) return json({ items: MEMBERS, next_cursor: null });
      if (url.includes("/steps")) return json({ items: STEPS, next_cursor: null });
      return json({ detail: "неизвестный маршрут" });
    }) as typeof fetch;
    const container = document.createElement("div");
    document.body.append(container);
    const dispose = mountExperimentsWorkspace(container, {
      client: new LntApiClient(fetchImpl),
      routes: new RouteStore(),
    });
    await flush();
    container.querySelector<HTMLButtonElement>('[data-experiment-id="exp-1"]')?.click();
    await flush();

    dispose();
    healthRequest.resolve(json({ items: [catalogSession()], next_cursor: null }));
    await flush();

    expect(container.querySelectorAll(".lnt-exp-member-row")).toHaveLength(0);
    expect(container.querySelector(".lnt-exp-timeline")?.textContent).not.toContain("база");
  });

  it("clears the old comparison as soon as another detail starts loading", async () => {
    const secondDetail = deferred<Response>();
    const json = (body: unknown): Response =>
      new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
    const experiment1 = { ...EXPERIMENT, steps: [{ order: 1, condition_id: "cond-1" }] };
    const experiment2 = {
      ...EXPERIMENT,
      experiment_id: "exp-2",
      steps: [{ order: 1, condition_id: "cond-2" }],
    };
    const fetchImpl = (async (input: string | URL | Request) => {
      const url = String(input);
      if (url.startsWith("/api/config")) return json(CONFIG);
      if (url === "/api/v2/experiments?page_size=200") {
        return json({ items: [experiment1, experiment2], next_cursor: null });
      }
      if (url === "/api/v2/experiments/exp-1") return json(experiment1);
      if (url === "/api/v2/experiments/exp-2") return secondDetail.promise;
      const id = url.includes("exp-2") ? "2" : "1";
      if (url.includes("/members")) {
        return json({
          items: [{ session_id: `sess-${id}`, role: "unit", condition_id: `cond-${id}`, order: 1 }],
          next_cursor: null,
        });
      }
      if (url.includes("/steps")) return json({ items: [], next_cursor: null });
      if (url.startsWith("/api/catalog/sessions")) {
        return json({ items: [{ ...catalogSession(), id: `sess-${id}` }], next_cursor: null });
      }
      return json({ items: [], next_cursor: null });
    }) as typeof fetch;
    const container = document.createElement("div");
    document.body.append(container);
    cleanups.push(
      mountExperimentsWorkspace(container, {
        client: new LntApiClient(fetchImpl),
        routes: new RouteStore(),
      }),
    );
    await flush();
    container.querySelector<HTMLButtonElement>('[data-experiment-id="exp-1"]')?.click();
    await flush();
    container.querySelector<HTMLButtonElement>('[data-exp-tab="compare"]')?.click();
    expect(container.querySelector(".pairbar")?.textContent).toContain("cond-1");

    container.querySelector<HTMLButtonElement>('[data-experiment-id="exp-2"]')?.click();
    await flush();
    expect(container.querySelector(".pairbar")?.textContent).not.toContain("cond-1");
    container.querySelector<HTMLButtonElement>("#lnt-exp-check-comparability")?.click();
    await flush();
    expect(container.querySelector(".lnt-exp-compare-status")?.textContent).toContain(
      "Нет данных эксперимента",
    );

    secondDetail.resolve(json(experiment2));
    await flush();
  });
});
