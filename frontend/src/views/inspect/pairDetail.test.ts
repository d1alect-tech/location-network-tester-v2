import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import type { SessionDetailPayload } from "../../api/types-plots";
import { createPairDetail } from "./pairDetail";

/** Given / When / Then: один fetch detail на пару инспекции (B2). */

function detail(name: string): SessionDetailPayload {
  return {
    name,
    manifest: {},
    analysis: { needle: { cycles_analyzed: 120 } },
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

describe("createPairDetail", () => {
  it("serves one fetch to three consumers of the same pair", async () => {
    // Given
    const fetchDetail = vi.fn(async (name: string) => detail(name));
    const store = createPairDetail(fetchDetail);

    // When: спектр, лента и analysis-v2 читают базу одной пары.
    const [first, second, third] = await Promise.all([
      store.load("sess-a"),
      store.load("sess-a"),
      store.load("sess-a"),
    ]);

    // Then
    expect(fetchDetail).toHaveBeenCalledTimes(1);
    expect(first).toBe(second);
    expect(second).toBe(third);
    expect(first.name).toBe("sess-a");
  });

  it("fetches again after reset: a new pair is a new generation", async () => {
    // Given
    const fetchDetail = vi.fn(async (name: string) => detail(name));
    const store = createPairDetail(fetchDetail);
    await store.load("sess-a");

    // When
    store.reset();
    await store.load("sess-a");

    // Then
    expect(fetchDetail).toHaveBeenCalledTimes(2);
  });

  it("aborts the shared request on reset so a stale pair cannot land", async () => {
    // Given
    let seen: AbortSignal | undefined;
    const store = createPairDetail(async (_name, options) => {
      seen = options?.signal;
      return detail("sess-a");
    });
    await store.load("sess-a");

    // When
    store.reset();

    // Then
    expect(seen?.aborted).toBe(true);
  });

  it("rejects the waiting consumer on its own signal without killing the pair", async () => {
    // Given
    const fetchDetail = vi.fn(async (name: string) => detail(name));
    const store = createPairDetail(fetchDetail);
    const consumer = new AbortController();
    const waiting = store.load("sess-a", { signal: consumer.signal });
    consumer.abort();

    // When / Then: ожидание потребителя сорвано, общий запрос жив.
    await expect(waiting).rejects.toMatchObject({ name: "AbortError" });
    await expect(store.load("sess-a")).resolves.toMatchObject({ name: "sess-a" });
    expect(fetchDetail).toHaveBeenCalledTimes(1);
  });

  it("keeps a failing detail shared: every consumer sees the same error", async () => {
    // Given
    const fetchDetail = vi.fn(async () => {
      throw new ApiError("http", { status: 500 });
    });
    const store = createPairDetail(fetchDetail);

    // When
    const first = store.load("sess-a");
    const second = store.load("sess-a");

    // Then
    await expect(first).rejects.toBeInstanceOf(ApiError);
    await expect(second).rejects.toBeInstanceOf(ApiError);
    expect(fetchDetail).toHaveBeenCalledTimes(1);
  });

  it("caches per session name: base and compare stay separate entries", async () => {
    // Given
    const fetchDetail = vi.fn(async (name: string) => detail(name));
    const store = createPairDetail(fetchDetail);

    // When
    await Promise.all([store.load("sess-a"), store.load("sess-b"), store.load("sess-a")]);

    // Then
    expect(fetchDetail).toHaveBeenCalledTimes(2);
  });

  it("rejects after dispose: teardown never starts a request", async () => {
    // Given
    const fetchDetail = vi.fn(async (name: string) => detail(name));
    const store = createPairDetail(fetchDetail);

    // When
    store.dispose();

    // Then
    await expect(store.load("sess-a")).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchDetail).not.toHaveBeenCalled();
  });
});
