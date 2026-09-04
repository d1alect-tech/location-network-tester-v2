import axe from "axe-core";
import { beforeEach, describe, expect, it } from "vitest";
import { openDialog } from "./dialog";
import { createField } from "./forms";
import { type TableColumn, createDataTable } from "./table";

interface Row {
  id: string;
  label: string;
  health: "ok" | "warn" | "error";
}

const columns: TableColumn<Row>[] = [
  {
    key: "label",
    header: "Метка",
    sortable: true,
    value: (r) => r.label,
    status: (r) =>
      r.health === "ok"
        ? { tone: "ok", label: "Готов" }
        : r.health === "warn"
          ? { tone: "warn", label: "Деградация" }
          : { tone: "error", label: "Авария" },
  },
];

/** axe-проверка собранного примитива (jsdom: контраст недоступен — исключён). */
describe("axe accessibility", () => {
  let fixture: HTMLElement;

  beforeEach(() => {
    document.body.textContent = "";
    fixture = document.createElement("div");
    document.body.append(fixture);
  });

  async function expectNoViolations(): Promise<void> {
    const results = await axe.run(fixture, {
      resultTypes: ["violations"],
      rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
    });
    const messages = results.violations.map(
      (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
    );
    expect(messages).toEqual([]);
  }

  it("form field with error has no violations", async () => {
    const control = document.createElement("input");
    control.type = "text";
    const field = createField({ label: "Метка сессии", control });
    field.setError("Значение не может быть пустым");
    fixture.append(field.root);
    await expectNoViolations();
  });

  it("data table in data state has no violations", async () => {
    const table = createDataTable<Row>(columns);
    table.setState({ kind: "data", rows: [{ id: "a", label: "Первая", health: "ok" }] });
    fixture.append(table.root);
    await expectNoViolations();
  });

  it("status pills with warn/error tones have no violations", async () => {
    const table = createDataTable<Row>(columns);
    table.setState({
      kind: "data",
      rows: [
        { id: "a", label: "Первая", health: "warn" },
        { id: "b", label: "Вторая", health: "error" },
      ],
    });
    fixture.append(table.root);
    expect(fixture.querySelector(".lnt-tone-warn")?.textContent).toContain("Деградация");
    expect(fixture.querySelector(".lnt-tone-error")?.textContent).toContain("Авария");
    await expectNoViolations();
  });

  it("open dialog has no violations", async () => {
    const invoker = document.createElement("button");
    invoker.textContent = "Открыть";
    fixture.append(invoker);
    const handle = openDialog({
      title: "Подтверждение",
      content: Object.assign(document.createElement("p"), { textContent: "Текст" }),
      actions: [{ label: "Отмена", onClick: () => undefined }],
    });
    fixture.append(handle.root);
    try {
      await expectNoViolations();
    } finally {
      handle.close();
    }
  });
});
