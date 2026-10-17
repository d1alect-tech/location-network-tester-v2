/** Управление развёрткой (Todo 8; задача 14 — сегменты liveSeg): В/дел и
 * пробник CH1 — сегментные группы полосы (значение на контроле; контрактные
 * #lnt-scope-vdiv/#lnt-scope-probe и класс .lnt-scope-seg сохраняются для
 * ре-парента), инверсия каналов и подпись эффективных В/дел — компакт-leftover
 * главной области. Только DOM и события: закон масштаба — в scopeScale,
 * интерактив — в scopeWorkspace (стейджинг помечает scopeStatus полосы). */

import { createLiveSeg } from "../../components/liveStrip/liveSeg";
import { el } from "../../components/primitives/dom";
import { PROBE_STEPS, VDIV_STEPS, effectiveVDiv, formatVDiv } from "./scopeScale";
import type { ScopeDisplaySettings } from "./scopeScale";

export interface ScopeControlsView {
  readonly root: HTMLElement;
  /** Сегмент В/дел (#lnt-scope-vdiv) — хост полосы (ре-парент). */
  readonly vdiv: HTMLElement;
  /** Сегмент пробника (#lnt-scope-probe) — хост полосы (ре-парент). */
  readonly probe: HTMLElement;
  /** Подпись эффективных В/дел — zone-echo полосы (ре-парент). */
  readonly vdivEffective: HTMLElement;
  /** Снимает настройки с DOM-контролов (значения задают только опции). */
  readSettings(): ScopeDisplaySettings;
}

export function buildScopeControls(
  onChange: (settings: ScopeDisplaySettings) => void,
): ScopeControlsView {
  const vDivSeg = createLiveSeg(
    {
      key: "vdiv",
      kind: "ctl",
      aria: "Вольт на деление",
      options: VDIV_STEPS.map((vDiv) => ({ value: String(vDiv), text: String(vDiv) })),
      current: "5",
      groupAttrs: { id: "lnt-scope-vdiv" },
      groupClassName: "lnt-scope-seg",
    },
    () => {
      refresh();
      onChange(readSettings());
    },
  );
  const probeSeg = createLiveSeg(
    {
      key: "probe",
      kind: "ctl",
      aria: "Пробник CH1",
      options: PROBE_STEPS.map((probe) => ({ value: String(probe), text: `×${probe}` })),
      current: "1",
      groupAttrs: { id: "lnt-scope-probe" },
      groupClassName: "lnt-scope-seg",
    },
    () => {
      refresh();
      onChange(readSettings());
    },
  );

  const invertCh1 = el("input", { attrs: { type: "checkbox", id: "lnt-scope-invert-ch1" } });
  const invertCh2 = el("input", { attrs: { type: "checkbox", id: "lnt-scope-invert-ch2" } });

  const effectiveLine = el("p", { className: "lnt-scope-vdiv-effective", text: "" });

  function readSettings(): ScopeDisplaySettings {
    return {
      vDiv: Number(vDivSeg.selection()),
      probe: Number(probeSeg.selection()),
      invertCh1: invertCh1.checked,
      invertCh2: invertCh2.checked,
    };
  }

  function refresh(): void {
    const settings = readSettings();
    effectiveLine.textContent = formatVDiv(effectiveVDiv(settings.vDiv, settings.probe));
  }

  for (const control of [invertCh1, invertCh2]) {
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
      el("div", { className: "lnt-scope-field" }, [
        el("span", { className: "lnt-scope-field-label", text: "В/дел (оба канала)" }),
        vDivSeg.root,
      ]),
      el("div", { className: "lnt-scope-field" }, [
        el("span", { className: "lnt-scope-field-label", text: "Пробник CH1" }),
        probeSeg.root,
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
        el("span", { className: "lnt-scope-field-label", text: "В/дел CH1 (с пробником)" }),
        effectiveLine,
      ]),
    ],
  );

  return {
    root,
    vdiv: vDivSeg.root,
    probe: probeSeg.root,
    vdivEffective: effectiveLine,
    readSettings,
  };
}
