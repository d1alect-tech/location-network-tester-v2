import { describe, expect, it, vi } from "vitest";
import { createPairState } from "./pairState";

describe("createPairState", () => {
  it("fills slot A first, slot B second, and replaces B on subsequent picks", () => {
    const pair = createPairState();
    expect(pair.get()).toEqual({ a: null, b: null });

    pair.pick("s1");
    expect(pair.get()).toEqual({ a: "s1", b: null });

    pair.pick("s2");
    expect(pair.get()).toEqual({ a: "s1", b: "s2" });

    pair.pick("s3");
    expect(pair.get()).toEqual({ a: "s1", b: "s3" });
  });

  it("is a no-op when picking an already selected sessionId", () => {
    const pair = createPairState();
    pair.pick("s1");
    pair.pick("s2");

    pair.pick("s1");
    expect(pair.get()).toEqual({ a: "s1", b: "s2" });

    pair.pick("s2");
    expect(pair.get()).toEqual({ a: "s1", b: "s2" });
  });

  it("swaps A and B when both slots are filled", () => {
    const pair = createPairState();
    pair.pick("s1");
    pair.pick("s3");

    pair.swap();
    expect(pair.get()).toEqual({ a: "s3", b: "s1" });
  });

  it("is a no-op when swapping while slot B is null", () => {
    const pair = createPairState();
    pair.pick("s1");

    pair.swap();
    expect(pair.get()).toEqual({ a: "s1", b: null });
  });

  it("notifies subscribers on successful mutation and supports unsubscribing", () => {
    const pair = createPairState();
    const listener = vi.fn();
    const unsubscribe = pair.subscribe(listener);

    pair.pick("s1");
    expect(listener).toHaveBeenCalledTimes(1);

    pair.pick("s1"); // no-op pick does NOT notify
    expect(listener).toHaveBeenCalledTimes(1);

    pair.swap(); // no-op swap does NOT notify
    expect(listener).toHaveBeenCalledTimes(1);

    pair.pick("s2"); // successful pick notifies
    expect(listener).toHaveBeenCalledTimes(2);

    pair.swap(); // successful swap notifies
    expect(listener).toHaveBeenCalledTimes(3);

    unsubscribe();
    pair.pick("s3");
    expect(listener).toHaveBeenCalledTimes(3);
  });

  it("assignSlot заменяет указанный слот, не трогая второй", () => {
    const pair = createPairState();
    pair.pick("s1");
    pair.pick("s2");

    pair.assignSlot("a", "s9");
    expect(pair.get()).toEqual({ a: "s9", b: "s2" });
  });

  it("setPair атомарно задаёт оба слота и снимает arm", () => {
    const pair = createPairState();
    pair.pick("s1");
    pair.arm("b");

    pair.setPair({ a: "x", b: "y" });
    expect(pair.get()).toEqual({ a: "x", b: "y" });
    expect(pair.armed()).toBeNull();
  });

  it("arm: pick идёт в вооружённый слот, повторный arm тем же слотом снимает", () => {
    const pair = createPairState();
    pair.pick("s1");
    pair.pick("s2");
    pair.arm("a");
    expect(pair.armed()).toBe("a");

    pair.pick("s9");
    expect(pair.get()).toEqual({ a: "s9", b: "s2" });
    expect(pair.armed()).toBeNull();

    pair.arm("b");
    pair.arm("b");
    expect(pair.armed()).toBeNull();
  });

  it("назначение id из соседнего слота освобождает соседа, а не дублирует", () => {
    const pair = createPairState();
    pair.pick("s1");
    pair.pick("s2");

    pair.assignSlot("a", "s2");
    expect(pair.get()).toEqual({ a: "s2", b: null });
  });

  it("swap снимает arm", () => {
    const pair = createPairState();
    pair.pick("s1");
    pair.pick("s2");
    pair.arm("a");

    pair.swap();
    expect(pair.get()).toEqual({ a: "s2", b: "s1" });
    expect(pair.armed()).toBeNull();
  });
});
