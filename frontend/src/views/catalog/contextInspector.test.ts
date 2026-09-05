import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import { createContextInspector } from "./contextInspector";

function fakeClient(): LntApiClient {
  return {
    context: vi.fn(),
    updateContext: vi.fn(),
    ensureReady: vi.fn(async () => undefined),
  } as unknown as LntApiClient;
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
