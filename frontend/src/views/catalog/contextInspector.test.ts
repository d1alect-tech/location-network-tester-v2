import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import type { ContextResponse } from "../../api/types";
import { createContextInspector } from "./contextInspector";

function fakeClient(context?: ContextResponse): LntApiClient {
  return {
    context: vi.fn(async () => {
      if (!context) throw new Error("context fixture missing");
      return context;
    }),
    updateContext: vi.fn(),
    ensureReady: vi.fn(async () => undefined),
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
    const inspector = createContextInspector({
      client: fakeClient(contextResponse("context_valid")),
    });

    await inspector.loadSession("session-1");

    expect(inspector.root.querySelector(".lnt-cat-session-summary")?.textContent).toContain(
      "Состояние контекста: Исправен",
    );
    expect(inspector.root.querySelector(".lnt-cat-recovery")).toBeNull();
  });

  it("explains an absent context without calling the session unusable", async () => {
    const inspector = createContextInspector({
      client: fakeClient(contextResponse("context_absent")),
    });

    await inspector.loadSession("session-1");

    const text = inspector.root.querySelector(".lnt-cat-recovery")?.textContent ?? "";
    expect(text).toContain("Контекст сессии ещё не сохранён");
    expect(text).toContain("можно заполнить и сохранить");
    expect(text).not.toContain("Сессия повреждена");
    expect(text).not.toContain("недоступна для анализа");
  });

  it("limits an invalid-context notice to context metadata", async () => {
    const inspector = createContextInspector({
      client: fakeClient(contextResponse("context_invalid", ["context_cache_malformed"])),
    });

    await inspector.loadSession("session-1");

    const text = inspector.root.querySelector(".lnt-cat-recovery")?.textContent ?? "";
    expect(text).toContain("Контекст сессии повреждён");
    expect(text).toContain("Проблема относится только к контексту");
    expect(text).toContain("Не удалось прочитать context.json");
    expect(text).not.toContain("Запись недоступна для анализа");
  });

  it("keeps a torn-tail warning on an otherwise valid context", async () => {
    const inspector = createContextInspector({
      client: fakeClient(contextResponse("context_valid", ["context_events_torn_tail"])),
    });

    await inspector.loadSession("session-1");

    const text = inspector.root.querySelector(".lnt-cat-recovery")?.textContent ?? "";
    expect(text).toContain("Контекст исправен");
    expect(text).toContain("Журнал изменений контекста оборван в конце");
    expect(text).toContain("загружена последняя целая версия контекста");
    expect(text).not.toContain("Сессия повреждена");
  });
});
