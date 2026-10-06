import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import type { ContextResponse } from "../../api/types";
import type { SessionDetailPayload } from "../../api/types-plots";
import { createContextInspector } from "./contextInspector";

function fakeClient(context?: ContextResponse, detail?: SessionDetailPayload | null): LntApiClient {
  return {
    context: vi.fn(async () => {
      if (!context) throw new Error("context fixture missing");
      return context;
    }),
    updateContext: vi.fn(async () => context),
    ensureReady: vi.fn(async () => undefined),
    plots: { detail: vi.fn(async () => detail ?? null) },
  } as unknown as LntApiClient;
}

function contextResponse(health: string, reasonCodes: string[] = []): ContextResponse {
  return {
    session_id: "session-1",
    revision: health === "context_absent" ? 0 : 2,
    health,
    reason_codes: reasonCodes,
    fields: {},
    tags: [],
    notes: null,
  };
}

function detailWith(metrics: Record<string, unknown>): SessionDetailPayload {
  return {
    name: "session-1",
    manifest: { duration_s: 12.4, line_frequency_hz: 50.0 },
    analysis: { line_quality: metrics },
    spectrum_available: false,
    waveform_available: false,
    ch2_available: false,
  };
}

const META = { id: "session-1", createdUtc: "2026-08-05T18:06:23Z", sessionHealth: "ok" };

async function mount(
  context: ContextResponse,
  detail?: SessionDetailPayload | null,
): Promise<LntApiClient & { root: HTMLElement }> {
  const client = fakeClient(context, detail);
  const inspector = createContextInspector({ client });
  await inspector.loadSession("session-1", META);
  return Object.assign(client, { root: inspector.root });
}

describe("createContextInspector pristine state", () => {
  it("shows no error-styled box before any session loads or save runs", () => {
    // Given: инспектор создан, сессия не выбрана, сохранений не было
    const inspector = createContextInspector({ client: fakeClient() });

    // Then: конфликт-панель скрыта, а не пустая красная рамка
    const conflict = inspector.root.querySelector(".lnt-cat-conflict");
    expect(conflict).not.toBeNull();
    expect(conflict?.hasAttribute("hidden")).toBe(true);

    // Then: пустая строка ошибки скрыта, а не пустой role=alert
    const error = inspector.root.querySelector(".lnt-error-text");
    expect(error).not.toBeNull();
    expect(error?.hasAttribute("hidden")).toBe(true);
    expect(error?.textContent).toBe("");
  });
});

describe("createContextInspector context health", () => {
  it("shows a healthy context without a damage notice", async () => {
    const mounted = await mount(contextResponse("context_valid"));

    // Supersession: сводка варианта «Плотный список» показывает здоровье
    // пилюлей «Контекст: …» вместо строки «Состояние контекста: …».
    const pill = mounted.root.querySelector("[data-cat-context-health='context_valid']");
    expect(pill?.textContent).toContain("Контекст: Исправен");
    expect(mounted.root.querySelector(".lnt-cat-recovery")).toBeNull();
  });

  it("explains an absent context without calling the session unusable", async () => {
    const mounted = await mount(contextResponse("context_absent"));

    const text = mounted.root.querySelector(".lnt-cat-recovery")?.textContent ?? "";
    expect(text).toContain("Контекст сессии ещё не сохранён");
    expect(text).toContain("можно заполнить и сохранить");
    expect(text).not.toContain("Сессия повреждена");
    expect(text).not.toContain("недоступна для анализа");
  });

  it("limits an invalid-context notice to context metadata", async () => {
    const mounted = await mount(contextResponse("context_invalid", ["context_cache_malformed"]));

    const text = mounted.root.querySelector(".lnt-cat-recovery")?.textContent ?? "";
    expect(text).toContain("Контекст сессии повреждён");
    expect(text).toContain("Проблема относится только к контексту");
    expect(text).toContain("Не удалось прочитать context.json");
    expect(text).not.toContain("Запись недоступна для анализа");
  });

  it("keeps a torn-tail warning on an otherwise valid context", async () => {
    const mounted = await mount(contextResponse("context_valid", ["context_events_torn_tail"]));

    const text = mounted.root.querySelector(".lnt-cat-recovery")?.textContent ?? "";
    expect(text).toContain("Контекст исправен");
    expect(text).toContain("Журнал изменений контекста оборван в конце");
    expect(text).toContain("загружена последняя целая версия контекста");
    expect(text).not.toContain("Сессия повреждена");
  });
});

describe("createContextInspector сводка варианта «Плотный список»", () => {
  it("readouts show duration and mains frequency from session detail", async () => {
    const mounted = await mount(
      contextResponse("context_valid"),
      detailWith({ thd_ratio: 0.037, cycles_analyzed: 620, fundamental_hz: 50.02 }),
    );

    const summary = mounted.root.querySelector(".lnt-cat-session-summary");
    expect(summary?.textContent).toContain("session-1");
    expect(summary?.textContent).toContain("12,4 с");
    expect(summary?.textContent).toContain("50,02 Гц");
    expect(mounted.root.querySelector("[data-cat-revision]")?.textContent).toContain("ревизия 2");
  });

  it("missing metrics read «недоступно» with a reason, never zero", async () => {
    const mounted = await mount(contextResponse("context_valid"), null);

    const summary = mounted.root.querySelector(".lnt-cat-session-summary");
    const unavailable = summary?.querySelectorAll(".is-unavailable") ?? [];
    expect(unavailable.length).toBe(2);
    for (const node of unavailable) {
      expect(node.textContent).toBe("недоступно");
      expect(node.getAttribute("title")).not.toBe("");
    }
    expect(summary?.textContent).not.toContain("0 с");
  });

  it("THD block compares to the limit factually and never says «норма»", async () => {
    const mounted = await mount(
      contextResponse("context_valid"),
      detailWith({ thd_ratio: 0.089, cycles_analyzed: 930 }),
    );

    const block = mounted.root.querySelector(".insp-thd");
    expect(block?.getAttribute("data-thd-compare")).toBe("above");
    expect(block?.querySelector("[data-thd-badge]")?.textContent).toBe("выше предела 8 %");
    expect(mounted.root.textContent).not.toMatch(/норм|годен/iu);
  });

  it("THD below the limit reads «ниже предела», without analysis — «нет данных»", async () => {
    const below = await mount(
      contextResponse("context_valid"),
      detailWith({ thd_ratio: 0.037, cycles_analyzed: 620 }),
    );
    expect(below.root.querySelector("[data-thd-badge]")?.textContent).toBe("ниже предела 8 %");

    const none = await mount(contextResponse("context_valid"), null);
    const block = none.root.querySelector(".insp-thd");
    expect(block?.getAttribute("data-thd-compare")).toBe("none");
    expect(block?.querySelector(".thd-value")?.textContent).toBe("недоступно");
  });

  it("entrance animation class lands on the inspector body once per session", async () => {
    const mounted = await mount(contextResponse("context_valid"));
    expect(mounted.root.querySelector(".insp-body.insp-enter")).not.toBeNull();
  });

  it("empty tags render «Тегов нет» instead of an empty chip row", async () => {
    const mounted = await mount(contextResponse("context_valid"));
    expect(mounted.root.querySelector(".tag-empty")?.textContent).toBe("Тегов нет");
  });
});

describe("createContextInspector отказ сохранения на повреждённом контексте", () => {
  it("refuses save with role=alert and never calls PUT", async () => {
    const context = contextResponse("context_invalid", ["context_cache_malformed"]);
    const client = fakeClient(context);
    const inspector = createContextInspector({ client });
    await inspector.loadSession("session-1", META);

    const save = inspector.root.querySelector<HTMLButtonElement>(".lnt-btn-primary");
    save?.click();
    await Promise.resolve();

    const alert = inspector.root.querySelector("[role='alert']");
    expect(alert?.hasAttribute("hidden")).toBe(false);
    expect(alert?.textContent).toContain("Сохранение отклонено: контекст повреждён");
    expect(alert?.textContent).toContain("context_cache_malformed");
    expect(client.updateContext).not.toHaveBeenCalled();
  });
});
