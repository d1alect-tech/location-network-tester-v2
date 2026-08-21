/** Панель фильтров каталога: health, метка, тип, диапазон дат, профиль, тег.
 * Значения живут в параметрах маршрута (routeState) — перезагрузка и «назад»
 * восстанавливают набор фильтров. Плюс сохранённые представления (localStorage):
 * именованные наборы фильтров применяются одним действием. */

import type { SessionHealth } from "../../api/types";
import { SESSION_HEALTH_VALUES } from "../../api/types";
import { openDialog } from "../../components/primitives/dialog";
import { el } from "../../components/primitives/dom";
import { createField } from "../../components/primitives/forms";
import type { RouteStore } from "../../state/routeState";
import { FILTER_PARAMS, HEALTH_LABELS, sessionTypeLabel } from "./catalogModel";
import { filtersFromParams } from "./catalogModel";
import { type SavedView, loadSavedViews, saveSavedViews } from "./savedViews";

export interface CatalogFilterPanelOptions {
  store: RouteStore;
  storage: Storage;
}

export interface CatalogFilterPanelHandle {
  root: HTMLElement;
  /** Синхронизирует контролы с текущими параметрами URL (назад/вперёд). */
  syncFromRoute(): void;
}

function healthOption(value: SessionHealth): { value: string; label: string } {
  return { value, label: HEALTH_LABELS[value].label };
}

export function createCatalogFilterPanel(
  options: CatalogFilterPanelOptions,
): CatalogFilterPanelHandle {
  const { store, storage } = options;

  const health = document.createElement("select");
  health.className = "lnt-select";
  const typeSelect = document.createElement("select");
  typeSelect.className = "lnt-select";
  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.className = "lnt-input";
  labelInput.placeholder = "стенд-А";
  const profileInput = document.createElement("input");
  profileInput.type = "text";
  profileInput.className = "lnt-input";
  const tagInput = document.createElement("input");
  tagInput.type = "text";
  tagInput.className = "lnt-input";
  const dateFrom = document.createElement("input");
  dateFrom.type = "date";
  dateFrom.className = "lnt-input";
  const dateTo = document.createElement("input");
  dateTo.type = "date";
  dateTo.className = "lnt-input";

  for (const node of [health, typeSelect]) {
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "Все";
    node.append(empty);
  }
  for (const value of SESSION_HEALTH_VALUES) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = healthOption(value).label;
    health.append(option);
  }
  for (const [value, labelText] of Object.entries({
    capture: sessionTypeLabel("capture"),
    simulate: sessionTypeLabel("simulate"),
    line_quality: sessionTypeLabel("line_quality"),
  })) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labelText;
    typeSelect.append(option);
  }

  /** Полная замена фильтров в URL: пустые значения не сериализуются.
   * sessionId null — явный сигнал убрать выбор сессии из маршрута. */
  function writeParams(filters: Record<string, string>, sessionId: string | null): void {
    const params: Record<string, string> = {};
    for (const [key, value] of Object.entries(filters)) {
      if (value !== "") params[key] = value;
    }
    if (sessionId !== null && sessionId !== "") params.session = sessionId;
    store.navigate({ route: "catalog", params });
  }

  const controlParam: Array<[HTMLElement, string, "input" | "change"]> = [
    [health, "health", "change"],
    [typeSelect, "session_type", "change"],
    [labelInput, "label", "input"],
    [dateFrom, "created_from", "change"],
    [dateTo, "created_to", "change"],
    [profileInput, "profile", "input"],
    [tagInput, "tag", "input"],
  ];
  for (const [control, , eventName] of controlParam) {
    control.addEventListener(eventName, () => emitFilters());
  }

  function currentFilters(): Record<string, string> {
    return filtersFromParams(store.get().params) as Record<string, string>;
  }

  function emitFilters(): void {
    writeParams(
      {
        health: health.value,
        session_type: typeSelect.value,
        label: labelInput.value.trim(),
        created_from: dateFrom.value,
        created_to: dateTo.value,
        profile: profileInput.value.trim(),
        tag: tagInput.value.trim(),
      },
      store.get().params.session ?? null,
    );
  }

  // --- Сохранённые представления -------------------------------------------
  const viewSelect = document.createElement("select");
  viewSelect.className = "lnt-select";

  function refreshViewOptions(views: SavedView[], selectedName?: string): void {
    clearChildren(viewSelect);
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "— выбрать —";
    viewSelect.append(placeholder);
    for (const view of views) {
      const option = document.createElement("option");
      option.value = view.name;
      option.textContent = view.name;
      viewSelect.append(option);
    }
    viewSelect.value = selectedName ?? "";
  }

  function clearChildren(node: HTMLElement): void {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  viewSelect.addEventListener("change", () => {
    const views = loadSavedViews(storage);
    const chosen = views.find((view) => view.name === viewSelect.value);
    if (!chosen) return;
    // Полная замена: отсутствующие во view фильтры сбрасываются в пусто.
    const fullFilters: Record<string, string> = {};
    for (const key of FILTER_PARAMS) fullFilters[key] = chosen.filters[key] ?? "";
    writeParams(fullFilters, null);
  });

  const saveButton = el("button", {
    className: "lnt-btn",
    text: "Сохранить фильтры…",
    attrs: { type: "button" },
  });
  saveButton.addEventListener("click", () => {
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.className = "lnt-input";
    const form = el("div", {}, [
      createField({ label: "Название представления", control: nameInput }).root,
    ]);
    const dialog = openDialog({
      title: "Сохранить набор фильтров",
      content: form,
      actions: [
        {
          label: "Сохранить",
          kind: "primary",
          onClick: (close) => {
            const name = nameInput.value.trim();
            if (name === "") {
              nameInput.setAttribute("aria-invalid", "true");
              return;
            }
            const views = loadSavedViews(storage).filter((view) => view.name !== name);
            views.push({ name, filters: filtersFromParams(currentFilters()) });
            saveSavedViews(storage, views);
            refreshViewOptions(views, name);
            close();
          },
        },
      ],
    });
    void dialog;
  });

  const deleteButton = el("button", {
    className: "lnt-btn",
    text: "Удалить представление",
    attrs: { type: "button" },
  });
  deleteButton.addEventListener("click", () => {
    if (viewSelect.value === "") return;
    const views = loadSavedViews(storage).filter((view) => view.name !== viewSelect.value);
    saveSavedViews(storage, views);
    refreshViewOptions(views);
  });

  const resetButton = el("button", {
    className: "lnt-btn",
    text: "Сбросить",
    attrs: { type: "button" },
  });
  resetButton.addEventListener("click", () => {
    store.navigate({ route: "catalog", params: {} });
  });

  const savedRow = el("div", { className: "lnt-cat-saved" }, [
    createField({ label: "Сохранённые представления", control: viewSelect }).root,
    saveButton,
    deleteButton,
  ]);

  const root = el("form", { className: "lnt-filter-bar lnt-cat-filters" }, [
    createField({ label: "Состояние (health)", control: health }).root,
    createField({ label: "Метка", control: labelInput }).root,
    createField({ label: "Тип сессии", control: typeSelect }).root,
    createField({ label: "Дата с", control: dateFrom }).root,
    createField({ label: "Дата по", control: dateTo }).root,
    createField({ label: "Профиль", control: profileInput }).root,
    createField({ label: "Тег", control: tagInput }).root,
    savedRow,
    resetButton,
  ]);
  root.addEventListener("submit", (event) => event.preventDefault());

  return {
    root,
    syncFromRoute: () => {
      const filters = currentFilters();
      for (const [control, param] of controlParam) {
        const input = control as HTMLInputElement | HTMLSelectElement;
        if (input.value !== (filters[param] ?? "")) input.value = filters[param] ?? "";
      }
      refreshViewOptions(loadSavedViews(storage), viewSelect.value || undefined);
    },
  };
}
