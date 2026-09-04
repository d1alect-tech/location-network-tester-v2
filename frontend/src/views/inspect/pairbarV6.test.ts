import { describe, expect, it, vi } from "vitest";
import type { CatalogSession } from "../../api/types";
import { createPairbar } from "./pairbarV6";

function session(label: string, id: string): CatalogSession {
  return {
    id,
    health: "ok",
    created_utc: "2026-01-15T10:00:00Z",
    source: null,
    session_type: "capture",
    profile: null,
    label,
  };
}

describe("createPairbar", () => {
  it("renders slot A as База and slot B as Сравнение", () => {
    const { root } = createPairbar({ onSwap: () => {} });
    expect(root.querySelector('[data-pair="a"]')?.textContent).toContain("База");
    expect(root.querySelector('[data-pair="b"]')?.textContent).toContain("Сравнение");
  });

  it("setPair writes session labels into slot names", () => {
    const bar = createPairbar({ onSwap: () => {} });
    bar.setPair(session("стенд-А", "id-a"), session("стенд-Б", "id-b"));
    expect(bar.root.querySelector('[data-pair="a"] .pair-name')?.textContent).toBe("стенд-А");
    expect(bar.root.querySelector('[data-pair="b"] .pair-name')?.textContent).toBe("стенд-Б");
  });

  it("clicking the swap control calls onSwap once", () => {
    const onSwap = vi.fn();
    const { root } = createPairbar({ onSwap });
    root.querySelector<HTMLButtonElement>("[data-pair-swap]")?.click();
    expect(onSwap).toHaveBeenCalledTimes(1);
  });

  it("setPair(null, null) shows em dash names and does not throw", () => {
    const bar = createPairbar({ onSwap: () => {} });
    expect(() => bar.setPair(null, null)).not.toThrow();
    expect(bar.root.querySelector('[data-pair="a"] .pair-name')?.textContent).toBe("—");
    expect(bar.root.querySelector('[data-pair="b"] .pair-name')?.textContent).toBe("—");
  });
});
