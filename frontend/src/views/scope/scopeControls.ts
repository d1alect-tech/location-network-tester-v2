/** Управление развёрткой (Todo 8): селектор В/дел из ОБЩЕЙ таблицы каналов,
 * пробник CH1 1×/10×, инверсия каналов и подпись эффективных В/дел
 * (масштабируется пробником). Только DOM и события: закон масштаба — в
 * scopeScale, подпись обновляется на каждое изменение, интерактив — в
 * scopeWorkspace. */

import { el } from "../../components/primitives/dom";
import { PROBE_STEPS, VDIV_STEPS, effectiveVDiv, formatVDiv } from "./scopeScale";
import type { ScopeDisplaySettings } from "./scopeScale";

export interface ScopeControlsView {
  readonly root: HTMLElement;
  /** Снимает настройки с DOM-контролов (значения задают только опции). */
  readSettings(): ScopeDisplaySettings;
}

export function buildScopeControls(
  onChange: (settings: ScopeDisplaySettings) => void,
): ScopeControlsView {
  const vDivSelect = el("select", {
    className: "ctl lnt-scope-vdiv",
    attrs: { id: "lnt-scope-vdiv", "aria-label": "Вольт на деление" },
  });
  for (const vDiv of VDIV_STEPS) {
    const option = el("option", { text: formatVDiv(vDiv) });
    option.value = String(vDiv);
    vDivSelect.append(option);
  }
  vDivSelect.value = "5";

  const probeSelect = el("select", {
    className: "ctl lnt-scope-probe",
    attrs: { id: "lnt-scope-probe", "aria-label": "Пробник CH1" },
  });
  for (const probe of PROBE_STEPS) {
    const option = el("option", { text: `×${probe}` });
    option.value = String(probe);
    probeSelect.append(option);
  }
  probeSelect.value = "1";

  const invertCh1 = el("input", { attrs: { type: "checkbox", id: "lnt-scope-invert-ch1" } });
  const invertCh2 = el("input", { attrs: { type: "checkbox", id: "lnt-scope-invert-ch2" } });

  const effectiveLine = el("p", { className: "lnt-scope-vdiv-effective", text: "" });

  function readSettings(): ScopeDisplaySettings {
    return {
      vDiv: Number(vDivSelect.value),
      probe: Number(probeSelect.value),
      invertCh1: invertCh1.checked,
      invertCh2: invertCh2.checked,
    };
  }

  function refresh(): void {
    const settings = readSettings();
    effectiveLine.textContent = formatVDiv(effectiveVDiv(settings.vDiv, settings.probe));
  }

  for (const control of [vDivSelect, probeSelect, invertCh1, invertCh2]) {
    control.addEventListener("change", () => {
      refresh();
      onChange(readSettings());
    });
  }
  refresh();

  const root = el(
    "div",
    {
      className: "lnt-scope-controls",
      attrs: { role: "group", "aria-label": "Управление развёрткой" },
    },
    [
      el("label", { className: "lnt-scope-field" }, [
        el("span", { className: "field-label", text: "В/дел (оба канала)" }),
        vDivSelect,
      ]),
      el("label", { className: "lnt-scope-field" }, [
        el("span", { className: "field-label", text: "Пробник CH1" }),
        probeSelect,
      ]),
      el("label", { className: "lnt-scope-check" }, [
        invertCh1,
        el("span", { className: "field-label", text: "Инверсия CH1" }),
      ]),
      el("label", { className: "lnt-scope-check" }, [
        invertCh2,
        el("span", { className: "field-label", text: "Инверсия CH2" }),
      ]),
      el("div", { className: "lnt-scope-field" }, [
        el("span", { className: "field-label", text: "В/дел CH1 (с пробником)" }),
        effectiveLine,
      ]),
    ],
  );

  return { root, readSettings };
}
