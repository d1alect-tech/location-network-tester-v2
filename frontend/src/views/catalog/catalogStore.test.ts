import { describe, expect, it } from "vitest";
import type { CatalogPage, CatalogSession } from "../../api/types";
import { CatalogStore } from "./catalogStore";

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function session(id: string): CatalogSession {
  return {
    id,
    health: "ok",
    created_utc: "2026-08-01T00:00:00Z",
    source: null,
    session_type: "capture",
    profile: null,
    label: null,
  };
}

function page(items: string[], nextCursor: string | null = null): CatalogPage {
  return {
    items: items.map(session),
    next_cursor: nextCursor,
  };
}

describe("CatalogStore", () => {
  it("accumulates pages on loadMore and reports hasMore", async () => {
    const gates = [deferred<CatalogPage>(), deferred<CatalogPage>()];
    const calls: Array<{ cursor: string | null; signal: AbortSignal }> = [];
    const store = new CatalogStore((query, signal) => {
      calls.push({ cursor: query.cursor ?? null, signal });
      const gate = gates[calls.length - 1];
      if (!gate) throw new Error("unexpected extra call");
      return gate.promise;
    });

    const first = store.applyQuery({});
    gates[0]?.resolve(page(["a", "b"], "cursor-1"));
    await first;
    expect(store.get().items.map((item) => item.id)).toEqual(["a", "b"]);
    expect(store.get().nextCursor).toBe("cursor-1");

    const second = store.loadMore();
    gates[1]?.resolve(page(["c"]));
    await second;
    expect(store.get().items.map((item) => item.id)).toEqual(["a", "b", "c"]);
    expect(store.get().nextCursor).toBeNull();
    expect(calls[1]?.cursor).toBe("cursor-1");
  });

  it("reversed completion order keeps the current query result intact", async () => {
    // Паттерн resource.test.ts: медленный ответ «А» завершается ПОСЛЕ быстрого «Б».
    const slowA = deferred<CatalogPage>();
    const fastB = deferred<CatalogPage>();
    const signals: AbortSignal[] = [];
    const store = new CatalogStore((_query, signal) => {
      signals.push(signal);
      const label = _query.label ?? "";
      if (label === "") return slowA.promise;
      return fastB.promise;
    });

    const runSlow = store.applyQuery({});
    const runFast = store.applyQuery({ label: "стенд" });
    // Предыдущий запрос оборван.
    expect(signals[0]?.aborted).toBe(true);
    expect(signals[1]?.aborted).toBe(false);

    fastB.resolve(page(["b-1", "b-2"]));
    await runFast;
    slowA.resolve(page(["stale-a"]));
    await runSlow;

    const state = store.get();
    expect(state.items.map((item) => item.id)).toEqual(["b-1", "b-2"]);
    expect(state.status).toBe("ready");
  });

  it("loadMore from a superseded generation is ignored entirely", async () => {
    const initialGate = deferred<CatalogPage>();
    const staleMoreGate = deferred<CatalogPage>();
    const freshGate = deferred<CatalogPage>();
    const gates = [initialGate, staleMoreGate, freshGate];
    let call = 0;
    const store = new CatalogStore(() => {
      const gate = gates[call];
      call += 1;
      if (!gate) throw new Error("unexpected call");
      return gate.promise;
    });

    const runInitial = store.applyQuery({});
    initialGate.resolve(page(["a"], "c1"));
    await runInitial;

    const runMore = store.loadMore();
    // Пока догрузка летит — пользователь меняет фильтры (новое поколение).
    const runFresh = store.applyQuery({ tag: "самошум" });
    staleMoreGate.resolve(page(["STALE-MORE"], "c9"));
    freshGate.resolve(page(["fresh-1"]));

    await Promise.all([runMore.catch(() => undefined), runFresh]);
    expect(store.get().items.map((item) => item.id)).toEqual(["fresh-1"]);
    expect(store.get().loadingMore).toBe(false);
  });

  it("network failure surfaces a Russian error and retry re-runs last query", async () => {
    let fail = true;
    const store = new CatalogStore(async () => {
      if (fail) throw new TypeError("fetch failed");
      return page(["ok-1"]);
    });
    await store.applyQuery({});
    expect(store.get().status).toBe("error");
    expect(store.get().error).toContain("Не удалось загрузить каталог");

    fail = false;
    await store.retry();
    expect(store.get().status).toBe("ready");
    expect(store.get().items[0]?.id).toBe("ok-1");
  });
});
