/** U2: тихие catch в settingsWorkspace — видимая русская ошибка + повтор.
 * RED: падает, пока refreshProfiles/bootstrap показывают голый текст без
 * role=alert и кнопки повтора. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import type { JobSnapshot } from "../../api/types-jobs";
import { createModeForm } from "../../capture/modeForm";
import { mountSettingsWorkspace } from "./settingsWorkspace";

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

const DEVICE_ABSENT = {
  state: "device_absent",
  description_ru: "Устройство не обнаружено на шине USB.",
  recovery_action_ru: "Проверьте подключение и программу Zadig.",
};

interface StubFlags {
  configFails: boolean;
  profilesFail: boolean;
}

function stubFetch(flags: StubFlags): typeof fetch {
  return (async (input: string | URL | Request) => {
    const url = String(input);
    const json = (body: unknown, status = 200): Response =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    if (url.startsWith("/api/config")) {
      return flags.configFails ? json({ detail: "сервер не отвечает" }, 500) : json(CONFIG);
    }
    if (url.startsWith("/api/profiles")) {
      return flags.profilesFail ? json({ detail: "сервер не отвечает" }, 500) : json({ items: [] });
    }
    if (url.startsWith("/api/device/state")) return json(DEVICE_ABSENT);
    if (url.startsWith("/api/analysis/recipes")) return json({ items: [] });
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

const PREFLIGHT_OK = {
  ready: true,
  device_state: "ready",
  findings: [],
};

function stubPreflight(seen: unknown[]): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const json = (body: unknown, status = 200): Response =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    if (url.startsWith("/api/config")) return json(CONFIG);
    if (url.startsWith("/api/profiles")) return json({ items: [] });
    if (url.startsWith("/api/device/state")) return json(DEVICE_ABSENT);
    if (url.startsWith("/api/analysis/recipes")) return json({ items: [] });
    if (url.startsWith("/api/capture/preflight")) {
      seen.push(JSON.parse(String(init?.body ?? "null")));
      return json(PREFLIGHT_OK);
    }
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

function politeRegion(): HTMLElement | null {
  return document.querySelector('[role="status"][aria-live="polite"]');
}

describe("settingsWorkspace error visibility (U2)", () => {
  const cleanups: Array<() => void> = [];

  afterEach(() => {
    for (const cleanup of cleanups) cleanup();
    cleanups.length = 0;
    document.body.replaceChildren();
  });

  it("profiles failure renders role=alert with retry; retry recovers with announce", async () => {
    // Given: сервер профилей недоступен.
    const flags: StubFlags = { configFails: false, profilesFail: true };
    const container = document.createElement("div");
    document.body.append(container);
    cleanups.push(
      mountSettingsWorkspace(container, { client: new LntApiClient(stubFetch(flags)) }),
    );
    await flush();

    // When/Then: видимая ошибка с повтором, а не голый текст.
    const profilesSection = [...container.querySelectorAll(".lnt-set-section")].find((section) =>
      section.textContent?.includes("Профили"),
    );
    expect(profilesSection).toBeInstanceOf(HTMLElement);
    const alert = profilesSection?.querySelector('[role="alert"]');
    expect(alert?.textContent).toMatch(/недоступен/i);
    const retry = [...(profilesSection?.querySelectorAll("button") ?? [])].find(
      (button) => button.textContent === "Повторить",
    );
    expect(retry).toBeInstanceOf(HTMLButtonElement);
    expect(politeRegion()?.textContent).toMatch(/недоступен/i);

    // When: сервер ожил, оператор жмёт повтор.
    flags.profilesFail = false;
    retry?.click();
    await flush();

    // Then: успех + объявление о восстановлении, баннер убран.
    expect(profilesSection?.textContent).toMatch(/Зарегистрированных профилей: 0/);
    expect(profilesSection?.querySelector('[role="alert"]')).toBeNull();
    expect(politeRegion()?.textContent).toMatch(/загружен/i);
  });

  it("settings preflight binds live Capture form values (U3 RED)", async () => {
    // Given: живая форма захвата с изменёнными длительностью и диапазоном.
    const seen: unknown[] = [];
    const container = document.createElement("div");
    document.body.append(container);
    const form = createModeForm();
    document.body.append(form.root);
    const setValue = (name: string, value: string): void => {
      const input = form.root.querySelector(`[name="${name}"]`);
      if (input instanceof HTMLInputElement || input instanceof HTMLSelectElement) {
        input.value = value;
      }
    };
    setValue("duration_s", "5");
    setValue("range_v", "1");
    cleanups.push(
      mountSettingsWorkspace(container, { client: new LntApiClient(stubPreflight(seen)) }),
    );
    await flush();

    // When: оператор жмёт проверку готовности в «Настройках».
    (container.querySelector("#lnt-set-preflight") as HTMLButtonElement).click();
    await flush();

    // Then: запрос preflight отражает живые значения формы, а не хардкод.
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ kind: "capture", duration_s: 5, range_v: 1 });
  });

  it("empty Capture form falls back to DEFAULT_FORM_VALUES (U3 RED)", async () => {
    // Given: форма захвата смонтирована, но поля пустые (не заполнены).
    const seen: unknown[] = [];
    const container = document.createElement("div");
    document.body.append(container);
    const form = createModeForm();
    document.body.append(form.root);
    for (const name of ["duration_s", "sample_rate_hz", "repeat", "interval_s"]) {
      const input = form.root.querySelector(`[name="${name}"]`);
      if (input instanceof HTMLInputElement) input.value = "";
    }
    cleanups.push(
      mountSettingsWorkspace(container, { client: new LntApiClient(stubPreflight(seen)) }),
    );
    await flush();

    // When: оператор жмёт проверку готовности в «Настройках».
    (container.querySelector("#lnt-set-preflight") as HTMLButtonElement).click();
    await flush();

    // Then: запрос собран из значений по умолчанию формы захвата.
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({
      kind: "capture",
      duration_s: 2.4,
      sample_rate_hz: 8_000_000,
      range_v: 5,
      channels: 2,
      repeat: 1,
      interval_s: 0,
    });
  });

  it("line-quality mode flows single channel plus transformer into preflight (U3 RED)", async () => {
    // Given: в живой форме выбран режим качества сети (1 канал + трансформатор).
    const seen: unknown[] = [];
    const container = document.createElement("div");
    document.body.append(container);
    const form = createModeForm();
    document.body.append(form.root);
    const lineQuality = form.root.querySelector<HTMLInputElement>("#capture-mode-line_quality");
    if (lineQuality) lineQuality.checked = true;
    cleanups.push(
      mountSettingsWorkspace(container, { client: new LntApiClient(stubPreflight(seen)) }),
    );
    await flush();

    // When: оператор жмёт проверку готовности в «Настройках».
    (container.querySelector("#lnt-set-preflight") as HTMLButtonElement).click();
    await flush();

    // Then: preflight несёт одноканальную трансформаторную конфигурацию.
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({
      kind: "capture",
      channels: 1,
      input: "transformer",
      baseline_session: null,
    });
  });

  it("bootstrap failure marks root value with role=alert and retry; retry recovers", async () => {
    // Given: /api/config недоступен.
    const flags: StubFlags = { configFails: true, profilesFail: false };
    const container = document.createElement("div");
    document.body.append(container);
    cleanups.push(
      mountSettingsWorkspace(container, { client: new LntApiClient(stubFetch(flags)) }),
    );
    await flush();

    // When/Then: корень помечен outage-состоянием с повтором.
    const rootValue = container.querySelector(".lnt-set-root-value");
    expect(rootValue?.textContent).toMatch(/недоступно/i);
    expect(rootValue?.getAttribute("role")).toBe("alert");
    const retry = container.querySelector("#lnt-set-root-retry");
    expect(retry).toBeInstanceOf(HTMLButtonElement);
    expect(politeRegion()?.textContent).toMatch(/недоступен/i);

    // When: сервер ожил, оператор жмёт повтор.
    flags.configFails = false;
    (retry as HTMLButtonElement).click();
    await flush();

    // Then: факт корня + объявление о восстановлении, повтор скрыт.
    expect(container.querySelector(".lnt-set-root-value")?.textContent).toBe(
      "C:\\lnt-sessions-test",
    );
    expect(container.querySelector(".lnt-set-root-value")?.getAttribute("role")).toBeNull();
    expect(container.querySelector("#lnt-set-root-retry")?.getAttribute("hidden")).not.toBeNull();
    expect(politeRegion()?.textContent).toMatch(/загружен/i);
  });
});
/** D2: кнопки бэкапа и сборника в «Настройках» — запуск panel-задач
 * backup/support_bundle через client.jobs.start со статусом и объявлением.
 * RED: падает, пока в секции сборника нет кнопок lnt-set-backup-run /
 * lnt-set-bundle-run и проводки на POST /api/jobs. */

function bundleSnap(overrides: Partial<JobSnapshot>): JobSnapshot {
  return {
    schema_version: 1,
    version: 1,
    job_id: "job-bundle-1",
    kind: "backup",
    status: "queued",
    stage: "queued",
    series_index: null,
    series_total: null,
    written_sessions: [],
    result: null,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

/** Фальшивый EventSource: именованные события "snapshot", как шлёт бэкенд. */
class FakeBundleEventSource {
  static instances: FakeBundleEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly snapshotHandlers: Array<(event: { data: string }) => void> = [];

  constructor(_url: string) {
    FakeBundleEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: { data: string }) => void): void {
    if (type === "snapshot") this.snapshotHandlers.push(handler);
  }

  close(): void {
    this.closed = true;
  }

  emit(snapshot: JobSnapshot): void {
    for (const handler of [...this.snapshotHandlers]) {
      handler({ data: JSON.stringify(snapshot) });
    }
  }
}

function stubBundleFetch(seen: unknown[], first: JobSnapshot): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const json = (body: unknown, status = 200): Response =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    if (url.startsWith("/api/config")) return json(CONFIG);
    if (url.startsWith("/api/profiles")) return json({ items: [] });
    if (url.startsWith("/api/device/state")) return json(DEVICE_ABSENT);
    if (url.startsWith("/api/analysis/recipes")) return json({ items: [] });
    if (url.startsWith("/api/jobs") && init?.method === "POST") {
      seen.push(JSON.parse(String(init.body)));
      return json(first, 202);
    }
    if (/\/api\/jobs\/[^/]+$/.exec(url) !== null) return json(first);
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

describe("settingsWorkspace bundle jobs (D2)", () => {
  const cleanups: Array<() => void> = [];

  afterEach(() => {
    for (const cleanup of cleanups) cleanup();
    cleanups.length = 0;
    vi.unstubAllGlobals();
    FakeBundleEventSource.instances = [];
    document.body.replaceChildren();
  });

  it("backup button starts {kind:'backup'} and announces the result file", async () => {
    // Given: секция сборника с кнопкой бэкапа, сервер принимает задачу.
    const seen: unknown[] = [];
    vi.stubGlobal("EventSource", FakeBundleEventSource);
    const container = document.createElement("div");
    document.body.append(container);
    cleanups.push(
      mountSettingsWorkspace(container, {
        client: new LntApiClient(stubBundleFetch(seen, bundleSnap({ kind: "backup" }))),
      }),
    );
    await flush();

    // When: оператор жмёт «Создать бэкап».
    const button = container.querySelector("#lnt-set-backup-run");
    expect(button).toBeInstanceOf(HTMLButtonElement);
    expect(button?.textContent).toContain("Создать бэкап");
    (button as HTMLButtonElement).click();
    await flush();

    // Then: POST /api/jobs с kind backup, кнопка заблокирована на время задачи.
    expect(seen).toEqual([{ kind: "backup" }]);
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(container.querySelector("#lnt-set-bundle-status")?.textContent).toMatch(/бэкап/i);

    // When: SSE приносит терминальный снимок с именем файла.
    const source = FakeBundleEventSource.instances[0];
    expect(source).toBeInstanceOf(FakeBundleEventSource);
    source?.emit(
      bundleSnap({
        kind: "backup",
        status: "succeeded",
        stage: "done",
        version: 2,
        result: { path: "lnt-backup-2026-09-06.zip" },
      }),
    );
    await flush();

    // Then: имя файла видно и объявлено, кнопка снова активна.
    expect(container.querySelector("#lnt-set-bundle-status")?.textContent).toContain(
      "lnt-backup-2026-09-06.zip",
    );
    expect(politeRegion()?.textContent).toContain("lnt-backup-2026-09-06.zip");
    expect((button as HTMLButtonElement).disabled).toBe(false);
  });

  it("bundle button starts {kind:'support_bundle'} and shows errorBlock on failure", async () => {
    // Given: секция сборника с кнопкой сборника.
    const seen: unknown[] = [];
    vi.stubGlobal("EventSource", FakeBundleEventSource);
    const container = document.createElement("div");
    document.body.append(container);
    cleanups.push(
      mountSettingsWorkspace(container, {
        client: new LntApiClient(stubBundleFetch(seen, bundleSnap({ kind: "support_bundle" }))),
      }),
    );
    await flush();

    // When: оператор жмёт «Собрать сборник».
    const button = container.querySelector("#lnt-set-bundle-run");
    expect(button).toBeInstanceOf(HTMLButtonElement);
    expect(button?.textContent).toContain("Собрать сборник");
    (button as HTMLButtonElement).click();
    await flush();

    // Then: POST /api/jobs с kind support_bundle.
    expect(seen).toEqual([{ kind: "support_bundle" }]);

    // When: SSE приносит провал задачи.
    const source = FakeBundleEventSource.instances[0];
    source?.emit(
      bundleSnap({
        kind: "support_bundle",
        status: "failed",
        stage: "done",
        version: 2,
        error_code: "bundle_failed",
        error_message: "не хватило места на диске",
      }),
    );
    await flush();

    // Then: видимый errorBlock с русской причиной, кнопка снова активна.
    const guidance = container.querySelector(".lnt-set-bundle-guidance");
    expect(guidance?.querySelector('[role="alert"]')?.textContent).toMatch(
      /не удалось собрать сборник/i,
    );
    expect(guidance?.querySelector('[role="alert"]')?.textContent).toContain(
      "не хватило места на диске",
    );
    expect((button as HTMLButtonElement).disabled).toBe(false);
  });
});
