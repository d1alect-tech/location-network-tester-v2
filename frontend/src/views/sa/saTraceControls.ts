/** Управление трассами и шкалой SA (Todo 14): тумблеры четырёх трасс
 * склада (clear-write включён всегда — это живая трасса), сброс статистики,
 * единицы дБВ/Гц↔В/√Гц и лог-шкала X. Только DOM и чтение состояния:
 * смена видимости/единиц/шкалы дергает перерисовку графика, «Сброс» —
 * склад. X лог по умолчанию НЕ включён (линейная сетка — решение MVP). */

import { el, nextId } from "../../components/primitives/dom";
import type { SaTraceKind } from "./saTraceStore";
import { SA_UNIT_OPTIONS, type SaDisplayUnit, parseSaUnit } from "./saUnits";

const TRACE_LABELS: Record<SaTraceKind, string> = {
  clear: "Трасса",
  max: "Max-hold",
  min: "Min-hold",
  avg: "Среднее",
};

export interface SaTraceControlsOptions {
  /** Сброс статистики склада (min/max/avg). */
  onClear(): void;
  /** Смена видимости/единиц/шкалы — перерисовать график. */
  onViewChange(): void;
}

export interface SaTraceControls {
  readonly root: HTMLElement;
  visibleTraces(): ReadonlySet<SaTraceKind>;
  unit(): SaDisplayUnit;
  xLog(): boolean;
}

interface Toggle {
  readonly input: HTMLInputElement;
  readonly host: HTMLElement;
}

/** Ряд «чекбокс + подпись»: вся зона кликабельна, тач-таргет 44px. */
function traceToggle(
  kind: SaTraceKind,
  checked: boolean,
  locked: boolean,
  onToggle: (input: HTMLInputElement) => void,
): Toggle {
  const input = el("input", {
    className: "lnt-sa-toggle",
    attrs: { type: "checkbox", "data-sa-trace": kind },
  });
  input.checked = checked;
  input.id = nextId("sa-trace");
  input.disabled = locked;
  input.addEventListener("change", () => {
    if (locked) input.checked = true;
    onToggle(input);
  });
  const host = el("label", { className: "lnt-sa-check", attrs: { for: input.id } }, [
    input,
    el("span", { className: "lnt-sa-toggle-label", text: TRACE_LABELS[kind] }),
  ]);
  return { input, host };
}

export function buildSaTraceControls(options: SaTraceControlsOptions): SaTraceControls {
  const visible = new Set<SaTraceKind>(["clear"]);
  const change = (): void => {
    options.onViewChange();
  };
  const flip =
    (kind: SaTraceKind) =>
    (input: HTMLInputElement): void => {
      if (input.checked) visible.add(kind);
      else visible.delete(kind);
      change();
    };
  // Живая трасса не отключается: это вход склада.
  const clearToggle = traceToggle("clear", true, true, () => undefined);
  const maxToggle = traceToggle("max", false, false, flip("max"));
  const minToggle = traceToggle("min", false, false, flip("min"));
  const avgToggle = traceToggle("avg", false, false, flip("avg"));

  const clearButton = el("button", {
    className: "btn btn-secondary",
    text: "Сбросить статистику",
    attrs: { type: "button", id: "lnt-sa-clear" },
  });
  clearButton.addEventListener("click", () => options.onClear());

  const unitId = nextId("sa-unit");
  const unitSelect = el("select", {
    className: "ctl",
    attrs: { id: unitId, "data-sa-unit": "" },
  });
  for (const option of SA_UNIT_OPTIONS) {
    unitSelect.append(el("option", { text: option.label, attrs: { value: option.value } }));
  }
  unitSelect.addEventListener("change", change);

  const logInput = el("input", { className: "lnt-sa-toggle", attrs: { type: "checkbox" } });
  logInput.checked = false;
  logInput.id = nextId("sa-xlog");
  logInput.addEventListener("change", change);

  const root = el("div", { className: "lnt-sa-trace-controls" }, [
    el("div", { className: "lnt-sa-trace-toggles" }, [
      clearToggle.host,
      maxToggle.host,
      minToggle.host,
      avgToggle.host,
    ]),
    clearButton,
    el("label", { className: "lnt-sa-field", text: "Единицы", attrs: { for: unitId } }, [
      unitSelect,
    ]),
    el("label", { className: "lnt-sa-check", attrs: { for: logInput.id } }, [
      logInput,
      el("span", { className: "lnt-sa-toggle-label", text: "Лог. шкала X" }),
    ]),
  ]);

  return {
    root,
    visibleTraces(): ReadonlySet<SaTraceKind> {
      return visible;
    },
    unit(): SaDisplayUnit {
      return parseSaUnit(unitSelect.value) ?? "dbv";
    },
    xLog(): boolean {
      return logInput.checked;
    },
  };
}
