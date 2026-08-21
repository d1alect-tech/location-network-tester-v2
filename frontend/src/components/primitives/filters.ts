/** Панель фильтров каталога: подписанные контролы, запись в параметры
 * маршрута (переживает перезагрузку), кнопка сброса. */

import type { RouteStore, WorkspaceLocation } from "../../state/routeState";
import { parseHash } from "../../state/routeState";
import { el, nextId } from "./dom";

export type FilterDef =
  | { kind: "text"; param: string; label: string }
  | {
      kind: "select";
      param: string;
      label: string;
      options: { value: string; label: string }[];
    }
  | { kind: "dateRange"; fromParam: string; toParam: string; label: string };

/** Свежие параметры читаются из живого hash: store обновляет кэш только
 * по hashchange, а последовательные правки фильтров не должны терять друг друга. */
function currentLocation(store: RouteStore): WorkspaceLocation {
  return parseHash(window.location.hash) ?? store.get();
}

function writeParam(store: RouteStore, param: string, value: string): void {
  const current = currentLocation(store);
  const params = { ...current.params };
  if (value === "") delete params[param];
  else params[param] = value;
  store.navigate({ route: current.route, params });
}

function labelledControl(control: HTMLElement, labelText: string): HTMLElement {
  const id = nextId("lnt-filter");
  control.id = id;
  const label = el("label", { className: "lnt-label", text: labelText });
  label.htmlFor = id;
  return el("div", { className: "lnt-field" }, [label, control]);
}

export function createFilterBar(store: RouteStore, defs: FilterDef[]): HTMLElement {
  const bar = el("form", { className: "lnt-filter-bar" });
  bar.addEventListener("submit", (event) => event.preventDefault());

  for (const def of defs) {
    if (def.kind === "text") {
      const input = document.createElement("input");
      input.type = "text";
      input.className = "lnt-input";
      input.value = store.get().params[def.param] ?? "";
      input.addEventListener("input", () => writeParam(store, def.param, input.value));
      bar.append(labelledControl(input, def.label));
    } else if (def.kind === "select") {
      const select = document.createElement("select");
      select.className = "lnt-select";
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "Все";
      select.append(empty);
      for (const option of def.options) {
        const node = document.createElement("option");
        node.value = option.value;
        node.textContent = option.label;
        select.append(node);
      }
      select.value = store.get().params[def.param] ?? "";
      if (!select.value) select.value = "";
      select.addEventListener("change", () => writeParam(store, def.param, select.value));
      bar.append(labelledControl(select, def.label));
    } else {
      const fromInput = document.createElement("input");
      const toInput = document.createElement("input");
      fromInput.type = "date";
      toInput.type = "date";
      fromInput.className = "lnt-input";
      toInput.className = "lnt-input";
      fromInput.value = store.get().params[def.fromParam] ?? "";
      toInput.value = store.get().params[def.toParam] ?? "";
      fromInput.addEventListener("change", () => writeParam(store, def.fromParam, fromInput.value));
      toInput.addEventListener("change", () => writeParam(store, def.toParam, toInput.value));
      const group = el("div", { className: "lnt-date-range", attrs: { role: "group" } }, [
        labelledControl(fromInput, `${def.label} с`),
        labelledControl(toInput, `${def.label} по`),
      ]);
      bar.append(group);
    }
  }

  const reset = el("button", { className: "lnt-btn", text: "Сбросить", attrs: { type: "button" } });
  reset.addEventListener("click", () => {
    store.navigate({ route: store.get().route, params: {} });
  });
  bar.append(reset);
  return bar;
}
