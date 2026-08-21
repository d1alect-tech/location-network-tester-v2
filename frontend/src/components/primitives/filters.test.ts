import { beforeEach, describe, expect, it } from "vitest";
import { RouteStore } from "../../state/routeState";
import { createFilterBar } from "./filters";

describe("createFilterBar", () => {
  beforeEach(() => {
    document.body.textContent = "";
    window.location.hash = "#/catalog";
  });

  it("builds labeled text/select/date controls bound to route params", () => {
    const store = new RouteStore(window);
    const bar = createFilterBar(store, [
      { kind: "text", param: "label", label: "Метка" },
      {
        kind: "select",
        param: "health",
        label: "Состояние",
        options: [
          { value: "ok", label: "Исправна" },
          { value: "partial", label: "Частичная" },
        ],
      },
      { kind: "dateRange", fromParam: "created_from", toParam: "created_to", label: "Дата" },
    ]);
    const labels = [...bar.querySelectorAll("label")].map((l) => l.textContent);
    expect(labels).toContain("Метка");
    expect(labels).toContain("Состояние");
    // Every control is programmatically associated with a label.
    for (const control of bar.querySelectorAll("input, select")) {
      const id = control.id;
      expect(id).toBeTruthy();
      expect(bar.querySelector(`label[for="${id}"]`)).not.toBeNull();
    }
    expect(bar.querySelector('input[type="date"]')).not.toBeNull();
  });

  it("typing into the text input writes the route param", () => {
    const store = new RouteStore(window);
    store.syncFromUrl();
    const bar = createFilterBar(store, [{ kind: "text", param: "label", label: "Метка" }]);
    const input = bar.querySelector("input") as HTMLInputElement;
    input.value = "кухня";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    store.syncFromUrl();
    expect(store.get().params.label).toBe("кухня");
  });

  it("select change and date range write params; reset clears them", () => {
    const store = new RouteStore(window);
    store.syncFromUrl();
    const bar = createFilterBar(store, [
      {
        kind: "select",
        param: "health",
        label: "Состояние",
        options: [{ value: "ok", label: "Исправна" }],
      },
      { kind: "dateRange", fromParam: "from", toParam: "to", label: "Дата" },
    ]);
    const select = bar.querySelector("select") as HTMLSelectElement;
    select.value = "ok";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    const [from, to] = [...bar.querySelectorAll<HTMLInputElement>('input[type="date"]')];
    if (!from || !to) throw new Error("date inputs missing");
    from.value = "2026-08-01";
    from.dispatchEvent(new Event("change", { bubbles: true }));
    to.value = "2026-08-21";
    to.dispatchEvent(new Event("change", { bubbles: true }));
    store.syncFromUrl();
    expect(store.get().params).toMatchObject({
      health: "ok",
      from: "2026-08-01",
      to: "2026-08-21",
    });

    const reset = [...bar.querySelectorAll("button")].find((b) => b.textContent === "Сбросить");
    reset?.click();
    store.syncFromUrl();
    expect(store.get().params).toEqual({});
  });

  it("seeds initial values from current route params (reload-safe)", () => {
    window.location.hash = "#/catalog?label=кит";
    const store = new RouteStore(window);
    const bar = createFilterBar(store, [{ kind: "text", param: "label", label: "Метка" }]);
    const input = bar.querySelector("input") as HTMLInputElement;
    expect(input.value).toBe("кит");
  });
});
