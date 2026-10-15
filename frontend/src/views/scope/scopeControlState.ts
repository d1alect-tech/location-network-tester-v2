/** Чтение и программное применение манифест-контролов полосы «Осциллограф»
 * (задача 15, зона-карта §8.11): значения читаются из ЖИВОГО DOM (нажатые
 * сегменты, staged-цель/применённое значение чипа частоты, поле уровня), а
 * применяются ТОЛЬКО через живые слушатели листьев (клик сегментов и опции
 * частоты, change поля уровня) — хэндлы листьев замкнуты в воркспейсе,
 * это паттерн «слушатели живы», не дублирование логики. Хэндлы для
 * автосета/сброса (scopeAutoset/scopeReset): эхо называет только реально
 * изменённое. */

import type { LiveTriggerMode, LiveTriggerSlope, LiveTriggerSource } from "../../api/types-live";

export interface ScopeControlHosts {
  /** Зона ВЕРТ: содержит #lnt-scope-vdiv и эффективное В/дел. */
  vdiv: HTMLElement;
  /** Зона ВЕРТ: содержит #lnt-scope-probe. */
  probe: HTMLElement;
  /** Зона ГОРИЗ: содержит чип частоты с опциями listbox. */
  rate: HTMLElement;
  /** Поле уровня #lnt-scope-level (в степпере полосы). */
  level: HTMLInputElement;
  /** Зона ТРИГГ: содержит сегменты [data-trigger-mode]. */
  mode: HTMLElement;
  /** Зона ТРИГГ: содержит сегменты [data-trigger-source]. */
  source: HTMLElement;
  /** Зона ТРИГГ: содержит сегменты [data-trigger-slope]. */
  slope: HTMLElement;
}

export interface ScopeControlTargets {
  vdiv: number;
  probe: number;
  rateHz: number;
  levelV: number;
  mode: LiveTriggerMode;
  source: LiveTriggerSource;
  slope: LiveTriggerSlope;
}

/** Изменённый контроль для эха: ключ и готовая подпись значения. */
export interface ScopeControlChange {
  key: keyof ScopeControlTargets;
  label: string;
}

export type ScopeControlState = Partial<ScopeControlTargets>;

const MODE_TEXT: Record<LiveTriggerMode, string> = {
  auto: "авто",
  normal: "норм",
  single: "одиночный",
};
const SLOPE_TEXT: Record<LiveTriggerSlope, string> = {
  rising: "подъём",
  falling: "спад",
};
const SOURCE_TEXT: Record<LiveTriggerSource, string> = {
  ch1: "CH1",
  ch2: "CH2",
};

function pressedAttr(host: HTMLElement, attr: string): string | null {
  const button = host.querySelector(`button[aria-pressed="true"][${attr}]`);
  return button?.getAttribute(attr) ?? null;
}

/** Текущая частота: staged-цель (опция с меткой «→») или применённое
 * (aria-selected) — то, что уйдёт со следующим Run. */
function currentRateHz(host: HTMLElement): number | null {
  const marked = host.querySelector<HTMLElement>(".lnt-live-opt-mark:not([hidden])");
  const target = marked?.closest("[role='option']")?.getAttribute("data-value");
  const applied = host.querySelector("[aria-selected='true']")?.getAttribute("data-value");
  const raw = target ?? applied;
  const value = raw === null ? null : Number(raw);
  return raw === null || !Number.isFinite(value) ? null : value;
}

export function readScopeControlState(hosts: ScopeControlHosts): ScopeControlState {
  const vdiv = Number(pressedAttr(hosts.vdiv, "data-value"));
  const probe = Number(pressedAttr(hosts.probe, "data-value"));
  const level = Number(hosts.level.value);
  return {
    vdiv: Number.isFinite(vdiv) ? vdiv : undefined,
    probe: Number.isFinite(probe) ? probe : undefined,
    rateHz: currentRateHz(hosts.rate) ?? undefined,
    levelV: hosts.level.value.trim() === "" || !Number.isFinite(level) ? undefined : level,
    mode: (pressedAttr(hosts.mode, "data-trigger-mode") as LiveTriggerMode | null) ?? undefined,
    source:
      (pressedAttr(hosts.source, "data-trigger-source") as LiveTriggerSource | null) ?? undefined,
    slope: (pressedAttr(hosts.slope, "data-trigger-slope") as LiveTriggerSlope | null) ?? undefined,
  };
}

function clickSegButton(host: HTMLElement, attr: string, value: string): void {
  const button = host.querySelector(`button[${attr}="${value}"]`);
  if (button instanceof HTMLButtonElement) button.click();
}

/** Применяет цели через живые слушатели; возвращает ТОЛЬКО реально
 * изменённое (эхо не врёт). Поле уровня пишется value + change. */
export function applyScopeControlTargets(
  hosts: ScopeControlHosts,
  targets: Partial<ScopeControlTargets>,
): ScopeControlChange[] {
  const before = readScopeControlState(hosts);
  const changed: ScopeControlChange[] = [];

  if (targets.vdiv !== undefined && targets.vdiv !== before.vdiv) {
    clickSegButton(hosts.vdiv, "data-value", String(targets.vdiv));
    changed.push({ key: "vdiv", label: `В/дел ${targets.vdiv}` });
  }
  if (targets.probe !== undefined && targets.probe !== before.probe) {
    clickSegButton(hosts.probe, "data-value", String(targets.probe));
    changed.push({ key: "probe", label: `пробник ×${targets.probe}` });
  }
  if (targets.rateHz !== undefined && targets.rateHz !== before.rateHz) {
    const option = hosts.rate.querySelector(`[role='option'][data-value="${targets.rateHz}"]`);
    if (option instanceof HTMLButtonElement) option.click();
    changed.push({ key: "rateHz", label: `частота ${rateText(targets.rateHz)}` });
  }
  if (targets.levelV !== undefined) {
    const value = Math.round(targets.levelV * 100) / 100;
    if (value !== before.levelV) {
      hosts.level.value = String(value);
      hosts.level.dispatchEvent(new Event("change", { bubbles: true }));
      changed.push({ key: "levelV", label: `уровень ${value} В` });
    }
  }
  if (targets.mode !== undefined && targets.mode !== before.mode) {
    clickSegButton(hosts.mode, "data-trigger-mode", targets.mode);
    changed.push({ key: "mode", label: `режим ${MODE_TEXT[targets.mode]}` });
  }
  if (targets.source !== undefined && targets.source !== before.source) {
    clickSegButton(hosts.source, "data-trigger-source", targets.source);
    changed.push({ key: "source", label: `источник ${SOURCE_TEXT[targets.source]}` });
  }
  if (targets.slope !== undefined && targets.slope !== before.slope) {
    clickSegButton(hosts.slope, "data-trigger-slope", targets.slope);
    changed.push({ key: "slope", label: `фронт ${SLOPE_TEXT[targets.slope]}` });
  }
  return changed;
}

function rateText(hz: number): string {
  return hz >= 1_000_000 ? `${hz / 1_000_000} МГц` : `${hz / 1_000} кГц`;
}
