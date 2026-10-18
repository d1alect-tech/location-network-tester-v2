/** Расширенное меню настройки захвата (задача 21, директива GATE A
 * 2026-10-18): disclosure-панель по r4-прецеденту stateless-диалога
 * (liveChip): кнопка «Захват» в зоне ИЗМЕР полосы, панель — overlay
 * (absolute, открывается ВВЕРХ от линии 1 — окно вида не переполняется),
 * Esc/клик мимо закрывают БЕЗ изменений. ВСЕ capture-настройки в одном
 * месте: В/дел, пробник, частота, триггер (режим/источник/фронт/уровень) —
 * таблицы опций те же (scopeScale/scopeRateField), значения читаются
 * снапшотом из живых typed-хостов полосы (задача 12: ScopeControlHosts),
 * запись — ТОЛЬКО живыми слушателями листьев (applyScopeControlTargets:
 * клик сегментов/опций, change поля уровня): каждый пункт пишет то же
 * поле, что и полоса, стейджится грамматикой scopeStatus («применится при
 * следующем запуске»), триггер на ходу горячий (POST /api/live/config) —
 * мгновенного применения старт-ручек нет. Комната под ФНЧ/persistence
 * (задачи 22/24) — секциями после capture-блока; мёртвых кнопок нет:
 * только реальные контролы. */

import { el } from "../../components/primitives/dom";
import type {
  ScopeControlHosts,
  ScopeControlState,
  ScopeControlTargets,
} from "./scopeControlState";
import { applyScopeControlTargets, readScopeControlState } from "./scopeControlState";
import { SCOPE_SAMPLE_RATES_HZ, rateLabelHz } from "./scopeRateField";
import { PROBE_STEPS, VDIV_STEPS } from "./scopeScale";
import { checkTriggerLevel } from "./scopeTrigger";

/** Опция меню: value — DOM-ключ, target — ГОТОВАЯ цель живой записи. */
interface MenuOption {
  readonly value: string;
  readonly text: string;
  readonly target: Partial<ScopeControlTargets>;
}

interface MenuRowDesc {
  readonly row: string;
  readonly label: string;
  readonly options: readonly MenuOption[];
  /** Текущее значение живого контрола (staged-цель или применённое). */
  readonly current: (state: ScopeControlState) => string;
}

interface MenuRow {
  readonly node: HTMLElement;
  readonly current: (state: ScopeControlState) => string;
  paint(value: string): void;
}

const TRIG_MODES: readonly MenuOption[] = [
  { value: "auto", text: "Авто", target: { mode: "auto" } },
  { value: "normal", text: "Норм", target: { mode: "normal" } },
  { value: "single", text: "Одиночный", target: { mode: "single" } },
];
const TRIG_SOURCES: readonly MenuOption[] = [
  { value: "ch1", text: "CH1", target: { source: "ch1" } },
  { value: "ch2", text: "CH2", target: { source: "ch2" } },
];
const TRIG_SLOPES: readonly MenuOption[] = [
  { value: "rising", text: "Подъём", target: { slope: "rising" } },
  { value: "falling", text: "Спад", target: { slope: "falling" } },
];

/** Числовое поле снапшота как строка ряда (vdiv/probe/rateHz). */
const numStr = (value: number | undefined): string => (value === undefined ? "" : String(value));

/** Ряды меню зеркалят живые контролы полосы (те же таблицы опций). */
const ROWS: readonly MenuRowDesc[] = [
  {
    row: "vdiv",
    label: "В/дел (оба канала)",
    options: VDIV_STEPS.map((v) => ({ value: String(v), text: String(v), target: { vdiv: v } })),
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
  { row: "trigmode", label: "Режим", options: TRIG_MODES, current: (s) => s.mode ?? "" },
  { row: "trigsource", label: "Источник", options: TRIG_SOURCES, current: (s) => s.source ?? "" },
  { row: "trigslope", label: "Фронт", options: TRIG_SLOPES, current: (s) => s.slope ?? "" },
];

export interface ScopeCaptureMenuOptions {
  /** Хост группы [data-action="capture"] зоны ИЗМЕР (кнопка + панель). */
  host: HTMLElement;
  /** Живые хосты контролов полосы: чтение снапшота + запись кликами. */
  controls: ScopeControlHosts;
  /** Дополнительные секции отображения (задачи 22/24: ФНЧ полосы,
   *  послесвечение) — узел вставляется после capture-блока; секции
   *  монтируются владельцем, это локальные контролы, не поля полосы. */
  extras?: Node;
}

export interface ScopeCaptureMenuHandle {
  readonly root: HTMLElement;
  dispose(): void;
}

/** Сигнатура живой записи: цель уходит в applyScopeControlTargets. */
type LivePick = (target: Partial<ScopeControlTargets>) => void;

function buildRow(desc: MenuRowDesc, onPick: LivePick): MenuRow {
  const buttons = new Map<string, HTMLButtonElement>();
  for (const option of desc.options) {
    const node = el("button", {
      className: "lnt-live-capture-opt",
      text: option.text,
      attrs: { type: "button", "data-menu-value": option.value, "aria-pressed": "false" },
    });
    node.addEventListener("click", () => onPick(option.target));
    buttons.set(option.value, node);
  }
  return {
    current: desc.current,
    node: el(
      "div",
      {
        className: "lnt-live-capture-row",
        attrs: { "data-menu-row": desc.row, role: "group", "aria-label": desc.label },
      },
      [
        el("span", { className: "lnt-live-capture-row-label", text: desc.label }),
        ...buttons.values(),
      ],
    ),
    paint(value: string): void {
      for (const [optionValue, button] of buttons) {
        button.setAttribute("aria-pressed", String(optionValue === value));
      }
    },
  };
}

export function mountScopeCaptureMenu(options: ScopeCaptureMenuOptions): ScopeCaptureMenuHandle {
  const host = options.host;
  const controls = options.controls;

  const pick: LivePick = (target) => {
    applyScopeControlTargets(controls, target);
    paintSnapshot();
  };
  const rows = new Map<string, MenuRow>();
  for (const desc of ROWS) rows.set(desc.row, buildRow(desc, pick));
  const rowNode = (name: string): HTMLElement => {
    const row = rows.get(name);
    if (row === undefined) throw new Error(`scopeCaptureMenu: нет ряда ${name}`);
    return row.node;
  };

  const levelInput = el("input", {
    className: "lnt-live-capture-level-input",
    attrs: { type: "number", "data-menu-level": "", "aria-label": "Уровень триггера, вольты" },
  });
  const levelError = el("p", {
    className: "t-compact lnt-live-capture-level-error",
    attrs: { "data-menu-level-error": "", role: "alert", hidden: "" },
  });
  levelInput.addEventListener("change", () => {
    const check = checkTriggerLevel(levelInput.value);
    levelError.hidden = check.value !== null;
    if (check.value === null) {
      levelError.textContent = check.error;
      return;
    }
    pick({ levelV: check.value });
  });
  const levelRow = el(
    "div",
    {
      className: "lnt-live-capture-row lnt-live-capture-level",
      attrs: { "data-menu-row": "level", role: "group", "aria-label": "Уровень триггера" },
    },
    [
      el("span", { className: "lnt-live-capture-row-label", text: "Уровень, В" }),
      levelInput,
      levelError,
    ],
  );

  const group = (title: string, names: readonly string[], extra?: Node): HTMLElement =>
    el("div", { className: "lnt-live-capture-group" }, [
      el("span", { className: "lnt-live-capture-hd", text: title }),
      ...names.map(rowNode),
      ...(extra === undefined ? [] : [extra]),
    ]);

  const panel = el(
    "div",
    {
      className: "lnt-live-capture-menu",
      attrs: { role: "dialog", "aria-label": "Настройки захвата", hidden: "" },
    },
    [
      el("span", { className: "lnt-live-menu-hd", text: "Настройки захвата" }),
      group("Вертикаль", ["vdiv", "probe"]),
      group("Горизонталь", ["rate"]),
      group("Триггер", ["trigmode", "trigsource", "trigslope"], levelRow),
      ...(options.extras === undefined ? [] : [options.extras]),
      el("p", {
        className: "t-compact lnt-live-capture-hint",
        text: "В/дел, пробник и частота — при следующем запуске; триггер на ходу — сразу.",
      }),
    ],
  );

  // Кнопка компактная (бюджет ширины линии 1); панель titled «Настройки захвата».
  const menuButton = el("button", {
    className: "lnt-live-capture-btn",
    text: "Меню",
    attrs: { type: "button", "aria-haspopup": "dialog", "aria-expanded": "false" },
  });
  const root = el("div", { className: "lnt-live-capture" }, [menuButton, panel]);
  host.append(root);

  function paintSnapshot(): void {
    const state = readScopeControlState(controls);
    for (const row of rows.values()) row.paint(row.current(state));
    levelInput.value = state.levelV !== undefined ? String(state.levelV) : "";
  }

  function close(refocus: boolean): void {
    panel.hidden = true;
    menuButton.setAttribute("aria-expanded", "false");
    if (refocus) menuButton.focus();
  }

  menuButton.addEventListener("click", () => {
    if (panel.hidden) {
      paintSnapshot();
      panel.hidden = false;
      menuButton.setAttribute("aria-expanded", "true");
      panel.querySelector<HTMLButtonElement>(".lnt-live-capture-opt")?.focus();
    } else close(true);
  });
  root.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || panel.hidden) return;
    // stateless: закрыть без изменений (снапшот просто уходит).
    event.preventDefault();
    close(true);
  });
  const onPointerDown = (event: Event): void => {
    if (!root.isConnected) {
      document.removeEventListener("pointerdown", onPointerDown);
      return;
    }
    if (panel.hidden) return;
    if (root.contains(event.target as Node)) return;
    close(false);
  };
  document.addEventListener("pointerdown", onPointerDown);

  return {
    root,
    dispose: () => {
      document.removeEventListener("pointerdown", onPointerDown);
      root.remove();
    },
  };
}
