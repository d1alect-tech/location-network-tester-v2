/** Опции расширенного меню из тех же таблиц, что у живых контролов. */
import type { ScopeControlState, ScopeControlTargets } from "./scopeControlState";
import { SCOPE_SAMPLE_RATES_HZ, rateLabelHz } from "./scopeRateField";
import { PROBE_STEPS, VDIV_STEPS, formatVDiv } from "./scopeScale";

interface MenuOption {
  readonly value: string;
  readonly text: string;
  readonly target: Partial<ScopeControlTargets>;
}

export interface MenuRowDesc {
  readonly row: string;
  readonly label: string;
  readonly options: readonly MenuOption[];
  readonly current: (state: ScopeControlState) => string;
}

const numStr = (value: number | undefined): string => (value === undefined ? "" : String(value));
export const CAPTURE_ROWS: readonly MenuRowDesc[] = [
  {
    row: "vdiv",
    label: "В/дел (оба канала)",
    options: VDIV_STEPS.map((v) => ({
      value: String(v),
      text: formatVDiv(v),
      target: { vdiv: v },
    })),
    current: (s) => numStr(s.vdiv),
  },
  {
    row: "probe",
    label: "Пробник CH1",
    options: PROBE_STEPS.map((p) => ({ value: String(p), text: `×${p}`, target: { probe: p } })),
    current: (s) => numStr(s.probe),
  },
  {
    row: "rate",
    label: "Частота дискретизации",
    options: SCOPE_SAMPLE_RATES_HZ.map((hz) => ({
      value: String(hz),
      text: rateLabelHz(hz),
      target: { rateHz: hz },
    })),
    current: (s) => numStr(s.rateHz),
  },
  {
    row: "trigmode",
    label: "Режим",
    current: (s) => s.mode ?? "",
    options: [
      { value: "auto", text: "Авто", target: { mode: "auto" } },
      { value: "normal", text: "Норм", target: { mode: "normal" } },
      { value: "single", text: "Одиночный", target: { mode: "single" } },
    ],
  },
  {
    row: "trigsource",
    label: "Источник",
    current: (s) => s.source ?? "",
    options: [
      { value: "ch1", text: "CH1", target: { source: "ch1" } },
      { value: "ch2", text: "CH2", target: { source: "ch2" } },
    ],
  },
  {
    row: "trigslope",
    label: "Фронт",
    current: (s) => s.slope ?? "",
    options: [
      { value: "rising", text: "Подъём", target: { slope: "rising" } },
      { value: "falling", text: "Спад", target: { slope: "falling" } },
    ],
  },
];
