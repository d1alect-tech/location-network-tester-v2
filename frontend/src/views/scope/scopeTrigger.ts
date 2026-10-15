/** Триггер-панель вкладки «Осциллограф» (Todo 9): источник, полярность,
 * уровень с валидацией и режим AUTO/NORMAL/SINGLE. Метки честные: связь
 * входов только DC (AC-связи нет), holdoff и предтриггерная память у
 * Hantek 6022BE отсутствуют — панель их не обещает и не показывает.
 * SINGLE останавливает прибор сервер (InstrumentService освобождает ручку
 * после кадра); подтверждение остановки — в workspace. Построение DOM +
 * локальное состояние секции: сеть остаётся в workspace, onTriggerChange
 * уходит только с валидным триггером целиком. */

import type {
  LiveTrigger,
  LiveTriggerMode,
  LiveTriggerSlope,
  LiveTriggerSource,
} from "../../api/types-live";
import { DEFAULT_LIVE_START_REQUEST } from "../../api/types-live";
import { el } from "../../components/primitives/dom";

/** Номинальная шкала каналов живого режима (CH1 ±5 В, CH2 всегда ±5 В):
 * порог вне шкалы физически недостижим — валидация до любого POST. */
export const TRIGGER_LEVEL_LIMIT_V = 5;

const MODE_HINT =
  "Авто — кадр по таймауту 0,2 с даже без фронта. Норм — кадр только по фронту. Одиночный — один кадр, затем остановка.";

export interface TriggerLevelCheck {
  value: number | null;
  error: string | null;
}

/** Валидация уровня до POST: пустое/нечисловое и выход за номинальную шкалу
 * каналов отклоняются локально — сервер не должен видеть заведомый мусор. */
export function checkTriggerLevel(raw: string): TriggerLevelCheck {
  const text = raw.trim().replace(",", ".");
  const notNumber = "Уровень триггера должен быть числом.";
  if (text === "") return { value: null, error: notNumber };
  const value = Number(text);
  if (!Number.isFinite(value)) return { value: null, error: notNumber };
  if (Math.abs(value) > TRIGGER_LEVEL_LIMIT_V) {
    return {
      value: null,
      error: `Уровень триггера должен быть в диапазоне от -${TRIGGER_LEVEL_LIMIT_V} до ${TRIGGER_LEVEL_LIMIT_V} В.`,
    };
  }
  return { value, error: null };
}

interface SegEntry<T extends string> {
  value: T;
  text: string;
}

interface SegGroup<T extends string> {
  readonly root: HTMLElement;
  paint(value: T): void;
}

/** Сегментная группа (role=group + aria-pressed, как plane-toggle инспектора):
 * нативные кнопки — табом и Enter; клик по уже нажатой — no-op. */
function buildSegGroup<T extends string>(options: {
  attr: string;
  groupLabel: string;
  entries: readonly SegEntry<T>[];
  value: T;
  onPick: (value: T) => void;
}): SegGroup<T> {
  const buttons = new Map<T, HTMLButtonElement>();
  for (const entry of options.entries) {
    buttons.set(
      entry.value,
      el("button", {
        className: "lnt-scope-seg-btn",
        text: entry.text,
        attrs: {
          type: "button",
          [options.attr]: entry.value,
          "aria-pressed": String(entry.value === options.value),
        },
      }),
    );
  }
  for (const [value, button] of buttons) {
    button.addEventListener("click", () => {
      if (button.getAttribute("aria-pressed") === "true") return;
      options.onPick(value);
    });
  }
  return {
    root: el(
      "div",
      { className: "lnt-scope-seg", attrs: { role: "group", "aria-label": options.groupLabel } },
      [...buttons.values()],
    ),
    paint(value: T): void {
      for (const [entryValue, button] of buttons) {
        button.setAttribute("aria-pressed", String(entryValue === value));
      }
    },
  };
}

function field(label: string, control: HTMLElement): HTMLElement {
  return el("div", { className: "lnt-scope-field" }, [
    el("span", { className: "lnt-scope-field-label", text: label }),
    control,
  ]);
}

export interface ScopeTriggerView {
  readonly root: HTMLElement;
  /** Текущий триггер панели: полный объект, готовый к POST/старту. */
  getTrigger(): LiveTrigger;
  /** Текущая ошибка валидации уровня; null — поле валидно. */
  validationError(): string | null;
  /** Перерисовка по истине сервиса (ответ start/config, повторный вход). */
  paintTrigger(trigger: LiveTrigger): void;
  focusLevel(): void;
}

export function buildScopeTriggerSection(options: {
  onTriggerChange: (trigger: LiveTrigger) => void;
}): ScopeTriggerView {
  let trigger: LiveTrigger = { ...DEFAULT_LIVE_START_REQUEST.trigger };
  let levelError: string | null = null;

  const levelInput = el("input", {
    className: "lnt-scope-ctl",
    attrs: {
      type: "number",
      id: "lnt-scope-level",
      min: String(-TRIGGER_LEVEL_LIMIT_V),
      max: String(TRIGGER_LEVEL_LIMIT_V),
      step: "0.1",
      inputmode: "decimal",
      "aria-describedby": "lnt-scope-level-hint",
      "aria-invalid": "false",
    },
  });
  levelInput.value = "0";

  const levelField = el("div", { className: "lnt-scope-field" }, [
    el("label", {
      className: "lnt-scope-field-label",
      text: "Уровень, В",
      attrs: { for: "lnt-scope-level" },
    }),
    levelInput,
    el("p", {
      className: "t-compact lnt-scope-hint",
      text: "Диапазон от -5 до 5 В.",
      attrs: { id: "lnt-scope-level-hint" },
    }),
  ]);

  function setError(message: string | null): void {
    levelError = message;
    levelInput.setAttribute("aria-invalid", String(message !== null));
    const existing = levelField.querySelector('[role="alert"]');
    if (message === null) {
      existing?.remove();
      levelInput.setAttribute("aria-describedby", "lnt-scope-level-hint");
      return;
    }
    const alert =
      existing ??
      el("p", {
        className: "lnt-scope-error-text",
        attrs: { role: "alert", id: "lnt-scope-level-error" },
      });
    alert.textContent = message;
    if (existing === null) levelField.append(alert);
    levelInput.setAttribute("aria-describedby", "lnt-scope-level-hint lnt-scope-level-error");
  }

  const sourceSeg = buildSegGroup<LiveTriggerSource>({
    attr: "data-trigger-source",
    groupLabel: "Источник триггера",
    entries: [
      { value: "ch1", text: "CH1" },
      { value: "ch2", text: "CH2" },
    ],
    value: trigger.source,
    onPick: (source) => apply({ source }),
  });
  const slopeSeg = buildSegGroup<LiveTriggerSlope>({
    attr: "data-trigger-slope",
    groupLabel: "Полярность фронта",
    entries: [
      { value: "rising", text: "Подъём" },
      { value: "falling", text: "Спад" },
    ],
    value: trigger.slope,
    onPick: (slope) => apply({ slope }),
  });
  const modeSeg = buildSegGroup<LiveTriggerMode>({
    attr: "data-trigger-mode",
    groupLabel: "Режим триггера",
    entries: [
      { value: "auto", text: "Авто" },
      { value: "normal", text: "Норм" },
      { value: "single", text: "Одиночный" },
    ],
    value: trigger.mode,
    onPick: (mode) => apply({ mode }),
  });

  function paint(): void {
    sourceSeg.paint(trigger.source);
    slopeSeg.paint(trigger.slope);
    modeSeg.paint(trigger.mode);
    // Правка уровня в фокусе честнее живого репейнта: heartbeat не затирает
    // несохранённый ввод оператора (blur доставит его change-ом).
    if (document.activeElement !== levelInput) {
      levelInput.value = String(trigger.level_v);
    }
  }

  function apply(patch: Partial<LiveTrigger>): void {
    trigger = { ...trigger, ...patch };
    paint();
    options.onTriggerChange(trigger);
  }

  levelInput.addEventListener("change", () => {
    const check = checkTriggerLevel(levelInput.value);
    if (check.value === null || check.error !== null) {
      setError(check.error);
      return;
    }
    setError(null);
    if (check.value === trigger.level_v) return;
    trigger = { ...trigger, level_v: check.value };
    options.onTriggerChange(trigger);
  });

  const root = el("section", { className: "panel lnt-scope-section lnt-scope-trigger" }, [
    el("div", { className: "panel-hd" }, [el("h3", { className: "panel-title", text: "Триггер" })]),
    el("div", { className: "panel-bd" }, [
      el("div", { className: "lnt-scope-trig-grid" }, [
        field("Источник", sourceSeg.root),
        field("Фронт", slopeSeg.root),
        levelField,
        field("Режим", modeSeg.root),
      ]),
      el("p", { className: "t-compact lnt-scope-mode-hint", text: MODE_HINT }),
      el("dl", { className: "readout-grid lnt-scope-coupling" }, [
        el("dt", { className: "readout-label", text: "связь входов" }),
        el("dd", { className: "t-compact", text: "DC (оба канала)" }),
      ]),
    ]),
  ]);

  return {
    root,
    getTrigger: () => ({ ...trigger }),
    validationError: () => levelError,
    paintTrigger(next: LiveTrigger): void {
      trigger = { ...next };
      paint();
      setError(null);
    },
    focusLevel: () => levelInput.focus(),
  };
}
