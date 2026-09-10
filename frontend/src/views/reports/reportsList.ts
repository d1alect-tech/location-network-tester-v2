import type { OpenRecord } from "../../api/types-research";
import { clearElement, el } from "../../components/primitives/dom";
import { errorWithRetry } from "../../components/primitives/stateViews";
import type { ResourceState } from "../../state/resource";

export interface ReportsListActions {
  refresh: () => void;
  open: (experimentId: string) => void;
}

export function renderReportsList(
  host: HTMLElement,
  state: ResourceState<OpenRecord[]>,
  actions: ReportsListActions,
): void {
  clearElement(host);
  if (state.kind === "loading") {
    host.append(el("p", { className: "lnt-helper-text", text: "Загрузка списка экспериментов…" }));
    return;
  }
  if (state.kind === "error") {
    host.append(
      errorWithRetry(
        `Не удалось загрузить список экспериментов: ${state.error.message}.`,
        actions.refresh,
      ),
    );
    return;
  }
  if (state.kind !== "ready") return;
  if (state.value.length === 0) {
    host.append(
      el("p", {
        className: "lnt-helper-text",
        text: "Экспериментов пока нет. Создайте их в разделе «Эксперименты».",
      }),
    );
    return;
  }
  const list = el("ul", {
    className: "lnt-exp-list",
    attrs: { "aria-label": "Эксперименты для отчётов" },
  });
  for (const item of state.value) {
    const id = String(item.experiment_id ?? "");
    const title = String(item.title ?? id);
    const open = el("button", {
      className: "btn btn-secondary lnt-btn lnt-exp-open",
      text: `${title} (${id})`,
      attrs: { type: "button", "data-experiment-id": id },
    });
    open.addEventListener("click", () => actions.open(id));
    list.append(el("li", { className: "lnt-exp-list-item" }, [open]));
  }
  host.append(list);
}
