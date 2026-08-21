import "./style.css";
import { createChartShell } from "./components/primitives/chartshell";
import { openDialog } from "./components/primitives/dialog";
import { el } from "./components/primitives/dom";
import { createFilterBar } from "./components/primitives/filters";
import { createField, setFormPending } from "./components/primitives/forms";
import { createSplitPane } from "./components/primitives/splitpane";
import { announcePolite, createJobProgress } from "./components/primitives/status";
import { type TableColumn, createDataTable } from "./components/primitives/table";
import { RouteStore } from "./state/routeState";

interface DemoRow {
  id: string;
  label: string;
  health: "ok" | "partial" | "corrupt_manifest";
}

const ROW_COLUMNS: TableColumn<DemoRow>[] = [
  { key: "label", header: "Метка", sortable: true, value: (row) => row.label },
  {
    key: "health",
    header: "Состояние",
    value: (row) => row.health,
    status: (row) => ({
      tone: row.health === "ok" ? "ok" : row.health === "partial" ? "warn" : ("error" as const),
      label:
        row.health === "ok" ? "Исправна" : row.health === "partial" ? "Частичная" : "Повреждена",
    }),
  },
];

function section(titleText: string, ...children: Node[]): HTMLElement {
  return el("section", { className: "demo-section" }, [
    el("h2", { className: "demo-title", text: titleText }),
    ...children,
  ]);
}

function mount(): void {
  const root = document.getElementById("showcase");
  if (!root) throw new Error("showcase root missing");
  root.className = "demo-root";

  // Диалог
  const dialogButton = el("button", {
    className: "lnt-btn lnt-btn-primary",
    text: "Открыть диалог",
  });
  dialogButton.addEventListener("click", () => {
    openDialog({
      title: "Подтверждение",
      content: el("p", { text: "Записать сессию самошума перед измерениями?" }),
      actions: [{ label: "Записать", kind: "primary", onClick: (close) => close() }],
    });
  });
  root.append(section("Диалог (ловушка фокуса, Esc, возврат фокуса)", dialogButton));

  // Таблица
  const table = createDataTable<DemoRow>(ROW_COLUMNS, {
    caption: "Сессии каталога",
    emptyText: "Сессии не найдены.",
  });
  table.setState({
    kind: "data",
    rows: [
      { id: "b", label: "Вторая", health: "partial" },
      { id: "a", label: "Первая", health: "ok" },
      { id: "c", label: "Третья", health: "corrupt_manifest" },
    ],
  });
  root.append(section("Таблица (стрелки, сортировка, статусы)", table.root));

  // Фильтры
  const store = new RouteStore(window);
  if (!window.location.hash) window.location.hash = "#/catalog";
  store.syncFromUrl();
  const filters = createFilterBar(store, [
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
  root.append(section("Фильтры (состояние в URL, переживает перезагрузку)", filters));

  // Прогресс задачи
  const progress = createJobProgress();
  progress.setIndeterminate("Подготовка устройства…");
  const stageButton = el("button", { className: "lnt-btn", text: "Стадия 2 из 5" });
  stageButton.addEventListener("click", () => progress.setStage("Запись", 2, 5));
  const doneButton = el("button", { className: "lnt-btn", text: "Завершить" });
  doneButton.addEventListener("click", () => progress.done());
  root.append(section("Прогресс и объявления (aria-live)", progress.root, stageButton, doneButton));

  // Разделитель панелей
  const left = el("div", { text: "Каталог" });
  const right = el("div", { text: "Рабочая область графиков" });
  const pane = createSplitPane(left, right, { initialRatio: 40, storageKey: "lnt-demo-split" });
  root.append(section("Разделитель панелей (стрелки ←/→)", pane.root));

  // Оболочка графика + форма с мутацией
  const shell = createChartShell({ title: "Спектр мощности", onDownloadCsv: () => undefined });
  shell.setLoading();
  window.setTimeout(() => {
    shell.setContent(el("p", { className: "demo-plot", text: "Точка монтирования uPlot/ECharts" }));
  }, 600);

  const form = document.createElement("form");
  const field = createField({
    label: "Метка сессии",
    control: Object.assign(document.createElement("input"), { type: "text" }),
  });
  field.setError("Значение не может быть пустым");
  const submit = el("button", {
    className: "lnt-btn lnt-btn-primary",
    text: "Сохранить",
    attrs: { type: "submit" },
  });
  form.append(field.root, submit);
  form.addEventListener("submit", (event) => event.preventDefault());
  setFormPending(form, {
    get: () => ({ kind: "pending" }),
    subscribe: () => () => undefined,
    run: async () => "",
    reset: () => undefined,
  });

  announcePolite("Витрина примитивов готова");
  root.append(section("Оболочка графика и поле формы", shell.root, form));
}

document.addEventListener("DOMContentLoaded", mount);
