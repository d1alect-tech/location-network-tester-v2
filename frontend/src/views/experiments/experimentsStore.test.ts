import { beforeEach, describe, expect, it } from "vitest";
import { LntApiClient } from "../../api/client";
import type { LntApiClient as LntApiClientType } from "../../api/client";
import { ApiError } from "../../api/errors";
import { ExperimentsStore, mutationErrorText } from "./experimentsStore";

/** Гонко-защита и разбор ошибок хранилища экспериментов (todo 43):
 * расширяет паттерны src/state/resource.test.ts на доменный контур. */

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function fakeResearch(
  overrides: Partial<Record<string, unknown>> = {},
): LntApiClientType["research"] {
  const base = {
    experiments: () => Promise.resolve({ items: [], next_cursor: null }),
    experiment: () => Promise.resolve({ experiment_id: "x" }),
    createExperiment: () => Promise.resolve({ experiment_id: "x" }),
    updateExperiment: () => Promise.resolve({ experiment_id: "x" }),
    revisions: () => Promise.resolve({ items: [], next_cursor: null }),
    members: () => Promise.resolve({ items: [], next_cursor: null }),
    steps: () => Promise.resolve({ items: [], next_cursor: null }),
    startRun: () => Promise.reject(new Error("not used")),
    runStatus: () => Promise.reject(new Error("not used")),
    confirmRun: () => Promise.reject(new Error("not used")),
    resumeRun: () => Promise.reject(new Error("not used")),
    cancelRun: () => Promise.reject(new Error("not used")),
    hypotheses: () => Promise.resolve({ items: [], next_cursor: null }),
    hypothesis: () => Promise.reject(new Error("not used")),
    createHypothesis: () => Promise.reject(new Error("not used")),
    updateHypothesis: () => Promise.reject(new Error("not used")),
    queryTrends: () => Promise.reject(new Error("not used")),
    comparabilityCheck: () => Promise.reject(new Error("not used")),
  };
  return { ...base, ...overrides } as unknown as LntApiClient["research"];
}

function storeOf(research: LntApiClientType["research"]): ExperimentsStore {
  return new ExperimentsStore({ client: { research } as unknown as LntApiClient });
}

describe("ExperimentsStore race guards (todo 43)", () => {
  it("stale detail response never overwrites the currently selected experiment", async () => {
    const gates = new Map<string, Deferred<unknown>>();
    const store = storeOf(
      fakeResearch({
        experiment: (id: string) =>
          (gates.get(id) as Deferred<unknown> | undefined)?.promise ?? Promise.resolve({}),
      }),
    );
    // Перехватываем members/steps тоже через deferred — упрощаем: они резолвятся сразу.
    void store;

    // Загружаем медленный эксперимент A, затем быстрый B.
    gates.set("slow", deferred());
    const slowRun = store.detail.load("slow");
    expect(store.detail.get()).toMatchObject({ kind: "loading", key: "slow" });
    const fastDone = store.detail.load("fast");
    await fastDone;
    // Медленный ответ приходит позже и обязан быть отброшен.
    const gateSlow = gates.get("slow");
    if (!gateSlow) throw new Error("missing slow gate");
    gateSlow.resolve({
      experiment: { experiment_id: "slow", revision: 1 },
      members: [],
      steps: [],
    });
    await slowRun;
    expect(store.detail.get().kind).toBe("ready");
    const finalState = store.detail.get();
    if (finalState.kind === "ready") {
      expect(finalState.key).toBe("fast");
    }
  });

  it("malformed experiment payload raises a typed ApiError('parse') instead of silent acceptance", async () => {
    // Реальный клиент + подменённый fetch: конверт-проверки client-research
    // должны отвергнуть payload без experiment_id.
    const fetchImpl = (async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/experiments/broken")
        ? { unexpected: true }
        : { items: [], next_cursor: null };
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }) as unknown as Response;
    }) as unknown as typeof fetch;
    const store = new ExperimentsStore({ client: new LntApiClient(fetchImpl) });
    await store.detail.load("broken");
    const state = store.detail.get();
    expect(state.kind).toBe("error");
    if (state.kind === "error") {
      expect(state.error).toBeInstanceOf(ApiError);
      expect(state.error.kind).toBe("parse");
    }
  });
});

describe("member inclusion via store (todo 43)", () => {
  let store: ExperimentsStore;
  beforeEach(() => {
    store = storeOf(fakeResearch());
  });

  it("exclude → undo restores the member while keeping the audit trail", () => {
    store.inclusion("exp1", "sess-1");
    store.excludeMember("exp1", "sess-1", "qc_clipping");
    const undone = store.undoMember("exp1", "sess-1", "оператор отменил исключение");
    // proposed(1) → excluded(2) → компенсация(3): аудит не переписывается.
    expect(undone.history).toHaveLength(3);
    expect(undone.history[2]?.undo_of_revision).toBe(2);
    // Возврат к состоянию ДО исключения (proposed), как в state.py undo().
    expect(undone.history[2]?.state).toBe("proposed");
    expect(undone.history[1]?.reason).toBe("qc_clipping");
  });

  it("inclusion journals are scoped per experiment", () => {
    store.excludeMember("expA", "s1", "r1");
    const other = store.inclusion("expB", "s1");
    expect(other.history).toHaveLength(1);
    expect(other.history[0]?.state).toBe("proposed");
  });

  it("conflict mutations surface an explicit Russian conflict message", () => {
    const text = mutationErrorText(
      new ApiError("conflict", { status: 409, code: "experiment_revision_conflict" }),
    );
    expect(text).toContain("Конфликт версий");
    expect(text).toContain("experiment_revision_conflict");
  });
});
