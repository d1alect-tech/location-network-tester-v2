/** Секция «Декларация адаптера» (N7) в шаге 2 визарда: утвердительная галка
 * preconnected (по умолчанию НЕ отмечена, D4), ёмкость/рядный R с префиллом
 * пресета (N4, числа не хардкодятся), радио-пара базиса значений (НИКОГДА
 * не value-diff), статическая строка тракта записи (H7 — полей пробника и
 * 1 МОм нет). Динамика — подсказка «стартуйте сразу» (D5) и консультативный
 * пол длительности через analysisFloorSeconds; оба живут в слотах с
 * зарезервированной min-height, поэтому появление/исчезновение текста не
 * сдвигает раскладку (H12). Значения и ошибки интегрируются в
 * ModeFormHandle (паттерн modeFormFields). */

import { el, nextId } from "../components/primitives/dom";
import { createField } from "../components/primitives/forms";
import { ADAPTER_PRESET, analysisFloorSeconds } from "./adapterPreset";
import { v6field } from "./modeFormFields";
import type { CaptureFieldErrors, CaptureFormValues } from "./modes";

/** Четыре значения декларации, читаемые с контролов секции. */
export interface AdapterValues {
  readonly adapterCapNf: string;
  readonly adapterSeriesROhm: string;
  readonly adapterPreconnected: boolean;
  readonly adapterBasis: "nominal" | "operator_measured";
}

export interface AdapterDeclarationSection {
  readonly root: HTMLFieldSetElement;
  values(): AdapterValues;
  setErrors(errors: CaptureFieldErrors): void;
  clearErrors(): void;
  /** Пересчитывает подсказку и пол длительности под значения всей формы. */
  sync(values: CaptureFormValues): void;
}

const HINT_TEXT = "подключите и стартуйте сразу — первые 10τ будут отброшены движком";

function numberInput(name: string, min: string): HTMLInputElement {
  return el("input", {
    className: "lnt-input ctl",
    attrs: { type: "number", name, step: "any", min, inputmode: "decimal" },
  }) as HTMLInputElement;
}

function parseNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const value = Number(raw.replace(",", "."));
  return Number.isFinite(value) ? value : null;
}

/** Компактное число без хвостовых нулей: 11 → «11», 2.05 → «2.05». */
function plain(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

export function createAdapterDeclarationSection(): AdapterDeclarationSection {
  // (1) Утверждение подключения: отдельная крупная цель 44px.
  const preconnectedInput = el("input", {
    className: "capture-adapter-check",
    attrs: { type: "checkbox", name: "adapter_preconnected", id: nextId("adapter-preconnected") },
  }) as HTMLInputElement;
  const confirmLabel = el("label", { className: "capture-adapter-confirm" }, [
    preconnectedInput,
    el("span", {
      className: "capture-adapter-confirm-text",
      text: "Адаптер подключён до старта, переподключений в эпохе записи не было",
    }),
  ]);
  confirmLabel.htmlFor = preconnectedInput.id;
  const confirmHint = el("p", {
    className: "capture-adapter-confirm-hint lnt-hint",
    text: "Без этого подтверждения публичные числа ripple будут недоступны (settling_unknown)",
  });

  // (2) Ёмкость и рядный R: префилл из закреплённого пресета (N4).
  const capInput = numberInput("adapter_cap_nf", "0");
  capInput.value = String(ADAPTER_PRESET.capNfNominal);
  const seriesInput = numberInput("adapter_series_r_ohm", "0");
  seriesInput.value = String(ADAPTER_PRESET.seriesROhmNominal);
  const capField = v6field(createField({ label: "Ёмкость C, нФ", control: capInput }));
  const seriesField = v6field(
    createField({ label: "Последовательный R, Ом", control: seriesInput }),
  );
  const valuesGrid = el("div", { className: "capture-adapter-grid form-grid" }, [
    capField.root,
    seriesField.root,
  ]);

  // (3) Базис значений: радио-пара, состояние — только выбор оператора.
  const basisLabelId = nextId("adapter-basis-label");
  const basisOption = (
    value: "nominal" | "operator_measured",
    text: string,
    checked: boolean,
  ): [HTMLInputElement, HTMLLabelElement] => {
    const radio = el("input", {
      className: "capture-radio-input",
      attrs: {
        type: "radio",
        name: "adapter_component_values_basis",
        value,
        id: nextId("adapter-basis"),
      },
    }) as HTMLInputElement;
    radio.checked = checked;
    const label = el("label", { className: "capture-basis-option" }, [radio, el("span", { text })]);
    label.htmlFor = radio.id;
    return [radio, label];
  };
  const [, nominalLabel] = basisOption("nominal", "номинал", true);
  const [measuredRadio, measuredLabel] = basisOption(
    "operator_measured",
    "измерено оператором",
    false,
  );
  const basisToggle = el(
    "div",
    {
      className: "capture-basis-toggle",
      attrs: { role: "radiogroup", "aria-labelledby": basisLabelId },
    },
    [nominalLabel, measuredLabel],
  );
  const basisField = el("div", { className: "capture-adapter-basis field" }, [
    el("span", { className: "field-label", text: "Базис значений", attrs: { id: basisLabelId } }),
    basisToggle,
  ]);
  let basisAlert: HTMLElement | null = null;

  // (4) Статическая строка тракта записи: полей пробника и 1 МОм нет (H7).
  const fixedLine = el("p", {
    className: "capture-adapter-fixed",
    text: "Вход осциллографа: 1 МОм (номинал) · пробник x1 — фиксируются трактом записи",
  });

  // (5)–(6) Слоты динамики с зарезервированной высотой (H12).
  const hint = el("p", { className: "capture-adapter-hint lnt-hint", text: HINT_TEXT });
  const floor = el("p", { className: "capture-adapter-floor", attrs: { role: "note" } });
  floor.hidden = true;
  const notices = el("div", { className: "capture-adapter-notices" }, [
    el("div", { className: "capture-adapter-slot" }, [hint]),
    el("div", { className: "capture-adapter-slot capture-adapter-slot-floor" }, [floor]),
  ]);

  const root = el("fieldset", { className: "capture-adapter-group" }, [
    el("legend", { text: "Декларация адаптера" }),
    confirmLabel,
    confirmHint,
    valuesGrid,
    basisField,
    fixedLine,
    notices,
  ]) as HTMLFieldSetElement;

  const renderFloor = (values: CaptureFormValues): void => {
    hint.hidden = values.adapterPreconnected;
    const cap = parseNumber(values.adapterCapNf);
    const series = parseNumber(values.adapterSeriesROhm);
    const fs = parseNumber(values.sampleRateHz);
    const duration = parseNumber(values.durationS);
    const seconds =
      cap !== null && cap > 0 && series !== null && series >= 0 && fs !== null && fs > 0
        ? analysisFloorSeconds(cap, series, fs)
        : null;
    // Консультативное зеркало пола: движок остаётся истиной, допустим дрейф
    // ≤1 отсчёта (float vs Decimal-ceil).
    if (
      cap === null ||
      fs === null ||
      seconds === null ||
      duration === null ||
      duration <= 0 ||
      duration >= seconds
    ) {
      floor.hidden = true;
      return;
    }
    floor.textContent = `При C=${plain(cap)} нФ и fs=${plain(fs)} Гц окну анализа нужно ≥${plain(seconds)} с записи — увеличьте длительность.`;
    floor.hidden = false;
  };

  const fieldByErrorKey: Record<string, { setError(message: string | null): void } | "basis"> = {
    adapterCapNf: capField,
    adapterSeriesROhm: seriesField,
    adapterBasis: "basis",
  };

  return {
    root,
    values: (): AdapterValues => ({
      adapterCapNf: capInput.value,
      adapterSeriesROhm: seriesInput.value,
      adapterPreconnected: preconnectedInput.checked,
      adapterBasis: measuredRadio.checked ? "operator_measured" : "nominal",
    }),
    setErrors: (errors: CaptureFieldErrors): void => {
      for (const [key, field] of Object.entries(fieldByErrorKey)) {
        const message = errors[key as keyof CaptureFieldErrors] ?? null;
        if (field === "basis") {
          basisAlert?.remove();
          basisAlert = null;
          if (message !== null) {
            basisAlert = el("p", {
              className: "lnt-error-text",
              text: message,
              attrs: { role: "alert" },
            });
            basisField.append(basisAlert);
          }
          continue;
        }
        field.setError(message);
      }
    },
    clearErrors: (): void => {
      capField.setError(null);
      seriesField.setError(null);
      basisAlert?.remove();
      basisAlert = null;
    },
    sync: renderFloor,
  };
}
