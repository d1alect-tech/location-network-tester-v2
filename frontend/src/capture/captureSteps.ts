// Пошаговый поток «Захвата» — вариант-победитель G4 («Визард»): рельс шагов
// и панели 1→2→3. Шаг 1 — режим и источник, шаг 2 — параметры (эхо выбора
// чипами), шаг 3 — запуск, устройство, live-грам и журнал задачи. «Далее»
// с шага 2 gated существующей валидацией формы (validateCaptureForm владеет
// вызывающий); переключение шагов — частое действие, поэтому без анимации
// (вход играет один раз на монтировании представления, см. captureView).
// Панели 1–2 живут внутри формы (секции modeForm переносятся сюда), панель 3
// возвращается владельцу — она не содержит полей формы.

import { el } from "../components/primitives/dom";
import type { CaptureModeDef, CaptureSource } from "./modes";

export type CaptureStep = 1 | 2 | 3;

interface StepCopy {
  readonly railTitle: string;
  readonly railSub: string;
  readonly headSub: string;
  readonly nextLabel: string | null;
  readonly backLabel: string | null;
}

// Копия шагов дословно из эталонного варианта V3 (frontend/prototypes,
// удалён после промоушена — копия живёт здесь как источник). Заголовок
// панели выводится из railTitle: «Шаг N · <название>».
const STEP_COPY: readonly [StepCopy, StepCopy, StepCopy] = [
  {
    railTitle: "Режим измерения",
    railSub: "что пишем",
    headSub: "Режим фиксирует каналы и вход: невозможные комбинации недоступны.",
    nextLabel: "Далее: параметры",
    backLabel: null,
  },
  {
    railTitle: "Параметры записи",
    railSub: "как пишем",
    headSub: "Критичные настройки видны всегда; серия и протокол — за раскрытием.",
    nextLabel: "Далее: запуск",
    backLabel: "Назад: режим",
  },
  {
    railTitle: "Запуск и прогресс",
    railSub: "задача и журнал",
    headSub: "Проверьте профиль: это то, что уйдёт в POST /api/jobs.",
    nextLabel: null,
    backLabel: "Назад: параметры",
  },
];

// Секции формы, которые раскладываются по панелям шагов. paramsTitle —
// h3 «Параметры записи» прежней одностраничной формы: заменяется заголовком
// шага 2 и удаляется из DOM. adapter — секция декларации адаптера (N7):
// обязательная видимая секция ВНУТРИ шага 2 между настройками и серией
// (OQ1 — рельс трёх шагов не тронут).
export interface CaptureStepSections {
  readonly modes: HTMLElement;
  readonly source: HTMLElement;
  readonly paramsTitle: HTMLElement;
  readonly settings: HTMLElement;
  readonly adapter: HTMLElement;
  readonly series: HTMLElement;
}

export interface CaptureStepsOptions {
  // Форма захвата (modeForm.root): родитель панелей шагов 1–2.
  readonly form: HTMLElement;
  readonly sections: CaptureStepSections;
  // Содержимое шага 3: алерт, стартовая строка, устройство, live-грам,
  // хронология — узлы владельца, порядок сохранён.
  readonly launch: readonly HTMLElement[];
  // Гейт «Далее» с шага 2: true — форма валидна. Ошибки показывает владелец.
  validateStep2(): boolean;
  // Смена шага (перерисовка эха и другие проекции владельца).
  onStep?(step: CaptureStep): void;
}

export interface CaptureStepsHandle {
  readonly rail: HTMLElement;
  readonly panel3: HTMLElement;
  current(): CaptureStep;
  // Прямой переход (восстановление задачи, префилл): без перехвата фокуса.
  show(step: CaptureStep): void;
  // Чипы-эхо шага 2: режим, источник, каналы, тип сессии.
  renderEcho(mode: CaptureModeDef, source: CaptureSource): void;
}

function chip(text: string, accent = false): HTMLElement {
  return el("span", {
    className: "capture-chip",
    text,
    attrs: accent ? { "data-tone": "accent" } : {},
  });
}

function stepButton(label: string, primary: boolean): HTMLButtonElement {
  return el("button", {
    className: primary ? "lnt-btn lnt-btn-primary btn" : "lnt-btn btn-quiet",
    text: label,
    attrs: { type: "button" },
  }) as HTMLButtonElement;
}

// Обращение за пределами трёх шагов — явная ошибка, не undefined-ветка.
function copyOf(index: number): StepCopy {
  const copy = STEP_COPY[index];
  if (copy === undefined) throw new Error(`нет копии шага ${index + 1}`);
  return copy;
}

export function createCaptureSteps(options: CaptureStepsOptions): CaptureStepsHandle {
  const { form, sections } = options;
  const echo = el("div", { className: "capture-echo" });
  const headings: HTMLElement[] = [];
  const panels: HTMLElement[] = [];
  const railItems: HTMLButtonElement[] = [];
  let current: CaptureStep = 1;

  function paint(): void {
    panels.forEach((panelRoot, index) => {
      panelRoot.hidden = index + 1 !== current;
    });
    railItems.forEach((item, index) => {
      const step = index + 1;
      const state = step === current ? "current" : step < current ? "done" : "todo";
      item.dataset.state = state;
      item.setAttribute("aria-current", state === "current" ? "step" : "false");
      const num = item.querySelector<HTMLElement>(".capture-stepnum");
      if (num !== null) num.textContent = state === "done" ? "✓" : String(step);
    });
  }

  function goto(step: CaptureStep, focus: boolean): void {
    current = step;
    paint();
    if (focus) headings[step - 1]?.focus();
    options.onStep?.(step);
  }

  function actions(index: number): HTMLElement {
    const copy = copyOf(index);
    const row = el("div", { className: "capture-step-actions" });
    if (copy.backLabel !== null) {
      const back = stepButton(copy.backLabel, false);
      back.addEventListener("click", () => goto((current - 1) as CaptureStep, true));
      row.append(back);
    }
    if (copy.nextLabel !== null) {
      const next = stepButton(copy.nextLabel, true);
      next.addEventListener("click", () => {
        if (current === 2 && !options.validateStep2()) return;
        goto((current + 1) as CaptureStep, true);
      });
      row.append(next);
    }
    row.append(
      el("span", { className: "capture-step-spacer" }),
      el("span", { className: "lnt-hint", text: `Шаг ${index + 1} из 3` }),
    );
    return row;
  }

  function panel(index: number, body: readonly HTMLElement[]): HTMLElement {
    const copy = copyOf(index);
    const title = el("h3", {
      className: "capture-step-title",
      text: `Шаг ${index + 1} · ${copy.railTitle}`,
      attrs: { tabindex: "-1" },
    });
    headings.push(title);
    const root = el(
      "div",
      { className: "capture-step", attrs: { "data-capture-step": String(index + 1) } },
      [
        el("div", { className: "capture-step-hd" }, [
          title,
          el("p", { className: "capture-step-sub", text: copy.headSub }),
        ]),
        ...body,
        actions(index),
      ],
    );
    panels.push(root);
    return root;
  }

  STEP_COPY.forEach((copy, index) => {
    const item = el(
      "button",
      { className: "capture-stepitem", attrs: { type: "button", "data-step": String(index + 1) } },
      [
        el("span", { className: "capture-stepnum", text: String(index + 1) }),
        el("span", { className: "capture-stepitem-label" }, [
          el("span", { text: copy.railTitle }),
          el("span", { className: "capture-stepitem-sub", text: copy.railSub }),
        ]),
      ],
    ) as HTMLButtonElement;
    item.addEventListener("click", () => goto((index + 1) as CaptureStep, true));
    railItems.push(item);
  });

  const rail = el(
    "nav",
    { className: "capture-steps", attrs: { "aria-label": "Шаги визарда" } },
    railItems,
  );

  // Секции формы раскладываются по панелям; прежний h3 заменяет заголовок шага.
  const panel1 = panel(0, [sections.modes, sections.source]);
  const panel2 = panel(1, [echo, sections.settings, sections.adapter, sections.series]);
  const panel3 = panel(2, options.launch);
  sections.paramsTitle.remove();
  form.append(panel1, panel2);
  paint();

  return {
    rail,
    panel3,
    current: () => current,
    show: (step) => goto(step, false),
    renderEcho: (mode, source) => {
      echo.replaceChildren(
        chip(mode.titleRu, true),
        chip(source === "simulator" ? "симулятор" : "осциллограф"),
        chip(`каналы: ${mode.channels}`),
        chip(mode.sessionTypeRu),
      );
    },
  };
}
