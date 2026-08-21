import { describe, expect, it } from "vitest";
import { ApiError } from "../api/errors";
import { createMutation, createResourceLoader } from "./resource";

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

describe("createResourceLoader", () => {
  it("transitions idle → loading → ready", async () => {
    const gate = deferred<string>();
    const loader = createResourceLoader<string>(() => gate.promise);
    expect(loader.get().kind).toBe("idle");
    const done = loader.load("a");
    expect(loader.get()).toMatchObject({ kind: "loading", key: "a" });
    gate.resolve("value-a");
    await done;
    expect(loader.get()).toEqual({ kind: "ready", key: "a", value: "value-a" });
  });

  it("out-of-order responses never overwrite the current selection", async () => {
    const slow = deferred<string>();
    const fast = deferred<string>();
    const signals: AbortSignal[] = [];
    const loader = createResourceLoader<string>((key, signal) => {
      signals.push(signal);
      return key === "slow-session" ? slow.promise : fast.promise;
    });

    const slowRun = loader.load("slow-session");
    const fastRun = loader.load("fast-session");
    // The superseded request is aborted.
    expect(signals[0]?.aborted).toBe(true);
    expect(signals[1]?.aborted).toBe(false);

    fast.resolve("fast-data");
    await fastRun;
    expect(loader.get()).toEqual({ kind: "ready", key: "fast-session", value: "fast-data" });

    // Late resolution of the stale request must be ignored entirely.
    slow.resolve("stale-data");
    await slowRun;
    expect(loader.get()).toEqual({ kind: "ready", key: "fast-session", value: "fast-data" });
  });

  // Todo 39: расширенный сценарий гонки — три загрузки, обратный порядок
  // завершения (C → A → B), финальное состояние соответствует последнему
  // ЗАПУЩЕННОМУ ключу, а не последнему завершившемуся ответу.
  it("reversed completion order across three loads keeps the current selection", async () => {
    const gates: Array<ReturnType<typeof deferred<string>>> = [
      deferred<string>(),
      deferred<string>(),
      deferred<string>(),
    ];
    const keys: string[] = [];
    const signals: AbortSignal[] = [];
    const loader = createResourceLoader<string>((key, signal) => {
      keys.push(key);
      signals.push(signal);
      const gate = gates[keys.length - 1];
      if (!gate) throw new Error("unexpected load");
      return gate.promise;
    });

    const runA = loader.load("a");
    const runB = loader.load("b");
    const runC = loader.load("c");
    expect(signals[0]?.aborted).toBe(true);
    expect(signals[1]?.aborted).toBe(true);
    expect(signals[2]?.aborted).toBe(false);

    gates[2]?.resolve("c-data");
    await runC;
    gates[0]?.resolve("a-data");
    await runA;
    gates[1]?.resolve("b-data");
    await runB;

    expect(loader.get()).toEqual({ kind: "ready", key: "c", value: "c-data" });
  });

  it("late failure of a superseded request does not clobber ready state", async () => {
    const slow = deferred<string>();
    const fast = deferred<string>();
    const loader = createResourceLoader<string>((key) =>
      key === "a" ? slow.promise : fast.promise,
    );
    const slowRun = loader.load("a");
    const fastRun = loader.load("b");
    fast.resolve("b-data");
    await fastRun;
    slow.reject(new Error("too late"));
    await slowRun;
    expect(loader.get().kind).toBe("ready");
  });

  it("error state carries a Russian message and retry() re-runs the last key", async () => {
    let fail = true;
    const loader = createResourceLoader<string>(async () => {
      if (fail) throw new TypeError("fetch failed");
      return "recovered";
    });
    await loader.load("s1");
    const state = loader.get();
    if (state.kind !== "error") throw new Error(`expected error state, got ${state.kind}`);
    expect(state.error).toBeInstanceOf(ApiError);
    expect(state.error.message).toContain("связ");

    fail = false;
    await loader.retry();
    expect(loader.get()).toEqual({ kind: "ready", key: "s1", value: "recovered" });
  });

  it("retry without a previous load stays idle", async () => {
    const loader = createResourceLoader<string>(async () => "x");
    await loader.retry();
    expect(loader.get().kind).toBe("idle");
  });
});

describe("createMutation", () => {
  it("exposes pending → success around the request", async () => {
    const gate = deferred<string>();
    const mutation = createMutation<string, string>(() => gate.promise);
    const run = mutation.run("input");
    expect(mutation.get().kind).toBe("pending");
    gate.resolve("ok");
    await run;
    expect(mutation.get()).toEqual({ kind: "success", value: "ok" });
  });

  it("exposes failure with a normalized ApiError", async () => {
    const mutation = createMutation<string, string>(async () => {
      throw new TypeError("fetch failed");
    });
    await mutation.run("input").catch(() => undefined);
    const state = mutation.get();
    expect(state.kind).toBe("failure");
    if (state.kind === "failure") {
      expect(state.error).toBeInstanceOf(ApiError);
      expect(state.error.message).toContain("связ");
    }
  });

  it("reset returns to idle", async () => {
    const mutation = createMutation<string, string>(async () => "done");
    await mutation.run("x");
    mutation.reset();
    expect(mutation.get().kind).toBe("idle");
  });
});
