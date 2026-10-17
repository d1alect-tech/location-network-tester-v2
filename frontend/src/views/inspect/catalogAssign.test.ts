import { describe, expect, it, vi } from "vitest";
import type { SessionHealth } from "../../api/types";
import { assignButtons } from "./catalogAssign";
import { createPairState } from "./pairState";

/** Строка рейла каталога, как её получает catalogAssign: подготовленный
 * ключ загрузки (dir-name для дублей) плюс контекст строки. Инвариант M1:
 * испускается ВСЕГДА loadKey, никогда сырой id. */
interface RailRow {
  readonly id: string;
  readonly name: string | null;
  readonly loadKey: string;
  readonly health: SessionHealth;
}

function railRow(overrides: Partial<RailRow> = {}): RailRow {
  return { id: "s1", name: "Alpha", loadKey: "s1", health: "ok", ...overrides };
}

type AssignHandle = ReturnType<typeof assignButtons>;

function buttonOf(handle: AssignHandle, slot: "a" | "b"): HTMLButtonElement {
  const found = handle.el.querySelector(`button[data-assign="${slot}"]`);
  if (!(found instanceof HTMLButtonElement)) {
    throw new Error(`assign button ${slot} not found`);
  }
  return found;
}

function click(node: Element): void {
  node.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
}

/** Ряд-хозяин: имитация tr каталога, куда рендер кладёт el кнопок. */
function mountRow(handle: AssignHandle): HTMLDivElement {
  const row = document.createElement("div");
  row.tabIndex = -1;
  row.append(handle.el);
  document.body.replaceChildren(row);
  return row;
}

function keydown(code: string): KeyboardEvent {
  return new KeyboardEvent("keydown", { code, bubbles: true, cancelable: true });
}

describe("assignButtons", () => {
  it.each([
    ["a", "Сделать базой", "А"],
    ["b", "Сделать сравнением", "Б"],
  ] as const)(
    "renders the full markup contract for button %s (type/data-assign/tabindex/aria-label/title/text)",
    (slot, ariaLabel, letter) => {
      const handle = assignButtons(railRow({ loadKey: "s1" }), null);
      const btn = buttonOf(handle, slot);

      expect(btn.getAttribute("type")).toBe("button");
      expect(btn.getAttribute("data-assign")).toBe(slot);
      expect(btn.getAttribute("tabindex")).toBe("-1");
      expect(btn.getAttribute("aria-label")).toBe(ariaLabel);
      expect(btn.getAttribute("title")).toBe("s1");
      expect(btn.textContent).toBe(letter);
      expect(btn.disabled).toBe(false);
      expect(btn.getAttribute("aria-pressed")).toBe("false");
    },
  );

  it.each([
    ["a", "А"],
    ["b", "Б"],
  ] as const)("unpaired row: clicking «%s» emits onAssign(slot, loadKey)", (slot, _letter) => {
    const handle = assignButtons(railRow({ loadKey: "s1" }), null);
    const onAssign = vi.fn();
    handle.onAssign = onAssign;

    click(buttonOf(handle, slot));

    expect(onAssign).toHaveBeenCalledTimes(1);
    expect(onAssign).toHaveBeenCalledWith(slot, "s1");
  });

  it("row in B: «А» stays enabled and emits the move; «Б» is aria-pressed and a no-op", () => {
    const handle = assignButtons(railRow({ loadKey: "s2" }), "b");
    const onAssign = vi.fn();
    handle.onAssign = onAssign;

    const btnB = buttonOf(handle, "b");
    expect(btnB.getAttribute("aria-pressed")).toBe("true");
    expect(btnB.disabled).toBe(false);
    click(btnB);
    expect(onAssign).not.toHaveBeenCalled();

    const btnA = buttonOf(handle, "a");
    expect(btnA.disabled).toBe(false);
    expect(btnA.getAttribute("aria-pressed")).toBe("false");
    click(btnA);
    expect(onAssign).toHaveBeenCalledTimes(1);
    expect(onAssign).toHaveBeenCalledWith("a", "s2");
  });

  it("row in A: «Б» stays enabled and emits the move; «А» is aria-pressed and a no-op", () => {
    const handle = assignButtons(railRow({ loadKey: "s1" }), "a");
    const onAssign = vi.fn();
    handle.onAssign = onAssign;

    const btnA = buttonOf(handle, "a");
    expect(btnA.getAttribute("aria-pressed")).toBe("true");
    expect(btnA.disabled).toBe(false);
    click(btnA);
    expect(onAssign).not.toHaveBeenCalled();

    const btnB = buttonOf(handle, "b");
    expect(btnB.disabled).toBe(false);
    expect(btnB.getAttribute("aria-pressed")).toBe("false");
    click(btnB);
    expect(onAssign).toHaveBeenCalledTimes(1);
    expect(onAssign).toHaveBeenCalledWith("b", "s1");
  });

  it.each(["corrupt_manifest", "missing_files"] as const)(
    "refused/manifest-less row (health %s) gets both buttons and both emissions",
    (health) => {
      const handle = assignButtons(railRow({ health, loadKey: "bad-1" }), null);
      const onAssign = vi.fn();
      handle.onAssign = onAssign;

      const btnA = buttonOf(handle, "a");
      const btnB = buttonOf(handle, "b");
      expect(btnA.disabled).toBe(false);
      expect(btnB.disabled).toBe(false);

      click(btnA);
      click(btnB);

      expect(onAssign).toHaveBeenNthCalledWith(1, "a", "bad-1");
      expect(onAssign).toHaveBeenNthCalledWith(2, "b", "bad-1");
    },
  );

  it("duplicate_id rows emit the dir-name loadKey, never the shared id", () => {
    const sharedId = "syn-quiet-seed6022";
    const first = assignButtons(
      railRow({
        id: sharedId,
        name: "sim-quiet-a",
        loadKey: "sim-quiet-a",
        health: "duplicate_id",
      }),
      null,
    );
    const second = assignButtons(
      railRow({
        id: sharedId,
        name: "sim-quiet-b",
        loadKey: "sim-quiet-b",
        health: "duplicate_id",
      }),
      null,
    );
    const firstEmit = vi.fn();
    const secondEmit = vi.fn();
    first.onAssign = firstEmit;
    second.onAssign = secondEmit;

    click(buttonOf(first, "a"));
    click(buttonOf(second, "a"));

    expect(firstEmit).toHaveBeenCalledWith("a", "sim-quiet-a");
    expect(secondEmit).toHaveBeenCalledWith("a", "sim-quiet-b");
    expect(firstEmit).not.toHaveBeenCalledWith("a", sharedId);
    expect(secondEmit).not.toHaveBeenCalledWith("a", sharedId);
    expect(buttonOf(first, "b").getAttribute("title")).toBe("sim-quiet-a");
    expect(buttonOf(second, "b").getAttribute("title")).toBe("sim-quiet-b");
  });

  it("button click never triggers the row's onPick (stopPropagation)", () => {
    const handle = assignButtons(railRow({ loadKey: "s1" }), null);
    const onPick = vi.fn();
    const row = mountRow(handle);
    row.addEventListener("click", onPick);

    click(buttonOf(handle, "b"));
    expect(onPick).not.toHaveBeenCalled();

    click(row); // клик по телу ряда остаётся pick'ом — контроль провода
    expect(onPick).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["KeyA", "a"],
    ["KeyB", "b"],
  ] as const)("keydown %s on the focused row emits the assign for slot %s", (code, slot) => {
    const handle = assignButtons(railRow({ loadKey: "s1" }), null);
    const onAssign = vi.fn();
    handle.onAssign = onAssign;
    const row = mountRow(handle);
    row.addEventListener("keydown", handle.handleKeydown);
    row.focus();

    row.dispatchEvent(keydown(code));

    expect(onAssign).toHaveBeenCalledTimes(1);
    expect(onAssign).toHaveBeenCalledWith(slot, "s1");
  });

  it("ignores KeyA/KeyB while typing in an input or textarea", () => {
    const handle = assignButtons(railRow({ loadKey: "s1" }), null);
    const onAssign = vi.fn();
    handle.onAssign = onAssign;
    const row = mountRow(handle);
    row.addEventListener("keydown", handle.handleKeydown);
    const input = document.createElement("input");
    const textarea = document.createElement("textarea");
    row.append(input, textarea);

    for (const field of [input, textarea]) {
      field.dispatchEvent(keydown("KeyA"));
      field.dispatchEvent(keydown("KeyB"));
    }

    expect(onAssign).not.toHaveBeenCalled();
  });

  it.each(["KeyC", "Enter", "Space"] as const)("ignores keydown code %s on the row", (code) => {
    const handle = assignButtons(railRow({ loadKey: "s1" }), null);
    const onAssign = vi.fn();
    handle.onAssign = onAssign;
    const row = mountRow(handle);
    row.addEventListener("keydown", handle.handleKeydown);

    row.dispatchEvent(keydown(code));

    expect(onAssign).not.toHaveBeenCalled();
  });

  it("invariant: assign of a row already in A moves it to B, the pair never duplicates", () => {
    const pair = createPairState();
    pair.pick("s1");
    pair.pick("s2"); // { a: "s1", b: "s2" }

    const handle = assignButtons(railRow({ id: "s1", loadKey: "s1" }), null);
    handle.onAssign = (slot, key) => pair.assignSlot(slot, key);

    // Тот же слот: pairState игнорирует назначение собой — пара не меняется.
    click(buttonOf(handle, "a"));
    expect(pair.get()).toEqual({ a: "s1", b: "s2" });

    // Соседний слот: MOVE — A освобождается, дубль невозможен.
    click(buttonOf(handle, "b"));
    expect(pair.get()).toEqual({ a: null, b: "s1" });
    const value = pair.get();
    expect(value.a).not.toBe(value.b);
  });

  it("invariant: assign of a row in B to slot A frees slot B (pairState.test.ts mirror)", () => {
    const pair = createPairState();
    pair.pick("s1");
    pair.pick("s2"); // { a: "s1", b: "s2" }

    const handle = assignButtons(railRow({ id: "s2", loadKey: "s2" }), null);
    handle.onAssign = (slot, key) => pair.assignSlot(slot, key);

    click(buttonOf(handle, "a"));

    expect(pair.get()).toEqual({ a: "s2", b: null });
    const value = pair.get();
    expect(value.a).not.toBe(value.b);
  });
});
