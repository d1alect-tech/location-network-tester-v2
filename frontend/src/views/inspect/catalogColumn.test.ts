import { describe, expect, it, vi } from "vitest";
import type { CatalogSession } from "../../api/types";
import { createCatalogColumn } from "./catalogColumn";
import { createPairState } from "./pairState";

function session(id: string, createdUtc: string, label: string): CatalogSession {
  return {
    id,
    health: "ok",
    created_utc: createdUtc,
    source: "hardware",
    session_type: "capture",
    profile: "lab",
    label,
  };
}

const s1 = session("s1", "2026-08-28T10:00:00Z", "Alpha");
const s2 = session("s2", "2026-08-29T14:30:00Z", "Beta");

function fakeClient(items: CatalogSession[]) {
  return {
    catalogSessions: async () => ({ items }),
  };
}

describe("createCatalogColumn", () => {
  it("renders a row for each session after reload", async () => {
    const pair = createPairState();
    const onPick = vi.fn();
    const column = createCatalogColumn({
      client: fakeClient([s1, s2]),
      pair,
      onPick,
    });

    await column.reload();

    expect(column.root.querySelector('[data-session="s1"]')).not.toBeNull();
    expect(column.root.querySelector('[data-session="s2"]')).not.toBeNull();
  });

  it("calls onPick with the session id when a row is clicked", async () => {
    const pair = createPairState();
    const onPick = vi.fn();
    const column = createCatalogColumn({
      client: fakeClient([s1, s2]),
      pair,
      onPick,
    });
    await column.reload();

    const row = column.root.querySelector('[data-session="s1"]');
    expect(row).toBeInstanceOf(HTMLTableRowElement);
    row?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(onPick).toHaveBeenCalledWith("s1");
  });

  it("renders A and B role chips when the pair is filled", async () => {
    const pair = createPairState();
    const column = createCatalogColumn({
      client: fakeClient([s1, s2]),
      pair,
      onPick: vi.fn(),
    });
    await column.reload();

    pair.pick("s1");
    pair.pick("s2");

    expect(column.root.querySelector('[data-cat-role="a"]')?.textContent).toBe("А");
    expect(column.root.querySelector('[data-cat-role="b"]')?.textContent).toBe("Б");
  });

  it("shows the empty marker when search matches nothing", async () => {
    const column = createCatalogColumn({
      client: fakeClient([s1, s2]),
      pair: createPairState(),
      onPick: vi.fn(),
    });
    await column.reload();

    const input = column.root.querySelector("[data-cat-search]");
    expect(input).toBeInstanceOf(HTMLInputElement);
    if (!(input instanceof HTMLInputElement)) {
      return;
    }
    input.value = "zzz-no-match";
    input.dispatchEvent(new Event("input", { bubbles: true }));

    expect(column.root.querySelector("[data-cat-empty]")).not.toBeNull();
  });

  it("exposes the full session name on the label for truncated rows", async () => {
    const pair = createPairState();
    const column = createCatalogColumn({
      client: fakeClient([s1, s2]),
      pair,
      onPick: vi.fn(),
    });
    await column.reload();

    const label = column.root.querySelector('[data-session="s1"] [data-cat-label]');
    expect(label?.textContent).toBe("Alpha");
    expect(label?.getAttribute("title")).toBe("Alpha");
  });

  it("drops day groups and sets aria-sort when sorting by label", async () => {
    const column = createCatalogColumn({
      client: fakeClient([s1, s2]),
      pair: createPairState(),
      onPick: vi.fn(),
    });
    await column.reload();
    expect(column.root.querySelector("[data-cat-group]")).not.toBeNull();

    const sortLabel = column.root.querySelector('[data-cat-sort="label"]');
    expect(sortLabel).toBeInstanceOf(HTMLElement);
    sortLabel?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(column.root.querySelectorAll("[data-cat-group]")).toHaveLength(0);
    const labelTh = sortLabel?.closest("th");
    expect(labelTh?.getAttribute("aria-sort")).toBe("ascending");
  });
});
