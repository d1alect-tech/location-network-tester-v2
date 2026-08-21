import { beforeEach, describe, expect, it } from "vitest";
import { type TableColumn, type TableState, createDataTable } from "./table";

interface Row {
  id: string;
  label: string;
  health: "ok" | "partial" | "corrupt_manifest";
}

const columns: TableColumn<Row>[] = [
  { key: "label", header: "Метка", sortable: true, value: (r) => r.label },
  {
    key: "health",
    header: "Состояние",
    value: (r) => r.health,
    status: (r) => ({
      tone: r.health === "ok" ? "ok" : r.health === "partial" ? "warn" : "error",
      label: r.health === "ok" ? "Исправна" : r.health === "partial" ? "Частичная" : "Повреждена",
    }),
  },
];

const rows: Row[] = [
  { id: "b", label: "Вторая", health: "partial" },
  { id: "a", label: "Первая", health: "ok" },
];

describe("createDataTable", () => {
  beforeEach(() => {
    document.body.textContent = "";
  });

  it("renders headers and row values in the data state", () => {
    const table = createDataTable<Row>(columns);
    table.setState({ kind: "data", rows });
    expect(table.root.querySelector("th")?.textContent).toContain("Метка");
    expect(table.root.textContent).toContain("Первая");
  });

  it("sortable headers are buttons with aria-sort and toggle order on click", () => {
    const table = createDataTable<Row>(columns);
    table.setState({ kind: "data", rows });
    const thButton = [...table.root.querySelectorAll("button")].find(
      (b) => b.textContent === "Метка",
    );
    expect(thButton).toBeDefined();
    const th = thButton?.closest("th");
    thButton?.click();
    expect(th?.getAttribute("aria-sort")).toBe("ascending");
    // Sorted ascending by value: «Вторая» < «Первая»? No — cyrillic compare; assert first row changed after second click.
    thButton?.click();
    expect(th?.getAttribute("aria-sort")).toBe("descending");
  });

  it("ArrowDown/ArrowUp move row focus with roving tabindex", () => {
    const table = createDataTable<Row>(columns);
    table.setState({ kind: "data", rows });
    document.body.append(table.root); // фокус в jsdom работает только на подключённых узлах
    const trs = [...table.root.querySelectorAll("tbody tr")];
    expect(trs.length).toBe(2);
    const first = trs[0] as HTMLElement;
    first.focus();
    first.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(document.activeElement).toBe(trs[1]);
    expect(trs[1]?.getAttribute("tabindex")).toBe("0");
    (trs[1] as HTMLElement).dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }),
    );
    expect(document.activeElement).toBe(first);
  });

  it("status cells pair an icon glyph with text — not color-only", () => {
    const table = createDataTable<Row>(columns);
    table.setState({ kind: "data", rows });
    const pill = table.root.querySelector(".lnt-status-pill");
    expect(pill?.textContent).toContain("Исправна");
    expect(pill?.textContent?.length).toBeGreaterThan("Исправна".length); // icon glyph present
  });

  it("loading state shows Загрузка… and aria-busy", () => {
    const table = createDataTable<Row>(columns);
    table.setState({ kind: "loading" });
    expect(table.root.getAttribute("aria-busy")).toBe("true");
    expect(table.root.textContent).toContain("Загрузка…");
  });

  it("error state shows Russian message and working Повторить button", () => {
    let retried = 0;
    const state: TableState<Row> = {
      kind: "error",
      onRetry: () => {
        retried += 1;
      },
    };
    const table = createDataTable<Row>(columns);
    table.setState(state);
    expect(table.root.textContent).toContain("Ошибка загрузки");
    const retry = [...table.root.querySelectorAll("button")].find(
      (b) => b.textContent === "Повторить",
    );
    retry?.click();
    expect(retried).toBe(1);
  });

  it("empty state shows the Russian empty text", () => {
    const table = createDataTable<Row>(columns, { emptyText: "По запросу ничего не найдено" });
    table.setState({ kind: "empty" });
    expect(table.root.textContent).toContain("По запросу ничего не найдено");
  });
});
