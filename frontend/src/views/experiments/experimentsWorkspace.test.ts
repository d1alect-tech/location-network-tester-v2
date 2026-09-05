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
});
