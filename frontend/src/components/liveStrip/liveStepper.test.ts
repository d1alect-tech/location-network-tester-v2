/** Задача 14 RED: степпер liveStepper — обёртка СУЩЕСТВУЮЩЕГО числового поля
 * (#lnt-scope-level): кнопки −/+ пишут поле и диспечатят нативное change
 * (живой слушатель scopeTrigger срабатывает), клавиатура ←/→/↑/↓ ±0,1,
 * PgUp/PgDn ±1, Home/End — границы, зажим ±5. Поле сохраняет свой id. */

import { afterEach, describe, expect, it } from "vitest";
import { el } from "../primitives/dom";
import { wrapLiveStepper } from "./liveStepper";

function button(root: ParentNode, selector: string): HTMLButtonElement {
  const node = root.querySelector(selector);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`нет кнопки ${selector}`);
  return node;
}

function mountField(value: string): {
  field: HTMLInputElement;
  stepper: ReturnType<typeof wrapLiveStepper>;
  changes: number[];
} {
  const field = el("input", {
    attrs: { type: "number", id: "lnt-scope-level", min: "-5", max: "5", step: "0.1" },
  });
  field.value = value;
  const stepper = wrapLiveStepper(field, {
    aria: "Уровень триггера",
    step: 0.1,
    min: -5,
    max: 5,
    minusLabel: "Уменьшить уровень на 0,1 В",
    plusLabel: "Увеличить уровень на 0,1 В",
  });
  document.body.append(stepper.root);
  const changes: number[] = [];
  field.addEventListener("change", () => changes.push(Number(field.value)));
  return { field, stepper, changes };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("wrapLiveStepper", () => {
  it("обёртка содержит кнопки −/+ и живое поле с прежним id", () => {
    const { field, stepper } = mountField("1.25");
    expect(stepper.root.querySelector('[data-step-dir="minus"]')).toBeInstanceOf(HTMLButtonElement);
    expect(stepper.root.querySelector('[data-step-dir="plus"]')).toBeInstanceOf(HTMLButtonElement);
    expect(stepper.root.querySelector("#lnt-scope-level")).toBe(field);
  });

  it("кнопки −/+ пишут поле и диспечатят change (живой слушатель срабатывает)", () => {
    const { field, stepper, changes } = mountField("1.25");
    button(stepper.root, '[data-step-dir="minus"]').click();
    expect(field.value).toBe("1.15");
    expect(changes).toEqual([1.15]);
    button(stepper.root, '[data-step-dir="plus"]').click();
    expect(field.value).toBe("1.25");
    expect(changes).toEqual([1.15, 1.25]);
  });

  it("зажим ±5: кнопка за пределом пишет границу, не выходя за шкалу", () => {
    const { field, stepper, changes } = mountField("4.95");
    button(stepper.root, '[data-step-dir="plus"]').click();
    expect(field.value).toBe("5");
    expect(changes).toEqual([5]);
  });

  it("клавиатура поля: PgUp/PgDn ±1, Home/End — границы, стрелки ±0,1", () => {
    const { field, changes } = mountField("0");
    const key = (k: string): void => {
      field.dispatchEvent(
        new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }),
      );
    };
    key("ArrowUp");
    expect(field.value).toBe("0.1");
    key("PageDown");
    expect(field.value).toBe("-0.9");
    key("End");
    expect(field.value).toBe("5");
    key("Home");
    expect(field.value).toBe("-5");
    expect(changes).toEqual([0.1, -0.9, 5, -5]);
  });

  it("нечисловое поле — кнопки не пишут мусор (валидация остаётся полю)", () => {
    const { field, stepper, changes } = mountField("1.25");
    field.value = "";
    button(stepper.root, '[data-step-dir="plus"]').click();
    expect(changes).toEqual([]);
  });
});
