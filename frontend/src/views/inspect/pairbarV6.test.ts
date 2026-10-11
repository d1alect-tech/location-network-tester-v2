import { describe, expect, it, vi } from "vitest";
import { isCatalogPage } from "../../api/guards";
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

  it("U3/U4: бейджи всегда на месте", () => {
    const { root } = createPairbar({ onSwap: () => {} });
    expect(root.querySelector('[data-pair-delta="mean"]')?.textContent).toBe("Δср —");
    expect(root.querySelector('[data-pair-delta="max"]')?.textContent).toBe("Δmax —");
  });

  it("U3: setDelta пишет сводку в бейджи, null гасит в прочерки", () => {
    const bar = createPairbar({ onSwap: () => {} });
    bar.setDelta({ bins: 2, meanDb: 5, maxAbsDb: 10 });
    expect(bar.root.querySelector('[data-pair-delta="mean"]')?.textContent).toBe("Δср +5,0 дБ");
    expect(bar.root.querySelector('[data-pair-delta="max"]')?.textContent).toBe("Δmax +10,0 дБ");
    bar.setDelta(null);
    expect(bar.root.querySelector('[data-pair-delta="mean"]')?.textContent).toBe("Δср —");
  });

  it("F-5: провод каталога без created_utc не роняет слот (exclude_none)", () => {
    // Бэкенд отдаёт response_model_exclude_none: null-поля отсутствуют, guard
    // isCatalogSession пропускает объект без created_utc (f3 F-5, pageerror).
    const page: unknown = {
      items: [{ id: "f3-longid", health: "corrupt_manifest" }],
      next_cursor: null,
    };
    expect(isCatalogPage(page)).toBe(true);
    const bar = createPairbar({ onSwap: () => {} });
    let slotName: string | null | undefined;
    let slotMeta: string | null | undefined;
    if (isCatalogPage(page)) {
      const wire = page.items[0] ?? null;
      expect(() => bar.setPair(wire, null)).not.toThrow();
      slotName = bar.root.querySelector('[data-pair="a"] .pair-name')?.textContent;
      slotMeta = bar.root.querySelector('[data-pair="a"] .pair-meta')?.textContent;
    }
    expect(slotName).toBe("f3-longid");
    expect(slotMeta).toBe("— · —");
  });

  it("F-5: created_utc undefined и нестроковый дают прочерк, а не TypeError", () => {
    const base = session("стенд-А", "id-a");
    const missing = { ...base, created_utc: undefined } as unknown as CatalogSession;
    const nonString = { ...base, created_utc: 42 } as unknown as CatalogSession;
    for (const broken of [missing, nonString]) {
      const bar = createPairbar({ onSwap: () => {} });
      expect(() => bar.setPair(broken, null)).not.toThrow();
      expect(bar.root.querySelector('[data-pair="a"] .pair-name')?.textContent).toBe("стенд-А");
      expect(bar.root.querySelector('[data-pair="a"] .pair-meta')?.textContent).toBe("capture · —");
    }
  });

  it("setPair(null, null) shows em dash names and does not throw", () => {
    const bar = createPairbar({ onSwap: () => {} });
    expect(() => bar.setPair(null, null)).not.toThrow();
    expect(bar.root.querySelector('[data-pair="a"] .pair-name')?.textContent).toBe("—");
    expect(bar.root.querySelector('[data-pair="b"] .pair-name')?.textContent).toBe("—");
  });
});
